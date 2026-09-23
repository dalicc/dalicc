# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""End-to-end solve against a stubbed SPARQL endpoint.

Skipped unless ``hexlite`` is installed (it is inside the container image), so
the rest of the suite stays runnable on a bare checkout.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from app.answersets import extract_answer_sets, parse_atoms
from app.config import get_settings
from app.conflicts import build_conflict_response
from app.solver import run_compatibility, run_dependency_graph

pytestmark = pytest.mark.skipif(
    shutil.which("hexlite") is None, reason="hexlite is not installed"
)

ODRL = "http://www.w3.org/ns/odrl/2/"
DALICC = "https://dalicc.net/ns#"
LIB = "https://dalicc.net/licenselibrary/"

LICENSES = {
    LIB + "A": [
        (LIB + "A", ODRL + "permission", ODRL + "distribute"),
        (LIB + "A", ODRL + "permission", ODRL + "modify"),
    ],
    LIB + "B": [
        (LIB + "B", ODRL + "prohibition", ODRL + "distribute"),
        (LIB + "B", ODRL + "prohibition", ODRL + "derive"),
    ],
    LIB + "C": [(LIB + "C", ODRL + "permission", ODRL + "distribute")],
    # Two licenses that forbid nothing at all and still cannot be combined.
    LIB + "D": [(LIB + "D", ODRL + "permission", ODRL + "ensureExclusivity")],
    LIB + "E": [(LIB + "E", ODRL + "permission", ODRL + "commercialize")],
}
DEPGRAPH = [
    (ODRL + "modify", ODRL + "includedIn", ODRL + "derive"),
    (ODRL + "ensureExclusivity", DALICC + "contradicts", ODRL + "commercialize"),
]


def _envelope(triples):
    return {
        "head": {"link": [], "vars": ["s", "p", "o"]},
        "results": {
            "distinct": False,
            "ordered": True,
            "bindings": [
                {
                    "s": {"type": "uri", "value": s},
                    "p": {"type": "uri", "value": p},
                    "o": {"type": "uri", "value": o},
                }
                for s, p, o in triples
            ],
        },
    }


class _Handler(BaseHTTPRequestHandler):
    def _answer(self, query: str) -> None:
        if "dependencygraph" in query:
            body = _envelope(DEPGRAPH)
        else:
            match = re.search(r"FILTER \(\?s = <([^>]*)>\)", query)
            body = _envelope(LICENSES.get(match.group(1) if match else "", []))
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/sparql-results+json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self._answer(parse_qs(urlparse(self.path).query).get("query", [""])[0])

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        self._answer(parse_qs(raw).get("query", [raw])[0])

    def log_message(self, fmt, *args) -> None:
        return


@pytest.fixture
def stub_sparql(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/sparql"
    monkeypatch.setenv("DALICC_SPARQL_ENDPOINT", endpoint)
    get_settings.cache_clear()
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _solve(licenses):
    result = run_compatibility(licenses)
    blocks = extract_answer_sets(result.stdout)
    assert blocks, f"no answer set in stdout: {result.stdout!r}"
    return build_conflict_response(parse_atoms(blocks[0]))


def test_direct_and_derived_conflict(stub_sparql) -> None:
    response = _solve([LIB + "A", LIB + "B"])
    direct = response["conflicting_statements"]["direct"]
    derived = response["conflicting_statements"]["derived"]
    assert direct["0"]["statement_1"] == [LIB + "A", ODRL + "permission", ODRL + "distribute"]
    assert direct["0"]["statement_2"] == [LIB + "B", ODRL + "prohibition", ODRL + "distribute"]
    assert derived["0"]["statement_1"] == [LIB + "A", ODRL + "permission", ODRL + "modify"]
    assert derived["0"]["statement_2"] == [LIB + "B", ODRL + "prohibition", ODRL + "derive"]
    assert "includedIn" in derived["0"]["reason"]


def test_two_permissions_the_graph_calls_contradictory(stub_sparql) -> None:
    """``dalicc:contradicts`` reaches the answer: exactly one conflict, reported once.

    The relation is directed in the graph; the rule needs no symmetric copy, because
    the two license variables cover either order of the bundle.
    """
    response = _solve([LIB + "D", LIB + "E"])
    assert response["conflicting_statements"]["direct"] == {}
    derived = response["conflicting_statements"]["derived"]
    assert list(derived) == ["0"]
    assert derived["0"]["statement_1"] == [
        LIB + "D", ODRL + "permission", ODRL + "ensureExclusivity"
    ]
    assert derived["0"]["statement_2"] == [
        LIB + "E", ODRL + "permission", ODRL + "commercialize"
    ]
    assert derived["0"]["reason"].startswith("Derived conflict between two permissions.")
    assert DALICC + "contradicts" in derived["0"]["reason"]

    # The same bundle in the other order is the same single conflict.
    assert _solve([LIB + "E", LIB + "D"]) == response


def test_no_conflict(stub_sparql) -> None:
    assert _solve([LIB + "A", LIB + "C"]) == {
        "conflicting_statements": {"direct": {}, "derived": {}}
    }


def test_unknown_license_is_not_an_error(stub_sparql) -> None:
    assert _solve([LIB + "DoesNotExist"]) == {
        "conflicting_statements": {"direct": {}, "derived": {}}
    }


def test_dependency_graph_closure(stub_sparql) -> None:
    result = run_dependency_graph()
    atoms = parse_atoms(extract_answer_sets(result.stdout)[0])
    assert (ODRL + "modify", ODRL + "includedIn", ODRL + "derive") in {a.args for a in atoms}


def test_timeout_maps_to_solver_timeout(stub_sparql) -> None:
    from app.solver import SolverTimeoutError

    with pytest.raises(SolverTimeoutError):
        run_compatibility([LIB + "A", LIB + "B"], timeout_seconds=0.001)
