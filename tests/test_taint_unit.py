"""D3 单元测试：归一化（§4）、工具分类（§2）、分块（§3）、TaintStore 落盘。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.taint import ToolClass, TaintStore, classify_tool
from engine.taint.chunk import MAX_CHUNK, MIN_MATCH, chunk_text, split_segments
from engine.taint.normalize import normalize
from engine.taint.store import TaintRecord


class TestNormalize:
    def test_nfkc_fullwidth(self) -> None:
        assert normalize("ＡＢＣ１２３") == "abc123"

    def test_zero_width_stripped(self) -> None:
        assert normalize("a\u200bb\u2060c") == "abc"

    def test_casefold(self) -> None:
        assert normalize("Canary-7F3A9C") == "canary-7f3a9c"

    def test_whitespace_collapse(self) -> None:
        assert normalize("  a\t\tb \n c  ") == "a b c"

    def test_order_zero_width_then_casefold(self) -> None:
        # 零宽不影响 NFKC/casefold 结果，但组合后必须全部消失
        assert normalize("İ\u200bx") == "i\u0307x"


class TestClassify:
    def test_defaults(self) -> None:
        assert classify_tool("web_fetch") is ToolClass.SOURCE
        assert classify_tool("read_external_doc") is ToolClass.SOURCE
        assert classify_tool("send_email") is ToolClass.SINK
        assert classify_tool("execute") is ToolClass.SINK
        assert classify_tool("read_doc") is ToolClass.NEUTRAL

    def test_override(self) -> None:
        overrides = {"my_scraper": "source", "read_doc": "sink"}
        assert classify_tool("my_scraper", overrides) is ToolClass.SOURCE
        assert classify_tool("read_doc", overrides) is ToolClass.SINK

    def test_override_only_applies_to_named_tools(self) -> None:
        assert classify_tool("echo", {"other": "sink"}) is ToolClass.NEUTRAL

    def test_invalid_override_rejected(self) -> None:
        with pytest.raises(ValueError):
            classify_tool("foo", {"foo": "unknown"})


class TestChunk:
    def test_short_text_single_chunk(self) -> None:
        text = "short untrusted line"
        assert chunk_text(text) == [text]

    def test_below_min_match_dropped(self) -> None:
        assert chunk_text("tiny") == []

    def test_split_segments(self) -> None:
        assert split_segments("one。two\nthree") == ["one。", "two", "three"]

    def test_greedy_pack_within_max(self) -> None:
        segs = ["句子" * 20, "句子" * 20]  # 各 40 字符，可装进一块
        text = "。".join(segs) + "。"
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert len(chunks[0]) <= MAX_CHUNK

    def test_adjacent_overlap_40(self) -> None:
        # 12 个 40 字符句：每块装 5 句 + 分隔空格，必然溢出产生多块
        seg = "句子" * 20 + "。"
        text = "".join(seg for _ in range(12))
        chunks = chunk_text(text)
        assert len(chunks) > 1
        for prev, cur in zip(chunks, chunks[1:]):
            assert cur.startswith(prev[-40:])

    def test_long_segment_windowed(self) -> None:
        text = "字" * 500  # 无句子边界
        chunks = chunk_text(text)
        assert len(chunks) == 3  # 240 + 200 + 200（stride 200），尾块 100 ≥ 12
        assert all(len(c) <= MAX_CHUNK for c in chunks)
        assert chunks[0] == text[:240]
        assert chunks[1] == text[200:440]
        assert chunks[2] == text[400:]

    def test_all_chunks_ge_min_match(self) -> None:
        text = "字" * 500
        assert all(len(c) >= MIN_MATCH for c in chunk_text(text))

    def test_boundary_copy_caught_by_overlap(self) -> None:
        # 块 1 覆盖 [0:205]，块 2 以 40 字符重叠开头覆盖 [165:369]；
        # 跨边界的真实连续片段不在块 1 内，但被块 2 的重叠区捕获
        segs = [f"{i:04d}" + "块" * 36 + "。" for i in range(12)]  # 各 41 字符、内容互异
        text = "".join(segs)
        chunks = chunk_text(text)
        assert len(chunks[0]) == 205
        span = text[175:235]
        assert span not in chunks[0]
        assert any(span in c for c in chunks[1:])


class TestTaintStore:
    def test_record_and_get(self) -> None:
        store = TaintStore()
        rec = store.record("c-1", "web_fetch", "Hello world. " * 10, ts_ms=1000)
        assert store.get("c-1") is rec
        assert rec.ts_ms == 1000
        assert rec.raw_text == "Hello world. " * 10
        assert rec.chunks and all(len(c) >= MIN_MATCH for c in rec.chunks)

    def test_normalized_chunks(self) -> None:
        store = TaintStore()
        rec = store.record("c-2", "read_external_doc", "ＡＢＣ\u200bDEFGHIJKLM")
        assert rec.chunks == ["abcdefghijklm"]

    def test_jsonl_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "taint" / "store.jsonl"
        store = TaintStore(path)
        store.record("c-3", "web_fetch", "persisted content", ts_ms=123)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["call_id"] == "c-3"
        assert entry["raw_text"] == "persisted content"
        assert entry["chunks"] == ["persisted content"]

    def test_empty_text_no_chunks(self) -> None:
        store = TaintStore()
        rec = store.record("c-4", "web_fetch", "  ")
        assert rec.chunks == []

    def test_memory_only_when_no_path(self, tmp_path: Path) -> None:
        store = TaintStore()
        store.record("c-5", "web_fetch", "x" * 20)
        assert len(store) == 1
        assert list(tmp_path.iterdir()) == []

    def test_iteration(self) -> None:
        store = TaintStore()
        store.record("a", "web_fetch", "x" * 20)
        store.record("b", "mail_read", "y" * 20)
        assert {r.call_id for r in store} == {"a", "b"}
        assert all(isinstance(r, TaintRecord) for r in store)
