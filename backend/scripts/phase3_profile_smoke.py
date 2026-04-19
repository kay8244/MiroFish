"""
Phase 3 DoD 수정안: reader → oasis_profile_generator 직접 경로 검증.

full pipeline 대신 Phase 2 stash(`mirofish_6c463911f0074dc9`)의 노드로
프로파일 생성만 수행. graph build 단계 건너뛰어 TPM 부하 최소화.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Zep 경로 강제 비활성 (Phase 2 stash 검증은 Graphiti만)
os.environ.pop("ZEP_API_KEY", None)

from app.services.zep_entity_reader import ZepEntityReader  # shim
from app.services.oasis_profile_generator import OasisProfileGenerator


GROUP_ID = "mirofish_6c463911f0074dc9"
N = int(os.environ.get("PROFILE_N", "3"))


def main():
    print(f"=== Phase 3 profile smoke (N={N}) ===")
    reader = ZepEntityReader()
    try:
        filtered = reader.filter_defined_entities(GROUP_ID, enrich_with_edges=True)
    finally:
        reader.close()

    # 연결 엣지가 있는 엔티티 우선 (profile 생성에 컨텍스트 풍부)
    connected = [e for e in filtered.entities if e.related_edges]
    top = connected[:N] if len(connected) >= N else filtered.entities[:N]

    print(f"candidates: {len(top)} (types: {[e.get_entity_type() for e in top]})")

    gen = OasisProfileGenerator(graph_id=GROUP_ID)
    print(f"zep_client enabled: {gen.zep_client is not None}  (must be False for pure Graphiti path)")

    t0 = time.time()
    profiles = gen.generate_profiles_from_entities(
        entities=top,
        use_llm=True,
        parallel_count=2,
        output_platform="reddit",
    )
    elapsed = time.time() - t0

    print(f"\n=== RESULT ===")
    print(f"profiles generated: {len(profiles)}/{len(top)}  in {elapsed:.1f}s")
    ok = 0
    for p in profiles:
        if p is None:
            continue
        ok += 1
        d = p.to_dict()
        print(f"  - user_id={d.get('user_id')} name={d.get('name')!r} "
              f"realname={d.get('realname')!r} bio_len={len(d.get('bio') or '')}")
    print(f"\nOK count: {ok}")
    if ok == 0:
        print("FAIL: no profile generated")
        sys.exit(1)
    if ok < len(top) // 2:
        print("WARN: < 50% success")
        sys.exit(2)
    print("PASS")


if __name__ == "__main__":
    main()
