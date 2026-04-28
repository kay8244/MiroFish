"""
시뮬레이션 - Agent 인터뷰 인터페이스

시뮬레이션 환경이 명령 대기 모드에 진입한 후 Agent에게 질문하고 응답을
수신. 단일/일괄/전체 모드 + 히스토리 조회 4종 지원.
"""

import traceback

from flask import jsonify, request

from .. import simulation_bp
from ...services.simulation_runner import SimulationRunner
from ...utils.logger import get_logger
from ._shared import optimize_interview_prompt

logger = get_logger('mirofish.api.simulation')


@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    단일 Agent 인터뷰

    참고: 이 기능은 시뮬레이션 환경이 실행 중 상태여야 합니다 (시뮬레이션 루프 완료 후 명령 대기 모드 진입)

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",       // 필수, 시뮬레이션 ID
            "agent_id": 0,                     // 필수, Agent ID
            "prompt": "이 일에 대해 어떻게 생각하세요?",  // 필수, 인터뷰 질문
            "platform": "twitter",             // 선택적, 플랫폼 지정 (twitter/reddit)
                                               // 미지정 시: 양대 플랫폼 시뮬레이션에서 두 플랫폼 동시 인터뷰
            "timeout": 60                      // 선택적, 타임아웃 시간 (초), 기본값 60
        }

    반환 (platform 미지정, 양대 플랫폼 모드):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "이 일에 대해 어떻게 생각하세요?",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    반환 (platform 지정):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "이 일에 대해 어떻게 생각하세요?",
                "result": {
                    "agent_id": 0,
                    "response": "저는 ...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # 선택적: twitter/reddit/None
        timeout = data.get('timeout', 60)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "agent_id 를 제공해주세요"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "prompt (인터뷰 질문) 를 제공해주세요"
            }), 400

        # platform 파라미터 검증
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform 파라미터는 'twitter' 또는 'reddit' 만 가능합니다"
            }), 400

        # 환경 상태 확인
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "시뮬레이션 환경이 실행 중이 아니거나 종료되었습니다. 시뮬레이션이 완료되고 명령 대기 모드에 진입했는지 확인하세요."
            }), 400

        # prompt 최적화, Agent 도구 호출 방지를 위한 접두어 추가
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Interview 응답 대기 시간 초과: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"Interview 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    여러 Agent 일괄 인터뷰

    참고: 이 기능은 시뮬레이션 환경이 실행 중 상태여야 합니다

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",       // 필수, 시뮬레이션 ID
            "interviews": [                    // 필수, 인터뷰 목록
                {
                    "agent_id": 0,
                    "prompt": "A에 대해 어떻게 생각하세요?",
                    "platform": "twitter"      // 선택적, 해당 Agent의 인터뷰 플랫폼 지정
                },
                {
                    "agent_id": 1,
                    "prompt": "B에 대해 어떻게 생각하세요?"  // platform 미지정 시 기본값 사용
                }
            ],
            "platform": "reddit",              // 선택적, 기본 플랫폼 (각 항목의 platform으로 덮어쓰기 가능)
                                               // 미지정 시: 양대 플랫폼 시뮬레이션에서 각 Agent를 두 플랫폼에서 동시 인터뷰
            "timeout": 120                     // 선택적, 타임아웃 시간 (초), 기본값 120
        }

    반환:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # 선택적: twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "interviews (인터뷰 목록) 를 제공해주세요"
            }), 400

        # platform 파라미터 검증
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform 파라미터는 'twitter' 또는 'reddit' 만 가능합니다"
            }), 400

        # 각 인터뷰 항목 검증
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"인터뷰 목록 {i+1}번째 항목에 agent_id 가 없습니다"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"인터뷰 목록 {i+1}번째 항목에 prompt 가 없습니다"
                }), 400
            # 각 항목의 platform 검증 (있는 경우)
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"인터뷰 목록 {i+1}번째 항목의 platform 은 'twitter' 또는 'reddit' 만 가능합니다"
                }), 400

        # 환경 상태 확인
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "시뮬레이션 환경이 실행 중이 아니거나 종료되었습니다. 시뮬레이션이 완료되고 명령 대기 모드에 진입했는지 확인하세요."
            }), 400

        # 각 인터뷰 항목의 prompt 최적화, Agent 도구 호출 방지를 위한 접두어 추가
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"일괄 Interview 응답 대기 시간 초과: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"일괄 Interview 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    전체 인터뷰 - 동일한 질문으로 모든 Agent 인터뷰

    참고: 이 기능은 시뮬레이션 환경이 실행 중 상태여야 합니다

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",            // 필수, 시뮬레이션 ID
            "prompt": "이 일에 대해 전반적으로 어떻게 생각하세요?",  // 필수, 인터뷰 질문 (모든 Agent에 동일한 질문 사용)
            "platform": "reddit",                   // 선택적, 플랫폼 지정 (twitter/reddit)
                                                    // 미지정 시: 양대 플랫폼 시뮬레이션에서 각 Agent를 두 플랫폼에서 동시 인터뷰
            "timeout": 180                          // 선택적, 타임아웃 시간 (초), 기본값 180
        }

    반환:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # 선택적: twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "prompt (인터뷰 질문) 를 제공해주세요"
            }), 400

        # platform 파라미터 검증
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform 파라미터는 'twitter' 또는 'reddit' 만 가능합니다"
            }), 400

        # 환경 상태 확인
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "시뮬레이션 환경이 실행 중이 아니거나 종료되었습니다. 시뮬레이션이 완료되고 명령 대기 모드에 진입했는지 확인하세요."
            }), 400

        # prompt 최적화, Agent 도구 호출 방지를 위한 접두어 추가
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"전체 Interview 응답 대기 시간 초과: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"전체 Interview 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    Interview 히스토리 조회

    시뮬레이션 데이터베이스에서 모든 Interview 기록 읽기

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",  // 필수, 시뮬레이션 ID
            "platform": "reddit",          // 선택적, 플랫폼 유형 (reddit/twitter)
                                           // 미지정 시 두 플랫폼의 모든 히스토리 반환
            "agent_id": 0,                 // 선택적, 해당 Agent의 인터뷰 히스토리만 조회
            "limit": 100                   // 선택적, 반환 수, 기본값 100
        }

    반환:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "저는 ...",
                        "prompt": "이 일에 대해 어떻게 생각하세요?",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # 미지정 시 두 플랫폼의 히스토리 반환
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"Interview 히스토리 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
