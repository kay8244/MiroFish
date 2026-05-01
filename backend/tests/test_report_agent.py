"""
ReportAgent + ReportManager 단위 테스트 (`app/services/report_agent.py`).

검증 단위 (LLM 생성 경로 plan_outline / generate_report 는 통합 테스트 영역):
- 데이터클래스: ReportStatus, ReportSection, ReportOutline, Report (to_dict, to_markdown)
- ReportAgent: _define_tools, _is_valid_tool_call, _parse_tool_calls,
  _get_tools_description, _execute_tool (도구 분기 + 예외 처리)
- ReportManager: 경로 헬퍼, save_outline, save_section + _clean_section_content,
  update_progress / get_progress, get_generated_sections, _post_process_report,
  assemble_full_report, save_report / get_report / list_reports / delete_report
  / get_report_by_simulation, get_console_log / get_agent_log
"""

import json
import os
from types import SimpleNamespace

import pytest

from app.services import report_agent as ra_mod
from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


# ============================================================================
# 데이터클래스
# ============================================================================

class TestReportStatusEnum:
    def test_values(self):
        assert ReportStatus.PENDING.value == "pending"
        assert ReportStatus.PLANNING.value == "planning"
        assert ReportStatus.COMPLETED.value == "completed"
        assert ReportStatus.FAILED.value == "failed"


class TestReportSection:
    def test_to_dict(self):
        s = ReportSection(title="요약", content="본문")
        assert s.to_dict() == {"title": "요약", "content": "본문"}

    def test_to_markdown_default_level(self):
        s = ReportSection(title="요약", content="본문")
        md = s.to_markdown()
        assert md.startswith("## 요약\n\n")
        assert "본문" in md

    def test_to_markdown_custom_level(self):
        s = ReportSection(title="X", content="C")
        md = s.to_markdown(level=4)
        assert md.startswith("#### X\n\n")

    def test_to_markdown_empty_content(self):
        s = ReportSection(title="X")
        md = s.to_markdown()
        assert md == "## X\n\n"


class TestReportOutline:
    def test_to_dict(self):
        o = ReportOutline(
            title="T",
            summary="S",
            sections=[ReportSection("A"), ReportSection("B")],
        )
        d = o.to_dict()
        assert d["title"] == "T"
        assert d["summary"] == "S"
        assert len(d["sections"]) == 2

    def test_to_markdown(self):
        o = ReportOutline(
            title="보고서",
            summary="개요",
            sections=[ReportSection("섹션1", content="내용1")],
        )
        md = o.to_markdown()
        assert md.startswith("# 보고서\n\n> 개요\n\n")
        assert "## 섹션1" in md


class TestReport:
    def test_to_dict_with_outline(self):
        r = Report(
            report_id="r1", simulation_id="s1", graph_id="g1",
            simulation_requirement="요구",
            status=ReportStatus.COMPLETED,
            outline=ReportOutline("T", "S", []),
            markdown_content="# Report",
        )
        d = r.to_dict()
        assert d["status"] == "completed"
        assert d["outline"]["title"] == "T"
        assert d["markdown_content"] == "# Report"

    def test_to_dict_without_outline(self):
        r = Report(
            report_id="r1", simulation_id="s1", graph_id="g1",
            simulation_requirement="요구",
            status=ReportStatus.PENDING,
        )
        d = r.to_dict()
        assert d["outline"] is None
        assert d["markdown_content"] == ""


# ============================================================================
# ReportAgent — LLM/도구 모킹
# ============================================================================

def _make_agent(zep_tools=None, llm=None):
    """ReportAgent 인스턴스 생성. LLMClient/ZepTools 는 Fake 로 차단."""
    fake_llm = llm or SimpleNamespace(chat=lambda **kw: "{}")
    fake_tools = zep_tools or SimpleNamespace()
    return ReportAgent(
        graph_id="g1",
        simulation_id="s1",
        simulation_requirement="요구사항",
        llm_client=fake_llm,
        zep_tools=fake_tools,
    )


class TestDefineTools:
    def test_returns_4_tools(self):
        agent = _make_agent()
        tools = agent._define_tools()
        assert set(tools.keys()) == {
            "insight_forge", "panorama_search", "quick_search", "interview_agents"
        }

    def test_each_tool_has_name_and_params(self):
        agent = _make_agent()
        for name, tool in agent.tools.items():
            assert tool["name"] == name
            assert "description" in tool
            assert "parameters" in tool


class TestIsValidToolCall:
    def test_valid_with_name_key(self):
        agent = _make_agent()
        assert agent._is_valid_tool_call({"name": "insight_forge", "parameters": {}}) is True

    def test_valid_with_tool_key_normalizes(self):
        agent = _make_agent()
        data = {"tool": "quick_search", "params": {"query": "x"}}
        assert agent._is_valid_tool_call(data) is True
        # 키가 통일됨
        assert data["name"] == "quick_search"
        assert data["parameters"] == {"query": "x"}

    def test_invalid_unknown_name(self):
        agent = _make_agent()
        assert agent._is_valid_tool_call({"name": "ghost"}) is False

    def test_missing_name(self):
        agent = _make_agent()
        assert agent._is_valid_tool_call({"parameters": {}}) is False


class TestParseToolCalls:
    def test_xml_style(self):
        agent = _make_agent()
        response = '''Some thought.
<tool_call>{"name": "insight_forge", "parameters": {"query": "X"}}</tool_call>
Done.'''
        calls = agent._parse_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "insight_forge"

    def test_multiple_xml_calls(self):
        agent = _make_agent()
        response = (
            '<tool_call>{"name": "insight_forge", "parameters": {}}</tool_call>\n'
            '<tool_call>{"name": "quick_search", "parameters": {}}</tool_call>'
        )
        calls = agent._parse_tool_calls(response)
        assert len(calls) == 2

    def test_bare_json_fallback(self):
        agent = _make_agent()
        response = '{"name": "insight_forge", "parameters": {"query": "X"}}'
        calls = agent._parse_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "insight_forge"

    def test_bare_json_invalid_tool_name(self):
        agent = _make_agent()
        response = '{"name": "unknown_tool", "parameters": {}}'
        calls = agent._parse_tool_calls(response)
        # _is_valid_tool_call 거부 → 빈 리스트
        assert calls == []

    def test_no_tool_call(self):
        agent = _make_agent()
        assert agent._parse_tool_calls("plain answer text") == []

    def test_trailing_json_extraction(self):
        agent = _make_agent()
        response = (
            'Some thinking text.\n'
            '{"name": "quick_search", "parameters": {"query": "X"}}'
        )
        calls = agent._parse_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "quick_search"


class TestGetToolsDescription:
    def test_includes_all_tool_names(self):
        agent = _make_agent()
        desc = agent._get_tools_description()
        assert "insight_forge" in desc
        assert "panorama_search" in desc
        assert "quick_search" in desc
        assert "interview_agents" in desc


class _FakeResult:
    def __init__(self, text):
        self._text = text

    def to_text(self):
        return self._text

    def to_dict(self):
        return {"text": self._text}


class TestExecuteTool:
    def test_insight_forge(self):
        captured = {}

        class _Tools:
            def insight_forge(self, **kw):
                captured.update(kw)
                return _FakeResult("insight 결과")

        agent = _make_agent(zep_tools=_Tools())
        result = agent._execute_tool(
            "insight_forge", {"query": "X", "report_context": "ctx"}
        )
        assert result == "insight 결과"
        assert captured["graph_id"] == "g1"
        assert captured["query"] == "X"
        assert captured["simulation_requirement"] == "요구사항"

    def test_panorama_search(self):
        class _Tools:
            def panorama_search(self, **kw):
                return _FakeResult("panorama")

        agent = _make_agent(zep_tools=_Tools())
        result = agent._execute_tool(
            "panorama_search", {"query": "X", "include_expired": "true"}
        )
        assert result == "panorama"

    def test_panorama_string_include_expired_coerced(self):
        captured = {}

        class _Tools:
            def panorama_search(self, **kw):
                captured.update(kw)
                return _FakeResult("p")

        agent = _make_agent(zep_tools=_Tools())
        agent._execute_tool("panorama_search", {"query": "X", "include_expired": "false"})
        assert captured["include_expired"] is False

    def test_quick_search(self):
        captured = {}

        class _Tools:
            def quick_search(self, **kw):
                captured.update(kw)
                return _FakeResult("quick")

        agent = _make_agent(zep_tools=_Tools())
        agent._execute_tool("quick_search", {"query": "X", "limit": "5"})
        assert captured["limit"] == 5  # str → int

    def test_interview_agents_caps_max_at_10(self):
        captured = {}

        class _Tools:
            def interview_agents(self, **kw):
                captured.update(kw)
                return _FakeResult("interview")

        agent = _make_agent(zep_tools=_Tools())
        agent._execute_tool(
            "interview_agents", {"interview_topic": "T", "max_agents": "20"}
        )
        assert captured["max_agents"] == 10  # 캡

    def test_unknown_tool_returns_message(self):
        agent = _make_agent()
        result = agent._execute_tool("ghost_tool", {})
        assert "알 수 없는 도구" in result

    def test_exception_caught(self):
        class _Tools:
            def insight_forge(self, **kw):
                raise RuntimeError("DB down")

        agent = _make_agent(zep_tools=_Tools())
        result = agent._execute_tool("insight_forge", {"query": "X"})
        assert "도구 실행 실패" in result
        assert "DB down" in result

    def test_search_graph_redirects_to_quick_search(self):
        captured = {}

        class _Tools:
            def quick_search(self, **kw):
                captured["called"] = True
                return _FakeResult("redirected")

        agent = _make_agent(zep_tools=_Tools())
        result = agent._execute_tool("search_graph", {"query": "X"})
        assert captured.get("called") is True
        assert result == "redirected"


# ============================================================================
# ReportManager — 경로 헬퍼
# ============================================================================

@pytest.fixture
def isolated_reports(tmp_path, monkeypatch):
    """REPORTS_DIR 을 tmp_path 로 격리."""
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    return tmp_path


class TestPathHelpers:
    def test_paths(self, isolated_reports, tmp_path):
        rid = "r_abc"
        assert ReportManager._get_report_folder(rid) == str(tmp_path / "r_abc")
        assert ReportManager._get_report_path(rid).endswith("meta.json")
        assert ReportManager._get_outline_path(rid).endswith("outline.json")
        assert ReportManager._get_progress_path(rid).endswith("progress.json")
        assert ReportManager._get_section_path(rid, 5).endswith("section_05.md")
        assert ReportManager._get_report_markdown_path(rid).endswith("full_report.md")
        assert ReportManager._get_agent_log_path(rid).endswith("agent_log.jsonl")
        assert ReportManager._get_console_log_path(rid).endswith("console_log.txt")


# ============================================================================
# save_outline / save_section / _clean_section_content
# ============================================================================

class TestSaveOutline:
    def test_writes_outline_json(self, isolated_reports, tmp_path):
        outline = ReportOutline(
            title="T", summary="S",
            sections=[ReportSection("A"), ReportSection("B")],
        )
        ReportManager.save_outline("r1", outline)
        path = tmp_path / "r1" / "outline.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["title"] == "T"
        assert len(data["sections"]) == 2


class TestCleanSectionContent:
    def test_removes_duplicate_heading(self):
        content = "## 요약\n\n본문 내용."
        result = ReportManager._clean_section_content(content, "요약")
        # 챕터 제목과 같은 ##는 제거됨
        assert "## 요약" not in result
        assert "본문 내용" in result

    def test_converts_h3_to_bold(self):
        content = "### 소제목\n\n내용"
        result = ReportManager._clean_section_content(content, "본문")
        assert "**소제목**" in result
        assert "###" not in result

    def test_removes_leading_separator(self):
        content = "---\n\n내용"
        result = ReportManager._clean_section_content(content, "T")
        assert not result.startswith("---")
        assert "내용" in result

    def test_empty_content(self):
        assert ReportManager._clean_section_content("", "T") == ""


class TestSaveSection:
    def test_creates_md_file(self, isolated_reports, tmp_path):
        section = ReportSection(title="요약", content="본문")
        path = ReportManager.save_section("r1", 1, section)
        assert os.path.exists(path)
        text = open(path, encoding="utf-8").read()
        assert text.startswith("## 요약\n\n")
        assert "본문" in text

    def test_filename_has_zero_padded_index(self, isolated_reports, tmp_path):
        ReportManager.save_section("r1", 7, ReportSection("X"))
        assert (tmp_path / "r1" / "section_07.md").exists()


# ============================================================================
# Progress
# ============================================================================

class TestProgress:
    def test_update_then_get(self, isolated_reports):
        ReportManager.update_progress(
            "r1", status="generating", progress=50, message="중간",
            current_section="섹션 A", completed_sections=["섹션 0"],
        )
        result = ReportManager.get_progress("r1")
        assert result["status"] == "generating"
        assert result["progress"] == 50
        assert result["completed_sections"] == ["섹션 0"]

    def test_get_missing_returns_none(self, isolated_reports):
        assert ReportManager.get_progress("ghost") is None


# ============================================================================
# get_generated_sections
# ============================================================================

class TestGetGeneratedSections:
    def test_empty_when_folder_missing(self, isolated_reports):
        assert ReportManager.get_generated_sections("ghost") == []

    def test_returns_sorted(self, isolated_reports):
        ReportManager.save_section("r1", 2, ReportSection("B", "본문 B"))
        ReportManager.save_section("r1", 1, ReportSection("A", "본문 A"))
        ReportManager.save_section("r1", 10, ReportSection("J", "본문 J"))
        result = ReportManager.get_generated_sections("r1")
        # filename 알파벳 정렬: section_01, section_02, section_10
        indices = [s["section_index"] for s in result]
        assert indices == [1, 2, 10]


# ============================================================================
# _post_process_report
# ============================================================================

class TestPostProcessReport:
    def test_keeps_main_title_and_section_titles(self):
        outline = ReportOutline(
            title="MAIN", summary="S",
            sections=[ReportSection("S1"), ReportSection("S2")],
        )
        content = "# MAIN\n\n> S\n\n## S1\n\n내용 1\n\n## S2\n\n내용 2"
        result = ReportManager._post_process_report(content, outline)
        assert "# MAIN" in result
        assert "## S1" in result
        assert "## S2" in result

    def test_converts_h3_to_bold(self):
        outline = ReportOutline("T", "S", [ReportSection("A")])
        content = "## A\n\n### 작은 제목\n\n본문"
        result = ReportManager._post_process_report(content, outline)
        assert "**작은 제목**" in result
        assert "### 작은 제목" not in result

    def test_collapses_3plus_blank_lines_to_2(self):
        outline = ReportOutline("T", "S", [])
        content = "내용 A\n\n\n\n\n내용 B"
        result = ReportManager._post_process_report(content, outline)
        # 빈 줄은 최대 2개
        assert "\n\n\n\n" not in result

    def test_dedup_consecutive_same_titles(self):
        outline = ReportOutline("T", "S", [ReportSection("A")])
        content = "## A\n\n## A\n\n본문"
        result = ReportManager._post_process_report(content, outline)
        # 2번째 ## A 는 제거
        assert result.count("## A") == 1


# ============================================================================
# assemble_full_report
# ============================================================================

class TestAssembleFullReport:
    def test_combines_sections(self, isolated_reports, tmp_path):
        outline = ReportOutline(
            title="MAIN", summary="개요",
            sections=[ReportSection("A"), ReportSection("B")],
        )
        ReportManager.save_section("r1", 1, ReportSection("A", "본문 A"))
        ReportManager.save_section("r1", 2, ReportSection("B", "본문 B"))
        result = ReportManager.assemble_full_report("r1", outline)
        # 헤더 + 섹션
        assert "# MAIN" in result
        assert "> 개요" in result
        assert "## A" in result
        assert "본문 A" in result
        assert "## B" in result
        # 파일도 작성됨
        assert (tmp_path / "r1" / "full_report.md").exists()


# ============================================================================
# save_report / get_report / list_reports / delete_report / get_report_by_simulation
# ============================================================================

def _make_report(report_id="r1", simulation_id="s1", status=ReportStatus.COMPLETED, **kw):
    defaults = dict(
        graph_id="g1",
        simulation_requirement="요구",
        status=status,
        outline=ReportOutline("T", "S", [ReportSection("A", "내용 A")]),
        markdown_content="# T\n\n## A\n\n내용",
        created_at="2026-05-01T00:00:00",
    )
    defaults.update(kw)
    return Report(report_id=report_id, simulation_id=simulation_id, **defaults)


class TestSaveAndGetReport:
    def test_save_writes_meta_outline_markdown(self, isolated_reports, tmp_path):
        ReportManager.save_report(_make_report("r1"))
        folder = tmp_path / "r1"
        assert (folder / "meta.json").exists()
        assert (folder / "outline.json").exists()
        assert (folder / "full_report.md").exists()

    def test_get_returns_reconstructed_report(self, isolated_reports):
        original = _make_report("r1")
        ReportManager.save_report(original)
        loaded = ReportManager.get_report("r1")
        assert loaded is not None
        assert loaded.report_id == "r1"
        assert loaded.simulation_id == "s1"
        assert loaded.status == ReportStatus.COMPLETED
        assert loaded.outline.title == "T"
        assert loaded.markdown_content == "# T\n\n## A\n\n내용"

    def test_get_missing_returns_none(self, isolated_reports):
        assert ReportManager.get_report("ghost") is None


class TestGetReportBySimulation:
    def test_finds_match(self, isolated_reports):
        ReportManager.save_report(_make_report("r_a", simulation_id="sim_a"))
        ReportManager.save_report(_make_report("r_b", simulation_id="sim_b"))
        result = ReportManager.get_report_by_simulation("sim_b")
        assert result is not None
        assert result.report_id == "r_b"

    def test_no_match_returns_none(self, isolated_reports):
        ReportManager.save_report(_make_report("r1", simulation_id="sim_x"))
        assert ReportManager.get_report_by_simulation("ghost") is None


class TestListReports:
    def test_lists_all_sorted_by_created_at_desc(self, isolated_reports):
        ReportManager.save_report(_make_report(
            "r1", simulation_id="s1", created_at="2026-04-01T00:00:00"
        ))
        ReportManager.save_report(_make_report(
            "r2", simulation_id="s2", created_at="2026-05-01T00:00:00"
        ))
        result = ReportManager.list_reports()
        assert [r.report_id for r in result] == ["r2", "r1"]

    def test_filter_by_simulation_id(self, isolated_reports):
        ReportManager.save_report(_make_report("r1", simulation_id="sim_a"))
        ReportManager.save_report(_make_report("r2", simulation_id="sim_b"))
        result = ReportManager.list_reports(simulation_id="sim_a")
        assert len(result) == 1
        assert result[0].simulation_id == "sim_a"

    def test_limit_applied(self, isolated_reports):
        for i in range(5):
            ReportManager.save_report(_make_report(
                f"r{i}", created_at=f"2026-05-0{i+1}T00:00:00"
            ))
        result = ReportManager.list_reports(limit=2)
        assert len(result) == 2


class TestDeleteReport:
    def test_deletes_folder(self, isolated_reports, tmp_path):
        ReportManager.save_report(_make_report("r1"))
        assert (tmp_path / "r1").exists()
        assert ReportManager.delete_report("r1") is True
        assert not (tmp_path / "r1").exists()

    def test_missing_returns_false(self, isolated_reports):
        assert ReportManager.delete_report("ghost") is False


# ============================================================================
# Console / Agent log
# ============================================================================

class TestConsoleLog:
    def test_missing_returns_empty_dict(self, isolated_reports):
        result = ReportManager.get_console_log("ghost")
        assert result == {
            "logs": [], "total_lines": 0, "from_line": 0, "has_more": False
        }

    def test_reads_lines_from_file(self, isolated_reports, tmp_path):
        folder = tmp_path / "r1"
        folder.mkdir()
        log_path = folder / "console_log.txt"
        log_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = ReportManager.get_console_log("r1")
        assert result["logs"] == ["line1", "line2", "line3"]
        assert result["total_lines"] == 3

    def test_from_line_skips(self, isolated_reports, tmp_path):
        folder = tmp_path / "r1"
        folder.mkdir()
        (folder / "console_log.txt").write_text("a\nb\nc\nd\n")
        result = ReportManager.get_console_log("r1", from_line=2)
        assert result["logs"] == ["c", "d"]


class TestAgentLog:
    def test_missing_returns_empty(self, isolated_reports):
        result = ReportManager.get_agent_log("ghost")
        assert result["logs"] == []

    def test_reads_jsonl(self, isolated_reports, tmp_path):
        folder = tmp_path / "r1"
        folder.mkdir()
        log_path = folder / "agent_log.jsonl"
        with open(log_path, "w") as f:
            f.write(json.dumps({"action": "start"}) + "\n")
            f.write(json.dumps({"action": "tool_call", "tool": "insight_forge"}) + "\n")
        result = ReportManager.get_agent_log("r1")
        assert len(result["logs"]) == 2
        assert result["logs"][0]["action"] == "start"

    def test_skips_invalid_json_lines(self, isolated_reports, tmp_path):
        folder = tmp_path / "r1"
        folder.mkdir()
        log_path = folder / "agent_log.jsonl"
        with open(log_path, "w") as f:
            f.write(json.dumps({"action": "ok"}) + "\n")
            f.write("not json\n")
            f.write(json.dumps({"action": "ok2"}) + "\n")
        result = ReportManager.get_agent_log("r1")
        assert len(result["logs"]) == 2

    def test_stream_returns_logs_list(self, isolated_reports, tmp_path):
        folder = tmp_path / "r1"
        folder.mkdir()
        log_path = folder / "agent_log.jsonl"
        log_path.write_text(json.dumps({"action": "x"}) + "\n")
        result = ReportManager.get_agent_log_stream("r1")
        assert isinstance(result, list)
        assert result[0]["action"] == "x"
