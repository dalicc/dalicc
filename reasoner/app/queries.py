# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The SPARQL a licence is reduced to facts with.

These templates are the whole of the reasoner's reading of a licence document, so they
live in a module of their own: :mod:`app.plugins.plugins` runs inside the ``hexlite``
subprocess and cannot be imported without ``dlvhex``, and a test that wants to check
what the program is given must be able to read the queries without starting a solver.

Two queries, because an ODRL licence states its rules at two depths:

* the rules hanging on the licence itself -- ``odrl:permission``, ``odrl:prohibition``,
  ``odrl:obligation`` and the licence-wide ``odrl:duty`` -- and the action each names;
* the duties hanging on one of those rules.  Their subject is the rule node, not the
  licence, so the first query cannot reach them.  A duty under a permission is the
  commonest shape in the library and the one the composer's questionnaire writes; the
  composer's expert view writes it too, and the licence documents of the library also
  carry duties under prohibitions and under other duties.

``{from_clause}`` is empty unless ``DALICC_REASONER_RESTRICT_GRAPHS`` is on, and
``{license_iri}`` is an ``IRIREF`` built by :func:`app.iri.sparql_iri_ref`.
"""

from __future__ import annotations

__all__ = [
    "DEPENDENCY_GRAPH_QUERY_TEMPLATE",
    "LICENSE_DUTY_QUERY_TEMPLATE",
    "LICENSE_QUERY_TEMPLATE",
]

LICENSE_QUERY_TEMPLATE = """PREFIX odrl: <http://www.w3.org/ns/odrl/2/>
SELECT DISTINCT ?s ?p ?o
{from_clause}WHERE {{
  ?s ?p ?o1 .
  ?o1 odrl:action ?o .
  FILTER (?s = {license_iri}) .
  FILTER (?p IN (odrl:permission, odrl:prohibition, odrl:obligation, odrl:duty)) .
}}
"""

LICENSE_DUTY_QUERY_TEMPLATE = """PREFIX odrl: <http://www.w3.org/ns/odrl/2/>
SELECT DISTINCT ?s ?p ?ra ?da
{from_clause}WHERE {{
  ?s ?p ?rule .
  ?rule odrl:action ?ra .
  ?rule odrl:duty ?duty .
  ?duty odrl:action ?da .
  FILTER (?s = {license_iri}) .
  FILTER (?p IN (odrl:permission, odrl:prohibition, odrl:obligation, odrl:duty)) .
}}
"""

DEPENDENCY_GRAPH_QUERY_TEMPLATE = """SELECT ?s ?p ?o
FROM {graph_iri}
WHERE {{ ?s ?p ?o }}
"""
