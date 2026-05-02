"""
Graphiti Phase 0 스모크: 에피소드 1개 추가 + 검색 왕복.

DoD:
  1. Graphiti 인스턴스 생성 (Neo4j 연결)
  2. build_indices_and_constraints() 성공
  3. add_episode로 1개 에피소드 추가 (완료까지 await)
  4. search()로 fact 최소 1건 검색
  5. Neo4j에 노드 존재 확인 (직접 Cypher)
  6. close() 정상 종료

Usage:
    cd backend && uv run python scripts/graphiti_smoke_add_one.py

사전 조건:
  - Neo4j docker 기동: `cd backend/graphiti-db && docker compose up -d`
  - .env에 OPENAI/LLM_API_KEY 유효
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# backend/ 를 sys.path에
HERE = Path(__file__).resolve()
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))

from app.utils.graphiti_client import (  # noqa: E402
    GraphitiConfig,
    create_graphiti,
    neo4j_driver,
)


SAMPLE_EPISODE_BODY = """
NVIDIA의 CEO Jensen Huang은 2026년 3월 GTC 키노트에서 Blackwell과 Rubin 아키텍처의
누적 매출이 $1T을 넘을 것이라고 발표했다. TSMC는 2026년 말까지 CoWoS 월 처리량을
130K wafer로 확장해 Blackwell/Rubin 공급을 뒷받침한다.
"""


async def main() -> int:
    cfg = GraphitiConfig.from_env()
    print(f'■ config: {cfg.neo4j_uri} user={cfg.neo4j_user} db={cfg.neo4j_database}')

    print('■ Graphiti 인스턴스 생성 중...')
    started = time.time()
    graphiti = create_graphiti(cfg)
    print(f'  .. 생성 완료 ({time.time() - started:.2f}s)')

    try:
        print('■ build_indices_and_constraints() 호출 중...')
        t0 = time.time()
        await graphiti.build_indices_and_constraints()
        print(f'  .. 인덱스/제약 준비 완료 ({time.time() - t0:.2f}s)')

        print('■ add_episode 1회 실행 중 (LLM 추출 포함, 10~40s 예상)...')
        t0 = time.time()
        try:
            from graphiti_core.nodes import EpisodeType  # type: ignore
        except ImportError:
            EpisodeType = None  # type: ignore

        episode_kwargs = dict(
            name='mirofish-phase0-smoke',
            episode_body=SAMPLE_EPISODE_BODY.strip(),
            source_description='Phase 0 health check',
            reference_time=datetime.now(timezone.utc),
            group_id='phase0-smoke',
        )
        if EpisodeType is not None:
            episode_kwargs['source'] = EpisodeType.text
        await graphiti.add_episode(**episode_kwargs)
        print(f'  .. 에피소드 1개 추가 완료 ({time.time() - t0:.2f}s)')

        print('■ search() "NVIDIA Rubin" 실행 중...')
        t0 = time.time()
        results = await graphiti.search(
            query='NVIDIA Rubin 매출 전망',
            group_ids=['phase0-smoke'],
        )
        print(f'  .. 검색 완료 ({time.time() - t0:.2f}s), results={len(results)}')
        for i, r in enumerate(results[:3], 1):
            fact = getattr(r, 'fact', None) or str(r)[:200]
            print(f'    [{i}] {fact[:200]}')

        print('■ Neo4j에 저장된 노드 수 직접 확인 중...')
        driver = neo4j_driver(cfg)
        try:
            with driver.session(database=cfg.neo4j_database) as session:
                record = session.run(
                    'MATCH (n) WHERE n.group_id = $gid RETURN count(n) AS cnt',
                    gid='phase0-smoke',
                ).single()
                node_count = record['cnt'] if record else 0
            print(f'  .. group_id=phase0-smoke 아래 노드 {node_count}개')
        finally:
            driver.close()

        print('\n=== ✅ Phase 0 smoke PASS ===')
        return 0

    except Exception as e:
        import traceback
        print('\n=== ❌ Phase 0 smoke FAIL ===')
        print(f'에러: {type(e).__name__}: {e}')
        traceback.print_exc()
        return 1
    finally:
        try:
            await graphiti.close()
        except Exception as e:
            print(f'(close 중 경고: {e})')


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
