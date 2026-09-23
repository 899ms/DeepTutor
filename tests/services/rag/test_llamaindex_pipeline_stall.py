"""Regression tests for bounded LlamaIndex indexing (issue #946).

Indexing steps run in a sync executor thread. An embedding provider that
accepts a request but never completes it (e.g. a blackholed keep-alive
connection) can stall the executor future forever: HTTP timeouts only bound
a single attempt, and provider retries extend the wait far past any
reasonable request budget. These tests pin the stall guard that fails such
operations with a clear error instead of hanging indefinitely.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest


def _llamaindex_modules() -> tuple[Any, Any, Any]:
    """Import the pipeline modules lazily, matching sibling test files."""
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_module
    from deeptutor.services.rag.pipelines.llamaindex import storage as storage_module
    from deeptutor.services.rag.pipelines.llamaindex.pipeline import LlamaIndexPipeline

    return pipeline_module, storage_module, LlamaIndexPipeline


async def _async_noop(*args, **kwargs) -> None:
    """Async stand-in for connectivity checks that need no provider call."""


def _make_pipeline(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build a pipeline with provider calls neutralized for fast tests."""
    pipeline_module, _storage_module, LlamaIndexPipeline = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.05)
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(LlamaIndexPipeline, "_configure_settings", lambda self: None)
    monkeypatch.setattr(LlamaIndexPipeline, "_verify_embedding_connectivity", _async_noop)

    async def _fake_load(file_paths, **kwargs):
        del file_paths, kwargs
        return [SimpleNamespace(text="hello world")]

    monkeypatch.setattr(
        pipeline_module, "LlamaIndexDocumentLoader", lambda logger: SimpleNamespace(load=_fake_load)
    )
    return LlamaIndexPipeline(kb_base_dir=str(tmp_path), signature_provider=lambda: None)


@pytest.mark.asyncio
async def test_stall_guard_raises_when_no_progress_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An executor step that never reports progress must fail bounded."""
    pipeline_module, _, _ = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.05)

    def never_finishes():
        time.sleep(5)

    started = time.monotonic()
    with pytest.raises(pipeline_module.IndexingStallError, match="no progress"):
        await pipeline_module._run_with_stall_guard(
            never_finishes, progress_callback=None, stall_timeout=0.2
        )
    assert time.monotonic() - started < 10


@pytest.mark.asyncio
async def test_stall_guard_returns_when_progress_keeps_flowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow-but-moving step must not be mistaken for a stall."""
    pipeline_module, _, _ = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.05)
    captured: dict = {}
    monkeypatch.setattr(pipeline_module, "set_progress_callback", lambda cb: captured.update(cb=cb))

    def slow_but_moving():
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            captured["cb"](1, 1)
            time.sleep(0.05)
        return "done"

    assert (
        await pipeline_module._run_with_stall_guard(
            slow_but_moving, progress_callback=None, stall_timeout=0.3
        )
        == "done"
    )


@pytest.mark.asyncio
async def test_stall_guard_keeps_its_worker_callback_when_another_job_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each executor's context keeps the callback captured at job start."""
    pipeline_module, _, _ = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.05)
    slot: dict = {}
    monkeypatch.setattr(pipeline_module, "set_progress_callback", lambda cb: slot.update(cb=cb))

    def displaced_then_moving():
        worker_callback = slot["cb"]
        # A concurrent job may start, but this worker retains its own callback.
        slot["cb"] = lambda *args, **kwargs: None
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            worker_callback(1, 1)
            time.sleep(0.05)
        return "done"

    assert (
        await pipeline_module._run_with_stall_guard(
            displaced_then_moving, progress_callback=None, stall_timeout=0.3
        )
        == "done"
    )


@pytest.mark.asyncio
async def test_timed_out_worker_blocks_same_kb_retry_and_late_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timeout is terminal for progress, but its sync thread still owns the KB."""
    pipeline_module, _, _ = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.01)
    callback: dict = {}
    monkeypatch.setattr(pipeline_module, "set_progress_callback", lambda cb: callback.update(cb=cb))
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    events: list[tuple[int, int]] = []

    def delayed_worker():
        started.set()
        release.wait(timeout=3)
        callback["cb"](1, 1)
        finished.set()

    try:
        with pytest.raises(pipeline_module.IndexingStallError, match="no progress"):
            await pipeline_module._run_with_stall_guard(
                delayed_worker,
                progress_callback=lambda n, total: events.append((n, total)),
                stall_timeout=0.05,
                worker_key="kb-1478",
            )
        assert started.is_set()
        with pytest.raises(pipeline_module.IndexingStallError, match="still running"):
            await pipeline_module._run_with_stall_guard(lambda: "retry", worker_key="kb-1478")
    finally:
        release.set()

    assert await asyncio.to_thread(finished.wait, 2)
    for _ in range(100):
        if "kb-1478" not in pipeline_module._INDEX_WORKERS:
            break
        await asyncio.sleep(0.01)
    assert "kb-1478" not in pipeline_module._INDEX_WORKERS
    assert events == []
    assert (
        await pipeline_module._run_with_stall_guard(lambda: "retry", worker_key="kb-1478")
        == "retry"
    )


@pytest.mark.asyncio
async def test_different_kb_workers_keep_independent_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second KB must not displace the first one's heartbeat (#1478)."""
    pipeline_module, _, _ = _llamaindex_modules()
    from deeptutor.services.rag.pipelines.llamaindex.embedding_adapter import (
        _task_progress_callback,
    )

    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.01)
    barrier = threading.Barrier(2)
    events: dict[str, list[tuple[int, int]]] = {"a": [], "b": []}

    def worker(name: str) -> str:
        callback = _task_progress_callback.get()
        assert callback is not None
        barrier.wait(timeout=2)
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            callback(1, 1)
            time.sleep(0.01)
        return name

    async def index(name: str) -> str:
        return await pipeline_module._run_with_stall_guard(
            lambda: worker(name),
            progress_callback=lambda n, total: events[name].append((n, total)),
            stall_timeout=0.08,
            worker_key=f"kb-{name}",
        )

    assert await asyncio.gather(index("a"), index("b")) == ["a", "b"]
    assert events["a"] and events["b"]


@pytest.mark.asyncio
async def test_busy_reindex_rejects_before_creating_an_empty_version(tmp_path, monkeypatch) -> None:
    pipeline_module, _, _ = _llamaindex_modules()
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    key = str((tmp_path / "kb").resolve())
    marker = threading.Event()
    pipeline_module._INDEX_WORKERS[key] = marker
    try:
        with pytest.raises(pipeline_module.IndexingStallError, match="still running"):
            await pipeline.initialize("kb", ["doc.pdf"])
    finally:
        marker.set()
        pipeline_module._INDEX_WORKERS.pop(key, None)

    assert not (tmp_path / "kb" / "version-1").exists()


@pytest.mark.asyncio
async def test_stall_guard_forwards_user_progress_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user-facing progress callback must keep receiving batch events."""
    pipeline_module, _, _ = _llamaindex_modules()
    monkeypatch.setattr(pipeline_module, "_INDEX_STALL_POLL_SECONDS", 0.05)
    captured: dict = {}
    monkeypatch.setattr(pipeline_module, "set_progress_callback", lambda cb: captured.update(cb=cb))
    events: list[tuple[int, int]] = []

    def user_callback(batch_num, total_batches):
        events.append((batch_num, total_batches))

    def reports_once():
        captured["cb"](2, 10)
        return "ok"

    assert (
        await pipeline_module._run_with_stall_guard(
            reports_once, progress_callback=user_callback, stall_timeout=1.0
        )
        == "ok"
    )
    assert events == [(2, 10)]


@pytest.mark.asyncio
async def test_initialize_fails_bounded_when_indexing_stalls(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """initialize() must raise IndexingStallError instead of hanging forever."""
    pipeline_module, storage_module, _ = _llamaindex_modules()
    pipeline = _make_pipeline(tmp_path, monkeypatch)

    def _blocking_create_index(*args, **kwargs):
        del args, kwargs
        time.sleep(5)

    monkeypatch.setattr(storage_module, "create_index", _blocking_create_index)

    started = time.monotonic()
    with pytest.raises(pipeline_module.IndexingStallError, match="no progress"):
        await pipeline.initialize("kb", ["doc.pdf"])
    assert time.monotonic() - started < 10


@pytest.mark.asyncio
async def test_add_documents_fails_bounded_when_new_index_stalls(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """add_documents() new-index path must also fail bounded on a stall."""
    pipeline_module, storage_module, _ = _llamaindex_modules()
    pipeline = _make_pipeline(tmp_path, monkeypatch)

    def _blocking_create_index(*args, **kwargs):
        del args, kwargs
        time.sleep(5)

    monkeypatch.setattr(storage_module, "create_index", _blocking_create_index)

    started = time.monotonic()
    with pytest.raises(pipeline_module.IndexingStallError, match="no progress"):
        await pipeline.add_documents("kb", ["doc.pdf"])
    assert time.monotonic() - started < 10


@pytest.mark.asyncio
async def test_initialize_succeeds_when_indexing_completes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path must be unaffected by the stall guard."""
    _pipeline_module, storage_module, _ = _llamaindex_modules()
    pipeline = _make_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(storage_module, "create_index", lambda *a, **k: 7)

    assert await pipeline.initialize("kb", ["doc.pdf"]) is True
