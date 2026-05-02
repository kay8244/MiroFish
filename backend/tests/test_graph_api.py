"""
Graph API 라우트 integration tests (`app/api/graph.py`).

라우트 11개:
- GET    /api/graph/project/<project_id>          : 프로젝트 상세
- GET    /api/graph/project/list                  : 프로젝트 목록
- DELETE /api/graph/project/<project_id>          : 프로젝트 삭제
- POST   /api/graph/project/<project_id>/reset    : 상태 초기화
- POST   /api/graph/ontology/generate             : multipart, 파일+요구사항 → 온톨로지
- POST   /api/graph/build                         : 비동기 그래프 빌드 (background watcher)
- POST   /api/graph/append                        : multipart, 기존 그래프에 incremental 추가
- GET    /api/graph/task/<task_id>                : 태스크 단건
- GET    /api/graph/tasks                         : 태스크 목록
- GET    /api/graph/data/<graph_id>               : 그래프 데이터 (노드/엣지)
- DELETE /api/graph/delete/<graph_id>             : 그래프 삭제

build/append 의 백그라운드 watcher 스레드는 threading.Thread monkeypatch 로 인라인 차단.
multipart 업로드는 `(BytesIO, filename, mimetype)` 튜플로 구성.
"""

import io

import pytest

from app.api import graph as graph_routes
from app.models.project import ProjectStatus
from app.utils.rate_limiter import _limiter as _rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    _rate_limiter._buckets.clear()
    yield
    _rate_limiter._buckets.clear()


# ---------------------------------------------------------------------------
# 가짜 객체
# ---------------------------------------------------------------------------

class _FakeProject:
    def __init__(
        self,
        project_id="p1",
        name="My Project",
        status=ProjectStatus.ONTOLOGY_GENERATED,
        graph_id=None,
        graph_build_task_id=None,
        ontology=None,
        chunk_size=500,
        chunk_overlap=50,
        total_text_length=0,
        files=None,
    ):
        self.project_id = project_id
        self.name = name
        self.status = status
        self.graph_id = graph_id
        self.graph_build_task_id = graph_build_task_id
        self.ontology = ontology if ontology is not None else {
            "entity_types": [{"name": "Person"}],
            "edge_types": [{"name": "knows"}],
        }
        self.simulation_requirement = None
        self.analysis_summary = ""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.total_text_length = total_text_length
        self.files = files if files is not None else []
        self.error = None

    def to_dict(self):
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "graph_id": self.graph_id,
            "files": self.files,
        }


class _FakeTask:
    def __init__(self, task_id="task_1", status="processing", progress=10, message="..."):
        self.task_id = task_id
        self.status = status
        self.progress = progress
        self.message = message

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
        }


@pytest.fixture
def block_threads(monkeypatch):
    """build/append 의 background watcher Thread 를 NO-OP."""
    class _NoopThread:
        def __init__(self, **kw):
            pass
        def start(self):
            pass
    monkeypatch.setattr(graph_routes.threading, "Thread", _NoopThread)


def _txt_upload(content="hello world", filename="doc.txt", mimetype="text/plain"):
    return (io.BytesIO(content.encode("utf-8")), filename, mimetype)


# ============================================================================
# 인증 게이트 (전역 before_request)
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("method,path", [
        ("get",    "/api/graph/project/p1"),
        ("get",    "/api/graph/project/list"),
        ("delete", "/api/graph/project/p1"),
        ("post",   "/api/graph/project/p1/reset"),
        ("post",   "/api/graph/ontology/generate"),
        ("post",   "/api/graph/build"),
        ("post",   "/api/graph/append"),
        ("get",    "/api/graph/task/t1"),
        ("get",    "/api/graph/tasks"),
        ("get",    "/api/graph/data/g1"),
        ("delete", "/api/graph/delete/g1"),
    ])
    def test_requires_auth(self, client, method, path):
        fn = getattr(client, method)
        if method == "post":
            resp = fn(path, json={})
        else:
            resp = fn(path)
        assert resp.status_code == 401


# ============================================================================
# 쓰기 메서드 — viewer 는 403
# ============================================================================

class TestWriteRoleGate:
    @pytest.mark.parametrize("method,path", [
        ("delete", "/api/graph/project/p1"),
        ("post",   "/api/graph/project/p1/reset"),
        ("post",   "/api/graph/ontology/generate"),
        ("post",   "/api/graph/build"),
        ("post",   "/api/graph/append"),
        ("delete", "/api/graph/delete/g1"),
    ])
    def test_viewer_forbidden(self, client, viewer_user, login_as, method, path):
        login_as("viewer@test.local")
        fn = getattr(client, method)
        if method == "post":
            resp = fn(path, json={})
        else:
            resp = fn(path)
        assert resp.status_code == 403


# ============================================================================
# GET /project/<id>
# ============================================================================

class TestGetProject:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "get_project",
            staticmethod(lambda pid: _FakeProject(project_id=pid)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/graph/project/proj_x")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["project_id"] == "proj_x"

    def test_not_found(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/graph/project/missing")
        assert resp.status_code == 404


# ============================================================================
# GET /project/list
# ============================================================================

class TestListProjects:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _list(limit=50):
            captured["limit"] = limit
            return [_FakeProject(project_id=f"p{i}") for i in range(2)]

        monkeypatch.setattr(graph_routes.ProjectManager, "list_projects", staticmethod(_list))
        login_as("viewer@test.local")
        resp = client.get("/api/graph/project/list")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 2
        assert captured["limit"] == 50

    def test_with_limit(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _list(limit=50):
            captured["limit"] = limit
            return []

        monkeypatch.setattr(graph_routes.ProjectManager, "list_projects", staticmethod(_list))
        login_as("viewer@test.local")
        resp = client.get("/api/graph/project/list?limit=7")
        assert resp.status_code == 200
        assert captured["limit"] == 7


# ============================================================================
# DELETE /project/<id>
# ============================================================================

class TestDeleteProject:
    def test_happy(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "delete_project", staticmethod(lambda _: True)
        )
        login_as("builder@test.local")
        resp = client.delete("/api/graph/project/p1")
        assert resp.status_code == 200

    def test_not_found(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "delete_project", staticmethod(lambda _: False)
        )
        login_as("builder@test.local")
        resp = client.delete("/api/graph/project/missing")
        assert resp.status_code == 404


# ============================================================================
# POST /project/<id>/reset
# ============================================================================

class TestResetProject:
    def test_not_found(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/project/missing/reset")
        assert resp.status_code == 404

    def test_with_ontology_resets_to_ontology_generated(
        self, client, builder_user, login_as, monkeypatch
    ):
        proj = _FakeProject(
            status=ProjectStatus.GRAPH_COMPLETED,
            graph_id="g_old",
            graph_build_task_id="t_old",
        )
        proj.error = "이전 에러"
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        saved = []
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "save_project",
            staticmethod(lambda p: saved.append(p)),
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/project/p1/reset")
        assert resp.status_code == 200
        assert proj.status == ProjectStatus.ONTOLOGY_GENERATED
        assert proj.graph_id is None
        assert proj.graph_build_task_id is None
        assert proj.error is None
        assert saved and saved[0] is proj

    def test_without_ontology_resets_to_created(
        self, client, builder_user, login_as, monkeypatch
    ):
        proj = _FakeProject(status=ProjectStatus.GRAPH_BUILDING, ontology=None)
        proj.ontology = None  # Force None
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "save_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/project/p1/reset")
        assert resp.status_code == 200
        assert proj.status == ProjectStatus.CREATED


# ============================================================================
# POST /ontology/generate (multipart)
# ============================================================================

class TestOntologyGenerate:
    def test_missing_requirement(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/ontology/generate",
            data={"files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "simulation_requirement" in resp.get_json()["error"]

    def test_no_files(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/ontology/generate",
            data={"simulation_requirement": "테스트"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_invalid_mime(self, client, builder_user, login_as, monkeypatch):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "create_project", staticmethod(lambda name: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/ontology/generate",
            data={
                "simulation_requirement": "X",
                "files": (io.BytesIO(b"binary"), "doc.txt", "application/x-malware"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "허용되지 않는" in resp.get_json()["error"]

    def test_happy_path(self, client, builder_user, login_as, monkeypatch):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "create_project", staticmethod(lambda name: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "save_file_to_project",
            staticmethod(lambda pid, f, fn: {
                "original_filename": fn, "size": 11, "path": "/tmp/x.txt"
            }),
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "save_extracted_text",
            staticmethod(lambda pid, text: None),
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "save_project", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            graph_routes.FileParser, "extract_text", staticmethod(lambda path: "추출 텍스트")
        )
        monkeypatch.setattr(
            graph_routes.TextProcessor, "preprocess_text", staticmethod(lambda t: t)
        )

        captured = {}

        class _Gen:
            def generate(self, **kw):
                captured.update(kw)
                return {
                    "entity_types": [{"name": "Person"}, {"name": "Org"}],
                    "edge_types": [{"name": "knows"}],
                    "analysis_summary": "분석 요약",
                }

        monkeypatch.setattr(graph_routes, "OntologyGenerator", _Gen)

        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/ontology/generate",
            data={
                "simulation_requirement": "AI 서버 수요 예측",
                "project_name": "AI",
                "additional_context": "ctx",
                "files": _txt_upload(content="문서 내용"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["project_id"] == proj.project_id
        assert len(body["data"]["ontology"]["entity_types"]) == 2
        assert body["data"]["analysis_summary"] == "분석 요약"
        assert captured["simulation_requirement"] == "AI 서버 수요 예측"
        assert captured["additional_context"] == "ctx"
        assert proj.status == ProjectStatus.ONTOLOGY_GENERATED

    def test_no_parsable_files(self, client, builder_user, login_as, monkeypatch):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "create_project", staticmethod(lambda name: proj)
        )
        deleted = {}
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "delete_project",
            staticmethod(lambda pid: deleted.update({"id": pid}) or True),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/ontology/generate",
            data={
                "simulation_requirement": "X",
                # 확장자 미허용 → allowed_file False → document_texts 비어 있음
                "files": (io.BytesIO(b"data"), "image.png", "image/png"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert deleted.get("id") == proj.project_id


# ============================================================================
# POST /build
# ============================================================================

class TestBuildGraph:
    def test_missing_project_id(self, client, builder_user, login_as, block_threads):
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={})
        assert resp.status_code == 400

    def test_unknown_project_404(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={"project_id": "ghost"})
        assert resp.status_code == 404

    def test_status_created_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(status=ProjectStatus.CREATED)
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={"project_id": "p1"})
        assert resp.status_code == 400
        assert "온톨로지" in resp.get_json()["error"]

    def test_already_building_blocks(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(
            status=ProjectStatus.GRAPH_BUILDING, graph_build_task_id="t_running"
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={"project_id": "p1"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["task_id"] == "t_running"

    def test_invalid_chunk_size(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/build",
            json={"project_id": "p1", "chunk_size": "abc"},
        )
        assert resp.status_code == 400
        assert "chunk_size" in resp.get_json()["error"]

    def test_negative_chunk_overlap(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/build",
            json={"project_id": "p1", "chunk_overlap": -3},
        )
        assert resp.status_code == 400
        assert "chunk_overlap" in resp.get_json()["error"]

    def test_no_extracted_text_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_extracted_text", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={"project_id": "p1"})
        assert resp.status_code == 400
        assert "텍스트" in resp.get_json()["error"]

    def test_no_ontology_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(ontology=None)
        proj.ontology = None
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_extracted_text", staticmethod(lambda _: "txt")
        )
        login_as("builder@test.local")
        resp = client.post("/api/graph/build", json={"project_id": "p1"})
        assert resp.status_code == 400
        assert "온톨로지" in resp.get_json()["error"]

    def test_happy_starts_task(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject()
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_extracted_text", staticmethod(lambda _: "추출")
        )
        saved = []
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "save_project",
            staticmethod(lambda p: saved.append(p.status)),
        )

        captured = {}

        class _Builder:
            def build_graph_async(self, **kw):
                captured.update(kw)
                return "task_built"

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        monkeypatch.setattr(graph_routes, "TaskManager", lambda: object())
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/build",
            json={"project_id": "p1", "chunk_size": 250, "chunk_overlap": 25},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["task_id"] == "task_built"
        assert captured["chunk_size"] == 250
        assert captured["chunk_overlap"] == 25
        assert proj.status == ProjectStatus.GRAPH_BUILDING
        assert proj.graph_build_task_id == "task_built"

    def test_force_rebuild_resets_status(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(
            status=ProjectStatus.GRAPH_BUILDING,
            graph_id="g_old",
            graph_build_task_id="t_old",
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_extracted_text", staticmethod(lambda _: "추출")
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "save_project", staticmethod(lambda _: None)
        )

        class _Builder:
            def build_graph_async(self, **kw):
                return "task_new"

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        monkeypatch.setattr(graph_routes, "TaskManager", lambda: object())
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/build", json={"project_id": "p1", "force": True}
        )
        assert resp.status_code == 200
        assert proj.graph_build_task_id == "task_new"


# ============================================================================
# POST /append (multipart)
# ============================================================================

class TestAppendToGraph:
    def test_missing_project_id(self, client, builder_user, login_as, block_threads):
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_unknown_project_404(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "ghost", "files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 404

    def test_no_graph_id_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(graph_id=None, status=ProjectStatus.GRAPH_COMPLETED)
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "p1", "files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "/build" in resp.get_json()["error"]

    def test_already_building_blocks(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(
            status=ProjectStatus.GRAPH_BUILDING,
            graph_id="g1",
            graph_build_task_id="t_active",
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "p1", "files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["task_id"] == "t_active"

    def test_no_ontology_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(graph_id="g1", status=ProjectStatus.GRAPH_COMPLETED)
        proj.ontology = None
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "p1", "files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "온톨로지" in resp.get_json()["error"]

    def test_no_files_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(graph_id="g1", status=ProjectStatus.GRAPH_COMPLETED)
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "p1"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_happy_path(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        proj = _FakeProject(graph_id="g_keep", status=ProjectStatus.GRAPH_COMPLETED)
        monkeypatch.setattr(
            graph_routes.ProjectManager, "get_project", staticmethod(lambda _: proj)
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "save_file_to_project",
            staticmethod(lambda pid, f, fn: {
                "original_filename": fn, "size": 5, "path": "/tmp/y.txt"
            }),
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager,
            "append_extracted_text",
            staticmethod(lambda pid, text: None),
        )
        monkeypatch.setattr(
            graph_routes.ProjectManager, "save_project", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            graph_routes.FileParser, "extract_text", staticmethod(lambda path: "새 텍스트")
        )
        monkeypatch.setattr(
            graph_routes.TextProcessor, "preprocess_text", staticmethod(lambda t: t)
        )

        captured = {}

        class _Builder:
            def build_graph_async(self, **kw):
                captured.update(kw)
                return "task_append"

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        monkeypatch.setattr(graph_routes, "TaskManager", lambda: object())

        login_as("builder@test.local")
        resp = client.post(
            "/api/graph/append",
            data={"project_id": "p1", "files": _txt_upload(content="추가 문서")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["graph_id"] == "g_keep"
        assert body["data"]["task_id"] == "task_append"
        assert len(body["data"]["files_added"]) == 1
        # build_graph_async 는 existing_graph_id 와 함께 호출돼야 함
        assert captured["existing_graph_id"] == "g_keep"
        assert proj.status == ProjectStatus.GRAPH_BUILDING
        assert proj.graph_build_task_id == "task_append"


# ============================================================================
# GET /task/<id> + /tasks
# ============================================================================

class TestTaskRoutes:
    def test_get_task_happy(self, client, viewer_user, login_as, monkeypatch):
        class _TM:
            def get_task(self, _):
                return _FakeTask(task_id="task_x")
        monkeypatch.setattr(graph_routes, "TaskManager", _TM)
        login_as("viewer@test.local")
        resp = client.get("/api/graph/task/task_x")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["task_id"] == "task_x"

    def test_get_task_not_found(self, client, viewer_user, login_as, monkeypatch):
        class _TM:
            def get_task(self, _):
                return None
        monkeypatch.setattr(graph_routes, "TaskManager", _TM)
        login_as("viewer@test.local")
        resp = client.get("/api/graph/task/missing")
        assert resp.status_code == 404

    def test_list_tasks(self, client, viewer_user, login_as, monkeypatch):
        class _TM:
            def list_tasks(self):
                return [_FakeTask(task_id="t1"), _FakeTask(task_id="t2")]
        monkeypatch.setattr(graph_routes, "TaskManager", _TM)
        login_as("viewer@test.local")
        resp = client.get("/api/graph/tasks")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 2


# ============================================================================
# GET /data/<graph_id>
# ============================================================================

class TestGetGraphData:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _Builder:
            def get_graph_data(self, gid):
                captured["graph_id"] = gid
                return {"nodes": [{"id": "n1"}], "edges": []}

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        login_as("viewer@test.local")
        resp = client.get("/api/graph/data/mirofish_xyz")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["nodes"][0]["id"] == "n1"
        assert captured["graph_id"] == "mirofish_xyz"

    def test_exception_500(self, client, viewer_user, login_as, monkeypatch):
        class _Builder:
            def get_graph_data(self, gid):
                raise RuntimeError("연결 실패")

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        login_as("viewer@test.local")
        resp = client.get("/api/graph/data/g_fail")
        assert resp.status_code == 500
        assert "연결 실패" in resp.get_json()["error"]


# ============================================================================
# DELETE /delete/<graph_id>
# ============================================================================

class TestDeleteGraph:
    def test_happy(self, client, builder_user, login_as, monkeypatch):
        captured = {}

        class _Builder:
            def delete_graph(self, gid):
                captured["graph_id"] = gid

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        login_as("builder@test.local")
        resp = client.delete("/api/graph/delete/g_x")
        assert resp.status_code == 200
        assert captured["graph_id"] == "g_x"

    def test_exception_500(self, client, builder_user, login_as, monkeypatch):
        class _Builder:
            def delete_graph(self, gid):
                raise RuntimeError("삭제 실패")

        monkeypatch.setattr(graph_routes, "GraphBuilderService", _Builder)
        login_as("builder@test.local")
        resp = client.delete("/api/graph/delete/g_fail")
        assert resp.status_code == 500
