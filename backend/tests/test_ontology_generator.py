"""
OntologyGenerator 단위 테스트 (`app/services/ontology_generator.py`).

- 헬퍼: `_split_words`, `_normalize_pascal_case`, `_normalize_upper_snake_case`
  → Zep API 명명 규칙 강제 (PascalCase entity, UPPER_SNAKE_CASE edge)
- OntologyGenerator: `_build_user_message`, `_validate_and_process`, `generate`,
  `generate_python_code`
"""

import json
import textwrap

import pytest

from app.services.ontology_generator import (
    OntologyGenerator,
    _normalize_pascal_case,
    _normalize_upper_snake_case,
    _split_words,
)


# ============================================================================
# _split_words
# ============================================================================

class TestSplitWords:
    @pytest.mark.parametrize("inp,expected", [
        ("media_outlet", ["media", "outlet"]),
        ("media-outlet", ["media", "outlet"]),
        ("media outlet", ["media", "outlet"]),
        ("MediaOutlet", ["Media", "Outlet"]),
        ("mediaOutlet", ["media", "Outlet"]),
        ("MEDIA_OUTLET", ["MEDIA", "OUTLET"]),
        ("'mediaoutlet'", ["mediaoutlet"]),
        ("mediaoutlet", ["mediaoutlet"]),
        ("NGO", ["NGO"]),
        ("URLParser", ["URL", "Parser"]),
    ])
    def test_split(self, inp, expected):
        assert _split_words(inp) == expected


# ============================================================================
# _normalize_pascal_case (entity types)
# ============================================================================

class TestNormalizePascalCase:
    @pytest.mark.parametrize("inp,expected", [
        # known map (lowercase)
        ("mediaoutlet", "MediaOutlet"),
        ("MEDIAOUTLET", "MediaOutlet"),
        ("ngo", "NGO"),
        ("person", "Person"),
        # snake/dash → 첫글자 대문자
        ("media_outlet", "MediaOutlet"),
        ("media-outlet", "MediaOutlet"),
        # camelCase
        ("mediaOutlet", "MediaOutlet"),
        # 이미 PascalCase
        ("MediaOutlet", "MediaOutlet"),
        # known_map 외 약어 보존 (3-4글자 대문자)
        ("CEO", "CEO"),
        # 따옴표 제거
        ("'Person'", "Person"),
        # 빈 문자열
        ("", ""),
        ("   ", ""),
    ])
    def test_normalize(self, inp, expected):
        assert _normalize_pascal_case(inp) == expected

    def test_custom_known_map(self):
        custom = {"foo": "FooBar"}
        assert _normalize_pascal_case("foo", known_map=custom) == "FooBar"


# ============================================================================
# _normalize_upper_snake_case (edge types)
# ============================================================================

class TestNormalizeUpperSnakeCase:
    @pytest.mark.parametrize("inp,expected", [
        # known map
        ("reportson", "REPORTS_ON"),
        ("worksfor", "WORKS_FOR"),
        # camelCase
        ("reportsOn", "REPORTS_ON"),
        # snake → upper
        ("reports_on", "REPORTS_ON"),
        # 이미 정규화
        ("REPORTS_ON", "REPORTS_ON"),
        # 단일 토큰
        ("supports", "SUPPORTS"),
        # 빈 문자열
        ("", ""),
    ])
    def test_normalize(self, inp, expected):
        assert _normalize_upper_snake_case(inp) == expected


# ============================================================================
# OntologyGenerator._build_user_message
# ============================================================================

class TestBuildUserMessage:
    def test_basic_message(self):
        gen = OntologyGenerator(llm_client=object())
        msg = gen._build_user_message(
            document_texts=["문서 A", "문서 B"],
            simulation_requirement="요구사항",
            additional_context=None,
        )
        assert "요구사항" in msg
        assert "문서 A" in msg
        assert "문서 B" in msg
        assert "추가 설명" not in msg

    def test_with_additional_context(self):
        gen = OntologyGenerator(llm_client=object())
        msg = gen._build_user_message(
            document_texts=["문서"],
            simulation_requirement="요구",
            additional_context="추가 컨텍스트 X",
        )
        assert "추가 설명" in msg
        assert "추가 컨텍스트 X" in msg

    def test_truncation_above_max_length(self):
        gen = OntologyGenerator(llm_client=object())
        long_text = "a" * (OntologyGenerator.MAX_TEXT_LENGTH_FOR_LLM + 1000)
        msg = gen._build_user_message(
            document_texts=[long_text],
            simulation_requirement="요구",
            additional_context=None,
        )
        # 잘림 표시 포함
        assert "원문 총" in msg
        assert "온톨로지 분석을 위해" in msg

    def test_no_truncation_at_or_below_max(self):
        gen = OntologyGenerator(llm_client=object())
        text = "a" * (OntologyGenerator.MAX_TEXT_LENGTH_FOR_LLM - 100)
        msg = gen._build_user_message(
            document_texts=[text],
            simulation_requirement="요구",
            additional_context=None,
        )
        assert "원문 총" not in msg


# ============================================================================
# _validate_and_process
# ============================================================================

class TestValidateAndProcess:
    def _gen(self):
        return OntologyGenerator(llm_client=object())

    def test_fills_missing_top_level_keys(self):
        result = self._gen()._validate_and_process({})
        assert result["edge_types"] == []
        assert result["analysis_summary"] == ""
        # entity_types: 폴백 Person + Organization 자동 추가
        names = {e["name"] for e in result["entity_types"]}
        assert names == {"Person", "Organization"}

    def test_normalizes_lowercase_entity_names(self):
        result = self._gen()._validate_and_process({
            "entity_types": [
                {"name": "mediaoutlet"},
                {"name": "company"},
            ],
            "edge_types": [],
        })
        names = {e["name"] for e in result["entity_types"]}
        assert "MediaOutlet" in names
        assert "Company" in names

    def test_normalizes_edge_names(self):
        result = self._gen()._validate_and_process({
            "entity_types": [],
            "edge_types": [
                {"name": "reportson"},
                {"name": "worksFor"},
            ],
        })
        names = {e["name"] for e in result["edge_types"]}
        assert "REPORTS_ON" in names
        assert "WORKS_FOR" in names

    def test_renames_source_targets_via_entity_map(self):
        """entity 가 mediaoutlet → MediaOutlet 으로 정규화되면, edge 의 source/target 도 일치 갱신."""
        result = self._gen()._validate_and_process({
            "entity_types": [{"name": "mediaoutlet"}],
            "edge_types": [
                {
                    "name": "reportson",
                    "source_targets": [
                        {"source": "mediaoutlet", "target": "person"},
                    ],
                }
            ],
        })
        edge = next(e for e in result["edge_types"] if e["name"] == "REPORTS_ON")
        st = edge["source_targets"][0]
        assert st["source"] == "MediaOutlet"
        assert st["target"] == "Person"

    def test_truncates_long_descriptions(self):
        long_desc = "x" * 200
        result = self._gen()._validate_and_process({
            "entity_types": [{"name": "Person", "description": long_desc}],
            "edge_types": [{"name": "WORKS_FOR", "description": long_desc}],
        })
        for entity in result["entity_types"]:
            assert len(entity.get("description", "")) <= 100
        for edge in result["edge_types"]:
            assert len(edge.get("description", "")) <= 100

    def test_fallback_already_present_not_duplicated(self):
        result = self._gen()._validate_and_process({
            "entity_types": [
                {"name": "Person"},
                {"name": "Organization"},
            ],
            "edge_types": [],
        })
        names = [e["name"] for e in result["entity_types"]]
        assert names.count("Person") == 1
        assert names.count("Organization") == 1

    def test_fallback_injection_trims_when_overflow(self):
        """10개 이미 있고 폴백 없으면, 끝에서 제거하고 폴백 추가."""
        entities = [{"name": f"Specific{i}"} for i in range(10)]
        result = self._gen()._validate_and_process({
            "entity_types": entities,
            "edge_types": [],
        })
        names = [e["name"] for e in result["entity_types"]]
        assert "Person" in names
        assert "Organization" in names
        assert len(result["entity_types"]) == 10

    def test_max_10_edge_types_enforced(self):
        edges = [{"name": f"REL_{i}"} for i in range(15)]
        result = self._gen()._validate_and_process({
            "entity_types": [],
            "edge_types": edges,
        })
        assert len(result["edge_types"]) == 10

    def test_fills_missing_attributes_and_examples(self):
        result = self._gen()._validate_and_process({
            "entity_types": [{"name": "Foo"}],
            "edge_types": [{"name": "BAR"}],
        })
        foo = next(e for e in result["entity_types"] if e["name"] == "Foo")
        assert foo["attributes"] == []
        assert foo["examples"] == []
        bar = next(e for e in result["edge_types"] if e["name"] == "BAR")
        assert bar["source_targets"] == []
        assert bar["attributes"] == []


# ============================================================================
# generate (LLMClient 모킹)
# ============================================================================

class TestGenerate:
    def test_calls_llm_and_postprocesses(self):
        captured = {}

        class _Client:
            def chat_json(self, messages, temperature, max_tokens):
                captured["messages"] = messages
                captured["temperature"] = temperature
                captured["max_tokens"] = max_tokens
                # LLM 출력 모사 (lowercase 이름 → 정규화 검증)
                return {
                    "entity_types": [{"name": "company"}, {"name": "mediaoutlet"}],
                    "edge_types": [{"name": "reportson"}],
                    "analysis_summary": "요약",
                }

        gen = OntologyGenerator(llm_client=_Client())
        result = gen.generate(
            document_texts=["doc"],
            simulation_requirement="요구",
        )
        # 메시지 두 개 (system + user)
        assert len(captured["messages"]) == 2
        assert captured["messages"][0]["role"] == "system"
        assert captured["messages"][1]["role"] == "user"
        assert captured["temperature"] == 0.3
        # 정규화 + 폴백 추가 확인
        names = {e["name"] for e in result["entity_types"]}
        assert "Company" in names
        assert "MediaOutlet" in names
        assert "Person" in names
        assert "Organization" in names
        edge_names = {e["name"] for e in result["edge_types"]}
        assert "REPORTS_ON" in edge_names


# ============================================================================
# generate_python_code
# ============================================================================

class TestGeneratePythonCode:
    def _gen(self):
        return OntologyGenerator(llm_client=object())

    def test_basic_code_generation(self):
        ontology = {
            "entity_types": [
                {
                    "name": "Person",
                    "description": "A person.",
                    "attributes": [
                        {"name": "full_name", "type": "text", "description": "Name"},
                    ],
                },
                {"name": "Company", "description": "A company.", "attributes": []},
            ],
            "edge_types": [
                {
                    "name": "WORKS_FOR",
                    "description": "Employment.",
                    "attributes": [],
                    "source_targets": [{"source": "Person", "target": "Company"}],
                }
            ],
        }
        code = self._gen().generate_python_code(ontology)

        # 기본 구성 요소
        assert "from pydantic import BaseModel, Field" in code
        assert "class Person(BaseModel):" in code
        assert "class Company(BaseModel):" in code
        assert "class WorksFor(BaseModel):" in code  # WORKS_FOR → PascalCase 클래스명
        assert "full_name: Optional[str]" in code
        assert "ENTITY_TYPES = {" in code
        assert "EDGE_TYPES = {" in code
        assert "EDGE_SOURCE_TARGETS = {" in code
        assert '"Person": Person' in code
        assert '"Company": Company' in code
        assert '"WORKS_FOR": WorksFor' in code

    def test_attributeless_entity_uses_pass(self):
        code = self._gen().generate_python_code({
            "entity_types": [{"name": "Empty"}],
            "edge_types": [],
        })
        # class Empty(BaseModel):\n    """A Empty entity."""\n    pass
        assert "class Empty(BaseModel):" in code
        # 속성 없으니 pass 사용
        idx = code.find("class Empty(BaseModel):")
        assert "pass" in code[idx:idx + 200]

    def test_compiles_to_valid_python(self):
        """생성된 코드가 실제로 import/실행 가능한지."""
        ontology = {
            "entity_types": [
                {
                    "name": "Reporter",
                    "description": "A journalist",
                    "attributes": [
                        {"name": "outlet", "type": "text", "description": "Affiliated outlet"},
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "REPORTS_ON",
                    "description": "reports on",
                    "attributes": [],
                    "source_targets": [{"source": "Reporter", "target": "Reporter"}],
                }
            ],
        }
        code = self._gen().generate_python_code(ontology)
        ns = {}
        exec(compile(code, "<test>", "exec"), ns)
        assert "Reporter" in ns
        assert "ReportsOn" in ns
        assert ns["ENTITY_TYPES"]["Reporter"] is ns["Reporter"]
        assert ns["EDGE_TYPES"]["REPORTS_ON"] is ns["ReportsOn"]
        # source_targets 매핑
        assert "REPORTS_ON" in ns["EDGE_SOURCE_TARGETS"]
        # Reporter 모델 인스턴스화
        instance = ns["Reporter"](outlet="Times")
        assert instance.outlet == "Times"
