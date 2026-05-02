"""
시뮬레이션 - 활동 피드 인터페이스

시뮬레이션 실행 결과 조회: Agent 액션, 라운드 타임라인, Agent 통계,
플랫폼별 게시물·댓글 (SQLite 데이터베이스에서 직접 읽기).
"""

import os
import sqlite3
import traceback

from flask import jsonify, request

from .. import simulation_bp
from ...services.simulation_runner import SimulationRunner
from ...utils.logger import get_logger
from ._shared import BACKEND_DIR, _validate_pagination

logger = get_logger('mirofish.api.simulation')


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    시뮬레이션의 Agent 액션 히스토리 가져오기

    Query 파라미터:
        limit: 반환 수 (기본값 100)
        offset: 오프셋 (기본값 0)
        platform: 플랫폼 필터링 (twitter/reddit)
        agent_id: Agent ID 필터링
        round_num: 라운드 필터링

    반환:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit, offset = _validate_pagination(request.args, max_limit=100, default_limit=100)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)

        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })

    except Exception as e:
        logger.error(f"액션 히스토리 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    시뮬레이션 타임라인 가져오기 (라운드별 요약)

    프론트엔드 진행 바 및 타임라인 뷰 표시에 사용

    Query 파라미터:
        start_round: 시작 라운드 (기본값 0)
        end_round: 종료 라운드 (기본값 전체)

    각 라운드의 요약 정보 반환
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)

        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )

        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })

    except Exception as e:
        logger.error(f"타임라인 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    각 Agent의 통계 정보 가져오기

    프론트엔드 Agent 활성도 순위, 액션 분포 등 표시에 사용
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)

        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })

    except Exception as e:
        logger.error(f"Agent 통계 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== 데이터베이스 조회 인터페이스 ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    시뮬레이션의 게시물 가져오기

    Query 파라미터:
        platform: 플랫폼 유형 (twitter/reddit)
        limit: 반환 수 (기본값 50)
        offset: 오프셋

    게시물 목록 반환 (SQLite 데이터베이스에서 읽기)
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit, offset = _validate_pagination(request.args, max_limit=100, default_limit=50)

        sim_dir = os.path.join(BACKEND_DIR, 'uploads', 'simulations', simulation_id)

        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)

        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "데이터베이스가 존재하지 않습니다. 시뮬레이션이 아직 실행되지 않았을 수 있습니다"
                }
            })

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT * FROM post
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

                posts = [dict(row) for row in cursor.fetchall()]

                cursor.execute("SELECT COUNT(*) FROM post")
                total = cursor.fetchone()[0]

            except sqlite3.OperationalError:
                posts = []
                total = 0
        finally:
            conn.close()

        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })

    except Exception as e:
        logger.error(f"게시물 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    시뮬레이션의 댓글 가져오기 (Reddit 전용)

    Query 파라미터:
        post_id: 게시물 ID 필터링 (선택적)
        limit: 반환 수
        offset: 오프셋
    """
    try:
        post_id = request.args.get('post_id')
        limit, offset = _validate_pagination(request.args, max_limit=100, default_limit=50)

        sim_dir = os.path.join(BACKEND_DIR, 'uploads', 'simulations', simulation_id)

        db_path = os.path.join(sim_dir, "reddit_simulation.db")

        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            try:
                if post_id:
                    cursor.execute("""
                        SELECT * FROM comment
                        WHERE post_id = ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                    """, (post_id, limit, offset))
                else:
                    cursor.execute("""
                        SELECT * FROM comment
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                    """, (limit, offset))

                comments = [dict(row) for row in cursor.fetchall()]

            except sqlite3.OperationalError:
                comments = []
        finally:
            conn.close()

        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })

    except Exception as e:
        logger.error(f"댓글 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
