"""
SimulationManager 단위 테스트 (`app/services/simulation_manager.py`).

검증 단위:
- `_atomic_write_json`: 성공/실패 (예외는 logger 로 흡수)
- SimulationState: to_dict / to_simple_dict
- SimulationManager:
  - 상태 저장/로드 (메모리 캐시 + 파일)
  - create_simulation (sim_ prefix, persist)
  - get_simulation, list_simulations (필터/숨김 파일 스킵)
  - get_profiles (파일 없음 → [], 파일 있음 → 로드)
  - get_simulation_config (파일 없음 → None)
  - get_run_instructions (경로 + commands dict)
  - prepare_simulation: 시뮬레이션 없음 / 엔티티 0개 / happy path

class-level SIMULATION_DATA_DIR 은 monkeypatch 로 tmp_path 격리.
"""

import json
import os

import pytest

from app.services import simulation_manager as sm_mod
from app.services.simulation_manager import (
    PlatformType,
    SimulationManager,
    SimulationState,
    SimulationStatus,
    _atomic_write_json,
)


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch):
    """SIMULATION_DATA_DIR 을 tmp_path 로 리다이렉트한 매니저."""
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    return SimulationManager()


# ============================================================================
# _atomic_write_json
# ============================================================================

class TestAtomicWriteJSON:
    def test_writes_correctly(self, tmp_path):
        target = tmp_path / "out.json"
        _atomic_write_json(str(target), {"k": "v", "kr": "한글"})
        assert target.exists()
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == {"k": "v", "kr": "한글"}

    def test_no_tmp_files_left(self, tmp_path):
        target = tmp_path / "out.json"
        _atomic_write_json(str(target), {"a": 1})
        leftover = [p.name for p in tmp_path.iterdir() if p.name != "out.json"]
        assert leftover == []

    def test_outer_exception_swallowed_and_logged(self, tmp_path, monkeypatch, caplog):
        """대상 디렉토리가 없으면 mkstemp 가 FileNotFoundError → outer except 가 흡수."""
        target = tmp_path / "missing_dir" / "out.json"
        # outer try 에서 잡고 logger.error → 호출은 정상 리턴
        _atomic_write_json(str(target), {"a": 1})
        assert not target.exists()


# ============================================================================
# SimulationState dataclass
# ============================================================================

class TestSimulationState:
    def test_to_dict_includes_all(self):
        s = SimulationState(
            simulation_id="sim_1",
            project_id="p1",
            graph_id="g1",
            simulation_requirement="시나리오 X",
            status=SimulationStatus.READY,
            entities_count=10,
            entity_types=["Person", "Org"],
        )
        d = s.to_dict()
        assert d["simulation_id"] == "sim_1"
        assert d["status"] == "ready"
        assert d["entities_count"] == 10
        assert d["entity_types"] == ["Person", "Org"]
        assert d["simulation_requirement"] == "시나리오 X"
        assert "created_at" in d and "updated_at" in d

    def test_to_simple_dict_is_subset(self):
        s = SimulationState(
            simulation_id="sim_2", project_id="p", graph_id="g",
            entities_count=5, profiles_count=4, error="oops",
        )
        d = s.to_simple_dict()
        assert set(d.keys()) == {
            "simulation_id", "project_id", "graph_id", "status",
            "entities_count", "profiles_count", "entity_types",
            "config_generated", "error",
        }
        assert d["error"] == "oops"

    def test_status_enum_value_in_dict(self):
        s = SimulationState(
            simulation_id="s", project_id="p", graph_id="g",
            status=SimulationStatus.RUNNING,
        )
        assert s.to_dict()["status"] == "running"


class TestEnums:
    def test_simulation_status_values(self):
        assert SimulationStatus.READY.value == "ready"
        assert SimulationStatus.RUNNING.value == "running"
        assert SimulationStatus.FAILED.value == "failed"

    def test_platform_type_values(self):
        assert PlatformType.TWITTER.value == "twitter"
        assert PlatformType.REDDIT.value == "reddit"


# ============================================================================
# SimulationManager — 기본 라이프사이클
# ============================================================================

class TestManagerInit:
    def test_creates_data_dir(self, tmp_path, monkeypatch):
        target = tmp_path / "new_dir"
        monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(target))
        SimulationManager()
        assert target.is_dir()

    def test_starts_with_empty_cache(self, isolated_manager):
        assert isolated_manager._simulations == {}


class TestCacheLRU:
    def test_save_then_load_via_cache(self, isolated_manager):
        # 별도 alias — 다른 라우트에서 cache hit 검증
        s = SimulationState(simulation_id="sim_lru0", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s)
        assert "sim_lru0" in isolated_manager._simulations

    def test_evicts_oldest_when_over_max(self, isolated_manager, monkeypatch):
        """캐시 한도를 넘으면 가장 오래 사용 안 된 항목을 축출."""
        # 작은 한도로 쉽게 트리거
        monkeypatch.setattr(SimulationManager, "MAX_CACHE_SIZE", 3)
        for i in range(5):
            s = SimulationState(simulation_id=f"sim_{i}", project_id="p", graph_id="g")
            isolated_manager._save_simulation_state(s)
        # 캐시는 3개만 유지 — 가장 최근 sim_2/sim_3/sim_4
        assert len(isolated_manager._simulations) == 3
        assert "sim_0" not in isolated_manager._simulations
        assert "sim_1" not in isolated_manager._simulations
        assert {"sim_2", "sim_3", "sim_4"} == set(isolated_manager._simulations.keys())

    def test_get_promotes_to_most_recent(self, isolated_manager, monkeypatch):
        """캐시 히트 시 LRU 갱신 — 다음 축출 대상에서 제외."""
        monkeypatch.setattr(SimulationManager, "MAX_CACHE_SIZE", 3)
        for i in range(3):
            s = SimulationState(simulation_id=f"sim_{i}", project_id="p", graph_id="g")
            isolated_manager._save_simulation_state(s)
        # sim_0 을 다시 읽어 LRU 의 최신으로 승격
        isolated_manager.get_simulation("sim_0")
        # 새 항목 추가 → sim_1 이 가장 오래된 항목으로 축출
        s_new = SimulationState(simulation_id="sim_new", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s_new)
        assert "sim_0" in isolated_manager._simulations
        assert "sim_1" not in isolated_manager._simulations
        assert "sim_new" in isolated_manager._simulations

    def test_disk_persisted_after_eviction(self, isolated_manager, monkeypatch, tmp_path):
        """축출 후에도 파일이 살아있어 다음 조회 시 디스크에서 복원."""
        monkeypatch.setattr(SimulationManager, "MAX_CACHE_SIZE", 1)
        s_a = SimulationState(simulation_id="sim_A", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s_a)
        s_b = SimulationState(simulation_id="sim_B", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s_b)
        # sim_A 는 캐시에서 축출됐지만 디스크에 있음
        assert "sim_A" not in isolated_manager._simulations
        assert (tmp_path / "sim_A" / "state.json").exists()
        # 다시 조회 → 디스크에서 복원
        loaded = isolated_manager.get_simulation("sim_A")
        assert loaded is not None
        assert loaded.project_id == "p"


class TestSaveLoadState:
    def test_save_then_load_via_cache(self, isolated_manager):
        s = SimulationState(simulation_id="sim_x", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s)
        # cache hit
        assert isolated_manager._load_simulation_state("sim_x") is s

    def test_save_writes_state_file(self, isolated_manager, tmp_path):
        s = SimulationState(simulation_id="sim_y", project_id="p", graph_id="g")
        isolated_manager._save_simulation_state(s)
        state_file = tmp_path / "sim_y" / "state.json"
        assert state_file.exists()
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["simulation_id"] == "sim_y"

    def test_save_updates_updated_at(self, isolated_manager):
        s = SimulationState(simulation_id="sim_z", project_id="p", graph_id="g")
        original_updated_at = s.updated_at
        # 같은 마이크로초로 떨어질 수 있으므로 차이를 강제
        s.updated_at = "2020-01-01T00:00:00"
        isolated_manager._save_simulation_state(s)
        assert s.updated_at != "2020-01-01T00:00:00"

    def test_load_from_disk_when_not_cached(self, isolated_manager, tmp_path):
        # 파일을 직접 작성한 뒤 캐시 미스로 로드되는지
        sim_id = "sim_disk"
        sim_dir = tmp_path / sim_id
        sim_dir.mkdir()
        with open(sim_dir / "state.json", "w", encoding="utf-8") as f:
            json.dump({
                "simulation_id": sim_id,
                "project_id": "p_disk",
                "graph_id": "g_disk",
                "status": "ready",
                "entities_count": 7,
                "entity_types": ["A"],
            }, f)
        loaded = isolated_manager._load_simulation_state(sim_id)
        assert loaded is not None
        assert loaded.project_id == "p_disk"
        assert loaded.status == SimulationStatus.READY
        assert loaded.entities_count == 7
        # 캐시에 저장됨
        assert sim_id in isolated_manager._simulations

    def test_load_missing_returns_none(self, isolated_manager):
        assert isolated_manager._load_simulation_state("ghost") is None


class TestCreateSimulation:
    def test_returns_state_with_prefix(self, isolated_manager):
        state = isolated_manager.create_simulation(
            project_id="p1", graph_id="g1",
        )
        assert state.simulation_id.startswith("sim_")
        assert state.project_id == "p1"
        assert state.graph_id == "g1"
        assert state.status == SimulationStatus.CREATED
        assert state.enable_twitter is True
        assert state.enable_reddit is True

    def test_persists_to_disk(self, isolated_manager, tmp_path):
        state = isolated_manager.create_simulation("p2", "g2")
        state_file = tmp_path / state.simulation_id / "state.json"
        assert state_file.exists()

    def test_disable_twitter_only(self, isolated_manager):
        state = isolated_manager.create_simulation(
            "p", "g", enable_twitter=False, enable_reddit=True,
        )
        assert state.enable_twitter is False
        assert state.enable_reddit is True

    def test_simulation_requirement_override(self, isolated_manager):
        state = isolated_manager.create_simulation(
            "p", "g", simulation_requirement="시나리오 B",
        )
        assert state.simulation_requirement == "시나리오 B"


class TestGetSimulation:
    def test_passthrough_to_load(self, isolated_manager):
        state = isolated_manager.create_simulation("p", "g")
        result = isolated_manager.get_simulation(state.simulation_id)
        assert result is state

    def test_unknown_returns_none(self, isolated_manager):
        assert isolated_manager.get_simulation("no_such") is None


class TestListSimulations:
    def test_empty(self, isolated_manager):
        assert isolated_manager.list_simulations() == []

    def test_returns_all(self, isolated_manager):
        isolated_manager.create_simulation("p1", "g1")
        isolated_manager.create_simulation("p2", "g2")
        result = isolated_manager.list_simulations()
        assert len(result) == 2

    def test_filter_by_project(self, isolated_manager):
        isolated_manager.create_simulation("p1", "g1")
        isolated_manager.create_simulation("p2", "g2")
        only_p1 = isolated_manager.list_simulations(project_id="p1")
        assert len(only_p1) == 1
        assert only_p1[0].project_id == "p1"

    def test_skips_hidden_files(self, isolated_manager, tmp_path):
        # .DS_Store 같은 숨김 파일/디렉토리는 무시
        (tmp_path / ".DS_Store").write_text("ignore me")
        (tmp_path / ".hidden_dir").mkdir()
        isolated_manager.create_simulation("p", "g")
        result = isolated_manager.list_simulations()
        assert len(result) == 1

    def test_skips_non_directories(self, isolated_manager, tmp_path):
        # 디렉토리가 아닌 일반 파일은 무시
        (tmp_path / "stray_file.json").write_text("{}")
        isolated_manager.create_simulation("p", "g")
        result = isolated_manager.list_simulations()
        assert len(result) == 1


class TestGetProfiles:
    def test_simulation_not_found_raises(self, isolated_manager):
        with pytest.raises(ValueError, match="존재하지 않음"):
            isolated_manager.get_profiles("ghost")

    def test_no_file_returns_empty(self, isolated_manager):
        state = isolated_manager.create_simulation("p", "g")
        assert isolated_manager.get_profiles(state.simulation_id) == []

    def test_returns_profiles_from_file(self, isolated_manager, tmp_path):
        state = isolated_manager.create_simulation("p", "g")
        profiles = [{"agent_id": 1, "name": "Alice"}]
        with open(tmp_path / state.simulation_id / "reddit_profiles.json", "w") as f:
            json.dump(profiles, f)
        assert isolated_manager.get_profiles(state.simulation_id) == profiles

    def test_platform_param_changes_filename(self, isolated_manager, tmp_path):
        state = isolated_manager.create_simulation("p", "g")
        # twitter platform 은 _profiles.json 파일을 찾지만 OASIS twitter 는 CSV 라
        # 메서드는 항상 .json 만 본다. 별도 파일이 없으면 [] 반환.
        # 같은 sim 에 twitter_profiles.json 을 떨궈도 platform=twitter 로 읽어진다.
        twitter_data = [{"id": 99}]
        with open(
            tmp_path / state.simulation_id / "twitter_profiles.json", "w"
        ) as f:
            json.dump(twitter_data, f)
        assert isolated_manager.get_profiles(
            state.simulation_id, platform="twitter"
        ) == twitter_data


class TestGetSimulationConfig:
    def test_no_file_returns_none(self, isolated_manager):
        state = isolated_manager.create_simulation("p", "g")
        assert isolated_manager.get_simulation_config(state.simulation_id) is None

    def test_returns_config(self, isolated_manager, tmp_path):
        state = isolated_manager.create_simulation("p", "g")
        cfg = {"max_rounds": 5, "agents": 10}
        with open(
            tmp_path / state.simulation_id / "simulation_config.json", "w"
        ) as f:
            json.dump(cfg, f)
        assert isolated_manager.get_simulation_config(state.simulation_id) == cfg


class TestGetRunInstructions:
    def test_returns_paths_and_commands(self, isolated_manager):
        state = isolated_manager.create_simulation("p", "g")
        info = isolated_manager.get_run_instructions(state.simulation_id)
        assert "simulation_dir" in info
        assert state.simulation_id in info["simulation_dir"]
        assert "scripts_dir" in info
        assert "config_file" in info
        assert info["config_file"].endswith("simulation_config.json")
        assert set(info["commands"].keys()) == {"twitter", "reddit", "parallel"}
        for cmd in info["commands"].values():
            assert "python" in cmd
            assert "--config" in cmd


# ============================================================================
# prepare_simulation
# ============================================================================

class _FakeFiltered:
    def __init__(self, count=3, types=None, entities=None):
        self.filtered_count = count
        self.entity_types = set(types or ["Person"])
        self.entities = entities or [{"name": f"e{i}"} for i in range(count)]


class TestPrepareSimulation:
    def test_simulation_not_found(self, isolated_manager):
        with pytest.raises(ValueError, match="존재하지 않음"):
            isolated_manager.prepare_simulation(
                "ghost",
                simulation_requirement="x",
                document_text="doc",
            )

    def test_zero_entities_marks_failed(
        self, isolated_manager, monkeypatch
    ):
        state = isolated_manager.create_simulation("p", "g")

        class _Reader:
            def filter_defined_entities(self, **kw):
                return _FakeFiltered(count=0, types=set(), entities=[])

        monkeypatch.setattr(sm_mod, "GraphitiEntityReader", _Reader)
        result = isolated_manager.prepare_simulation(
            state.simulation_id,
            simulation_requirement="요구",
            document_text="문서",
        )
        assert result.status == SimulationStatus.FAILED
        assert result.error is not None
        assert "엔티티" in result.error

    def test_happy_path_marks_ready_and_persists(
        self, isolated_manager, tmp_path, monkeypatch
    ):
        state = isolated_manager.create_simulation("p", "g")

        class _Reader:
            def filter_defined_entities(self, **kw):
                return _FakeFiltered(count=2, types=["Person"])

        monkeypatch.setattr(sm_mod, "GraphitiEntityReader", _Reader)

        save_calls = []

        class _ProfileGen:
            def __init__(self, **kw):
                pass
            def generate_profiles_from_entities(self, **kw):
                return [{"agent_id": 1}, {"agent_id": 2}]
            def save_profiles(self, profiles, file_path, platform):
                save_calls.append((file_path, platform))
                # 실제 파일도 떨궈서 후속 검증 가능
                with open(file_path, "w") as f:
                    json.dump(profiles, f)

        monkeypatch.setattr(sm_mod, "OasisProfileGenerator", _ProfileGen)

        class _ConfigGen:
            def generate_config(self, **kw):
                class _P:
                    generation_reasoning = "테스트 설정"
                    def to_json(self):
                        return json.dumps({"max_rounds": 3})
                return _P()

        monkeypatch.setattr(sm_mod, "SimulationConfigGenerator", _ConfigGen)

        progress_log = []

        def _progress(stage, pct, msg, **kw):
            progress_log.append((stage, pct))

        result = isolated_manager.prepare_simulation(
            state.simulation_id,
            simulation_requirement="요구",
            document_text="문서",
            progress_callback=_progress,
        )
        assert result.status == SimulationStatus.READY
        assert result.entities_count == 2
        assert result.profiles_count == 2
        assert result.config_generated is True
        assert result.config_reasoning == "테스트 설정"
        # save_profiles 는 reddit + twitter 두 번
        platforms = {p for _, p in save_calls}
        assert "reddit" in platforms
        assert "twitter" in platforms
        # config 파일 작성됨
        cfg_file = tmp_path / state.simulation_id / "simulation_config.json"
        assert cfg_file.exists()
        # progress 콜백 호출됨
        stages = {s for s, _ in progress_log}
        assert "reading" in stages
        assert "generating_profiles" in stages
        assert "generating_config" in stages
