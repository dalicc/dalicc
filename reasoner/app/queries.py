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
    "LICENSE_COMPATIBILITY_QUERY_TEMPLATE",
    "LICENSE_DUTY_QUERY_TEMPLATE",
    "LICENSE_PROFILE_QUERY_TEMPLATE",
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

#: What a licence says about the licence it is a version of, for the share-alike
#: reciprocity rule: its SPDX identifier, the version the record models, whether it
#: offers a later version, the share-alike version qualifier, and the identifier of the
#: licence it is a jurisdiction port of.  Every column is optional, because most records
#: carry only some of them; :mod:`app.profiles` turns the rows into one profile.
LICENSE_PROFILE_QUERY_TEMPLATE = """PREFIX dalicc: <https://dalicc.net/ns#>
PREFIX spdx: <http://spdx.org/rdf/terms#>
SELECT DISTINCT ?id ?version ?orlater ?qualifier ?portid
{from_clause}WHERE {{
  VALUES ?s {{ {license_iri} }}
  OPTIONAL {{ ?s spdx:licenseId ?id . }}
  OPTIONAL {{ ?s dalicc:licenseVersion ?version . }}
  OPTIONAL {{ ?s dalicc:orLaterVersionOption ?orlater . }}
  OPTIONAL {{ ?s dalicc:shareAlikeVersionQualifier ?qualifier . }}
  OPTIONAL {{ ?s dalicc:jurisdictionPortOf ?parent . ?parent spdx:licenseId ?portid . }}
}}
"""

#: The licences a record names with ``dalicc:compatibleWith``, each with the columns of
#: the profile query read from the named record, so that the program can follow one
#: hop (the same licence text, or an "or later" option) from the named licence to a
#: licence of the request.  :mod:`app.profiles` groups the rows by ``?other``.
LICENSE_COMPATIBILITY_QUERY_TEMPLATE = """PREFIX dalicc: <https://dalicc.net/ns#>
PREFIX spdx: <http://spdx.org/rdf/terms#>
SELECT DISTINCT ?other ?id ?version ?orlater ?qualifier ?portid
{from_clause}WHERE {{
  VALUES ?s {{ {license_iri} }}
  ?s dalicc:compatibleWith ?other .
  FILTER(isIRI(?other))
  OPTIONAL {{ ?other spdx:licenseId ?id . }}
  OPTIONAL {{ ?other dalicc:licenseVersion ?version . }}
  OPTIONAL {{ ?other dalicc:orLaterVersionOption ?orlater . }}
  OPTIONAL {{ ?other dalicc:shareAlikeVersionQualifier ?qualifier . }}
  OPTIONAL {{ ?other dalicc:jurisdictionPortOf ?parent . ?parent spdx:licenseId ?portid . }}
}}
"""

DEPENDENCY_GRAPH_QUERY_TEMPLATE = """SELECT ?s ?p ?o
FROM {graph_iri}
WHERE {{ ?s ?p ?o }}
"""
