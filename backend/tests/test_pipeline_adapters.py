"""
Pipeline adapters 단위 테스트 (`app/services/pipeline_adapters.py`).

4 adapter:
- graph_adapter: TextProcessor → OntologyGenerator → GraphBuilderService.build_graph_async
                 + TaskManager 폴링. 빈 seed_dir / 폴링 완료 / 폴링 실패 / 캐시 재사용 검증.
- agents_adapter: pass-through (graph_meta.json 읽고 agents_meta.json 작성).
- simulation_adapter: SimulationManager.create→prepare + SimulationRunner.start→poll.
- report_adapter: ReportAgent.generate_report.

폴링 루프의 time.sleep 은 monkeypatch 로 NO-OP — 인라인 실행.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import pipeline_adapters as pa
from app.services.pipeline_orchestrator import StepContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    tmp_path: Path,
    *,
    seed_files=None,
    prev_meta=None,
    prev_meta_filename=None,
    config=None,
    run_id="run_12345678abcd",
    step_name="graph",
    assumptions_version="v1",
) -> StepContext:
    """StepContext + tmp 디렉토리 구조 셋업."""
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    for fname, content in (seed_files or []):
        (seed_dir / fname).write_text(content, encoding="utf-8")

    tmp_dir = tmp_path / "step_tmp"
    prev_step_dir = None
    if prev_meta is not None:
        prev_step_dir = tmp_path / "prev"
        prev_step_dir.mkdir()
        (prev_step_dir / prev_meta_filename).write_text(
            json.dumps(prev_meta), encoding="utf-8"
        )

    return StepContext(
        run_id=run_id,
        step_name=step_name,
        zep_group_id="zep_g",
        seed_dir=seed_dir,
        tmp_dir=tmp_dir,
        prev_step_dir=prev_step_dir,
        assumptions_version=assumptions_version,
        config=config or {},
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """폴링 루프 가속 — time.sleep no-op."""
    monkeypatch.setattr(pa.time, "sleep", lambda _s: None)


# ============================================================================
# graph_adapter
# ============================================================================

class TestGraphAdapter:
    def test_empty_seed_dir_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)  # seed_dir 비어있음
        with pytest.raises(RuntimeError, match="seed_dir에 파일 없음"):
            pa.graph_adapter(ctx)

    def test_happy_path(self, tmp_path, monkeypatch):
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "content a")])

        monkeypatch.setattr(
            pa.TextProcessor, "extract_from_files",
            staticmethod(lambda paths: "원문 텍스트")
        )
        monkeypatch.setattr(
            pa.TextProcessor, "preprocess_text",
            staticmethod(lambda t: t)
        )
        monkeypatch.setattr(
            pa.TextProcessor, "get_text_stats",
            staticmethod(lambda t: {"total_chars": len(t)})
        )

        ontology_gen_calls = []

        class _OG:
            def generate(self, **kw):
                ontology_gen_calls.append(kw)
                return {
                    "entity_types": [{"name": "Person"}, {"name": "Org"}],
                    "edge_types": [{"name": "knows"}],
                }

        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        builder_args = {}

        class _Builder:
            def build_graph_async(self, **kw):
                builder_args.update(kw)
                return "task_g"

        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        # TaskManager: PROCESSING → COMPLETED
        states = iter([
            SimpleNamespace(progress=10, message="...", status=pa.TaskStatus.PROCESSING, error=None, result=None),
            SimpleNamespace(
                progress=100, message="done", status=pa.TaskStatus.COMPLETED,
                error=None,
                result={"graph_id": "mirofish_xyz", "graph_info": {"node_count": 5}, "chunks_processed": 3},
            ),
        ])

        class _TM:
            def get_task(self, _):
                return next(states)

        monkeypatch.setattr(pa, "TaskManager", _TM)

        meta = pa.graph_adapter(ctx)
        assert meta["graph_id"] == "mirofish_xyz"
        assert meta["chunks_processed"] == 3
        assert meta["entity_types_defined"] == 2
        assert meta["edge_types_defined"] == 1
        # graph_meta.json 작성
        assert (ctx.tmp_dir / "graph_meta.json").exists()
        # ontology.json 캐시
        assert (ctx.tmp_dir / "ontology.json").exists()
        # OntologyGenerator 호출됨
        assert len(ontology_gen_calls) == 1
        # builder 인자
        assert builder_args["existing_graph_id"] is None
        assert builder_args["skip_chunk_indices"] == []

    def test_ontology_cache_reused(self, tmp_path, monkeypatch):
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "x")])
        # 미리 캐시 작성
        ctx.tmp_dir.mkdir(parents=True)
        cached = {"entity_types": [{"name": "Cached"}], "edge_types": []}
        (ctx.tmp_dir / "ontology.json").write_text(
            json.dumps(cached), encoding="utf-8"
        )

        monkeypatch.setattr(
            pa.TextProcessor, "extract_from_files",
            staticmethod(lambda paths: "txt"),
        )
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))
        monkeypatch.setattr(pa.TextProcessor, "get_text_stats", staticmethod(lambda t: {}))

        called = []

        class _OG:
            def generate(self, **kw):
                called.append(1)
                raise AssertionError("OntologyGenerator 호출되면 안 됨")

        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        class _Builder:
            def build_graph_async(self, **kw):
                return "t1"

        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        class _TM:
            def get_task(self, _):
                return SimpleNamespace(
                    progress=100, message="ok",
                    status=pa.TaskStatus.COMPLETED,
                    error=None,
                    result={"graph_id": "g1"},
                )

        monkeypatch.setattr(pa, "TaskManager", _TM)
        pa.graph_adapter(ctx)
        assert called == []  # cached 재사용

    def test_graph_progress_resume(self, tmp_path, monkeypatch):
        """이전 retry 의 graph_progress.json 이 있으면 existing_graph_id + skip 전달."""
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "x")])
        ctx.tmp_dir.mkdir(parents=True)
        (ctx.tmp_dir / "graph_progress.json").write_text(
            json.dumps({"graph_id": "g_existing", "chunks_processed": [0, 1]}),
            encoding="utf-8",
        )

        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))
        monkeypatch.setattr(pa.TextProcessor, "get_text_stats", staticmethod(lambda t: {}))

        class _OG:
            def generate(self, **kw):
                return {"entity_types": [], "edge_types": []}
        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        builder_args = {}

        class _Builder:
            def build_graph_async(self, **kw):
                builder_args.update(kw)
                return "t1"

        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        class _TM:
            def get_task(self, _):
                return SimpleNamespace(
                    progress=100, message="ok",
                    status=pa.TaskStatus.COMPLETED,
                    error=None,
                    result={"graph_id": "g_existing"},
                )

        monkeypatch.setattr(pa, "TaskManager", _TM)
        pa.graph_adapter(ctx)
        assert builder_args["existing_graph_id"] == "g_existing"
        assert builder_args["skip_chunk_indices"] == [0, 1]

    def test_task_disappears(self, tmp_path, monkeypatch):
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "x")])
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))
        monkeypatch.setattr(pa.TextProcessor, "get_text_stats", staticmethod(lambda t: {}))

        class _OG:
            def generate(self, **kw):
                return {"entity_types": [], "edge_types": []}
        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        class _Builder:
            def build_graph_async(self, **kw):
                return "t_lost"
        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        class _TM:
            def get_task(self, _):
                return None  # 사라짐
        monkeypatch.setattr(pa, "TaskManager", _TM)

        with pytest.raises(RuntimeError, match="사라짐"):
            pa.graph_adapter(ctx)

    def test_task_failed(self, tmp_path, monkeypatch):
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "x")])
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))
        monkeypatch.setattr(pa.TextProcessor, "get_text_stats", staticmethod(lambda t: {}))

        class _OG:
            def generate(self, **kw):
                return {"entity_types": [], "edge_types": []}
        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        class _Builder:
            def build_graph_async(self, **kw):
                return "t1"
        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        class _TM:
            def get_task(self, _):
                return SimpleNamespace(
                    progress=50, message="...",
                    status=pa.TaskStatus.FAILED,
                    error="LLM rate limit",
                    result=None,
                )
        monkeypatch.setattr(pa, "TaskManager", _TM)

        with pytest.raises(RuntimeError, match="LLM rate limit"):
            pa.graph_adapter(ctx)

    def test_completed_but_no_graph_id(self, tmp_path, monkeypatch):
        ctx = _make_ctx(tmp_path, seed_files=[("a.txt", "x")])
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))
        monkeypatch.setattr(pa.TextProcessor, "get_text_stats", staticmethod(lambda t: {}))

        class _OG:
            def generate(self, **kw):
                return {"entity_types": [], "edge_types": []}
        monkeypatch.setattr(pa, "OntologyGenerator", _OG)

        class _Builder:
            def build_graph_async(self, **kw):
                return "t1"
        monkeypatch.setattr(pa, "GraphBuilderService", _Builder)

        class _TM:
            def get_task(self, _):
                return SimpleNamespace(
                    progress=100, message="ok",
                    status=pa.TaskStatus.COMPLETED,
                    error=None,
                    result={},  # graph_id 누락
                )
        monkeypatch.setattr(pa, "TaskManager", _TM)
        with pytest.raises(RuntimeError, match="graph_id 누락"):
            pa.graph_adapter(ctx)


# ============================================================================
# agents_adapter
# ============================================================================

class TestAgentsAdapter:
    def test_no_prev_step_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(RuntimeError, match="prev_step_dir 없음"):
            pa.agents_adapter(ctx)

    def test_missing_graph_meta(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        prev = tmp_path / "prev"
        prev.mkdir()
        ctx = StepContext(
            run_id="r", step_name="agents", zep_group_id="z",
            seed_dir=ctx.seed_dir, tmp_dir=tmp_path / "out",
            prev_step_dir=prev, assumptions_version="v1", config={},
        )
        with pytest.raises(RuntimeError, match="graph_meta.json 없음"):
            pa.agents_adapter(ctx)

    def test_missing_graph_id(self, tmp_path):
        ctx = _make_ctx(
            tmp_path,
            prev_meta={"other": "data"},
            prev_meta_filename="graph_meta.json",
            step_name="agents",
        )
        with pytest.raises(RuntimeError, match="graph_id 누락"):
            pa.agents_adapter(ctx)

    def test_happy_path(self, tmp_path):
        ctx = _make_ctx(
            tmp_path,
            prev_meta={"graph_id": "g_xyz", "extra": "ignored"},
            prev_meta_filename="graph_meta.json",
            step_name="agents",
        )
        meta = pa.agents_adapter(ctx)
        assert meta["graph_id"] == "g_xyz"
        assert meta["pass_through"] is True
        # 파일 작성
        out = ctx.tmp_dir / "agents_meta.json"
        assert out.exists()
        assert json.loads(out.read_text())["graph_id"] == "g_xyz"


# ============================================================================
# simulation_adapter
# ============================================================================

class TestSimulationAdapter:
    def test_no_prev_step_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path, step_name="simulation")
        with pytest.raises(RuntimeError, match="prev_step_dir 없음"):
            pa.simulation_adapter(ctx)

    def test_missing_graph_id(self, tmp_path):
        ctx = _make_ctx(
            tmp_path,
            seed_files=[("a.txt", "x")],
            prev_meta={"other": "x"},
            prev_meta_filename="agents_meta.json",
            step_name="simulation",
        )
        with pytest.raises(RuntimeError, match="graph_id 누락"):
            pa.simulation_adapter(ctx)

    def test_happy_path(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            seed_files=[("a.txt", "doc")],
            prev_meta={"graph_id": "g1"},
            prev_meta_filename="agents_meta.json",
            step_name="simulation",
            config={
                "simulation_requirement": "기본 요구",
                "assumptions_text": "assumptions body",
                "enable_twitter": True,
                "enable_reddit": True,
                "parallel_profile_count": 5,
                "simulation_max_rounds": 4,
            },
        )

        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "doc"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))

        captured = {}

        class _SM:
            def create_simulation(self, project_id, graph_id, enable_twitter, enable_reddit):
                captured["create"] = dict(
                    project_id=project_id, graph_id=graph_id,
                    enable_twitter=enable_twitter, enable_reddit=enable_reddit,
                )
                return SimpleNamespace(simulation_id="sim_xyz")
            def prepare_simulation(self, **kw):
                captured["prepare"] = kw

        monkeypatch.setattr(pa, "SimulationManager", _SM)

        # SimulationRunner: start_simulation no-op + 폴링은 한 번에 COMPLETED
        runner_calls = []
        states = iter([
            SimpleNamespace(
                runner_status=pa.RunnerStatus.RUNNING,
                current_round=1, total_rounds=4,
                twitter_actions_count=0, reddit_actions_count=0,
                error=None, completed_at=None,
            ),
            SimpleNamespace(
                runner_status=pa.RunnerStatus.COMPLETED,
                current_round=4, total_rounds=4,
                twitter_actions_count=20, reddit_actions_count=15,
                error=None, completed_at="2026-05-01T00:00:00",
            ),
        ])

        class _Runner:
            @staticmethod
            def start_simulation(**kw):
                runner_calls.append(kw)
            @staticmethod
            def get_run_state(_):
                return next(states)
            @staticmethod
            def stop_simulation(_):
                runner_calls.append({"stopped": True})

        monkeypatch.setattr(pa, "SimulationRunner", _Runner)

        # final get_run_state — completed_at 만 사용. 다음 호출은 재공급 필요.
        # 위 iter 는 2번 사용 가능. 종료 후 final_state 한 번 더 부르므로 추가.
        # 패치를 다시 — 마지막에 한 번 더 COMPLETED 반환
        states_full = [
            SimpleNamespace(
                runner_status=pa.RunnerStatus.RUNNING,
                current_round=1, total_rounds=4,
                twitter_actions_count=0, reddit_actions_count=0,
                error=None, completed_at=None,
            ),
            SimpleNamespace(
                runner_status=pa.RunnerStatus.COMPLETED,
                current_round=4, total_rounds=4,
                twitter_actions_count=20, reddit_actions_count=15,
                error=None, completed_at="2026-05-01T00:00:00",
            ),
            SimpleNamespace(
                runner_status=pa.RunnerStatus.COMPLETED,
                current_round=4, total_rounds=4,
                twitter_actions_count=20, reddit_actions_count=15,
                error=None, completed_at="2026-05-01T00:00:00",
            ),
        ]
        states_iter = iter(states_full)

        class _Runner2:
            @staticmethod
            def start_simulation(**kw):
                runner_calls.append(kw)
            @staticmethod
            def get_run_state(_):
                return next(states_iter)
            @staticmethod
            def stop_simulation(_):
                runner_calls.append({"stopped": True})

        monkeypatch.setattr(pa, "SimulationRunner", _Runner2)

        meta = pa.simulation_adapter(ctx)

        assert meta["graph_id"] == "g1"
        assert meta["simulation_id"] == "sim_xyz"
        assert meta["platform"] == "parallel"
        assert meta["total_rounds"] == 4
        assert meta["twitter_actions_count"] == 20
        assert meta["reddit_actions_count"] == 15
        # simulation_requirement 에 assumptions 가 임베드됨
        assert "assumptions body" in meta["simulation_requirement"]
        assert "Assumptions (vv1)" in meta["simulation_requirement"]
        # create 인자
        assert captured["create"]["graph_id"] == "g1"
        assert captured["create"]["enable_twitter"] is True
        # prepare 인자
        assert captured["prepare"]["parallel_profile_count"] == 5
        # start 호출
        assert runner_calls[0]["platform"] == "parallel"
        assert runner_calls[0]["max_rounds"] == 4

    def test_run_state_disappears(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            seed_files=[("a.txt", "x")],
            prev_meta={"graph_id": "g1"},
            prev_meta_filename="agents_meta.json",
            step_name="simulation",
        )
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))

        class _SM:
            def create_simulation(self, **kw):
                return SimpleNamespace(simulation_id="sim_q")
            def prepare_simulation(self, **kw):
                pass
        monkeypatch.setattr(pa, "SimulationManager", _SM)

        class _Runner:
            @staticmethod
            def start_simulation(**kw):
                pass
            @staticmethod
            def get_run_state(_):
                return None
            @staticmethod
            def stop_simulation(_):
                pass
        monkeypatch.setattr(pa, "SimulationRunner", _Runner)
        with pytest.raises(RuntimeError, match="run_state 사라짐"):
            pa.simulation_adapter(ctx)

    def test_run_failed(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            seed_files=[("a.txt", "x")],
            prev_meta={"graph_id": "g1"},
            prev_meta_filename="agents_meta.json",
            step_name="simulation",
        )
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))

        class _SM:
            def create_simulation(self, **kw):
                return SimpleNamespace(simulation_id="sim_q")
            def prepare_simulation(self, **kw):
                pass
        monkeypatch.setattr(pa, "SimulationManager", _SM)

        class _Runner:
            @staticmethod
            def start_simulation(**kw):
                pass
            @staticmethod
            def get_run_state(_):
                return SimpleNamespace(
                    runner_status=pa.RunnerStatus.FAILED,
                    current_round=0, total_rounds=0,
                    twitter_actions_count=0, reddit_actions_count=0,
                    error="OASIS 충돌", completed_at=None,
                )
            @staticmethod
            def stop_simulation(_):
                pass
        monkeypatch.setattr(pa, "SimulationRunner", _Runner)
        with pytest.raises(RuntimeError, match="OASIS 충돌"):
            pa.simulation_adapter(ctx)

    def test_platform_twitter_only(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            seed_files=[("a.txt", "x")],
            prev_meta={"graph_id": "g1"},
            prev_meta_filename="agents_meta.json",
            step_name="simulation",
            config={"enable_twitter": True, "enable_reddit": False},
        )
        monkeypatch.setattr(pa.TextProcessor, "extract_from_files", staticmethod(lambda p: "x"))
        monkeypatch.setattr(pa.TextProcessor, "preprocess_text", staticmethod(lambda t: t))

        class _SM:
            def create_simulation(self, **kw):
                return SimpleNamespace(simulation_id="sim_t")
            def prepare_simulation(self, **kw):
                pass
        monkeypatch.setattr(pa, "SimulationManager", _SM)

        captured = {}
        states = iter([
            SimpleNamespace(
                runner_status=pa.RunnerStatus.COMPLETED,
                current_round=1, total_rounds=1,
                twitter_actions_count=10, reddit_actions_count=0,
                error=None, completed_at="2026-05-01T00:00:00",
            ),
            SimpleNamespace(
                runner_status=pa.RunnerStatus.COMPLETED,
                current_round=1, total_rounds=1,
                twitter_actions_count=10, reddit_actions_count=0,
                error=None, completed_at="2026-05-01T00:00:00",
            ),
        ])

        class _Runner:
            @staticmethod
            def start_simulation(**kw):
                captured.update(kw)
            @staticmethod
            def get_run_state(_):
                return next(states)
            @staticmethod
            def stop_simulation(_):
                pass
        monkeypatch.setattr(pa, "SimulationRunner", _Runner)

        meta = pa.simulation_adapter(ctx)
        assert meta["platform"] == "twitter"
        assert captured["platform"] == "twitter"


# ============================================================================
# report_adapter
# ============================================================================

class TestReportAdapter:
    def test_no_prev_step_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path, step_name="report")
        with pytest.raises(RuntimeError, match="prev_step_dir 없음"):
            pa.report_adapter(ctx)

    def test_happy_path(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            prev_meta={
                "graph_id": "g1",
                "simulation_id": "sim_x",
                "simulation_requirement": "요구",
            },
            prev_meta_filename="simulation_meta.json",
            step_name="report",
        )

        captured = {}

        class _Agent:
            def __init__(self, **kw):
                captured["init"] = kw
            def generate_report(self, report_id):
                captured["report_id"] = report_id
                outline = SimpleNamespace(
                    sections=[1, 2, 3]
                )
                return SimpleNamespace(
                    outline=outline,
                    status="completed",
                )

        monkeypatch.setattr(pa, "ReportAgent", _Agent)
        meta = pa.report_adapter(ctx)
        assert meta["graph_id"] == "g1"
        assert meta["simulation_id"] == "sim_x"
        assert meta["sections_count"] == 3
        assert meta["report_id"].startswith("run_")
        # ReportAgent 인자
        assert captured["init"]["graph_id"] == "g1"
        assert captured["init"]["simulation_id"] == "sim_x"
        # report_meta.json 작성
        assert (ctx.tmp_dir / "report_meta.json").exists()

    def test_no_outline(self, tmp_path, monkeypatch):
        ctx = _make_ctx(
            tmp_path,
            prev_meta={
                "graph_id": "g1",
                "simulation_id": "sim_x",
                "simulation_requirement": "요구",
            },
            prev_meta_filename="simulation_meta.json",
            step_name="report",
        )

        class _Agent:
            def __init__(self, **kw):
                pass
            def generate_report(self, report_id):
                return SimpleNamespace(outline=None, status="failed")

        monkeypatch.setattr(pa, "ReportAgent", _Agent)
        meta = pa.report_adapter(ctx)
        assert meta["sections_count"] == 0
