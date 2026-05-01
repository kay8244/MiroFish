"""
SimulationConfigGenerator 단위 테스트 (`app/services/simulation_config_generator.py`).

검증 단위:
- 데이터클래스 (AgentActivityConfig / TimeSimulationConfig / PlatformConfig /
  SimulationParameters): defaults + to_dict / to_json 직렬화
- 순수 헬퍼: `_fix_truncated_json`, `_try_fix_config_json`, `_get_default_time_config`,
  `_parse_time_config` (clamping), `_parse_event_config`, `_summarize_entities`,
  `_build_context` (truncation), `_assign_initial_post_agents` (직접/별칭/폴백 매칭),
  `_generate_agent_config_by_rule` (유형별 분기)
- LLM 호출 경로 (LLMClient 모킹): `_call_llm_with_retry`, `_generate_time_config`
  실패 시 default fallback, `generate_config` end-to-end
"""

import json
from types import SimpleNamespace

import pytest

from app.services import simulation_config_generator as scg
from app.services.simulation_config_generator import (
    AgentActivityConfig,
    EventConfig,
    PlatformConfig,
    SimulationConfigGenerator,
    SimulationParameters,
    TimeSimulationConfig,
)


# ---------------------------------------------------------------------------
# 가짜 EntityNode (실제 dataclass 와 유사)
# ---------------------------------------------------------------------------

class _FakeEntity:
    def __init__(self, uuid, name, entity_type, summary=""):
        self.uuid = uuid
        self.name = name
        self._type = entity_type
        self.summary = summary
        self.labels = ["Entity", entity_type] if entity_type else ["Entity"]
        self.attributes = {}

    def get_entity_type(self):
        return self._type


def _gen_no_llm():
    """LLMClient 의 외부 호출을 차단하기 위해 더미 client 주입."""
    g = SimulationConfigGenerator.__new__(SimulationConfigGenerator)
    g.model_name = "test-model"
    g.base_url = "https://test"
    g.llm_client = SimpleNamespace(provider="openai", chat=lambda **kw: "{}")
    return g


# ============================================================================
# 데이터클래스
# ============================================================================

class TestAgentActivityConfigDefaults:
    def test_defaults(self):
        cfg = AgentActivityConfig(
            agent_id=1, entity_uuid="u", entity_name="N", entity_type="Person"
        )
        assert cfg.activity_level == 0.5
        assert cfg.posts_per_hour == 1.0
        assert cfg.comments_per_hour == 2.0
        assert cfg.active_hours == list(range(8, 23))
        assert cfg.stance == "neutral"
        assert cfg.influence_weight == 1.0


class TestTimeSimulationConfigDefaults:
    def test_defaults(self):
        cfg = TimeSimulationConfig()
        assert cfg.total_simulation_hours == 72
        assert cfg.minutes_per_round == 60
        assert cfg.peak_hours == [19, 20, 21, 22]
        assert cfg.off_peak_hours == [0, 1, 2, 3, 4, 5]
        assert cfg.morning_hours == [6, 7, 8]
        assert cfg.work_hours == list(range(9, 19))


class TestPlatformConfig:
    def test_defaults(self):
        p = PlatformConfig(platform="twitter")
        assert p.recency_weight == 0.4
        assert p.popularity_weight == 0.3
        assert p.relevance_weight == 0.3
        assert p.viral_threshold == 10
        assert p.echo_chamber_strength == 0.5


class TestSimulationParametersSerialization:
    def test_to_dict_with_no_platforms(self):
        p = SimulationParameters(
            simulation_id="s1", project_id="p", graph_id="g",
            simulation_requirement="요구",
        )
        d = p.to_dict()
        assert d["simulation_id"] == "s1"
        assert d["twitter_config"] is None
        assert d["reddit_config"] is None
        assert d["agent_configs"] == []
        assert "time_config" in d and isinstance(d["time_config"], dict)

    def test_to_dict_with_platforms(self):
        p = SimulationParameters(
            simulation_id="s1", project_id="p", graph_id="g",
            simulation_requirement="요구",
            twitter_config=PlatformConfig(platform="twitter"),
            reddit_config=PlatformConfig(platform="reddit"),
        )
        d = p.to_dict()
        assert d["twitter_config"]["platform"] == "twitter"
        assert d["reddit_config"]["platform"] == "reddit"

    def test_to_json_roundtrip(self):
        p = SimulationParameters(
            simulation_id="s1", project_id="p", graph_id="g",
            simulation_requirement="요구",
        )
        s = p.to_json()
        parsed = json.loads(s)
        assert parsed["simulation_id"] == "s1"


# ============================================================================
# JSON 수정 헬퍼
# ============================================================================

class TestFixTruncatedJSON:
    def test_closes_open_string_and_brace(self):
        # 끝이 따옴표로 안 닫힌 문자열 + 닫히지 않은 brace
        result = _gen_no_llm()._fix_truncated_json('{"a": "hello')
        # '"' 추가 후 '}' 추가
        assert result == '{"a": "hello"}'
        assert json.loads(result) == {"a": "hello"}

    def test_closes_nested_braces_and_brackets(self):
        # 끝이 ',' 라 미완 문자열은 추가 안 함, 괄호만 닫힘
        result = _gen_no_llm()._fix_truncated_json('{"a": [1, 2,')
        assert result.endswith("]}")

    def test_already_complete_passthrough(self):
        result = _gen_no_llm()._fix_truncated_json('{"a": 1}')
        assert json.loads(result) == {"a": 1}

    def test_appends_quote_for_incomplete_value(self):
        # 끝이 숫자로 끝나면 '"' 가 추가됨 (구현 한계 — 정확한 JSON은 아님)
        result = _gen_no_llm()._fix_truncated_json('{"a": 1')
        # '"' 가 추가되어 invalid JSON 이지만 함수 계약상 그렇게 동작
        assert result.count('}') == 1
        assert '"' in result[-3:]


class TestTryFixConfigJSON:
    def test_extracts_valid_json_block(self):
        wrapped = 'Here is the result: {"key": "val"} END'
        result = _gen_no_llm()._try_fix_config_json(wrapped)
        assert result == {"key": "val"}

    def test_handles_newline_in_string(self):
        bad = '{"text": "line1\nline2", "x": 1}'
        result = _gen_no_llm()._try_fix_config_json(bad)
        assert result is not None
        assert result["x"] == 1
        assert "line1" in result["text"]

    def test_returns_none_when_no_json(self):
        assert _gen_no_llm()._try_fix_config_json("no json here") is None


# ============================================================================
# Time config helpers
# ============================================================================

class TestGetDefaultTimeConfig:
    def test_default_structure(self):
        d = _gen_no_llm()._get_default_time_config(num_entities=30)
        assert d["total_simulation_hours"] == 72
        assert d["minutes_per_round"] == 60
        assert d["peak_hours"] == [19, 20, 21, 22]
        assert d["off_peak_hours"] == [0, 1, 2, 3, 4, 5]
        assert d["agents_per_hour_min"] == 2  # 30 // 15
        assert d["agents_per_hour_max"] == 6  # 30 // 5

    def test_min_floor(self):
        d = _gen_no_llm()._get_default_time_config(num_entities=3)
        # 3 // 15 = 0 → max(1, 0) = 1
        assert d["agents_per_hour_min"] == 1
        # 3 // 5 = 0 → max(5, 0) = 5
        assert d["agents_per_hour_max"] == 5


class TestParseTimeConfig:
    def test_uses_provided_values(self):
        cfg = _gen_no_llm()._parse_time_config({
            "total_simulation_hours": 48,
            "minutes_per_round": 30,
            "agents_per_hour_min": 5,
            "agents_per_hour_max": 20,
            "peak_hours": [20, 21],
            "morning_hours": [7],
            "work_hours": [10, 11],
        }, num_entities=30)
        assert cfg.total_simulation_hours == 48
        assert cfg.minutes_per_round == 30
        assert cfg.agents_per_hour_min == 5
        assert cfg.agents_per_hour_max == 20
        assert cfg.peak_hours == [20, 21]

    def test_clamps_min_above_total(self):
        cfg = _gen_no_llm()._parse_time_config({
            "agents_per_hour_min": 200,  # 30 보다 큼
            "agents_per_hour_max": 25,
        }, num_entities=30)
        # min 이 total 초과 → max(1, 30 // 10) = 3 으로 clamp
        assert cfg.agents_per_hour_min == 3

    def test_clamps_max_above_total(self):
        cfg = _gen_no_llm()._parse_time_config({
            "agents_per_hour_min": 2,
            "agents_per_hour_max": 100,
        }, num_entities=30)
        assert cfg.agents_per_hour_max <= 30

    def test_swaps_when_min_ge_max(self):
        cfg = _gen_no_llm()._parse_time_config({
            "agents_per_hour_min": 20,
            "agents_per_hour_max": 5,
        }, num_entities=100)
        assert cfg.agents_per_hour_min < cfg.agents_per_hour_max


# ============================================================================
# Event config / entity summary
# ============================================================================

class TestParseEventConfig:
    def test_passes_fields(self):
        cfg = _gen_no_llm()._parse_event_config({
            "initial_posts": [{"content": "p1"}],
            "hot_topics": ["topic1"],
            "narrative_direction": "direction",
        })
        assert cfg.initial_posts == [{"content": "p1"}]
        assert cfg.hot_topics == ["topic1"]
        assert cfg.narrative_direction == "direction"
        assert cfg.scheduled_events == []

    def test_handles_missing_keys(self):
        cfg = _gen_no_llm()._parse_event_config({})
        assert cfg.initial_posts == []
        assert cfg.hot_topics == []


class TestSummarizeEntities:
    def test_groups_by_type(self):
        entities = [
            _FakeEntity("u1", "Alice", "Person", summary="알리스 요약"),
            _FakeEntity("u2", "Bob", "Person", summary="밥 요약"),
            _FakeEntity("u3", "ACME", "Company", summary="회사 요약"),
        ]
        result = _gen_no_llm()._summarize_entities(entities)
        assert "### Person (2개)" in result
        assert "### Company (1개)" in result
        assert "Alice" in result
        assert "ACME" in result

    def test_unknown_type_for_unlabeled(self):
        e = _FakeEntity("u1", "X", None)
        result = _gen_no_llm()._summarize_entities([e])
        assert "Unknown" in result

    def test_truncates_when_too_many_per_type(self):
        # ENTITIES_PER_TYPE_DISPLAY = 20
        entities = [
            _FakeEntity(f"u{i}", f"E{i}", "Person") for i in range(25)
        ]
        result = _gen_no_llm()._summarize_entities(entities)
        assert "외 5개" in result


# ============================================================================
# _build_context
# ============================================================================

class TestBuildContext:
    def test_includes_requirement_and_entities(self):
        gen = _gen_no_llm()
        result = gen._build_context(
            simulation_requirement="요구사항",
            document_text="문서 내용",
            entities=[_FakeEntity("u1", "X", "Person")],
        )
        assert "요구사항" in result
        assert "문서 내용" in result
        assert "## 엔티티 정보 (1개)" in result

    def test_truncates_document_when_long(self):
        gen = _gen_no_llm()
        # entities 정보가 작으므로 doc_text 잘림 마커 확인
        long_text = "x" * (gen.MAX_CONTEXT_LENGTH + 1000)
        result = gen._build_context(
            simulation_requirement="요구",
            document_text=long_text,
            entities=[_FakeEntity("u1", "X", "Person")],
        )
        assert "...(문서가 잘렸습니다)" in result


# ============================================================================
# _assign_initial_post_agents
# ============================================================================

def _agent(agent_id, entity_type="Person", influence_weight=1.0):
    return AgentActivityConfig(
        agent_id=agent_id,
        entity_uuid=f"u{agent_id}",
        entity_name=f"name{agent_id}",
        entity_type=entity_type,
        influence_weight=influence_weight,
    )


class TestAssignInitialPostAgents:
    def test_no_initial_posts(self):
        cfg = _gen_no_llm()._assign_initial_post_agents(
            EventConfig(initial_posts=[]),
            [_agent(1, "Person")],
        )
        assert cfg.initial_posts == []

    def test_direct_type_match(self):
        ec = EventConfig(initial_posts=[
            {"content": "p1", "poster_type": "Person"},
        ])
        result = _gen_no_llm()._assign_initial_post_agents(
            ec, [_agent(1, "Person"), _agent(2, "Company")]
        )
        assert result.initial_posts[0]["poster_agent_id"] == 1

    def test_alias_match(self):
        ec = EventConfig(initial_posts=[
            {"content": "p", "poster_type": "Government"},  # → governmentagency 별칭
        ])
        result = _gen_no_llm()._assign_initial_post_agents(
            ec, [_agent(7, "GovernmentAgency")]
        )
        assert result.initial_posts[0]["poster_agent_id"] == 7

    def test_fallback_to_highest_influence(self):
        ec = EventConfig(initial_posts=[
            {"content": "p", "poster_type": "Robot"},  # 매칭 없음
        ])
        result = _gen_no_llm()._assign_initial_post_agents(
            ec, [_agent(1, "Person", 0.5), _agent(2, "Company", 5.0), _agent(3, "Org", 1.0)]
        )
        assert result.initial_posts[0]["poster_agent_id"] == 2  # 영향력 가장 높음

    def test_no_agents_fallback_to_zero(self):
        ec = EventConfig(initial_posts=[
            {"content": "p", "poster_type": "X"},
        ])
        result = _gen_no_llm()._assign_initial_post_agents(ec, [])
        assert result.initial_posts[0]["poster_agent_id"] == 0

    def test_round_robin_within_type(self):
        ec = EventConfig(initial_posts=[
            {"content": "p1", "poster_type": "Student"},
            {"content": "p2", "poster_type": "Student"},
            {"content": "p3", "poster_type": "Student"},
        ])
        agents = [_agent(1, "Student"), _agent(2, "Student")]
        result = _gen_no_llm()._assign_initial_post_agents(ec, agents)
        ids = [p["poster_agent_id"] for p in result.initial_posts]
        # 3개 게시물에 대해 [1, 2, 1] 라운드 로빈
        assert ids == [1, 2, 1]


# ============================================================================
# _generate_agent_config_by_rule
# ============================================================================

class TestGenerateAgentConfigByRule:
    def test_university_low_activity_high_influence(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "S대", "University")
        )
        assert cfg["activity_level"] == 0.2
        assert cfg["influence_weight"] == 3.0
        assert cfg["active_hours"] == list(range(9, 18))

    def test_media_outlet(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "Daily News", "MediaOutlet")
        )
        assert cfg["influence_weight"] == 2.5
        assert cfg["stance"] == "observer"
        assert cfg["active_hours"] == list(range(7, 24))

    def test_professor(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "Prof", "Professor")
        )
        assert cfg["influence_weight"] == 2.0

    def test_student(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "S", "Student")
        )
        assert cfg["activity_level"] == 0.8
        assert 23 in cfg["active_hours"]

    def test_alumni(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "A", "Alumni")
        )
        assert cfg["activity_level"] == 0.6

    def test_default_general_person(self):
        cfg = _gen_no_llm()._generate_agent_config_by_rule(
            _FakeEntity("u", "X", "RandomType")
        )
        assert cfg["activity_level"] == 0.7
        assert cfg["sentiment_bias"] == 0.0


# ============================================================================
# _call_llm_with_retry — LLM 모킹
# ============================================================================

class TestCallLLMWithRetry:
    def test_returns_parsed_json_on_first_attempt(self, monkeypatch):
        gen = _gen_no_llm()

        def _chat(**kw):
            return '{"foo": 1}'

        gen.llm_client.chat = _chat
        result = gen._call_llm_with_retry("p", "s")
        assert result == {"foo": 1}

    def test_recovers_via_try_fix(self, monkeypatch):
        gen = _gen_no_llm()
        # 처음에는 망가진 JSON, 그러나 _try_fix_config_json 으로 추출 가능
        gen.llm_client.chat = lambda **kw: 'prefix {"foo": 2} suffix'
        result = gen._call_llm_with_retry("p", "s")
        assert result == {"foo": 2}

    def test_raises_after_max_attempts(self, monkeypatch):
        gen = _gen_no_llm()
        gen.llm_client.chat = lambda **kw: "completely broken"
        # time.sleep 차단
        monkeypatch.setattr("time.sleep", lambda _: None)
        with pytest.raises(Exception):
            gen._call_llm_with_retry("p", "s")


# ============================================================================
# _generate_time_config — 실패 시 default fallback
# ============================================================================

class TestGenerateTimeConfig:
    def test_default_on_llm_failure(self, monkeypatch):
        gen = _gen_no_llm()

        def _boom(prompt, system_prompt):
            raise RuntimeError("LLM unreachable")

        monkeypatch.setattr(gen, "_call_llm_with_retry", _boom)
        result = gen._generate_time_config(context="ctx", num_entities=20)
        assert result["total_simulation_hours"] == 72
        assert "기본 한국인 생활 리듬" in result["reasoning"]

    def test_passes_through_llm_result(self, monkeypatch):
        gen = _gen_no_llm()
        monkeypatch.setattr(
            gen, "_call_llm_with_retry",
            lambda p, s: {"total_simulation_hours": 24, "reasoning": "짧음"},
        )
        result = gen._generate_time_config(context="ctx", num_entities=20)
        assert result["total_simulation_hours"] == 24


# ============================================================================
# generate_config — end-to-end (모든 LLM 모킹)
# ============================================================================

class TestGenerateConfig:
    def test_full_flow(self, monkeypatch):
        gen = _gen_no_llm()

        # LLM 호출은 모두 차단 → 각 단계가 default/rule 경로로 흐름
        monkeypatch.setattr(
            gen, "_call_llm_with_retry",
            lambda p, s: (_ for _ in ()).throw(RuntimeError("no LLM")),
        )

        entities = [
            _FakeEntity(f"u{i}", f"E{i}", "Person") for i in range(5)
        ]

        progress_log = []

        def _progress(step, total, msg):
            progress_log.append((step, total))

        params = gen.generate_config(
            simulation_id="s1",
            project_id="p1",
            graph_id="g1",
            simulation_requirement="여론 시뮬",
            document_text="문서",
            entities=entities,
            enable_twitter=True,
            enable_reddit=True,
            progress_callback=_progress,
        )

        assert isinstance(params, SimulationParameters)
        assert params.simulation_id == "s1"
        # 5 entities → 1 batch (15 / batch)
        assert len(params.agent_configs) == 5
        assert params.twitter_config is not None
        assert params.reddit_config is not None
        assert params.twitter_config.platform == "twitter"
        # 진행 콜백이 적어도 4번 (시간/이벤트/agent batch/플랫폼)
        assert len(progress_log) >= 4
        # generation_reasoning 에 단계별 메시지 포함
        assert "Agent 설정" in params.generation_reasoning

    def test_disable_twitter(self, monkeypatch):
        gen = _gen_no_llm()
        monkeypatch.setattr(
            gen, "_call_llm_with_retry",
            lambda p, s: (_ for _ in ()).throw(RuntimeError("no LLM")),
        )
        params = gen.generate_config(
            simulation_id="s1", project_id="p", graph_id="g",
            simulation_requirement="x", document_text="d",
            entities=[_FakeEntity("u", "E", "Person")],
            enable_twitter=False, enable_reddit=True,
        )
        assert params.twitter_config is None
        assert params.reddit_config is not None
