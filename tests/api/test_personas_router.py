"""GET /api/personas merges admin presets for every role (#1534)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from deeptutor.services.persona.service import PersonaService

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional in the CLI-only package
    FastAPI = None
    TestClient = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or TestClient is None, reason="fastapi not installed"
)


@pytest.fixture
def personas_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = importlib.import_module("deeptutor.api.routers.personas")
    workspace = PersonaService(root=tmp_path / "workspace" / "personas")
    admin = PersonaService(root=tmp_path / "admin" / "personas")
    admin.seed_presets()
    monkeypatch.setattr(module, "get_persona_service", lambda: workspace)
    monkeypatch.setattr(module, "_admin_persona_service", lambda: admin)

    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    return TestClient(app), workspace, admin


def _by_name(body: dict) -> dict[str, dict]:
    return {row["name"]: row for row in body["personas"]}


def test_empty_workspace_lists_admin_presets(personas_api) -> None:
    # The #1534 shape: an explicit workspace has no local PERSONA.md files,
    # but the account still has the bundled presets. Admins used to skip the
    # merge and see only Default.
    client, workspace, _admin = personas_api
    assert workspace.list_personas() == []

    body = client.get("/api/personas").json()
    names = _by_name(body)
    assert {"peer", "teacher", "research-assistant"} <= names.keys()
    for name in ("peer", "teacher", "research-assistant"):
        assert names[name]["source"] == "admin"
        assert names[name]["read_only"] is True


def test_workspace_persona_shadows_admin_preset(personas_api) -> None:
    client, workspace, _admin = personas_api
    workspace.create("teacher", "Mine", "Local voice.")

    names = _by_name(client.get("/api/personas").json())
    assert names["teacher"]["source"] == "user"
    assert names["teacher"]["read_only"] is False
    assert names["teacher"]["description"] == "Mine"
    assert names["peer"]["source"] == "admin"


def test_get_persona_falls_back_to_admin_preset(personas_api) -> None:
    client, workspace, _admin = personas_api
    assert workspace.list_personas() == []

    detail = client.get("/api/personas/peer").json()
    assert detail["name"] == "peer"
    assert detail["source"] == "admin"
    assert detail["read_only"] is True
    assert "content" in detail


def test_create_writes_only_to_the_workspace(personas_api) -> None:
    client, workspace, admin = personas_api
    created = client.post(
        "/api/personas",
        json={"name": "coach", "description": "Local", "content": "Stay curious."},
    )
    assert created.status_code == 200, created.text
    assert created.json()["source"] == "user"
    assert {p.name for p in workspace.list_personas()} == {"coach"}
    assert "coach" not in {p.name for p in admin.list_personas()}
