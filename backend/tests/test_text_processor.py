"""
TextProcessor 서비스 단위 테스트 (`app/services/text_processor.py`).

4 메서드:
- extract_from_files (FileParser delegate)
- split_text (split_text_into_chunks delegate)
- preprocess_text (순수 — 줄바꿈/공백 정규화)
- get_text_stats (순수 — 통계)
"""

import pytest

from app.services import text_processor as tp_mod
from app.services.text_processor import TextProcessor


class TestExtractFromFiles:
    def test_delegates_to_file_parser(self, monkeypatch):
        captured = {}

        def _extract(paths):
            captured["paths"] = paths
            return "merged text"

        monkeypatch.setattr(tp_mod.FileParser, "extract_from_multiple", staticmethod(_extract))
        result = TextProcessor.extract_from_files(["a.pdf", "b.txt"])
        assert result == "merged text"
        assert captured["paths"] == ["a.pdf", "b.txt"]


class TestSplitText:
    def test_delegates_with_defaults(self, monkeypatch):
        captured = {}

        def _split(text, chunk_size, overlap):
            captured.update(text=text, chunk_size=chunk_size, overlap=overlap)
            return ["c1", "c2"]

        monkeypatch.setattr(tp_mod, "split_text_into_chunks", _split)
        result = TextProcessor.split_text("abc")
        assert result == ["c1", "c2"]
        assert captured["chunk_size"] == 500
        assert captured["overlap"] == 50

    def test_passes_custom_args(self, monkeypatch):
        captured = {}

        def _split(text, chunk_size, overlap):
            captured.update(chunk_size=chunk_size, overlap=overlap)
            return []

        monkeypatch.setattr(tp_mod, "split_text_into_chunks", _split)
        TextProcessor.split_text("x", chunk_size=200, overlap=10)
        assert captured["chunk_size"] == 200
        assert captured["overlap"] == 10


class TestPreprocessText:
    def test_normalizes_crlf(self):
        assert TextProcessor.preprocess_text("a\r\nb\rc") == "a\nb\nc"

    def test_collapses_3plus_newlines_to_two(self):
        result = TextProcessor.preprocess_text("a\n\n\n\nb")
        assert result == "a\n\nb"

    def test_keeps_double_newline(self):
        result = TextProcessor.preprocess_text("a\n\nb")
        assert result == "a\n\nb"

    def test_strips_per_line_whitespace(self):
        result = TextProcessor.preprocess_text("  hello  \n   world\t")
        assert result == "hello\nworld"

    def test_strips_outer_whitespace(self):
        assert TextProcessor.preprocess_text("\n\n  text  \n\n") == "text"

    def test_empty_string(self):
        assert TextProcessor.preprocess_text("") == ""

    def test_only_whitespace(self):
        assert TextProcessor.preprocess_text("   \n\n   \n  ") == ""

    def test_combined_normalization(self):
        raw = "  Title  \r\n\r\n\r\n  Body line  \r\n\r\n"
        assert TextProcessor.preprocess_text(raw) == "Title\n\nBody line"


class TestGetTextStats:
    def test_basic_stats(self):
        stats = TextProcessor.get_text_stats("hello world\nfoo bar baz")
        assert stats == {
            "total_chars": len("hello world\nfoo bar baz"),
            "total_lines": 2,
            "total_words": 5,
        }

    def test_empty_text(self):
        # 주의: count('\n') + 1 = 1, split() == []
        stats = TextProcessor.get_text_stats("")
        assert stats == {"total_chars": 0, "total_lines": 1, "total_words": 0}

    def test_single_line(self):
        stats = TextProcessor.get_text_stats("only one line")
        assert stats["total_lines"] == 1
        assert stats["total_words"] == 3

    def test_multibyte_chars_use_codepoint_count(self):
        # len() 은 codepoint 수 — 한글 5자 → 5
        stats = TextProcessor.get_text_stats("안녕하세요")
        assert stats["total_chars"] == 5
