"""
OasisProfileGenerator 단위 테스트 (`app/services/oasis_profile_generator.py`).

검증 단위:
- OasisAgentProfile: to_reddit_format / to_twitter_format / to_dict (선택 필드 분기)
- 클래스 상수 (MBTI_TYPES / COUNTRIES / INDIVIDUAL/GROUP_ENTITY_TYPES)
- __init__: API 키 없으면 raise
- _generate_username: 특수 문자 제거, 소문자, 접미사
- _is_individual_entity / _is_group_entity
- _fix_truncated_json / _try_fix_json (망가진 JSON 추출)
- _build_entity_context: attributes / related_edges / related_nodes
- _generate_profile_rule_based: student/expert/media/institution/default 분기
- _normalize_gender: 한국어/영어/None 매핑
- _search_zep_for_entity: zep_client=None → no-op
- save_profiles + _save_twitter_csv + _save_reddit_json
- generate_profile_from_entity (use_llm=False end-to-end)
"""

import csv as _csv
import json
import random
from types import SimpleNamespace

import pytest

from app.services import oasis_profile_generator as opg_mod
from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
)


# ---------------------------------------------------------------------------
# 가짜 EntityNode
# ---------------------------------------------------------------------------

class _FakeEntity:
    def __init__(
        self, uuid="u1", name="N", entity_type="Person",
        summary="요약", attributes=None, related_edges=None, related_nodes=None,
    ):
        self.uuid = uuid
        self.name = name
        self._type = entity_type
        self.summary = summary
        self.labels = ["Entity", entity_type] if entity_type else ["Entity"]
        self.attributes = attributes or {}
        self.related_edges = related_edges or []
        self.related_nodes = related_nodes or []

    def get_entity_type(self):
        return self._type


def _gen(api_key="dummy", graph_id=None):
    g = OasisProfileGenerator(api_key=api_key, graph_id=graph_id)
    return g


@pytest.fixture(autouse=True)
def _stable_random():
    """random 호출 격리 — 결과 재현성."""
    random.seed(42)
    yield


# ============================================================================
# OasisAgentProfile
# ============================================================================

class TestOasisAgentProfile:
    def _make(self, **overrides):
        defaults = dict(
            user_id=1, user_name="alice_123", name="Alice",
            bio="bio", persona="persona",
        )
        defaults.update(overrides)
        return OasisAgentProfile(**defaults)

    def test_to_reddit_format_minimal(self):
        p = self._make()
        d = p.to_reddit_format()
        assert d["username"] == "alice_123"
        assert d["karma"] == 1000
        # optional 필드 미설정 → 누락
        assert "age" not in d
        assert "gender" not in d

    def test_to_reddit_format_with_optionals(self):
        p = self._make(
            age=25, gender="female", mbti="INTJ", country="한국",
            profession="Student", interested_topics=["X"],
        )
        d = p.to_reddit_format()
        assert d["age"] == 25
        assert d["gender"] == "female"
        assert d["mbti"] == "INTJ"
        assert d["interested_topics"] == ["X"]

    def test_to_twitter_format(self):
        p = self._make(age=30, gender="male", profession="Dev")
        d = p.to_twitter_format()
        assert d["friend_count"] == 100
        assert d["follower_count"] == 150
        assert d["statuses_count"] == 500
        assert d["age"] == 30
        assert d["profession"] == "Dev"

    def test_to_dict_includes_all(self):
        p = self._make(age=40, source_entity_uuid="u1", source_entity_type="Person")
        d = p.to_dict()
        # 모든 필드 포함 (None 값도)
        assert d["user_id"] == 1
        assert d["age"] == 40
        assert d["source_entity_uuid"] == "u1"
        assert d["source_entity_type"] == "Person"


# ============================================================================
# 클래스 상수
# ============================================================================

class TestClassConstants:
    def test_mbti_count(self):
        # 16 standard MBTI types
        assert len(OasisProfileGenerator.MBTI_TYPES) == 16

    def test_individual_types(self):
        assert "student" in OasisProfileGenerator.INDIVIDUAL_ENTITY_TYPES
        assert "professor" in OasisProfileGenerator.INDIVIDUAL_ENTITY_TYPES

    def test_group_types(self):
        assert "university" in OasisProfileGenerator.GROUP_ENTITY_TYPES
        assert "ngo" in OasisProfileGenerator.GROUP_ENTITY_TYPES


# ============================================================================
# __init__ + 기본 헬퍼
# ============================================================================

class TestInit:
    def test_no_api_key_raises(self, monkeypatch):
        # Config.LLM_API_KEY 도 비우기
        monkeypatch.setattr(opg_mod.Config, "LLM_API_KEY", "")
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            OasisProfileGenerator(api_key=None)

    def test_graph_id_stored(self):
        g = _gen(graph_id="g_xyz")
        assert g.graph_id == "g_xyz"

    def test_set_graph_id(self):
        g = _gen()
        g.set_graph_id("new_g")
        assert g.graph_id == "new_g"


class TestGenerateUsername:
    def test_lowercase_and_underscored(self):
        g = _gen()
        u = g._generate_username("Alice Smith")
        assert u.startswith("alice_smith_")

    def test_strips_special_chars(self):
        g = _gen()
        u = g._generate_username("Alice!@#$%^Smith")
        # 영숫자/언더스코어만 남음
        body = u.rsplit("_", 1)[0]
        assert all(c.isalnum() or c == "_" for c in body)
        assert "alicesmith" in body

    def test_suffix_in_range(self):
        g = _gen()
        u = g._generate_username("Bob")
        suffix = u.rsplit("_", 1)[-1]
        n = int(suffix)
        assert 100 <= n <= 999


class TestEntityTypeChecks:
    def test_individual_match(self):
        g = _gen()
        assert g._is_individual_entity("Student") is True
        assert g._is_individual_entity("Person") is True
        assert g._is_individual_entity("PROFESSOR") is True
        assert g._is_individual_entity("University") is False

    def test_group_match(self):
        g = _gen()
        assert g._is_group_entity("University") is True
        assert g._is_group_entity("MEDIAOUTLET") is True
        assert g._is_group_entity("Student") is False


# ============================================================================
# JSON 수정 헬퍼
# ============================================================================

class TestFixTruncatedJSON:
    def test_closes_brace(self):
        result = _gen()._fix_truncated_json('{"a": "x')
        assert result == '{"a": "x"}'
        assert json.loads(result) == {"a": "x"}

    def test_closes_brackets(self):
        result = _gen()._fix_truncated_json('{"a": [1, 2,')
        assert result.endswith("]}")

    def test_already_complete(self):
        result = _gen()._fix_truncated_json('{"a": 1}')
        assert json.loads(result) == {"a": 1}


class TestTryFixJSON:
    def test_extracts_valid_block(self):
        wrapped = 'noise {"bio": "X", "persona": "Y"} more'
        result = _gen()._try_fix_json(wrapped, "name", "Person")
        assert result["bio"] == "X"
        assert result["persona"] == "Y"

    def test_handles_newline_in_strings(self):
        bad = '{"bio": "line1\nline2", "persona": "p"}'
        result = _gen()._try_fix_json(bad, "name", "Person")
        # 망가진 JSON 에서 추출 — bio/persona 가 살아 있어야 함
        assert "line1" in result["bio"]
        assert result["persona"] == "p"

    def test_partial_extraction_via_regex(self):
        # JSON 블록 전체는 망가졌지만 bio 가 남아있음
        content = 'random text "bio": "from regex" more garbage'
        result = _gen()._try_fix_json(content, "name", "Person")
        assert result["bio"] == "from regex"

    def test_complete_failure_returns_default_structure(self):
        result = _gen()._try_fix_json("absolutely no json", "Alice", "Person", "요약")
        # 기본 구조 — entity_summary 또는 default 메시지
        assert "bio" in result
        assert "persona" in result


# ============================================================================
# _build_entity_context
# ============================================================================

class TestBuildEntityContext:
    def test_with_attributes(self):
        e = _FakeEntity(attributes={"role": "CEO", "title": "엔지니어"})
        ctx = _gen()._build_entity_context(e)
        assert "엔티티 속성" in ctx
        assert "role: CEO" in ctx

    def test_with_related_edges(self):
        e = _FakeEntity(
            related_edges=[
                {"fact": "Alice works at ACME", "edge_name": "WORKS_FOR"},
                {"edge_name": "FOUNDED", "direction": "outgoing"},
            ]
        )
        ctx = _gen()._build_entity_context(e)
        assert "Alice works at ACME" in ctx
        assert "FOUNDED" in ctx

    def test_with_related_nodes(self):
        e = _FakeEntity(
            related_nodes=[
                {"name": "ACME", "labels": ["Entity", "Company"], "summary": "회사"},
                {"name": "Bob", "labels": ["Entity", "Person"]},
            ]
        )
        ctx = _gen()._build_entity_context(e)
        assert "ACME" in ctx
        assert "Company" in ctx
        assert "Bob" in ctx

    def test_empty_entity(self):
        e = _FakeEntity()
        ctx = _gen()._build_entity_context(e)
        assert ctx == ""  # Zep 검색 no-op + 다른 정보 없음


# ============================================================================
# _generate_profile_rule_based
# ============================================================================

class TestRuleBasedProfile:
    def test_student(self):
        p = _gen()._generate_profile_rule_based("Alice", "Student", "학생", {})
        assert "Student" in p["bio"] or "student" in p["bio"]
        assert p["profession"] == "Student"
        assert 18 <= p["age"] <= 30
        assert p["gender"] in ["male", "female"]
        assert p["mbti"] in OasisProfileGenerator.MBTI_TYPES

    def test_expert(self):
        p = _gen()._generate_profile_rule_based(
            "Dr. X", "Expert", "전문가", {"occupation": "Researcher"}
        )
        assert p["profession"] == "Researcher"
        assert 35 <= p["age"] <= 60
        assert p["mbti"] in ["ENTJ", "INTJ", "ENTP", "INTP"]

    def test_media(self):
        p = _gen()._generate_profile_rule_based(
            "Daily News", "MediaOutlet", "신문사", {}
        )
        assert p["age"] == 30
        assert p["gender"] == "other"
        assert p["mbti"] == "ISTJ"
        assert p["country"] == "한국"
        assert p["profession"] == "Media"

    def test_institution(self):
        p = _gen()._generate_profile_rule_based(
            "S대", "University", "대학교", {}
        )
        assert p["age"] == 30
        assert p["gender"] == "other"
        assert p["country"] == "한국"

    def test_default_unknown_type(self):
        p = _gen()._generate_profile_rule_based(
            "X", "RandomType", "기타", {}
        )
        assert 25 <= p["age"] <= 50
        assert p["gender"] in ["male", "female"]
        assert p["profession"] == "RandomType"


# ============================================================================
# _normalize_gender
# ============================================================================

class TestNormalizeGender:
    @pytest.mark.parametrize("inp,expected", [
        (None, "other"),
        ("", "other"),
        ("male", "male"),
        ("female", "female"),
        ("Male", "male"),
        ("FEMALE", "female"),
        ("other", "other"),
        ("남", "male"),
        ("여", "female"),
        ("기관", "other"),
        ("기타", "other"),
        ("unknown_value", "other"),  # 폴백
    ])
    def test_mappings(self, inp, expected):
        assert _gen()._normalize_gender(inp) == expected


# ============================================================================
# _search_zep_for_entity (zep_client=None → no-op)
# ============================================================================

class TestSearchZepForEntity:
    def test_no_zep_client_returns_empty(self):
        g = _gen()
        # legacy zep is optional — 평상시 None
        assert g.zep_client is None
        result = g._search_zep_for_entity(_FakeEntity())
        assert result == {"facts": [], "node_summaries": [], "context": ""}


# ============================================================================
# save_profiles
# ============================================================================

def _profile(idx=0, **kw):
    base = dict(
        user_id=idx, user_name=f"u{idx}", name=f"N{idx}",
        bio=f"bio{idx}", persona=f"persona{idx}",
    )
    base.update(kw)
    return OasisAgentProfile(**base)


class TestSaveProfiles:
    def test_save_reddit_json_includes_required_fields(self, tmp_path):
        g = _gen()
        profiles = [
            _profile(0, age=25, gender="female", mbti="INTJ", country="한국"),
            _profile(1),  # 기본값 fallback 검증
        ]
        path = tmp_path / "reddit.json"
        g.save_profiles(profiles, str(path), platform="reddit")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["user_id"] == 0
        assert data[0]["username"] == "u0"
        assert data[0]["age"] == 25
        assert data[0]["gender"] == "female"
        # 기본값 fallback
        assert data[1]["age"] == 30
        assert data[1]["mbti"] == "ISTJ"
        assert data[1]["country"] == "한국"

    def test_save_reddit_json_normalizes_gender(self, tmp_path):
        g = _gen()
        path = tmp_path / "r.json"
        g.save_profiles(
            [_profile(0, gender="남")],
            str(path), platform="reddit",
        )
        data = json.loads(path.read_text())
        assert data[0]["gender"] == "male"

    def test_save_twitter_csv(self, tmp_path):
        g = _gen()
        path = tmp_path / "twitter.csv"
        g.save_profiles(
            [_profile(0, persona="페르소나"), _profile(1)],
            str(path), platform="twitter",
        )
        with open(path, encoding="utf-8") as f:
            rows = list(_csv.reader(f))
        # 헤더 + 2 rows
        assert rows[0] == ["user_id", "name", "username", "user_char", "description"]
        assert rows[1][0] == "0"
        assert rows[1][1] == "N0"
        # user_char = bio + persona 결합
        assert "페르소나" in rows[1][3]
        # description = bio
        assert rows[1][4] == "bio0"

    def test_save_twitter_changes_extension(self, tmp_path):
        g = _gen()
        path = tmp_path / "twitter.json"  # 잘못된 확장자
        g.save_profiles(
            [_profile(0)], str(path), platform="twitter",
        )
        # .csv 로 변환 후 저장됨
        assert (tmp_path / "twitter.csv").exists()


# ============================================================================
# generate_profile_from_entity (use_llm=False end-to-end)
# ============================================================================

class TestGenerateProfileFromEntity:
    def test_rule_based(self):
        g = _gen()
        e = _FakeEntity(uuid="u1", name="Alice", entity_type="Student", summary="학생")
        profile = g.generate_profile_from_entity(e, user_id=42, use_llm=False)
        assert isinstance(profile, OasisAgentProfile)
        assert profile.user_id == 42
        assert profile.name == "Alice"
        assert profile.user_name.startswith("alice_")
        assert profile.source_entity_uuid == "u1"
        assert profile.source_entity_type == "Student"
        assert profile.profession == "Student"
        assert 18 <= profile.age <= 30

    def test_rule_based_unknown_type_defaults(self):
        g = _gen()
        e = _FakeEntity(name="X", entity_type="UnknownType", summary="요약")
        profile = g.generate_profile_from_entity(e, user_id=0, use_llm=False)
        assert profile.profession == "UnknownType"
        # bio 는 entity_summary 사용
        assert "요약" in profile.bio

    def test_rule_based_institution_no_llm(self):
        g = _gen()
        e = _FakeEntity(name="S대", entity_type="University", summary="대학")
        profile = g.generate_profile_from_entity(e, user_id=5, use_llm=False)
        assert profile.gender == "other"
        assert profile.country == "한국"
