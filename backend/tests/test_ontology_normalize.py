"""
OntologyGenerator 명명 규칙 정규화 테스트.

스모크 #2 (sim_8e034c1ae42f)에서 LLM이 `mediaoutlet`, `governmentagency` 같은
lowercase entity_type을 출력 → Zep API 거부 → 재시도 2회 발생. 이를 코드 레이어에서
강제 정규화해 재시도 낭비를 막는다.
"""

import os
import sys

# backend/tests/ → backend/ 를 sys.path에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ontology_generator import (  # noqa: E402
    OntologyGenerator,
    _normalize_pascal_case,
    _normalize_upper_snake_case,
)


class TestNormalizePascalCase:
    def test_already_pascal(self):
        assert _normalize_pascal_case("MediaOutlet") == "MediaOutlet"
        assert _normalize_pascal_case("Company") == "Company"
        assert _normalize_pascal_case("Person") == "Person"

    def test_lowercase_known(self):
        # 스모크 #2 실제 회귀 케이스
        assert _normalize_pascal_case("mediaoutlet") == "MediaOutlet"
        assert _normalize_pascal_case("governmentagency") == "GovernmentAgency"
        assert _normalize_pascal_case("company") == "Company"
        assert _normalize_pascal_case("person") == "Person"

    def test_lowercase_unknown_fallback(self):
        # known_map에 없는 lowercase는 첫 글자만 대문자화
        assert _normalize_pascal_case("semiconductor") == "Semiconductor"

    def test_snake_case(self):
        assert _normalize_pascal_case("media_outlet") == "MediaOutlet"
        assert _normalize_pascal_case("government_agency") == "GovernmentAgency"
        assert _normalize_pascal_case("trade_association") == "TradeAssociation"

    def test_camel_case(self):
        assert _normalize_pascal_case("mediaOutlet") == "MediaOutlet"
        assert _normalize_pascal_case("governmentAgency") == "GovernmentAgency"

    def test_kebab_case(self):
        assert _normalize_pascal_case("media-outlet") == "MediaOutlet"

    def test_space_separated(self):
        assert _normalize_pascal_case("Media Outlet") == "MediaOutlet"

    def test_acronym_preserved(self):
        # known_map 경유로 NGO 보존
        assert _normalize_pascal_case("ngo") == "NGO"
        assert _normalize_pascal_case("NGO") == "NGO"

    def test_upper_snake(self):
        # UPPER_SNAKE도 실수로 들어올 수 있음
        assert _normalize_pascal_case("MEDIA_OUTLET") == "MediaOutlet"

    def test_whitespace_and_quotes(self):
        assert _normalize_pascal_case("  mediaoutlet  ") == "MediaOutlet"
        assert _normalize_pascal_case('"Company"') == "Company"

    def test_empty(self):
        assert _normalize_pascal_case("") == ""


class TestNormalizeUpperSnakeCase:
    def test_already_upper_snake(self):
        assert _normalize_upper_snake_case("WORKS_FOR") == "WORKS_FOR"
        assert _normalize_upper_snake_case("REPORTS_ON") == "REPORTS_ON"

    def test_lowercase_known(self):
        assert _normalize_upper_snake_case("reportson") == "REPORTS_ON"
        assert _normalize_upper_snake_case("worksfor") == "WORKS_FOR"

    def test_camel_case(self):
        assert _normalize_upper_snake_case("reportsOn") == "REPORTS_ON"
        assert _normalize_upper_snake_case("worksFor") == "WORKS_FOR"

    def test_pascal_case(self):
        assert _normalize_upper_snake_case("ReportsOn") == "REPORTS_ON"

    def test_snake_lower(self):
        assert _normalize_upper_snake_case("reports_on") == "REPORTS_ON"

    def test_kebab(self):
        assert _normalize_upper_snake_case("reports-on") == "REPORTS_ON"

    def test_unknown(self):
        # known_map에 없는 신규 관계도 처리
        assert _normalize_upper_snake_case("shipsToHyperscaler") == "SHIPS_TO_HYPERSCALER"

    def test_empty(self):
        assert _normalize_upper_snake_case("") == ""


class TestValidateAndProcess:
    """smoke #2 재현 — LLM이 lowercase 이름을 출력했을 때 정규화 후 후속 처리가
    올바로 돌아가는지."""

    def test_smoke_regression_lowercase_entity_types(self):
        gen = OntologyGenerator.__new__(OntologyGenerator)  # LLM 호출 회피
        llm_output = {
            "entity_types": [
                {"name": "company", "description": "A company"},
                {"name": "mediaoutlet", "description": "A media outlet"},
                {"name": "governmentagency", "description": "A gov agency"},
                {"name": "investor", "description": "An investor"},
            ],
            "edge_types": [
                {
                    "name": "reportson",
                    "description": "reports on",
                    "source_targets": [
                        {"source": "mediaoutlet", "target": "company"}
                    ],
                },
                {
                    "name": "suppliesTo",
                    "description": "supplies to",
                    "source_targets": [
                        {"source": "company", "target": "company"}
                    ],
                },
            ],
            "analysis_summary": "test",
        }

        result = gen._validate_and_process(llm_output)

        entity_names = [e["name"] for e in result["entity_types"]]
        assert "Company" in entity_names
        assert "MediaOutlet" in entity_names
        assert "GovernmentAgency" in entity_names
        assert "Investor" in entity_names

        # 폴백 Person/Organization 자동 추가 확인
        assert "Person" in entity_names
        assert "Organization" in entity_names

        edge_names = [e["name"] for e in result["edge_types"]]
        assert "REPORTS_ON" in edge_names
        assert "SUPPLIES_TO" in edge_names

        # source_targets 참조도 정규화됐는지
        reports_on = next(e for e in result["edge_types"] if e["name"] == "REPORTS_ON")
        assert reports_on["source_targets"][0]["source"] == "MediaOutlet"
        assert reports_on["source_targets"][0]["target"] == "Company"

    def test_already_correct_no_change(self):
        gen = OntologyGenerator.__new__(OntologyGenerator)
        llm_output = {
            "entity_types": [
                {"name": "Company", "description": "A company"},
                {"name": "Person", "description": "A person"},
                {"name": "Organization", "description": "An org"},
            ],
            "edge_types": [
                {
                    "name": "WORKS_FOR",
                    "description": "works for",
                    "source_targets": [{"source": "Person", "target": "Company"}],
                }
            ],
            "analysis_summary": "",
        }
        result = gen._validate_and_process(llm_output)
        entity_names = [e["name"] for e in result["entity_types"]]
        assert entity_names[:3] == ["Company", "Person", "Organization"]
        assert result["edge_types"][0]["name"] == "WORKS_FOR"
        assert result["edge_types"][0]["source_targets"][0]["source"] == "Person"
