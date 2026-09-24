# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The reasoner reads one dependency graph, and that graph is complete.

Until version 8 of the DALICC vocabulary a jurisdiction graph named the core graph with
``dalicc:extendsGraph`` and ``&getDependencyGraph`` followed the link one step.  Every
published graph now holds the axioms and the rules a check under it reads, so the atom
queries one named graph and follows nothing; a graph that still carries the old link is
read as it is, with a warning.  The second half runs ``query.lp`` under plain
``clingo`` over the shipped jurisdiction graphs, read from their files with no link,
and checks that the core graph's adopted rule fires from the graph itself.
"""

from __future__ import annotations

import importlib
import logging
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROGRAM = REPO / "reasoner" / "app" / "programs" / "query.lp"
GRAPHS = REPO / "licensedata" / "dependencygraph"
DALICC = "https://dalicc.net/ns#"
ODRL = "http://www.w3.org/ns/odrl/2/"
EXTENDS = DALICC + "extendsGraph"
CORE = "https://dalicc.net/dependencygraph/dg_default"
ENDORSEMENT = "https://dalicc.net/dependencygraph/rules/endorsement-worldwide"
JURISDICTION_GRAPHS = ("dg_eu", "dg_us", "dg_cn", "dg_gb", "dg_jp", "dg_in", "dg_br")


@pytest.fixture()
def plugins(monkeypatch):
    """The hexlite plugin module with a recording stand-in for ``dlvhex``."""
    emitted: list[tuple[str, str, str]] = []
    stub = types.ModuleType("dlvhex")
    stub.output = emitted.append
    monkeypatch.setitem(sys.modules, "dlvhex", stub)
    module = importlib.import_module("app.plugins.plugins")
    module = importlib.reload(module)
    module.emitted = emitted
    return module


def test_the_atom_queries_one_graph_and_ignores_the_link(plugins, monkeypatch, caplog) -> None:
    asked: list[str] = []
    rows = [
        ["https://dalicc.net/dependencygraph/dg_xx", EXTENDS, CORE],
        [ODRL + "print", ODRL + "includedIn", ODRL + "use"],
    ]

    def graph_triples(_settings, graph_iri):
        asked.append(graph_iri)
        return rows

    monkeypatch.setattr(plugins, "_graph_triples", graph_triples)
    with caplog.at_level(logging.WARNING, logger="dalicc.reasoner.plugins"):
        plugins.getDependencyGraph("dg_default")
    assert len(asked) == 1
    assert [tuple(row) for row in plugins.emitted] == [tuple(row) for row in rows]
    assert "deprecated" in caplog.text


def _graph_facts(graph_id: str) -> list[str]:
    from rdflib import Graph

    graph = Graph().parse((GRAPHS / f"{graph_id}.ttl").as_posix(), format="turtle")
    return [
        'dg("{}","{}","{}").'.format(*(str(term).replace('"', "'") for term in triple))
        for triple in graph
    ]


@pytest.mark.parametrize("graph_id", JURISDICTION_GRAPHS)
def test_a_jurisdiction_graph_carries_the_core_rule_itself(graph_id) -> None:
    """A licence silent about endorsement gets the core rule from the graph alone."""
    clingo = pytest.importorskip("clingo")
    pytest.importorskip("rdflib")
    rules = "\n".join(
        line for line in PROGRAM.read_text(encoding="utf-8").splitlines() if "&get" not in line
    )
    licence = "https://dalicc.net/licenselibrary/Silent"
    facts = [
        *_graph_facts(graph_id),
        f'license("{licence}","{ODRL}permission","{ODRL}use").',
        f'license("{licence.encode().hex()}").',
        f'bundleLicense("{licence}").',
    ]
    control = clingo.Control(["--warn=none"])
    control.add("base", [], rules + "\n" + "\n".join(facts))
    control.ground([("base", [])])
    with control.solve(yield_=True) as handle:
        shown = next(
            (sorted(str(symbol) for symbol in model.symbols(shown=True)) for model in handle),
            [],
        )
    assert any(
        atom.startswith("defaultStatement(") and ENDORSEMENT in atom and "promote" in atom
        for atom in shown
    ), shown
    assert not any(EXTENDS in fact for fact in _graph_facts(graph_id))
