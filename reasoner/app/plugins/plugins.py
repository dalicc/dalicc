# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""hexlite plugin providing the external atoms used by the DALICC programs.

Loaded by ``hexlite --pluginpath <dir> --plugin plugins`` into a *separate*
process, so this module is imported as a top-level module and bootstraps the
``app`` package onto ``sys.path`` itself (the solver subprocess also gets a
``PYTHONPATH`` pointing at the service root; the bootstrap is a belt-and-braces
fallback for direct ``hexlite`` invocations).

External atoms
--------------
``&getLicense[T](S, P, O)``
    ``T`` is a **hex-encoded** licence IRI (see :mod:`app.iri`).  It is decoded
    and re-validated here, then embedded in a SPARQL ``IRIREF`` with every
    character that could close the reference percent-encoded.  The endpoint and
    the optional ``FROM`` graphs come from configuration, never from the
    request.  Only the rules hanging on the licence itself are returned.
``&getLicenseDuties[T](S, P, RA, DA)``
    The duties that hang on one of those rules rather than on the licence: ``P``
    is the rule's predicate (``odrl:permission``, ``odrl:prohibition``,
    ``odrl:obligation`` or ``odrl:duty``), ``RA`` the rule's action and ``DA`` the
    duty's action.  ``&getLicense`` cannot see these, because its subject is the
    licence and theirs is the rule node, so without this atom every duty a licence
    attaches to a permission was invisible to the program.
``&getDependencyGraph[G](S, P, O)``
    Returns every triple of the configured dependency graph.  ``G`` is only a
    fallback graph *name*; the graph IRI itself is taken from
    ``DALICC_DEPENDENCY_GRAPH``.
``&concat[...](R)``
    String concatenation, kept for backwards compatibility with older programs.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import dlvhex

if __package__ in (None, ""):  # imported as a top-level module by hexlite
    _SERVICE_ROOT = Path(__file__).resolve().parents[2]
    if str(_SERVICE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SERVICE_ROOT))

from app.config import get_settings
from app.iri import decode_license_token, sparql_iri_ref, validate_license_iri
from app.queries import (
    DEPENDENCY_GRAPH_QUERY_TEMPLATE,
    LICENSE_DUTY_QUERY_TEMPLATE,
    LICENSE_QUERY_TEMPLATE,
)

logger = logging.getLogger("dalicc.reasoner.plugins")


def _term_value(term: object) -> str:
    """Return the plain string behind a dlvhex term."""
    value = term
    getter = getattr(term, "value", None)
    if callable(getter):
        value = getter()
    text = value if isinstance(value, str) else str(value)
    return text.strip().strip('"')


def _sparql_client(endpoint: str):
    """Build a per-call SPARQLWrapper (never share one across calls)."""
    from SPARQLWrapper import JSON, SPARQLWrapper

    settings = get_settings()
    client = SPARQLWrapper(endpoint)
    client.setReturnFormat(JSON)
    client.setTimeout(settings.sparql_timeout_seconds)
    client.agent = "dalicc-reasoner/2.0"
    return client


def _select(endpoint: str, query: str, names: tuple[str, ...] = ("s", "p", "o")) -> list[list[str]]:
    client = _sparql_client(endpoint)
    client.setQuery(query)
    results = client.query().convert()
    bindings = results.get("results", {}).get("bindings", [])
    return [
        [row[name]["value"] for name in names]
        for row in bindings
        if all(name in row for name in names)
    ]


def _from_clause(settings) -> str:
    """The ``FROM`` graphs the licence queries use, or nothing at all."""
    if not settings.from_graphs:
        return ""
    return "".join(f"FROM {sparql_iri_ref(graph)}\n" for graph in settings.from_graphs)


def getLicense(strs):  # noqa: N802 - name fixed by the ASP programs
    """Emit ``(subject, deontic predicate, action)`` triples for one licence."""
    settings = get_settings()
    token = _term_value(strs[0])
    license_iri = decode_license_token(token)

    query = LICENSE_QUERY_TEMPLATE.format(
        from_clause=_from_clause(settings),
        license_iri=sparql_iri_ref(license_iri),
    )
    triples = _select(settings.sparql_endpoint, query)
    logger.debug("getLicense(%s) -> %d triples", license_iri, len(triples))
    for subject, predicate, obj in triples:
        dlvhex.output((subject, predicate, obj))


def getLicenseDuties(strs):  # noqa: N802 - name fixed by the ASP programs
    """Emit ``(licence, rule predicate, rule action, duty action)`` for one licence.

    A duty attached to a permission, a prohibition or another duty hangs off that
    rule's node, not off the licence, so :func:`getLicense` never sees it.  Each one
    is reported here with the rule that carries it, so the program can reason about
    "Distribute, with the duty Attribution" without flattening it into a licence-wide
    duty and without losing it.
    """
    settings = get_settings()
    token = _term_value(strs[0])
    license_iri = decode_license_token(token)

    query = LICENSE_DUTY_QUERY_TEMPLATE.format(
        from_clause=_from_clause(settings),
        license_iri=sparql_iri_ref(license_iri),
    )
    rows = _select(settings.sparql_endpoint, query, ("s", "p", "ra", "da"))
    logger.debug("getLicenseDuties(%s) -> %d rows", license_iri, len(rows))
    for subject, predicate, rule_action, duty_action in rows:
        dlvhex.output((subject, predicate, rule_action, duty_action))


def concat(strs):
    """Concatenate string terms (legacy helper, unused by the shipped programs)."""
    needquote = any('"' in term.value() for term in strs)
    result = "".join(term.value().strip('"') for term in strs)
    if needquote:
        result = '"' + result + '"'
    dlvhex.output((dlvhex.storeConstant(result),))


def getDependencyGraph(dp_named_graph):  # noqa: N802 - name fixed by the ASP programs
    """Emit every triple of the configured dependency graph."""
    settings = get_settings()
    graph_iri = settings.dependency_graph
    if not graph_iri:  # pragma: no cover - config always supplies a default
        name = _term_value(dp_named_graph)
        graph_iri = "https://dalicc.net/dependencygraph/" + name
    validate_license_iri(graph_iri)

    query = DEPENDENCY_GRAPH_QUERY_TEMPLATE.format(graph_iri=sparql_iri_ref(graph_iri))
    triples = _select(settings.sparql_endpoint, query)
    logger.debug("getDependencyGraph(%s) -> %d triples", graph_iri, len(triples))
    for subject, predicate, obj in triples:
        dlvhex.output((subject, predicate, obj))


def register(arguments=None):
    """Hexlite entry point: declare the external atoms."""
    prop = dlvhex.ExtSourceProperties()
    prop.addFiniteOutputDomain(0)
    dlvhex.addAtom("getLicense", (dlvhex.TUPLE,), 3, prop)
    dlvhex.addAtom("getLicenseDuties", (dlvhex.TUPLE,), 4, prop)
    dlvhex.addAtom("concat", (dlvhex.TUPLE,), 1, prop)
    dlvhex.addAtom("getDependencyGraph", (dlvhex.CONSTANT,), 3, prop)
