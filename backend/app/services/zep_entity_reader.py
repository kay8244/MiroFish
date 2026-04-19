"""
[SHIM] Phase 3 이후: zep_entity_reader는 graphiti_entity_reader로 위임.

기존 Zep Cloud 구현은 Graphiti/Neo4j 경로로 전면 교체됐다. 이 파일은 Phase 6
cleanup 때 call-site import를 일괄 rename한 뒤 삭제된다.

호출부는 `from ..services.zep_entity_reader import ZepEntityReader` 같이
여전히 Zep 네이밍을 쓰지만, 실제 반환 객체는 GraphitiEntityReader.
"""
from .graphiti_entity_reader import (
    EntityNode,
    FilteredEntities,
    GraphitiEntityReader as ZepEntityReader,
)

__all__ = ["ZepEntityReader", "EntityNode", "FilteredEntities"]
