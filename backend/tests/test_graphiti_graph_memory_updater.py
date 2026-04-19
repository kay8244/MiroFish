"""
Phase 5 — graphiti_graph_memory_updater 테스트.

Tier A (오프라인): graphiti.add_episode를 mock으로 가짜 페이로드 캡처.
    AgentActivity → episode 변환, 배치 플러시, 통계, manager lifecycle 검증. 항상 실행.
Tier B (live Neo4j): MIROFISH_NEO4J=1일 때만. add_episode 라이브 호출.
"""

from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


NEO4J_ENABLED = os.environ.get("MIROFISH_NEO4J") == "1"


def _require_neo4j():
    if not NEO4J_ENABLED:
        pytest.skip(
            "Neo4j live 테스트는 기본 비활성화. `MIROFISH_NEO4J=1` + docker neo4j "
            "기동 후 실행.",
            allow_module_level=False,
        )


# ═══════════════════════════════════════════════════════════════════════
# Tier A — 오프라인
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def fake_graphiti():
    """add_episode 호출을 캡처하는 가짜 graphiti."""
    captured: List[dict] = []

    async def fake_add_episode(**kwargs):
        captured.append(kwargs)
        return None

    async def fake_close():
        return None

    g = SimpleNamespace(
        add_episode=fake_add_episode,
        close=fake_close,
        _captured=captured,
    )
    return g


def _make_activity(action_type: str = "CREATE_POST", agent_name: str = "Alice",
                    platform: str = "twitter", action_args=None):
    from app.services.graphiti_graph_memory_updater import AgentActivity
    return AgentActivity(
        platform=platform,
        agent_id=1,
        agent_name=agent_name,
        action_type=action_type,
        action_args=action_args or {"content": "hello world"},
        round_num=1,
        timestamp="2026-04-19T18:00:00",
    )


def test_agent_activity_to_episode_text_create_post():
    a = _make_activity("CREATE_POST", "Alice", action_args={"content": "GPT 신규 출시"})
    text = a.to_episode_text()
    assert "Alice" in text
    assert "GPT 신규 출시" in text


def test_agent_activity_to_episode_text_like_post():
    a = _make_activity("LIKE_POST", "Bob", action_args={
        "post_content": "테슬라 주가 상승",
        "post_author_name": "Charlie",
    })
    text = a.to_episode_text()
    assert "Bob" in text
    assert "Charlie" in text
    assert "테슬라 주가 상승" in text


def test_init_lazy_graphiti_no_api_key_required(fake_graphiti):
    """ZEP_API_KEY 없이도 초기화 OK (lazy graphiti, no zep dependency)."""
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    assert upd.graph_id == "g1"
    assert upd._graphiti is fake_graphiti
    assert upd._owns_graphiti is False  # 외부 주입


def test_add_activity_skips_do_nothing(fake_graphiti):
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    upd.add_activity(_make_activity("DO_NOTHING"))
    stats = upd.get_stats()
    assert stats["skipped_count"] == 1
    assert stats["total_activities"] == 0
    assert stats["queue_size"] == 0


def test_add_activity_increments_queue(fake_graphiti):
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    upd.add_activity(_make_activity("CREATE_POST"))
    upd.add_activity(_make_activity("LIKE_POST"))
    stats = upd.get_stats()
    assert stats["total_activities"] == 2
    assert stats["queue_size"] == 2


def test_send_batch_calls_add_episode(fake_graphiti):
    """직접 _send_batch_activities 호출 → graphiti.add_episode 캡처."""
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    activities = [
        _make_activity("CREATE_POST", "Alice", action_args={"content": "Post A"}),
        _make_activity("LIKE_POST", "Bob", action_args={
            "post_content": "Post A", "post_author_name": "Alice",
        }),
    ]
    upd._send_batch_activities(activities, "twitter")

    assert len(fake_graphiti._captured) == 1
    call = fake_graphiti._captured[0]
    assert call["group_id"] == "g1"
    assert "agent activity batch (twitter)" in call["source_description"]
    assert call["name"].startswith("agent-activity-twitter-")
    body = call["episode_body"]
    assert "Alice" in body
    assert "Bob" in body
    assert "Post A" in body

    stats = upd.get_stats()
    assert stats["batches_sent"] == 1
    assert stats["items_sent"] == 2
    assert stats["failed_count"] == 0


def test_send_batch_retries_on_failure(monkeypatch):
    """add_episode가 raise → MAX_RETRIES만큼 시도 후 failed_count 증가."""
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater

    call_count = {"n": 0}

    async def boom(**kwargs):
        call_count["n"] += 1
        raise RuntimeError("network down")

    fake_g = SimpleNamespace(add_episode=boom, close=lambda: _coro_none())

    async def _coro_none():
        return None

    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_g)
    upd.MAX_RETRIES = 2
    upd.RETRY_DELAY = 0  # 빠른 테스트

    upd._send_batch_activities([_make_activity()], "twitter")

    assert call_count["n"] == 2
    assert upd.get_stats()["failed_count"] == 1


def test_worker_loop_flushes_at_batch_size(fake_graphiti):
    """BATCH_SIZE개 활동 추가 → 워커가 자동 플러시 → add_episode 1회."""
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    upd.SEND_INTERVAL = 0  # 빠른 테스트
    upd.start()
    try:
        for i in range(upd.BATCH_SIZE):
            upd.add_activity(_make_activity("CREATE_POST", f"Agent{i}",
                                             action_args={"content": f"Post {i}"}))
        # 워커가 큐를 비우고 배치를 보낼 때까지 대기 (최대 5초)
        deadline = time.time() + 5
        while time.time() < deadline:
            if upd.get_stats()["batches_sent"] >= 1:
                break
            time.sleep(0.05)
    finally:
        upd.stop()

    assert len(fake_graphiti._captured) >= 1
    call = fake_graphiti._captured[0]
    assert call["group_id"] == "g1"
    body = call["episode_body"]
    # BATCH_SIZE개의 게시물 모두 episode_body에 포함
    for i in range(upd.BATCH_SIZE):
        assert f"Agent{i}" in body


def test_flush_remaining_on_stop(fake_graphiti):
    """BATCH_SIZE 미만 활동도 stop() 시 플러시."""
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    upd = GraphitiGraphMemoryUpdater(graph_id="g1", graphiti=fake_graphiti)
    upd.start()
    try:
        # BATCH_SIZE 미만
        for i in range(2):
            upd.add_activity(_make_activity("CREATE_POST", f"Agent{i}"))
        time.sleep(0.2)  # 워커가 큐에서 buffer로 이동할 시간
    finally:
        upd.stop()  # _flush_remaining 호출됨

    assert len(fake_graphiti._captured) >= 1
    assert upd.get_stats()["items_sent"] >= 2


def test_manager_create_get_stop():
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryManager

    g_inst = SimpleNamespace(
        add_episode=_async_noop,
        close=_async_noop,
    )

    # Manager는 GraphitiGraphMemoryUpdater(graph_id)로 생성하므로 graphiti=None →
    # _ensure_graphiti가 create_graphiti() 호출 시도. 실제 호출 방지를 위해 직접
    # 인스턴스 생성 후 등록 패턴은 안 됨. 대신 manager 내부에서 lazy init이라
    # add 호출이 없으면 graphiti 미생성 상태 유지 → get_stats만 검증.
    upd = GraphitiGraphMemoryManager.create_updater("sim-1", "g1")
    try:
        assert GraphitiGraphMemoryManager.get_updater("sim-1") is upd
        stats = upd.get_stats()
        assert stats["graph_id"] == "g1"
        assert stats["running"] is True
    finally:
        GraphitiGraphMemoryManager.stop_updater("sim-1")
        # stop 후 제거 확인
        assert GraphitiGraphMemoryManager.get_updater("sim-1") is None


async def _async_noop(*args, **kwargs):
    return None


def test_zep_shim_aliases_to_graphiti():
    from app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater, ZepGraphMemoryManager
    from app.services.graphiti_graph_memory_updater import (
        GraphitiGraphMemoryUpdater, GraphitiGraphMemoryManager,
    )
    assert ZepGraphMemoryUpdater is GraphitiGraphMemoryUpdater
    assert ZepGraphMemoryManager is GraphitiGraphMemoryManager


# ═══════════════════════════════════════════════════════════════════════
# Tier B — live Neo4j (MIROFISH_NEO4J=1 게이트)
# ═══════════════════════════════════════════════════════════════════════


def test_live_send_one_episode_to_dedicated_group():
    """라이브 graphiti.add_episode 1회 호출. 새 group_id로 격리."""
    _require_neo4j()
    from app.services.graphiti_graph_memory_updater import GraphitiGraphMemoryUpdater
    from app.utils.graphiti_client import neo4j_driver

    test_gid = f"phase5_smoke_{int(time.time())}"
    upd = GraphitiGraphMemoryUpdater(graph_id=test_gid)
    try:
        activities = [
            _make_activity("CREATE_POST", "TestAlice",
                           action_args={"content": "Phase 5 smoke test post"}),
        ]
        upd._send_batch_activities(activities, "twitter")
        stats = upd.get_stats()
        assert stats["batches_sent"] == 1
        assert stats["items_sent"] == 1
        assert stats["failed_count"] == 0

        # 검증: Neo4j에 episode 노드 존재
        drv = neo4j_driver()
        try:
            with drv.session(database="neo4j") as s:
                rec = s.run(
                    "MATCH (n) WHERE n.group_id = $gid RETURN count(n) AS cnt",
                    gid=test_gid,
                ).single()
                assert rec["cnt"] > 0, f"group_id={test_gid}에 노드 없음"
        finally:
            drv.close()
    finally:
        upd.close()
