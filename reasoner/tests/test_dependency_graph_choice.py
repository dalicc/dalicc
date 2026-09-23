# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The per-request dependency graph: validation, and how it reaches the solver.

The reasoner is reachable on its own, so it validates the graph itself rather than
trusting the API service to have done it: the value ends up in a SPARQL ``FROM`` clause
inside the hexlite plugin, and only the two DALICC graph spaces are acceptable there.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.iri import IriValidationError, validate_dependency_graph_iri
from app.main import create_app
from app.routers import reasoner as reasoner_router
from app.solver import SolverResult, dependency_graph_override
from tests.conftest import DEPGRAPH_STDOUT, NO_CONFLICT_STDOUT

APACHE = "https://dalicc.net/licenselibrary/Apache-2.0"
MIT = "https://dalicc.net/licenselibrary/MIT"

CORE = "https://dalicc.net/dependencygraph/dg_strict"
USER = "https://dalicc.net/users/u1/dependencygraphs/g1"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def _stub(monkeypatch, stdout: str = NO_CONFLICT_STDOUT) -> dict:
    captured: dict = {}

    def fake_run(licenses, **kwargs):
        captured["licenses"] = list(licenses)
        captured["kwargs"] = kwargs
        return SolverResult(stdout, "")

    monkeypatch.setattr(reasoner_router, "run_compatibility", fake_run)
    return captured


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize("value", [CORE, USER])
def test_the_two_dalicc_graph_spaces_are_accepted(value: str) -> None:
    assert validate_dependency_graph_iri(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/dependencygraph/dg_default",
        "https://dalicc.net/licenselibrary/",
        "dg_default",
        'https://dalicc.net/dependencygraph/x> . ?a ?b ?c . FILTER(?s = <y',
        "",
    ],
)
def test_anything_else_is_refused(value: str) -> None:
    with pytest.raises(IriValidationError):
        validate_dependency_graph_iri(value)


# --- the request body -------------------------------------------------------


def test_the_body_field_reaches_the_solver(client, monkeypatch) -> None:
    """A valid graph is passed to the solver for that one run."""
    captured = _stub(monkeypatch)
    response = client.post(
        "/reasoner/compatibility",
        json={"licenses": [APACHE, MIT], "dependency_graph": CORE},
    )
    assert response.status_code == 200
    assert captured["kwargs"]["dependency_graph"] == CORE


def test_without_the_field_nothing_is_overridden(client, monkeypatch) -> None:
    """The historical body still produces the historical solver call."""
    captured = _stub(monkeypatch)
    response = client.post("/reasoner/compatibility", json={"licenses": [APACHE, MIT]})
    assert response.status_code == 200
    assert captured["kwargs"]["dependency_graph"] is None
    assert response.json() == {"conflicting_statements": {"direct": {}, "derived": {}}}


def test_an_empty_string_is_the_same_as_nothing(client, monkeypatch) -> None:
    """A client that always sends the key must not be refused for sending it empty."""
    captured = _stub(monkeypatch)
    response = client.post(
        "/reasoner/compatibility", json={"licenses": [APACHE], "dependency_graph": "   "}
    )
    assert response.status_code == 200
    assert captured["kwargs"]["dependency_graph"] is None


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/dependencygraph/x",
        "dg_default",
        'https://dalicc.net/dependencygraph/x").  #script (python) x #end. license("y',
    ],
)
def test_an_unusable_graph_is_422_with_a_reason(client, monkeypatch, value: str) -> None:
    """The solver is never started for a graph the service would not write down."""
    captured = _stub(monkeypatch)
    response = client.post(
        "/reasoner/compatibility",
        json={"licenses": [APACHE], "dependency_graph": value},
    )
    assert response.status_code == 422
    assert "detail" in response.json()
    assert captured == {}


# --- the closure endpoint ---------------------------------------------------


def test_the_closure_endpoint_takes_a_graph(client, monkeypatch) -> None:
    """``?graph=`` computes the closure of another dependency graph."""
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return SolverResult(DEPGRAPH_STDOUT, "")

    monkeypatch.setattr(reasoner_router, "run_dependency_graph", fake_run)
    response = client.get("/reasoner/dependency_graph", params={"graph": CORE})
    assert response.status_code == 200
    assert captured["dependency_graph"] == CORE


def test_the_closure_endpoint_refuses_a_foreign_graph(client, monkeypatch) -> None:
    """The same allow-list as the request body."""
    response = client.get(
        "/reasoner/dependency_graph", params={"graph": "https://example.org/g"}
    )
    assert response.status_code == 422


# --- how the override reaches the plugin ------------------------------------


def test_the_override_is_one_environment_variable(monkeypatch) -> None:
    """The plugin runs in its own process and reads DALICC_DEPENDENCY_GRAPH there."""
    assert dependency_graph_override(None) == {}
    assert dependency_graph_override("") == {}
    assert dependency_graph_override(USER) == {"DALICC_DEPENDENCY_GRAPH": USER}
    with pytest.raises(IriValidationError):
        dependency_graph_override("https://example.org/g")


def test_the_override_does_not_leak_into_this_process(monkeypatch) -> None:
    """Two concurrent requests must not see each other's choice."""
    import os

    from app.solver import _subprocess_env

    monkeypatch.delenv("DALICC_DEPENDENCY_GRAPH", raising=False)
    env = _subprocess_env(dependency_graph_override(CORE))
    assert env["DALICC_DEPENDENCY_GRAPH"] == CORE
    assert "DALICC_DEPENDENCY_GRAPH" not in os.environ


def test_the_subprocess_env_still_carries_the_plugin_path(monkeypatch) -> None:
    """The override must not replace the PYTHONPATH the plugin needs."""
    from app.config import service_root
    from app.solver import _subprocess_env

    env = _subprocess_env(dependency_graph_override(CORE))
    assert str(service_root()) in env["PYTHONPATH"]
