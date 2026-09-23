# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""HTTP behaviour: validation, compat flag, error mapping and /healthz."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import health
from app.main import create_app
from app.routers import reasoner as reasoner_router
from app.solver import SolverFailureError, SolverResult, SolverTimeoutError
from tests.conftest import CONFLICT_STDOUT, DEPGRAPH_STDOUT, NO_CONFLICT_STDOUT

APACHE = "https://dalicc.net/licenselibrary/Apache-2.0"
MIT = "https://dalicc.net/licenselibrary/MIT"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _stub_solver(monkeypatch, stdout: str = NO_CONFLICT_STDOUT):
    captured: dict = {}

    def fake_run(licenses, **kwargs):
        captured["licenses"] = list(licenses)
        return SolverResult(stdout, "")

    monkeypatch.setattr(reasoner_router, "run_compatibility", fake_run)
    return captured


# --- request validation -----------------------------------------------------


def test_missing_body_is_422(client) -> None:
    response = client.post("/reasoner/compatibility")
    assert response.status_code == 422
    assert "detail" in response.json()


def test_non_json_body_is_422(client) -> None:
    response = client.post(
        "/reasoner/compatibility",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"licenses": ['https://dalicc.net/x").  #script (python) x #end. license("y']},
        {"licenses": ["https://dalicc.net/x> . ?a ?b ?c . FILTER(?s = <y"]},
        {"licenses": ["Apache-2.0"]},
        {"licenses": ["file:///etc/passwd"]},
        {"licenses": [123]},
        {"licenses": [APACHE, "not an iri"]},
        {"licenses": "not-a-list"},
    ],
)
def test_invalid_licenses_are_422_with_json_detail(client, monkeypatch, payload) -> None:
    called = _stub_solver(monkeypatch)
    response = client.post("/reasoner/compatibility", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert "licenses" not in called, "the solver must not run on invalid input"


def test_valid_licenses_reach_the_solver_unchanged(client, monkeypatch) -> None:
    captured = _stub_solver(monkeypatch)
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE, MIT]})
    assert response.status_code == 200
    assert captured["licenses"] == [APACHE, MIT]


def test_empty_license_list_is_accepted(client, monkeypatch) -> None:
    _stub_solver(monkeypatch)
    response = client.post("/reasoner/compatibility", json={"licenses": []})
    assert response.status_code == 200
    assert response.json() == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_unknown_body_keys_are_ignored(client, monkeypatch) -> None:
    _stub_solver(monkeypatch)
    response = client.post(
        "/reasoner/compatibility", json={"licenses": [APACHE], "userID": "x"}
    )
    assert response.status_code == 200


# --- response shapes --------------------------------------------------------


def test_conflict_response_shape(client, monkeypatch) -> None:
    _stub_solver(monkeypatch, CONFLICT_STDOUT)
    body = client.post("/reasoner/compatibility", json={"licenses": [APACHE, MIT]}).json()
    assert list(body["conflicting_statements"]["direct"]) == ["0"]
    assert body["conflicting_statements"]["direct"]["0"]["reason"] == (
        "Direct permission-prohibition conflict."
    )


def test_no_conflict_returns_the_empty_object_by_default(client, monkeypatch) -> None:
    """An empty answer set ``{}`` has always produced the empty object."""
    _stub_solver(monkeypatch, NO_CONFLICT_STDOUT)
    body = client.post("/reasoner/compatibility", json={"licenses": [APACHE, MIT]}).json()
    assert body == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_no_answer_set_returns_the_legacy_empty_string(client, monkeypatch) -> None:
    """Legacy fall-through: empty stdout used to be serialised as ``""``."""
    _stub_solver(monkeypatch, "")
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE]})
    assert response.status_code == 200
    assert response.json() == ""


def test_no_answer_set_is_normalised_with_the_body_flag(client, monkeypatch) -> None:
    _stub_solver(monkeypatch, "")
    body = client.post(
        "/reasoner/compatibility", json={"licenses": [APACHE], "normalize": True}
    ).json()
    assert body == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_no_answer_set_is_normalised_with_the_compat_header(client, monkeypatch) -> None:
    _stub_solver(monkeypatch, "")
    body = client.post(
        "/reasoner/compatibility",
        json={"licenses": [APACHE]},
        headers={"X-DALICC-Compat": "2"},
    ).json()
    assert body == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_other_compat_header_values_stay_legacy(client, monkeypatch) -> None:
    _stub_solver(monkeypatch, "")
    response = client.post(
        "/reasoner/compatibility",
        json={"licenses": [APACHE]},
        headers={"X-DALICC-Compat": "1"},
    )
    assert response.json() == ""


# --- solver failures --------------------------------------------------------


def test_timeout_is_504(client, monkeypatch) -> None:
    def boom(licenses, **kwargs):
        raise SolverTimeoutError(42)

    monkeypatch.setattr(reasoner_router, "run_compatibility", boom)
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE]})
    assert response.status_code == 504
    assert "42s" in response.json()["detail"]


def test_solver_error_is_502_with_stderr_tail(client, monkeypatch) -> None:
    def boom(licenses, **kwargs):
        raise SolverFailureError(
            "solver exited with status 1", returncode=1, stderr="urllib.error.URLError: nope"
        )

    monkeypatch.setattr(reasoner_router, "run_compatibility", boom)
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE]})
    assert response.status_code == 502
    assert "URLError" in response.json()["detail"]


def test_unexpected_errors_return_json_not_a_bare_500(client, monkeypatch) -> None:
    def boom(licenses, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(reasoner_router, "run_compatibility", boom)
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE]})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}


# --- dependency graph -------------------------------------------------------


def test_dependency_graph_legacy_and_normalized(client, monkeypatch) -> None:
    monkeypatch.setattr(
        reasoner_router, "run_dependency_graph", lambda **kw: SolverResult(DEPGRAPH_STDOUT, "")
    )
    legacy = client.get("/reasoner/dependency_graph").json()
    assert legacy[0][0].startswith('"')
    assert legacy[0][2].endswith('")')

    normalized = client.get("/reasoner/dependency_graph?normalize=true").json()
    assert normalized == [
        [
            "http://www.w3.org/ns/odrl/2/modify",
            "http://www.w3.org/ns/odrl/2/includedIn",
            "http://www.w3.org/ns/odrl/2/derive",
        ]
    ]


def test_dependency_graph_solver_failure_is_502(client, monkeypatch) -> None:
    def boom(**kwargs):
        raise SolverFailureError("solver exited with status 1", returncode=1, stderr="nope")

    monkeypatch.setattr(reasoner_router, "run_dependency_graph", boom)
    assert client.get("/reasoner/dependency_graph").status_code == 502


# --- health -----------------------------------------------------------------


def test_healthz_ok(client, monkeypatch) -> None:
    monkeypatch.setattr(
        health, "probe_hexlite", lambda **kw: {"ok": True, "binary": "hexlite", "detail": "ok"}
    )
    monkeypatch.setattr(
        health, "probe_sparql", lambda *a, **kw: {"ok": True, "endpoint": "x", "detail": "HTTP 200"}
    )
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz_degraded_when_sparql_is_down(client, monkeypatch) -> None:
    monkeypatch.setattr(
        health, "probe_hexlite", lambda **kw: {"ok": True, "binary": "hexlite", "detail": "ok"}
    )
    monkeypatch.setattr(
        health,
        "probe_sparql",
        lambda *a, **kw: {"ok": False, "endpoint": "x", "detail": "unreachable: ConnectionError"},
    )
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["sparql"]["ok"] is False


def test_healthz_503_when_the_solver_is_missing(client, monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "probe_hexlite",
        lambda **kw: {"ok": False, "binary": "hexlite", "detail": "executable not found"},
    )
    monkeypatch.setattr(
        health, "probe_sparql", lambda *a, **kw: {"ok": True, "endpoint": "x", "detail": "HTTP 200"}
    )
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_hexlite_probe_accepts_the_usage_banner_exit_code(monkeypatch) -> None:
    """``hexlite --help`` exits 1 after printing its banner."""

    class _Completed:
        returncode = 1
        stdout = b"usage: hexlite [-h] ...\n"
        stderr = b""

    monkeypatch.setattr(health.subprocess, "run", lambda *a, **kw: _Completed())
    assert health.probe_hexlite(refresh=True)["ok"] is True


def test_hexlite_probe_reports_a_missing_binary(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(health.subprocess, "run", boom)
    probe = health.probe_hexlite(refresh=True)
    assert probe["ok"] is False
    assert probe["detail"] == "executable not found"


def test_hexlite_probe_is_cached(monkeypatch) -> None:
    calls = []

    class _Completed:
        returncode = 0
        stdout = b"usage: hexlite"
        stderr = b""

    def counting(*args, **kwargs):
        calls.append(1)
        return _Completed()

    monkeypatch.setattr(health.subprocess, "run", counting)
    health.probe_hexlite(refresh=True)
    health.probe_hexlite()
    health.probe_hexlite()
    assert len(calls) == 1


def test_sparql_probe_handles_unreachable_endpoints(monkeypatch) -> None:
    import requests

    monkeypatch.setenv("DALICC_SPARQL_ENDPOINT", "http://nowhere.invalid/sparql")
    from app.config import get_settings

    get_settings.cache_clear()

    def boom(*args, **kwargs):
        raise requests.ConnectionError("nope")

    monkeypatch.setattr(requests, "get", boom)
    probe = health.probe_sparql()
    assert probe["ok"] is False
    assert "unreachable" in probe["detail"]


# --- legacy content-type tolerance ------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Content-Type": "application/x-www-form-urlencoded"},
        {"Content-Type": "application/json"},
        {"Content-Type": "application/json; charset=utf-8"},
    ],
)
def test_json_body_is_accepted_regardless_of_content_type(client, monkeypatch, headers) -> None:
    """``requests.post(url, data=<str>)`` sends no Content-Type at all."""
    _stub_solver(monkeypatch)
    response = client.post(
        "/reasoner/compatibility",
        content=f'{{"licenses": ["{APACHE}"]}}'.encode(),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_untyped_non_json_body_is_still_422(client, monkeypatch) -> None:
    _stub_solver(monkeypatch)
    response = client.post("/reasoner/compatibility", content=b"licenses=abc", headers={})
    assert response.status_code == 422
