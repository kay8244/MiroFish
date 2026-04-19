"""
Graphiti 클라이언트 팩토리.

MiroFish Graphiti(Neo4j) 백엔드의 인스턴스 + Neo4jDriver 생성 헬퍼.

환경 변수 (.env):
    NEO4J_URI             (기본 bolt://localhost:7687)
    NEO4J_USER            (기본 neo4j)
    NEO4J_PASSWORD        (기본 mirofish-dev — graphiti-db/docker-compose.yml과 일치)
    NEO4J_DATABASE        (기본 neo4j — Community Edition 단일 DB)
    GRAPHITI_MODEL        (기본 gpt-4o-mini — 엔티티/엣지 추출 메인 모델)
    GRAPHITI_SMALL_MODEL  (기본 gpt-4o-mini — attribute 추출 등 간단 프롬프트)
    GRAPHITI_LLM_BASE_URL (옵션 — LLM_BASE_URL과 분리하고 싶을 때)

LLM 모델 기본이 `gpt-4o-mini`인 이유: graphiti-core 기본(`gpt-4.1-mini` + small
`gpt-4.1-nano`)은 조직 TPM 한도(우리 환경 200k)에 27 chunk 파이프라인이 즉시 걸림.
`gpt-4o-mini`는 TPM 여유가 크고 품질 대비 비용 효율도 좋음.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GraphitiConfig:
    """Graphiti/Neo4j + LLM 모델 설정. Config 클래스 + .env 오버라이드."""

    neo4j_uri: str = 'bolt://localhost:7687'
    neo4j_user: str = 'neo4j'
    neo4j_password: str = 'mirofish-dev'
    neo4j_database: str = 'neo4j'
    llm_model: str = 'gpt-4o-mini'
    llm_small_model: str = 'gpt-4o-mini'
    llm_base_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'GraphitiConfig':
        # GRAPHITI_LLM_BASE_URL이 명시되면 우선, 없으면 LLM_BASE_URL fallback.
        base_url = (
            os.environ.get('GRAPHITI_LLM_BASE_URL')
            or os.environ.get('LLM_BASE_URL')
        )
        return cls(
            neo4j_uri=os.environ.get('NEO4J_URI', cls.neo4j_uri),
            neo4j_user=os.environ.get('NEO4J_USER', cls.neo4j_user),
            neo4j_password=os.environ.get('NEO4J_PASSWORD', cls.neo4j_password),
            neo4j_database=os.environ.get('NEO4J_DATABASE', cls.neo4j_database),
            llm_model=os.environ.get('GRAPHITI_MODEL', cls.llm_model),
            llm_small_model=os.environ.get('GRAPHITI_SMALL_MODEL', cls.llm_small_model),
            llm_base_url=base_url,
        )


def create_graphiti(config: Optional[GraphitiConfig] = None):
    """Graphiti 인스턴스 생성.

    주의: graphiti-core 는 async-first. 반환된 객체의 주요 메서드
    (`add_episode`, `search`, `build_indices_and_constraints`, `close`)는
    모두 coroutine이다.

    Args:
        config: 명시 설정. None이면 환경 변수에서 로드.

    Returns:
        graphiti_core.Graphiti 인스턴스. 사용 후 `await graphiti.close()` 필수.

    Raises:
        RuntimeError: graphiti-core 패키지 미설치.
    """
    try:
        from graphiti_core import Graphiti  # type: ignore
        from graphiti_core.llm_client import OpenAIClient  # type: ignore
        from graphiti_core.llm_client.config import LLMConfig  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            'graphiti-core가 설치되지 않았습니다. '
            '`uv sync` 또는 `uv add graphiti-core` 실행 후 재시도하세요.'
        ) from e

    cfg = config or GraphitiConfig.from_env()

    # Graphiti는 내부적으로 OPENAI_API_KEY 환경 변수를 읽는다. MiroFish는
    # LLM_API_KEY/LLM_BASE_URL 네임을 쓰므로 명시 전파. 이미 OPENAI_API_KEY가
    # 설정돼 있으면 덮어쓰지 않는다.
    api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('LLM_API_KEY')
    if api_key and not os.environ.get('OPENAI_API_KEY'):
        os.environ['OPENAI_API_KEY'] = api_key

    # LLM 모델 override: graphiti-core 기본(gpt-4.1-mini + gpt-4.1-nano) 대신
    # GraphitiConfig의 llm_model/llm_small_model(기본 gpt-4o-mini) 사용. TPM 한도
    # + 비용 효율 때문. base_url은 OpenAI 호환 엔드포인트용.
    llm_config = LLMConfig(
        api_key=api_key,
        model=cfg.llm_model,
        small_model=cfg.llm_small_model,
        base_url=cfg.llm_base_url,
    )
    llm_client = OpenAIClient(config=llm_config)

    # graphiti-core v0.4+는 Graphiti 생성자가 driver 객체를 직접 받는 시그니처와
    # URI/user/password를 개별 인자로 받는 시그니처 두 가지를 모두 지원한다.
    # 호환 최대화를 위해 후자를 사용. llm_client 주입으로 모델 선택.
    return Graphiti(
        uri=cfg.neo4j_uri,
        user=cfg.neo4j_user,
        password=cfg.neo4j_password,
        llm_client=llm_client,
    )


def neo4j_driver(config: Optional[GraphitiConfig] = None):
    """순수 Neo4j 드라이버 (Graphiti가 제공하지 않는 직접 Cypher 쿼리용).

    entity_reader/tools에서 UUID 기반 노드 lookup 등을 할 때 사용.
    """
    from neo4j import GraphDatabase  # type: ignore

    cfg = config or GraphitiConfig.from_env()
    return GraphDatabase.driver(
        cfg.neo4j_uri,
        auth=(cfg.neo4j_user, cfg.neo4j_password),
    )
