"""
Zep 그래프 메모리 업데이트 서비스 — Graphiti shim (Phase 5).

Phase 5부터 실제 구현은 `services/graphiti_graph_memory_updater`에 위임.
이 모듈은 호출부(simulation_runner.py, services/__init__.py)의 import 경로
호환을 위한 얇은 재노출 레이어.

Phase 6 cleanup에서:
- 호출부 import 경로를 `from .graphiti_graph_memory_updater import ...`로 변경
- 이 shim 파일 삭제
"""

from .graphiti_graph_memory_updater import (  # noqa: F401
    AgentActivity,
    GraphitiGraphMemoryManager,
    GraphitiGraphMemoryUpdater,
)

# 하위 호환 alias
ZepGraphMemoryUpdater = GraphitiGraphMemoryUpdater
ZepGraphMemoryManager = GraphitiGraphMemoryManager

__all__ = [
    "AgentActivity",
    "GraphitiGraphMemoryManager",
    "GraphitiGraphMemoryUpdater",
    "ZepGraphMemoryManager",
    "ZepGraphMemoryUpdater",
]
