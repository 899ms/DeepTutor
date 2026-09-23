"""Regression tests for learner surfaces and restriction preset changes.

Two failure modes covered:

1. Knowledge Center browsing needs a precise GET allowlist. Admin diagnostics
   and engine configuration endpoints share the same URL prefix.
2. Assigning guardian restrictions to a `standard`-preset account left the
   account in a `standard` preset + `learning_policy` mix: the frontend then
   rendered the full admin shell and every surface request 403'd. The PUT
   restrictions handler now seeds the default policy and flips the preset to
   ``learner``.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers.auth import _learning_surface_for_path


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        # Pre-existing mappings keep working.
        ("/api/reading/materials", "GET", "reading"),
        ("/api/courses", "GET", "reading"),
        ("/api/chat/sessions", "GET", "chat"),
        ("/api/question/generate", "POST", "chat"),
        ("/api/sessions/abc", "GET", "chat"),
        # Mastery Path: the learner's own per-user progress, all methods.
        ("/api/mastery-paths/topics", "GET", "chat"),
        ("/api/mastery-paths/topics/index", "GET", "chat"),
        ("/api/mastery-paths/progress/book-1", "GET", "chat"),
        ("/api/mastery-paths/progress/book-1", "PATCH", "chat"),
        ("/api/mastery-paths/progress/book-1/redo", "POST", "chat"),
        # KB writes stay denied, even when the route is otherwise browsable.
        ("/api/knowledge-bases", "POST", ""),
        ("/api/knowledge-bases/kb1/upload", "POST", ""),
        ("/api/knowledge-bases/kb1/files/a.pdf", "DELETE", ""),
        # Everything else still default-denies.
        ("/api/settings", "GET", ""),
        ("/api/system/status", "GET", ""),
        ("/api/partners", "GET", ""),
        ("/api/memory/overview", "GET", ""),
        ("", "GET", ""),
    ],
)
def test_learning_surface_map(path: str, method: str, expected: str) -> None:
    assert _learning_surface_for_path(path, method) == expected


@pytest.mark.parametrize(
    ("path", "route_path", "expected"),
    [
        ("/api/knowledge-bases", "/api/knowledge-bases", "reading"),
        ("/api/knowledge-bases/kb1", "/api/knowledge-bases/{kb_name}", "reading"),
        ("/api/knowledge-bases/kb1/files", "/api/knowledge-bases/{kb_name}/files", "reading"),
        (
            "/api/knowledge-bases/kb1/files/a.pdf",
            "/api/knowledge-bases/{kb_name}/files/{filename:path}",
            "reading",
        ),
        (
            "/api/knowledge-bases/kb1/file-preview-text/a.pdf",
            "/api/knowledge-bases/{kb_name}/file-preview-text/{filename:path}",
            "reading",
        ),
        ("/api/knowledge-bases/kb1/progress", "/api/knowledge-bases/{kb_name}/progress", "reading"),
        ("/api/knowledge-bases/health", "/api/knowledge-bases/health", ""),
        ("/api/knowledge-bases/configs", "/api/knowledge-bases/configs", ""),
        ("/api/knowledge-bases/default", "/api/knowledge-bases/default", ""),
        (
            "/api/knowledge-bases/rag-pipelines/lightrag/config",
            "/api/knowledge-bases/rag-pipelines/lightrag/config",
            "",
        ),
        ("/api/knowledge-bases/kb1/config", "/api/knowledge-bases/{kb_name}/config", ""),
        (
            "/api/knowledge-bases/kb1/reindex-config",
            "/api/knowledge-bases/{kb_name}/reindex-config",
            "",
        ),
        (
            "/api/knowledge-bases/kb1/linked-folders",
            "/api/knowledge-bases/{kb_name}/linked-folders",
            "",
        ),
        (
            "/api/knowledge-bases/kb1/github-sources",
            "/api/knowledge-bases/{kb_name}/github-sources",
            "",
        ),
        (
            "/api/knowledge-bases/kb1/web-sources",
            "/api/knowledge-bases/{kb_name}/web-sources",
            "",
        ),
    ],
)
def test_learner_kb_get_allowlist(path: str, route_path: str, expected: str) -> None:
    assert _learning_surface_for_path(path, "GET", route_path=route_path) == expected
    if expected:
        assert _learning_surface_for_path(path, "HEAD", route_path=route_path) == ""
        assert _learning_surface_for_path(path, "OPTIONS", route_path=route_path) == ""
        assert _learning_surface_for_path(path, "POST", route_path=route_path) == ""
        assert _learning_surface_for_path(path, "GET") == ""


def test_route_template_is_passed_to_surface_guard(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from deeptutor.api.routers.auth import require_learning_surface
    from deeptutor.multi_user import learning_access

    observed = []
    monkeypatch.setattr(learning_access, "assert_learning_surface", observed.append)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/knowledge-bases/health",
        "headers": [],
        "route": SimpleNamespace(path="/api/knowledge-bases/health"),
    }
    asyncio.run(require_learning_surface(Request(scope), None))
    assert observed == [""]


def test_fastapi_guard_denies_kb_diagnostics_but_allows_browsing(monkeypatch) -> None:
    from deeptutor.api.routers.auth import require_auth, require_learning_surface
    from deeptutor.multi_user import learning_access

    def deny_unmapped(surface: str) -> None:
        if not surface:
            raise PermissionError("denied")

    monkeypatch.setattr(learning_access, "assert_learning_surface", deny_unmapped)
    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: None

    @app.get("/api/knowledge-bases/health", dependencies=[Depends(require_learning_surface)])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/knowledge-bases/{kb_name}", dependencies=[Depends(require_learning_surface)])
    def details(kb_name: str) -> dict[str, str]:
        return {"name": kb_name}

    client = TestClient(app)
    assert client.get("/api/knowledge-bases/health").status_code == 403
    assert client.get("/api/knowledge-bases/kb1").json() == {"name": "kb1"}


def test_put_restrictions_flips_standard_preset_to_learner(
    mu_isolated_root, seed_user, monkeypatch
):
    """PUT restrictions on a standard-preset account seeds the policy and
    flips the account preset to ``learner`` (#1222 preset/policy mix)."""
    import asyncio
    from types import SimpleNamespace

    from deeptutor.api.routers import multi_user
    from deeptutor.api.routers.multi_user import (
        GuardianRestrictionsPayload,
        put_guardian_restrictions,
    )
    from deeptutor.multi_user.grants import load_grant
    from deeptutor.multi_user.identity import get_user_by_id

    # The first account in an empty store is promoted to admin by save_user;
    # seed a bootstrap account first so the learner keeps role="user".
    seed_user("bootstrap-admin")
    record = seed_user("student-standard")
    learner_user_id = record["id"]
    admin = SimpleNamespace(user_id="u_admin", role="admin")

    payload = GuardianRestrictionsPayload(
        age_band="13-15",
        allow_upload=True,
        allowed_surfaces=["chat", "reading"],
        extensions=[],
    )

    original_set_preset = multi_user.set_preset

    def set_preset_after_grant(username: str, preset: str) -> bool:
        assert load_grant(learner_user_id)["learning_policy"]["age_band"] == "13-15"
        return original_set_preset(username, preset)

    monkeypatch.setattr(multi_user, "set_preset", set_preset_after_grant)

    result = asyncio.run(put_guardian_restrictions(learner_user_id, payload, admin))
    assert result["restrictions"]["age_band"] == "13-15"

    _username, updated = get_user_by_id(learner_user_id)
    assert updated.get("preset") == "learner"


def test_failed_grant_save_does_not_change_standard_preset(
    mu_isolated_root, seed_user, monkeypatch
) -> None:
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from deeptutor.api.routers import multi_user
    from deeptutor.multi_user.grants import load_grant
    from deeptutor.multi_user.identity import get_user_by_id

    seed_user("bootstrap-admin")
    record = seed_user("student-standard")
    learner_user_id = record["id"]
    payload = multi_user.GuardianRestrictionsPayload(
        age_band="13-15",
        allow_upload=True,
        allowed_surfaces=["chat", "reading"],
        extensions=[],
    )

    def fail_save_grant(*_args, **_kwargs):
        raise ValueError("Grant store unavailable")

    monkeypatch.setattr(multi_user, "save_grant", fail_save_grant)
    with pytest.raises(HTTPException, match="Grant store unavailable"):
        asyncio.run(
            multi_user.put_guardian_restrictions(
                learner_user_id, payload, SimpleNamespace(user_id="u_admin", role="admin")
            )
        )

    _username, updated = get_user_by_id(learner_user_id)
    assert updated.get("preset") == "standard"
    assert load_grant(learner_user_id).get("learning_policy") is None
