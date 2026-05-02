"""
PoC: 기존 Graphiti 그래프에 새 seed 1개를 incremental add 했을 때
     entity dedup 동작 + 비용 절감 가설을 검증.

대상 그래프:
  group_id = mirofish_586ca77a16ec49a7  (proj_haiku_6dd3b358f0, 1-file solo seed,
                                         01_hyperscaler_capex.md 로 빌드됨, ~62 nodes)

추가하는 파일:
  seed_documents/ai_server_si_wafer/02_nvidia_datacenter.md
  (CoWoS / NVIDIA / TSMC / HBM 도메인 — 01과 일부 entity 겹침)

검증 항목:
  1. add_episode 가 같은 group_id 에 정상 누적되는가
  2. 기존 entity (e.g. "Microsoft") 가 새 episode 에서 다시 추출됐을 때
     중복 노드 안 만들고 dedup 되는가
  3. 신규 entity 만 노드로 추가되는가 (delta 측정)
  4. 1 file 추가에 걸리는 시간 (cost proxy)

Usage:
  cd MiroFish/backend && uv run python scripts/append_to_existing_graph_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[1]
ROOT = BACKEND.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(BACKEND))

# .env 로드 (MiroFish/.env)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / '.env')
except ImportError:
    pass

from app.utils.graphiti_client import (  # noqa: E402
    GraphitiConfig,
    create_graphiti,
    neo4j_driver,
)
from app.services.text_processor import TextProcessor  # noqa: E402


GRAPH_ID = 'mirofish_586ca77a16ec49a7'
NEW_FILE = REPO_ROOT / 'seed_documents' / 'ai_server_si_wafer' / '02_nvidia_datacenter.md'
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def snapshot_graph(driver, database, group_id):
    """그래프 노드/엣지 카운트 + entity 이름 집합."""
    with driver.session(database=database) as s:
        nodes = s.run(
            'MATCH (n {group_id: $gid}) RETURN count(n) AS c', gid=group_id
        ).single()['c']
        edges = s.run(
            'MATCH ()-[r {group_id: $gid}]->() RETURN count(r) AS c', gid=group_id
        ).single()['c']
        names = {
            r['name']
            for r in s.run(
                'MATCH (n {group_id: $gid}) WHERE n.name IS NOT NULL '
                'RETURN n.name AS name',
                gid=group_id,
            )
        }
    return {'nodes': nodes, 'edges': edges, 'names': names}


async def main() -> int:
    if not NEW_FILE.exists():
        print(f'❌ 파일 없음: {NEW_FILE}')
        return 1

    text = NEW_FILE.read_text(encoding='utf-8')
    chunks = TextProcessor.split_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
    total = len(chunks)
    print(f'■ 추가 대상 파일: {NEW_FILE.name}')
    print(f'  size={len(text):,} chars, chunks={total} (chunk_size={CHUNK_SIZE} overlap={CHUNK_OVERLAP})')

    cfg = GraphitiConfig.from_env()
    print(f'■ Graphiti config: provider={cfg.llm_provider} model={cfg.llm_model}')
    print(f'  neo4j={cfg.neo4j_uri} db={cfg.neo4j_database}')

    # BEFORE 스냅샷
    driver = neo4j_driver(cfg)
    before = snapshot_graph(driver, cfg.neo4j_database, GRAPH_ID)
    print(f'\n■ BEFORE: nodes={before["nodes"]} edges={before["edges"]} '
          f'unique_named_entities={len(before["names"])}')

    # add_episode 루프
    graphiti = create_graphiti(cfg)
    chunk_times = []
    try:
        print('\n■ build_indices_and_constraints()...')
        await graphiti.build_indices_and_constraints()

        try:
            from graphiti_core.nodes import EpisodeType  # type: ignore
            source = EpisodeType.text
        except ImportError:
            source = None

        ref_time = datetime.now(timezone.utc)
        t0 = time.time()
        for i, chunk in enumerate(chunks, 1):
            ct0 = time.time()
            kwargs = dict(
                name=f'02_nvidia_datacenter chunk {i}/{total}',
                episode_body=chunk,
                source_description='PoC append smoke',
                reference_time=ref_time,
                group_id=GRAPH_ID,
            )
            if source is not None:
                kwargs['source'] = source
            await graphiti.add_episode(**kwargs)
            dt = time.time() - ct0
            chunk_times.append(dt)
            print(f'  chunk {i:>2}/{total}  {dt:5.1f}s')
        elapsed = time.time() - t0
    finally:
        try:
            await graphiti.close()
        except Exception as e:
            print(f'(close 경고: {e})')

    # AFTER 스냅샷
    after = snapshot_graph(driver, cfg.neo4j_database, GRAPH_ID)
    driver.close()

    new_names = after['names'] - before['names']
    kept_names = before['names'] & after['names']

    print(f'\n■ AFTER:  nodes={after["nodes"]} edges={after["edges"]} '
          f'unique_named_entities={len(after["names"])}')
    print('\n=== DELTA ===')
    print(f'  +nodes : {after["nodes"] - before["nodes"]}')
    print(f'  +edges : {after["edges"] - before["edges"]}')
    print(f'  새 entity 이름 : {len(new_names)}')
    print(f'  기존과 동일 이름 (잠재 dedup) : {len(kept_names)}')
    print(f'  before-only (사라진 이름) : {len(before["names"] - after["names"])}  '
          f'  ← 0이어야 정상 (기존 노드 유지)')
    print(f'\n  총 시간 : {elapsed:.1f}s ({elapsed / total:.1f}s/chunk 평균)')

    if new_names:
        sample = sorted(new_names)[:10]
        print(f'\n  sample 신규 entities (최대 10): {sample}')
    if kept_names:
        sample = sorted(kept_names)[:10]
        print(f'  sample 유지 entities (최대 10): {sample}')

    print('\n=== ✅ append smoke 완료 ===')
    print('  hypothesis check:')
    print('  - 기존 그래프 노드 보존?  ',
          '✓' if len(before["names"] - after["names"]) == 0 else '✗')
    print('  - 새 노드 추가됐나?       ',
          '✓' if (after["nodes"] - before["nodes"]) > 0 else '✗')
    print('  - dedup 작동 가능성 (겹침 entity 존재)? ',
          '✓' if len(kept_names) > 0 else '?')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
