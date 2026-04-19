"""
Zep 검색 도구 서비스 — Graphiti shim (Phase 4).

Phase 4부터 실제 구현은 `services/graphiti_tools.GraphitiToolsService`에 위임.
이 모듈은 호출부(report_agent.py, api/report.py)의 import 경로
`from .zep_tools import ZepToolsService` 호환을 위한 얇은 재노출 레이어.

Phase 6 cleanup에서:
- 호출부 import 경로를 `from .graphiti_tools import GraphitiToolsService`로 변경
- 이 shim 파일 삭제
"""

from .graphiti_tools import (  # noqa: F401
    AgentInterview,
    EdgeInfo,
    GraphitiToolsService,
    InsightForgeResult,
    InterviewResult,
    NodeInfo,
    PanoramaResult,
    SearchResult,
)

# 하위 호환 alias
ZepToolsService = GraphitiToolsService

__all__ = [
    "AgentInterview",
    "EdgeInfo",
    "GraphitiToolsService",
    "InsightForgeResult",
    "InterviewResult",
    "NodeInfo",
    "PanoramaResult",
    "SearchResult",
    "ZepToolsService",
]
