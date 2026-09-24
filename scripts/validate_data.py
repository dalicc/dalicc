#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Validate the DALICC license data. This is the CI gate for ``licensedata/``.

Checks performed
----------------
Errors (exit status 1):

1.  Encoding hygiene -- every ``.ttl`` file is UTF-8 without BOM, LF-only, final newline.
2.  Every ``licensedata/licenses/*.ttl`` parses as Turtle and declares exactly one
    ``odrl:Set``.
3.  The file name equals the local name of that ``odrl:Set`` IRI
    (``licenses/Apache-2.0.ttl`` -> ``dalicclib:Apache-2.0``).
4.  ``licensedata/licenselibrary/licenselibrary.ttl`` parses and holds exactly the same
    licenses as the per-license files, triple for triple.  Blank nodes are compared by a
    canonical form rather than by identity (see :func:`canonical_form`).
5.  Every license carries ``dct:title``, ``odrl:target``, ``odrl:permission`` and
    ``cc:jurisdiction``.
6.  ``licensedata/dependencygraph/dg_default.ttl`` parses, uses only the
    ``https://dalicc.net/ns#`` namespace for DALICC terms (never plain ``http://``) and
    uses only the four known dependency relations.
7.  ``licensedata/vocabulary/dalicc-ns.ttl`` parses, and every term it marks
    ``owl:deprecated true`` names its replacement with ``dct:isReplacedBy``.  Every
    ``dalicc:`` IRI of the records, the dependency graphs and the difference files, and
    every ``dalicc:`` term the application, the reasoner's programs, the SDK and the
    scripts name, is defined there; a property used with a literal is a datatype
    property and one used with an IRI an object property; every subject and object fits
    the declared ``rdfs:domain`` and ``rdfs:range`` (:func:`vocabulary_use_problems`).
8.  Every ``*.ttl`` that is loaded into Virtuoso has a matching ``*.ttl.graph`` file
    holding an absolute graph IRI.
9.  Every license has a review record in ``licensedata/reviews/`` and every review record
    has a license; each one parses as YAML, carries the keys of ``reviews/README.md`` and
    a known verdict; every license carries ``dalicc:reviewStatus`` and
    ``dalicc:reviewedOn``.
10. ``dalicc:jurisdictionPortOf`` points at a record that exists, no record is a port of
    itself, no parent is itself a port, every port carries ``dalicc:variantKind``, and a
    review record that names a parent has the matching triple in the data.  Every
    ``dalicc:variantKind`` value is a known one, every version-option, exception and rider
    record names its base with ``dalicc:variantOf``, and that base exists.
11. The library-wide decisions of the 2026-09-15 review still hold: no NoDerivatives
    record permits ``odrl:modify`` or ``dalicc:ModifiedWorks`` and every one of them
    prohibits derivatives; every Creative Commons record (except the CC0 dedication)
    plus ODbL and ODC-By prohibits ``dalicc:sublicense``; exactly the two known test
    fixtures carry ``dalicc:recordStatus``.
12. ``cc:ShareAlike dalicc:contradicts odrl:grantUse`` stays out of the dependency graph.

Warnings (reported, do not fail the build):

*   Licenses without ``spdx:licenseId`` / ``dct:source`` / ``cc:legalcode``.
*   ``odrl:action`` values that are neither defined in the DALICC vocabulary nor taken
    from ODRL or Creative Commons (this is how ``odrl:action dct:source`` shows up).
*   ``dalicc:`` terms used in the data but not defined in the vocabulary file.
*   Deprecated vocabulary terms that the data still uses.
*   ``licensedata/vocabulary/usage-counts.json`` out of date (regenerate it with
    ``--write-usage-counts``; the ``/ns`` page reads it for the "used in N licenses"
    column, because parsing the 1.2 MB library at application startup is not worth it).
*   ``licensedata/spdx-mapping.json`` missing or out of date (regenerate it with
    ``python scripts/review/build_spdx_mapping.py``).

Usage
-----
    python scripts/validate_data.py            # validate the repository
    python scripts/validate_data.py -v         # per-file detail
    python scripts/validate_data.py --strict   # treat warnings as errors
    python scripts/validate_data.py --write-usage-counts   # refresh usage-counts.json

Exit status: 0 = clean, 1 = at least one error (or a warning with ``--strict``).
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
from pathlib import Path
import re
import sys

import rdflib
from rdflib.namespace import OWL, RDF, RDFS, Namespace
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "licensedata"
LICENSES_DIR = DATA_DIR / "licenses"
LIBRARY_FILE = DATA_DIR / "licenselibrary" / "licenselibrary.ttl"
DEPENDENCY_FILE = DATA_DIR / "dependencygraph" / "dg_default.ttl"
VOCABULARY_FILE = DATA_DIR / "vocabulary" / "dalicc-ns.ttl"
USAGE_COUNTS_FILE = DATA_DIR / "vocabulary" / "usage-counts.json"
REVIEWS_DIR = DATA_DIR / "reviews"
HISTORY_DIR = DATA_DIR / "history"
SPDX_MAPPING_FILE = DATA_DIR / "spdx-mapping.json"

CC = Namespace("http://creativecommons.org/ns#")
DALICC = Namespace("https://dalicc.net/ns#")
DALICCLIB = Namespace("https://dalicc.net/licenselibrary/")
DCT = Namespace("http://purl.org/dc/terms/")
ODRL = Namespace("http://www.w3.org/ns/odrl/2/")

LEGACY_DALICC_NS = "http://dalicc.net/ns#"
ACTION_NAMESPACES = (str(ODRL), str(CC), str(DALICC))
DEPENDENCY_RELATIONS = {ODRL.includedIn, ODRL.implies, OWL.sameAs, DALICC.contradicts}

#: The predicates a dependency graph may carry beside its four relations.  A
#: dalicc:DefaultRule node says what applies to an action a license is silent about, a
#: dalicc:AxiomRemoval names a core axiom a jurisdiction graph leaves out, and a graph
#: may describe itself and name the graph it was built from.  dalicc:extendsGraph is
#: deprecated in vocabulary version 2 and refused: every graph is complete.
DEPENDENCY_RULE_PREDICATES = {
    rdflib.RDF.type,
    DALICC.appliesTo,
    DALICC.defaultOutcome,
    DALICC.inJurisdiction,
    DALICC.ruleBasis,
    DALICC.ruleExplanation,
    DALICC.ruleStatus,
    DALICC.replacesRule,
    DALICC.basedOnGraph,
    DALICC.basedOnVersion,
    rdflib.RDF.subject,
    rdflib.RDF.predicate,
    rdflib.RDF.object,
    rdflib.RDFS.label,
    DCT.title,
    DCT.description,
    DCT.date,
    DCT.coverage,
    DCT.contributor,
    DCT.dateAccepted,
}

#: The four values a rule may conclude with, and the two states it may be in.
DEPENDENCY_RULE_OUTCOMES = {
    DALICC.NotGrantedByDefault,
    DALICC.GrantedByDefault,
    DALICC.RequiredByDefault,
    DALICC.NotWaivable,
}
DEPENDENCY_RULE_STATUSES = {DALICC.Adopted, DALICC.Proposed}

#: Every dependency graph that ships.  The core graph is the one the reasoner uses
#: when nothing is chosen and the only one that may adopt a rule; the seven
#: jurisdiction graphs are complete graphs generated from it and a difference file.
SHIPPED_DEPENDENCY_GRAPHS = (
    "dg_default", "dg_eu", "dg_us", "dg_cn", "dg_gb", "dg_jp", "dg_in", "dg_br",
)
REQUIRED_PREDICATES = (DCT.title, ODRL.target, ODRL.permission, CC.jurisdiction)
SPDX_LICENSE_ID = rdflib.URIRef("http://spdx.org/rdf/terms#licenseId")

#: Keys every review record must carry, in the order licensedata/reviews/README.md gives.
REVIEW_KEYS = (
    "id", "title", "reviewed_on", "reviewer", "text_source", "text_retrieved",
    "verdict", "summary", "findings", "family", "port_of", "variant_kind", "notes",
)
REVIEW_VERDICTS = {
    "correct", "corrected", "created", "issues-proposed", "text-unavailable",
}

#: The records that are composer and test fixtures rather than published licenses.  They
#: keep their published IRIs and are flagged instead of removed (review decision 13).
TEST_FIXTURE_RECORDS = {"SampleLicenseSl", "DeveloperLicense"}

#: Every value ``dalicc:variantKind`` takes.  The first four say that the record models
#: another text of the same license; the last three say that it models the same text with
#: one thing changed, and each of those three names its base with ``dalicc:variantOf``.
VARIANT_KINDS = {
    "jurisdiction-port", "translation", "version", "edition",
    "version-option", "exception", "rider",
}
#: The kinds that require ``dalicc:variantOf``.
VARIANT_OF_KINDS = {"version-option", "exception", "rider"}

#: CC0 and the Public Domain Dedication and Certification are dedications, so neither
#: carries a sublicensing ban (review decision 1): the dedicator relinquishes the
#: copyright rather than licensing it, so there is nothing to sublicense.
CC_SUBLICENSE_EXEMPT = {"Cc010Universal", "CC-PDDC"}
#: The two data licenses that carry the same express ban as the Creative Commons records.
EXTRA_SUBLICENSE_RECORDS = {"OdcOpenDatabaseLicense", "OpenDataCommonsAttributionLicenseV10"}

#: Removed from the dependency graph on 2026-09-15: passing the same terms on is the
#: normal way to satisfy a share-alike condition, not a contradiction of it.
RETIRED_DEPENDENCY_AXIOMS = (
    (CC.ShareAlike, DALICC.contradicts, ODRL.grantUse),
    (ODRL.grantUse, DALICC.contradicts, CC.ShareAlike),
)

#: Carried by every curated model to say which version of it a reader is looking at.
#: They are excluded from the comparison with the committed version, because they are
#: what a version bump changes: including them would make every record look changed.
VERSION_PREDICATES = (DCT.hasVersion, DCT.modified, DALICC.versionHistory)

RECOMMENDED_PREDICATES = (
    rdflib.URIRef("http://spdx.org/rdf/terms#licenseId"),
    DCT.source,
    CC.legalcode,
)

LOG = logging.getLogger("validate_data")


class Report:
    """Collects errors and warnings and prints a summary."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)
        LOG.error("%s", message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        LOG.warning("%s", message)


def canonical_form(graph: rdflib.Graph, node: rdflib.term.Node, depth: int = 0) -> str:
    """Return a canonical string for ``node`` and everything reachable through blank nodes.

    The DALICC blank-node structure is a tree (every blank node has exactly one incoming
    edge, there are no cycles), so a recursive, order-independent rendering is an exact
    canonical form.  That makes comparing the two representations linear instead of
    running a general graph-isomorphism algorithm over 27,000 triples.
    """
    if not isinstance(node, rdflib.BNode):
        return node.n3()
    if depth > 64:
        raise RecursionError("blank-node nesting deeper than 64 -- cyclic data?")
    parts = sorted(
        f"{p.n3()} {canonical_form(graph, o, depth + 1)}"
        for p, o in graph.predicate_objects(node)
    )
    return "[ " + " ; ".join(parts) + " ]"


def canonical_subject(graph: rdflib.Graph, subject: rdflib.term.Node) -> str:
    """Canonical string for one license: its subject plus its whole blank-node tree."""
    parts = sorted(
        f"{p.n3()} {canonical_form(graph, o)}" for p, o in graph.predicate_objects(subject)
    )
    return f"{subject.n3()} " + " ; ".join(parts) + " ."


def check_encoding(path: Path, report: Report) -> bytes | None:
    """Check BOM / line endings / final newline; return the file bytes or None on error."""
    raw = path.read_bytes()
    ok = True
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error(f"{path.relative_to(REPO_ROOT)}: UTF-8 BOM")
        ok = False
    if b"\r" in raw:
        report.error(f"{path.relative_to(REPO_ROOT)}: CR or CRLF line endings")
        ok = False
    if raw and not raw.endswith(b"\n"):
        report.error(f"{path.relative_to(REPO_ROOT)}: no final newline")
        ok = False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.error(f"{path.relative_to(REPO_ROOT)}: not valid UTF-8 ({exc})")
        ok = False
    return raw if ok else None


def check_graph_file(ttl_path: Path, report: Report) -> None:
    """Every bulk-loaded .ttl needs a sibling .ttl.graph naming an absolute graph IRI."""
    graph_file = ttl_path.with_suffix(ttl_path.suffix + ".graph")
    if not graph_file.exists():
        report.error(f"{ttl_path.relative_to(REPO_ROOT)}: missing {graph_file.name}")
        return
    iri = graph_file.read_text(encoding="utf-8").strip()
    if not iri.startswith(("http://", "https://")):
        report.error(f"{graph_file.relative_to(REPO_ROOT)}: '{iri}' is not an absolute IRI")
    elif "\n" in iri:
        report.error(f"{graph_file.relative_to(REPO_ROOT)}: more than one graph IRI")
    else:
        LOG.debug("%s -> <%s>", ttl_path.name, iri)


def dalicc_terms_in(graph: rdflib.Graph) -> set[str]:
    """Every ``https://dalicc.net/ns#`` IRI that occurs anywhere in ``graph``."""
    return {
        str(node)
        for triple in graph
        for node in triple
        if isinstance(node, rdflib.URIRef) and str(node).startswith(str(DALICC))
    }


def validate_licenses(report: Report) -> tuple[rdflib.Graph, dict[str, str], Counter[str]]:
    """Parse every per-license file.

    Returns the union graph, the canonical form of every license and a counter of how
    many *licenses* mention each ``dalicc:`` term (counted per file, so a term used
    twice in one license still counts once).
    """
    union = rdflib.Graph()
    canonical: dict[str, str] = {}
    per_license: Counter[str] = Counter()
    files = sorted(LICENSES_DIR.glob("*.ttl"))
    if not files:
        report.error(f"{LICENSES_DIR.relative_to(REPO_ROOT)}: no .ttl files found")
        return union, canonical, per_license

    missing: Counter[str] = Counter()
    for path in files:
        if check_encoding(path, report) is None:
            continue
        graph = rdflib.Graph()
        try:
            graph.parse(path, format="turtle")
        except Exception as exc:
            report.error(f"{path.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")
            continue

        subjects = list(graph.subjects(RDF.type, ODRL.Set))
        if len(subjects) != 1:
            report.error(
                f"{path.relative_to(REPO_ROOT)}: expected exactly 1 odrl:Set, found {len(subjects)}"
            )
            continue
        subject = subjects[0]

        if not str(subject).startswith(str(DALICCLIB)):
            report.error(
                f"{path.relative_to(REPO_ROOT)}: <{subject}> is not in the "
                f"{DALICCLIB} namespace"
            )
            continue
        local_name = str(subject)[len(str(DALICCLIB)):]
        if local_name != path.stem:
            report.error(
                f"{path.relative_to(REPO_ROOT)}: file name '{path.stem}' does not match "
                f"the license identifier '{local_name}'"
            )

        for predicate in REQUIRED_PREDICATES:
            if (subject, predicate, None) not in graph:
                report.error(
                    f"{path.relative_to(REPO_ROOT)}: missing required "
                    f"{graph.namespace_manager.normalizeUri(predicate)}"
                )
        for predicate in RECOMMENDED_PREDICATES:
            if (subject, predicate, None) not in graph:
                missing[str(predicate)] += 1

        # An odrl:target without a dct:type is invisible to the faceted search, which
        # filters on the asset type (CC-BY-NC-SA-4.0 has a bare `odrl:target [ ]`).
        for target in graph.objects(subject, ODRL.target):
            if (target, DCT.type, None) not in graph:
                report.warn(
                    f"{path.relative_to(REPO_ROOT)}: odrl:target has no dct:type, so this "
                    f"license never matches an asset-type facet"
                )

        canonical[str(subject)] = canonical_subject(graph, subject)
        per_license.update(dalicc_terms_in(graph))
        union += graph
        LOG.debug("%s: %d triples", path.name, len(graph))

    LOG.info("licenses: %d files, %d triples, %d distinct odrl:Set subjects",
             len(files), len(union), len(canonical))
    for predicate, count in sorted(missing.items()):
        report.warn(
            f"{count} of {len(files)} licenses have no <{predicate}>"
        )
    return union, canonical, per_license


def validate_library(canonical: dict[str, str], report: Report) -> rdflib.Graph:
    """Parse the combined library file and compare it with the per-license files."""
    library = rdflib.Graph()
    if check_encoding(LIBRARY_FILE, report) is None:
        return library
    try:
        library.parse(LIBRARY_FILE, format="turtle")
    except Exception as exc:
        report.error(f"{LIBRARY_FILE.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")
        return library

    subjects = set(library.subjects(RDF.type, ODRL.Set))
    LOG.info("licenselibrary.ttl: %d triples, %d odrl:Set subjects", len(library), len(subjects))

    library_ids = {str(s) for s in subjects}
    file_ids = set(canonical)
    for only_in_library in sorted(library_ids - file_ids):
        report.error(
            f"licenselibrary.ttl contains <{only_in_library}> but there is no "
            f"licenses/*.ttl for it"
        )
    for only_in_files in sorted(file_ids - library_ids):
        report.error(
            f"licenses/*.ttl contains <{only_in_files}> but licenselibrary.ttl does not "
            f"(run: python scripts/build_licenselibrary.py)"
        )

    mismatched = []
    for identifier in sorted(library_ids & file_ids):
        if canonical_subject(library, rdflib.URIRef(identifier)) != canonical[identifier]:
            mismatched.append(identifier)
    if mismatched:
        for identifier in mismatched[:10]:
            report.error(
                f"<{identifier}> differs between licenses/*.ttl and licenselibrary.ttl "
                f"(run: python scripts/build_licenselibrary.py)"
            )
        if len(mismatched) > 10:
            report.error(f"... and {len(mismatched) - 10} more licenses differ")
    elif not (library_ids ^ file_ids):
        LOG.info("licenselibrary.ttl matches licenses/*.ttl triple for triple (%d licenses)",
                 len(file_ids))
    return library


def validate_dependency_graph(report: Report) -> rdflib.Graph:
    """Parse every shipped dependency graph and check what it is allowed to say.

    A graph holds two kinds of statement.  An axiom relates two actions with one of
    the four relations.  A ``dalicc:DefaultRule`` says what applies to an action a
    license is silent about, and carries an action, an outcome, a jurisdiction, a
    basis and a status.  Anything else is refused, because the reasoner would not know
    what to do with it.

    Only the core graph may adopt a rule: a rule that takes part in a check the reader
    did not ask for is a decision of the library.  A jurisdiction graph is complete, so
    it carries the core's adopted rules too, and what it adds is proposed.  It has to be
    exactly what ``scripts/build_dependency_graphs.py`` generates from the core graph
    and its difference file, name the core graph and its current version with
    ``dalicc:basedOnGraph`` and ``dalicc:basedOnVersion``, never hold an axiom it
    records as removed, and never hold two default rules of one kind for one action in
    one territory.  Every rule and every removal carries a basis and an explanation.
    The core graph is the one this function returns, because the rest of the script
    reasons about it.
    """
    core = rdflib.Graph()
    parsed: dict[str, rdflib.Graph] = {}
    for graph_id in SHIPPED_DEPENDENCY_GRAPHS:
        path = DATA_DIR / "dependencygraph" / f"{graph_id}.ttl"
        if not path.is_file():
            report.error(f"licensedata/dependencygraph/{graph_id}.ttl: missing")
            continue
        graph = core if graph_id == "dg_default" else rdflib.Graph()
        if check_encoding(path, report) is None:
            continue
        try:
            graph.parse(path, format="turtle")
        except Exception as exc:
            report.error(f"{path.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")
            continue
        if graph_id != "dg_default":
            parsed[graph_id] = graph
        _check_dependency_graph(graph_id, graph, report)
    core_rules = {
        rule for rule in core.subjects(RDF.type, DALICC.DefaultRule)
    }
    for graph_id, graph in parsed.items():
        _check_generated_graph(graph_id, graph, core_rules, report)
    _check_build(report)
    return core


def _check_dependency_graph(graph_id: str, graph: rdflib.Graph, report: Report) -> None:
    """Check the statements of one dependency graph."""
    name = f"{graph_id}.ttl"
    rules: set[rdflib.term.Node] = set()
    for subject, predicate, obj in graph:
        for node in (subject, predicate, obj):
            if isinstance(node, rdflib.URIRef) and str(node).startswith(LEGACY_DALICC_NS):
                report.error(
                    f"{name}: <{node}> uses the legacy http:// DALICC namespace; "
                    f"use {DALICC}"
                )
        if predicate in DEPENDENCY_RELATIONS:
            continue
        if predicate == DALICC.extendsGraph:
            report.error(
                f"{name}: dalicc:extendsGraph is deprecated; every published graph is "
                "complete and names the graph it was built from with dalicc:basedOnGraph"
            )
            continue
        if predicate not in DEPENDENCY_RULE_PREDICATES:
            report.error(f"{name}: unknown dependency relation <{predicate}>")
            continue
        if predicate == rdflib.RDF.type and obj == DALICC.DefaultRule:
            rules.add(subject)

    axioms = [triple for triple in graph if triple[1] in DEPENDENCY_RELATIONS]
    for rule in sorted(rules, key=str):
        for label, predicate, allowed in (
            ("an action", DALICC.appliesTo, None),
            ("an outcome", DALICC.defaultOutcome, DEPENDENCY_RULE_OUTCOMES),
            ("a jurisdiction", DALICC.inJurisdiction, None),
            ("a basis", DALICC.ruleBasis, None),
            ("an explanation", DALICC.ruleExplanation, None),
            ("a status", DALICC.ruleStatus, DEPENDENCY_RULE_STATUSES),
        ):
            values = list(graph.objects(rule, predicate))
            if len(values) != 1:
                report.error(f"{name}: <{rule}> has to name {label} exactly once")
                continue
            if allowed is not None and values[0] not in allowed:
                report.error(f"{name}: <{rule}> names <{values[0]}>, which is not {label} "
                             f"the reasoner knows")
        adopted = DALICC.Adopted in set(graph.objects(rule, DALICC.ruleStatus))
        if not adopted and graph_id == "dg_default":
            report.error(
                f"{name}: <{rule}> is a proposal, and the core graph carries only "
                f"adopted rules"
            )
    # A graph that every reader can choose is published; what is proposed is each rule,
    # and dalicc:ruleStatus says so.  A title that says "proposal" contradicts that.
    for title in graph.objects(None, DCT.title):
        if "proposal" in str(title).lower():
            report.error(
                f"{name}: the title \"{title}\" says proposal; the status belongs on "
                f"each rule (dalicc:ruleStatus), not in the name of the graph"
            )
    removals = set(graph.subjects(RDF.type, DALICC.AxiomRemoval))
    for removal in sorted(removals, key=str):
        parts = [graph.value(removal, predicate) for predicate in (RDF.subject, RDF.predicate,
                                                                   RDF.object)]
        if None in parts:
            report.error(f"{name}: <{removal}> has to name the axiom it removes in full")
        elif tuple(parts) in graph:
            report.error(f"{name}: <{removal}> removes an axiom the graph still holds")
        for label, predicate in (("a basis", DALICC.ruleBasis),
                                 ("an explanation", DALICC.ruleExplanation)):
            if len(list(graph.objects(removal, predicate))) != 1:
                report.error(f"{name}: <{removal}> has to name {label} exactly once")
    LOG.info("%s: %d axioms over %d relations, %d default rule(s), %d removal(s)",
             name, len(axioms), len({p for _, p, _ in axioms}), len(rules), len(removals))


def _check_generated_graph(
    graph_id: str, graph: rdflib.Graph, core_rules: set, report: Report
) -> None:
    """A jurisdiction graph: its provenance, its adopted rules and its duplicates."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from dalicc_check import depgraph_build
    from dalicc_check.consistency import rules_from_triples

    name = f"{graph_id}.ttl"
    node = rdflib.URIRef(depgraph_build.graph_iri_for(graph_id))
    based_on = list(graph.objects(node, DALICC.basedOnGraph))
    if based_on != [rdflib.URIRef(depgraph_build.graph_iri_for("dg_default"))]:
        report.error(f"{name}: has to name dg_default once with dalicc:basedOnGraph")
    core_version = depgraph_build.file_version(HISTORY_DIR / "dependencygraph", "dg_default")
    versions = [str(value) for value in graph.objects(node, DALICC.basedOnVersion)]
    if versions != [str(core_version["version"])]:
        report.error(
            f"{name}: dalicc:basedOnVersion is {versions or 'missing'}, but the core graph "
            f"is at version {core_version['version']} (run "
            "scripts/build_dependency_graphs.py --bump)"
        )
    for rule in graph.subjects(RDF.type, DALICC.DefaultRule):
        adopted = DALICC.Adopted in set(graph.objects(rule, DALICC.ruleStatus))
        if adopted and rule not in core_rules:
            report.error(
                f"{name}: <{rule}> is adopted, and only the core graph may adopt a rule"
            )
    triples = [(str(s), str(p), str(o)) for s, p, o in graph]
    for problem in depgraph_build.rule_problems(rules_from_triples(triples)):
        report.error(f"{name}: {problem}")


def _check_build(report: Report) -> None:
    """Every generated graph is what the build writes from the core and its difference."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from dalicc_check.depgraph_build import BuildError
    import build_dependency_graphs as build_script

    for graph_id in build_script.difference_ids():
        path = DATA_DIR / "dependencygraph" / f"{graph_id}.ttl"
        try:
            expected = build_script.generate(graph_id)
        except BuildError as exc:
            report.error(f"differences/{graph_id}.ttl: {exc}")
            continue
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            report.error(
                f"{graph_id}.ttl is not what the build generates from dg_default.ttl and "
                f"differences/{graph_id}.ttl (run scripts/build_dependency_graphs.py)"
            )
    missing = sorted(
        set(SHIPPED_DEPENDENCY_GRAPHS) - {"dg_default"} - set(build_script.difference_ids())
    )
    for graph_id in missing:
        report.error(f"licensedata/dependencygraph/differences/{graph_id}.ttl: missing")


def validate_vocabulary(report: Report) -> rdflib.Graph:
    """Parse the DALICC vocabulary file."""
    graph = rdflib.Graph()
    if not VOCABULARY_FILE.exists():
        report.error(f"{VOCABULARY_FILE.relative_to(REPO_ROOT)}: missing")
        return graph
    if check_encoding(VOCABULARY_FILE, report) is None:
        return graph
    try:
        graph.parse(VOCABULARY_FILE, format="turtle")
    except Exception as exc:
        report.error(f"{VOCABULARY_FILE.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")
        return graph
    defined = set(graph.subjects(RDFS.isDefinedBy, DALICC[""]))

    # A deprecated term keeps dereferencing (external data may use its IRI), but it must
    # say what replaces it, and the replacement must itself be a defined term: one of
    # this vocabulary, or an ODRL or Creative Commons action the library uses.
    deprecated = set(graph.subjects(OWL.deprecated, rdflib.Literal(True)))
    for term in sorted(deprecated, key=str):
        replacements = list(graph.objects(term, DCT.isReplacedBy))
        if not replacements:
            report.error(
                f"{VOCABULARY_FILE.name}: <{term}> is owl:deprecated but has no "
                f"dct:isReplacedBy"
            )
            continue
        for replacement in replacements:
            if replacement not in defined and not str(replacement).startswith(
                (str(ODRL), str(CC))
            ):
                report.error(
                    f"{VOCABULARY_FILE.name}: <{term}> dct:isReplacedBy <{replacement}>, "
                    f"which is not defined in this vocabulary"
                )

    LOG.info("dalicc-ns.ttl: %d triples, %d defined terms, %d deprecated",
             len(graph), len(defined), len(deprecated))
    return graph


def validate_vocabulary_coverage(
    licenses: rdflib.Graph,
    dependency: rdflib.Graph,
    vocabulary: rdflib.Graph,
    report: Report,
) -> None:
    """Warn about actions and DALICC terms that the vocabulary does not define."""
    known_actions = set(vocabulary.subjects(RDF.type, ODRL.Action))
    defined_terms = {str(s) for s in vocabulary.subjects(RDFS.isDefinedBy, DALICC[""])}

    actions = Counter(licenses.objects(None, ODRL.action))
    for action, count in sorted(actions.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        if action in known_actions:
            continue
        if str(action).startswith(str(DALICC)):
            report.warn(
                f"odrl:action <{action}> ({count}x) is a DALICC term but is not defined in "
                f"{VOCABULARY_FILE.name}"
            )
        elif not str(action).startswith(ACTION_NAMESPACES):
            report.warn(
                f"odrl:action <{action}> ({count}x) is outside the ODRL, CC and DALICC "
                f"action vocabularies"
            )

    used_terms: set[str] = set()
    for graph in (licenses, dependency):
        for triple in graph:
            for node in triple:
                if isinstance(node, rdflib.URIRef) and str(node).startswith(str(DALICC)):
                    used_terms.add(str(node))
                if isinstance(node, rdflib.URIRef) and str(node).startswith(LEGACY_DALICC_NS):
                    report.error(f"<{node}> uses the legacy http:// DALICC namespace")
    undefined = sorted(used_terms - defined_terms)
    for term in undefined:
        report.warn(f"DALICC term <{term}> is used in the data but not defined in "
                    f"{VOCABULARY_FILE.name}")

    deprecated = {str(s) for s in vocabulary.subjects(OWL.deprecated, rdflib.Literal(True))}
    for term in sorted(used_terms & deprecated):
        replacement = next(
            (str(o) for o in vocabulary.objects(rdflib.URIRef(term), DCT.isReplacedBy)), ""
        )
        report.warn(
            f"DALICC term <{term}> is deprecated but still used in the data"
            + (f"; use <{replacement}> instead" if replacement else "")
        )

    LOG.info("vocabulary: %d of %d DALICC terms used in the data are defined",
             len(used_terms) - len(undefined), len(used_terms))


#: Where the application names ``dalicc:`` terms: Python, templates, scripts and the
#: reasoner's programs.  Scanned by :func:`application_terms`.
APPLICATION_SOURCES = (
    ("app", ("**/*.py", "**/*.html")),
    ("reasoner/app", ("**/*.py", "**/*.lp")),
    ("sdk", ("**/*.py",)),
    ("scripts", ("*.py", "review/*.py")),
)

#: ``dalicc:`` strings in the application that are not vocabulary terms, with the reason.
#: A new entry needs a reason as good as these.
APPLICATION_NON_TERMS = {
    # a URN of the SPARQL property path trick, not the namespace
    "none",
}

_APPLICATION_TERM_RE = re.compile(
    r"(?:\bdalicc:|https://dalicc\.net/ns#)([A-Za-z][A-Za-z0-9]*)\b"
)
#: Python also spells a term ``DALICC + "<name>"``, ``DALICC.<name>`` or
#: ``DALICC["<name>"]``; in a template or a script ``DALICC.`` is the site's JavaScript
#: namespace, so these forms are read in Python files only.
_PYTHON_TERM_RE = re.compile(
    r"(?:\bDALICC\s*\+\s*[\"']|\b_?DALICC\.|\bDALICC\[[\"'])([A-Za-z][A-Za-z0-9]*)\b"
)
#: The reasoner's programs spell a term ``dalicc_<name>``.
_PROGRAM_TERM_RE = re.compile(r"\bdalicc_([A-Za-z][A-Za-z0-9]*)\b")


def application_terms(root: Path = REPO_ROOT) -> dict[str, set[str]]:
    """``{local name: {file, ...}}`` of every ``dalicc:`` term the application names.

    The reasoner's programs spell a term ``dalicc_<name>``; everything else spells it as
    a CURIE, an IRI or ``DALICC + "<name>"``.
    """
    found: dict[str, set[str]] = {}
    for base, patterns in APPLICATION_SOURCES:
        for pattern in patterns:
            for path in sorted((root / base).glob(pattern)):
                if "__pycache__" in path.parts or path.name == "validate_data.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                names = [match.group(1) for match in _APPLICATION_TERM_RE.finditer(text)]
                if path.suffix == ".py":
                    names += [match.group(1) for match in _PYTHON_TERM_RE.finditer(text)]
                if path.suffix == ".lp":
                    names += [match.group(1) for match in _PROGRAM_TERM_RE.finditer(text)]
                for name in names:
                    found.setdefault(name, set()).add(str(path.relative_to(root)))
    return found


def all_dependency_graphs() -> rdflib.Graph:
    """Every shipped dependency graph and every difference file, in one graph."""
    graph = rdflib.Graph()
    folder = DATA_DIR / "dependencygraph"
    for path in sorted(folder.glob("*.ttl")) + sorted((folder / "differences").glob("*.ttl")):
        graph.parse(path, format="turtle")
    return graph


#: Classes whose members stand in for a declared domain or range.
_SUBCLASSES = {
    ODRL.Rule: {ODRL.Permission, ODRL.Prohibition, ODRL.Duty},
    ODRL.Action: {ODRL.Action, DALICC.RuleAction, DALICC.DutyAction},
}

XSD = rdflib.XSD
BPI_COUNTRIES = "http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#"


def _has_class(node: rdflib.term.Node, cls: rdflib.term.Node, data: rdflib.Graph,
               vocabulary: rdflib.Graph) -> bool:
    types = set(data.objects(node, RDF.type)) | set(vocabulary.objects(node, RDF.type))
    if types & _SUBCLASSES.get(cls, {cls}):
        return True
    if cls == ODRL.Action and isinstance(node, rdflib.URIRef) and not types:
        # an action of the ODRL or CC vocabulary, which the data does not type
        return str(node).startswith(ACTION_NAMESPACES)
    # a BPI country is a jurisdiction; the comment of dalicc:inJurisdiction says so
    return cls == DALICC.Jurisdiction and str(node).startswith(BPI_COUNTRIES)


def _literal_fits(value: rdflib.Literal, datatype: rdflib.term.Node) -> bool:
    if datatype == RDF.langString:
        return bool(value.language)
    if datatype == XSD.string:
        return value.language is None and value.datatype in (None, XSD.string)
    return value.datatype == datatype


def vocabulary_use_problems(data: rdflib.Graph, vocabulary: rdflib.Graph,
                            application: dict[str, set[str]] | None = None) -> list[str]:
    """What the data and the application use of the vocabulary that it does not declare.

    * every ``dalicc:`` IRI of the data, and every ``dalicc:`` name the application
      uses, is a defined term;
    * a property used with a literal is a datatype property, one used with an IRI or a
      blank node an object property;
    * every subject of a property with ``rdfs:domain`` is of that class, and every
      object of one with ``rdfs:range`` is of that class or datatype.
    """
    problems: list[str] = []
    defined = {str(s) for s in vocabulary.subjects(RDFS.isDefinedBy, DALICC[""])}
    used = {
        str(node)
        for triple in data
        for node in triple
        if isinstance(node, rdflib.URIRef) and str(node).startswith(str(DALICC))
        and str(node) != str(DALICC)
    }
    for iri in sorted(used - defined):
        problems.append(f"<{iri}> is used in the data but not defined in the vocabulary")
    for name, files in sorted((application or {}).items()):
        if name in APPLICATION_NON_TERMS or str(DALICC) + name in defined:
            continue
        problems.append(f"dalicc:{name} is named in {', '.join(sorted(files)[:3])} "
                        f"but not defined in the vocabulary")

    for prop in sorted(defined):
        predicate = rdflib.URIRef(prop)
        kinds = set(vocabulary.objects(predicate, RDF.type))
        if not kinds & {OWL.DatatypeProperty, OWL.ObjectProperty, OWL.AnnotationProperty}:
            continue
        domains = list(vocabulary.objects(predicate, RDFS.domain))
        ranges = list(vocabulary.objects(predicate, RDFS.range))
        name = "dalicc:" + prop[len(str(DALICC)):]
        for subject, obj in data.subject_objects(predicate):
            if isinstance(obj, rdflib.Literal):
                if OWL.ObjectProperty in kinds:
                    problems.append(f"{name} is an object property but has the literal {obj!r}")
                    break
            elif OWL.DatatypeProperty in kinds:
                problems.append(f"{name} is a datatype property but has the object <{obj}>")
                break
            for domain in domains:
                if not _has_class(subject, domain, data, vocabulary):
                    problems.append(f"{name}: subject {subject} is not a {domain}")
                    break
            for range_ in ranges:
                fits = (
                    _literal_fits(obj, range_)
                    if isinstance(obj, rdflib.Literal)
                    else _has_class(obj, range_, data, vocabulary)
                )
                if not fits:
                    problems.append(f"{name}: object {obj!r} does not fit the range {range_}")
                    break
    return problems


def validate_vocabulary_use(licenses: rdflib.Graph, vocabulary: rdflib.Graph,
                            report: Report) -> None:
    """Every term used is defined, and every use fits the declared domain and range."""
    data = rdflib.Graph()
    data += licenses
    data += all_dependency_graphs()
    problems = vocabulary_use_problems(data, vocabulary, application_terms())
    for problem in problems:
        report.error(problem)
    LOG.info("vocabulary use: %d problem(s)", len(problems))


def load_reviews(report: Report) -> dict[str, dict]:
    """Parse every review record and check that it has the keys the README prescribes."""
    reviews: dict[str, dict] = {}
    if not REVIEWS_DIR.is_dir():
        report.error(f"{REVIEWS_DIR.relative_to(REPO_ROOT)}: missing")
        return reviews
    for path in sorted(REVIEWS_DIR.glob("*.yaml")):
        if check_encoding(path, report) is None:
            continue
        try:
            review = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            report.error(f"{path.relative_to(REPO_ROOT)}: YAML parse error: {exc}")
            continue
        if not isinstance(review, dict):
            report.error(f"{path.relative_to(REPO_ROOT)}: not a mapping")
            continue
        missing = [key for key in REVIEW_KEYS if key not in review]
        if missing:
            report.error(
                f"{path.relative_to(REPO_ROOT)}: review record is missing "
                f"{', '.join(missing)}"
            )
        if review.get("id") != path.stem:
            report.error(
                f"{path.relative_to(REPO_ROOT)}: id '{review.get('id')}' does not match "
                f"the file name"
            )
        if review.get("verdict") not in REVIEW_VERDICTS:
            report.error(
                f"{path.relative_to(REPO_ROOT)}: unknown verdict {review.get('verdict')!r}"
            )
        for finding in review.get("findings") or []:
            if not isinstance(finding, dict):
                report.error(f"{path.relative_to(REPO_ROOT)}: a finding is not a mapping")
                continue
            for key in ("rubric", "severity", "field", "description", "action"):
                if key not in finding:
                    report.error(
                        f"{path.relative_to(REPO_ROOT)}: a finding has no '{key}'"
                    )
        reviews[path.stem] = review
    LOG.info("reviews: %d records", len(reviews))
    return reviews


def validate_review_coverage(
    licenses: rdflib.Graph, canonical: dict[str, str], reviews: dict[str, dict], report: Report
) -> None:
    """Every record has a review record and every review record has a license file."""
    license_ids = {identifier[len(str(DALICCLIB)):] for identifier in canonical}
    for missing in sorted(license_ids - set(reviews)):
        report.error(f"licenses/{missing}.ttl has no reviews/{missing}.yaml")
    for orphan in sorted(set(reviews) - license_ids):
        report.error(f"reviews/{orphan}.yaml has no licenses/{orphan}.ttl")

    for license_id in sorted(license_ids):
        subject = DALICCLIB[license_id]
        if not list(licenses.objects(subject, DALICC.reviewStatus)):
            report.error(f"{license_id}: no dalicc:reviewStatus")
        if not list(licenses.objects(subject, DALICC.reviewedOn)):
            report.error(f"{license_id}: no dalicc:reviewedOn")


def validate_ports(
    licenses: rdflib.Graph, canonical: dict[str, str], reviews: dict[str, dict], report: Report
) -> None:
    """Port relations point at existing records, and no parent is itself a port."""
    license_ids = {identifier[len(str(DALICCLIB)):] for identifier in canonical}
    ports: dict[str, str] = {}
    for license_id in sorted(license_ids):
        subject = DALICCLIB[license_id]
        parents = list(licenses.objects(subject, DALICC.jurisdictionPortOf))
        review_parent = (reviews.get(license_id) or {}).get("port_of")
        if review_parent and not parents:
            report.error(
                f"{license_id}: reviews say port_of {review_parent} but the record has no "
                f"dalicc:jurisdictionPortOf"
            )
        for parent in parents:
            name = str(parent)[len(str(DALICCLIB)):] if str(parent).startswith(str(DALICCLIB)) \
                else str(parent)
            if name not in license_ids:
                report.error(f"{license_id}: dalicc:jurisdictionPortOf <{parent}> does not exist")
                continue
            if name == license_id:
                report.error(f"{license_id}: dalicc:jurisdictionPortOf points at itself")
                continue
            ports[license_id] = name
            if not list(licenses.objects(subject, DALICC.variantKind)):
                report.error(f"{license_id}: is a port but has no dalicc:variantKind")
    for port, parent in sorted(ports.items()):
        if parent in ports:
            report.error(
                f"{port}: its parent {parent} is itself a port of {ports[parent]}; the "
                f"relation must be one level deep"
            )
    LOG.info("ports: %d records under %d parents", len(ports), len(set(ports.values())))


def validate_variants(
    licenses: rdflib.Graph, canonical: dict[str, str], reviews: dict[str, dict], report: Report
) -> None:
    """``dalicc:variantKind`` takes a known value and the flavour kinds name their base.

    A version option, an exception combination and a rider model the same legal text as
    another record with one thing changed, so each of them says which record that is.
    Unlike ``dalicc:jurisdictionPortOf`` the relation may be two steps long: an exception
    on an or-later identifier is a variant of the or-later record, which is itself a
    variant of the ``-only`` one.
    """
    license_ids = {identifier[len(str(DALICCLIB)):] for identifier in canonical}
    counts: Counter[str] = Counter()
    for license_id in sorted(license_ids):
        subject = DALICCLIB[license_id]
        kinds = [str(value) for value in licenses.objects(subject, DALICC.variantKind)]
        bases = list(licenses.objects(subject, DALICC.variantOf))
        for kind in kinds:
            counts[kind] += 1
            if kind not in VARIANT_KINDS:
                report.error(
                    f"{license_id}: dalicc:variantKind '{kind}' is not one of "
                    f"{', '.join(sorted(VARIANT_KINDS))}"
                )
        if set(kinds) & VARIANT_OF_KINDS and not bases:
            report.error(
                f"{license_id}: dalicc:variantKind '{kinds[0]}' but no dalicc:variantOf"
            )
        if bases and not set(kinds) & VARIANT_OF_KINDS:
            report.error(
                f"{license_id}: dalicc:variantOf but no version-option, exception or "
                f"rider dalicc:variantKind"
            )
        for base in bases:
            name = str(base)[len(str(DALICCLIB)):] if str(base).startswith(str(DALICCLIB)) \
                else str(base)
            if name not in license_ids:
                report.error(f"{license_id}: dalicc:variantOf <{base}> does not exist")
            elif name == license_id:
                report.error(f"{license_id}: dalicc:variantOf points at itself")
        review_base = (reviews.get(license_id) or {}).get("variant_of")
        if review_base and not bases:
            report.error(
                f"{license_id}: reviews say variant_of {review_base} but the record has no "
                f"dalicc:variantOf"
            )
    LOG.info("variants: %s", ", ".join(f"{kind} {count}" for kind, count in sorted(counts.items())))


def _actions_of(licenses: rdflib.Graph, subject: rdflib.term.Node, predicate) -> set[str]:
    """The ``odrl:action`` values of every node ``subject predicate`` points at."""
    actions: set[str] = set()
    for node in licenses.objects(subject, predicate):
        for action in licenses.objects(node, ODRL.action):
            actions.add(str(action))
    return actions


def validate_review_decisions(
    licenses: rdflib.Graph, canonical: dict[str, str], report: Report
) -> None:
    """The library-wide decisions of the 2026-09-15 review still hold in the data."""
    license_ids = sorted(identifier[len(str(DALICCLIB)):] for identifier in canonical)
    fixtures = set()
    no_derivatives = 0
    sublicensing = 0
    for license_id in license_ids:
        subject = DALICCLIB[license_id]
        permitted = _actions_of(licenses, subject, ODRL.permission)
        prohibited = _actions_of(licenses, subject, ODRL.prohibition)

        if list(licenses.objects(subject, DALICC.recordStatus)):
            fixtures.add(license_id)

        titles = [str(value) for value in licenses.objects(subject, DCT.title)]
        is_nd = "noderiv" in license_id.lower() or any(
            "noderiv" in title.lower() for title in titles
        )
        if is_nd:
            no_derivatives += 1
            for action in (str(ODRL.modify), str(DALICC.ModifiedWorks)):
                if action in permitted:
                    report.error(
                        f"{license_id}: a NoDerivatives license may not permit <{action}>"
                    )
            if not ({str(ODRL.derive), str(CC.DerivativeWorks)} & prohibited):
                report.error(
                    f"{license_id}: a NoDerivatives license must prohibit odrl:derive or "
                    f"cc:DerivativeWorks"
                )

        legalcodes = [str(value) for value in licenses.objects(subject, CC.legalcode)]
        is_cc = any("creativecommons.org" in url for url in legalcodes)
        needs_sublicense_ban = (
            is_cc and license_id not in CC_SUBLICENSE_EXEMPT
        ) or license_id in EXTRA_SUBLICENSE_RECORDS
        if needs_sublicense_ban:
            if str(DALICC.sublicense) not in prohibited:
                report.error(f"{license_id}: no dalicc:sublicense prohibition")
            else:
                sublicensing += 1

    if fixtures != TEST_FIXTURE_RECORDS:
        for extra in sorted(fixtures - TEST_FIXTURE_RECORDS):
            report.error(f"{extra}: carries dalicc:recordStatus but is not a known fixture")
        for missing in sorted(TEST_FIXTURE_RECORDS - fixtures):
            report.error(f"{missing}: is a test fixture but carries no dalicc:recordStatus")
    LOG.info(
        "review decisions: %d NoDerivatives records, %d sublicensing bans, %d fixtures",
        no_derivatives, sublicensing, len(fixtures),
    )


def _git_show(revision: str, path: str) -> str | None:
    """The content of ``path`` at ``revision``, or ``None`` when git cannot say."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    return None if result.returncode != 0 else result.stdout.decode("utf-8")


def _model_form(graph: rdflib.Graph, subject: rdflib.term.Node) -> str:
    """Canonical form of one license, without the three version predicates."""
    parts = sorted(
        f"{p.n3()} {canonical_form(graph, o)}"
        for p, o in graph.predicate_objects(subject)
        if p not in VERSION_PREDICATES
    )
    return " ; ".join(parts)


def _archived_versions(folder: Path) -> list[int]:
    """The version numbers archived in one history folder, ascending."""
    numbers: list[int] = []
    for path in folder.glob("v*.ttl"):
        stem = path.stem[1:]
        if stem.isdigit():
            numbers.append(int(stem))
    return sorted(numbers)


def _changelog_versions(path: Path, report: Report) -> list[int] | None:
    """The versions a changelog describes, or ``None`` when it cannot be read."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        report.error(f"{path.relative_to(REPO_ROOT)}: cannot be read ({exc})")
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        report.error(f"{path.relative_to(REPO_ROOT)}: no 'entries' list")
        return None
    versions: list[int] = []
    for entry in payload["entries"]:
        if not isinstance(entry, dict):
            report.error(f"{path.relative_to(REPO_ROOT)}: an entry is not a mapping")
            continue
        for key in ("version", "date", "summary", "changes", "reviewer"):
            if key not in entry:
                report.error(f"{path.relative_to(REPO_ROOT)}: an entry has no '{key}'")
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                report.error(f"{path.relative_to(REPO_ROOT)}: a change is not a mapping")
                continue
            for key in ("action", "statement", "reason", "source"):
                if key not in change:
                    report.error(f"{path.relative_to(REPO_ROOT)}: a change has no '{key}'")
        if isinstance(entry.get("version"), int):
            versions.append(entry["version"])
    return sorted(versions)


def _check_modified(
    license_id: str, licenses: rdflib.Graph, changelog_path: Path, version: int, report: Report
) -> None:
    """``dct:modified`` of a record past version 1 is the date of its current version.

    The record page tells a reader that a record changed after its review by comparing
    ``dct:modified`` with ``dalicc:reviewedOn``; a date older than the current version
    hides the change.  ``bump_version.py`` writes both from the same day.
    """
    try:
        payload = yaml.safe_load(changelog_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return
    entry = next((e for e in payload.get("entries") or []
                  if isinstance(e, dict) and e.get("version") == version), None)
    if entry is None:
        return
    dates = [str(v) for v in licenses.objects(DALICCLIB[license_id], DCT.modified)]
    if dates != [str(entry.get("date"))]:
        report.error(
            f"{license_id}: dct:modified is {dates or 'missing'} but version {version} is "
            f"dated {entry.get('date')}; the record must carry the date of its current version"
        )


def validate_history(
    licenses: rdflib.Graph,
    canonical: dict[str, str],
    report: Report,
    *,
    against_git: bool = False,
) -> None:
    """The model history of every curated record is complete and consistent.

    ``dct:hasVersion`` is the number of the version a reader is looking at, so it is
    always one more than the number of versions archived under
    ``licensedata/history/licenses/<id>/``; every archived version parses; and the
    changelog holds exactly one entry per version from 2 upwards.

    With ``--against-git`` (what CI runs) the working tree is also compared with
    ``HEAD``: a record whose model changed must have been versioned, which means a
    higher ``dct:hasVersion`` than the committed one and a changelog entry for it.  A
    record that does not exist at ``HEAD`` yet is new and is version 1.
    """
    license_ids = sorted(identifier[len(str(DALICCLIB)):] for identifier in canonical)
    versioned = 0
    archived_total = 0
    unversioned: list[str] = []
    for license_id in license_ids:
        subject = DALICCLIB[license_id]
        folder = HISTORY_DIR / "licenses" / license_id
        archived = _archived_versions(folder) if folder.is_dir() else []
        archived_total += len(archived)

        values = [str(v) for v in licenses.objects(subject, DCT.hasVersion)]
        if len(values) != 1 or not values[0].isdigit():
            report.error(
                f"{license_id}: dct:hasVersion must be exactly one integer literal, "
                f"found {values or 'nothing'}"
            )
            continue
        version = int(values[0])
        if version > 1:
            versioned += 1

        expected_history = rdflib.URIRef(
            f"https://dalicc.net/licenselibrary/{license_id}/versions"
        )
        if expected_history not in set(licenses.objects(subject, DALICC.versionHistory)):
            report.error(f"{license_id}: no dalicc:versionHistory <{expected_history}>")

        if archived != list(range(1, len(archived) + 1)):
            report.error(
                f"{license_id}: the archived versions are {archived}, expected "
                f"{list(range(1, len(archived) + 1))}"
            )
        if version != len(archived) + 1:
            report.error(
                f"{license_id}: dct:hasVersion is '{version}' but {len(archived)} "
                f"version(s) are archived; expected '{len(archived) + 1}' "
                f"(run: python scripts/review/bump_version.py {license_id} --summary ...)"
            )
        for number in archived:
            path = folder / f"v{number}.ttl"
            if check_encoding(path, report) is None:
                continue
            try:
                rdflib.Graph().parse(path, format="turtle")
            except Exception as exc:
                report.error(f"{path.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")

        changelog_path = folder / "changelog.yaml"
        entries: list[int] = []
        if version > 1 or archived:
            if not changelog_path.is_file():
                report.error(f"{license_id}: {len(archived)} archived version(s) but no changelog")
            else:
                entries = _changelog_versions(changelog_path, report) or []
                expected = list(range(2, version + 1))
                if entries != expected:
                    report.error(
                        f"{license_id}: the changelog describes versions {entries}, "
                        f"expected {expected}"
                    )
                _check_modified(license_id, licenses, changelog_path, version, report)
        elif changelog_path.is_file():
            report.error(f"{license_id}: a changelog but no archived version")

        if not against_git:
            continue
        committed = _git_show("HEAD", f"licensedata/licenses/{license_id}.ttl")
        if committed is None:
            continue  # new record, or no git: version 1 and nothing to compare
        head = rdflib.Graph()
        try:
            head.parse(data=committed, format="turtle")
        except Exception as exc:
            report.error(f"{license_id}: the committed version does not parse ({exc})")
            continue
        head_subjects = list(head.subjects(RDF.type, ODRL.Set))
        if not head_subjects:
            continue
        if _model_form(head, head_subjects[0]) == _model_form(licenses, subject):
            continue
        head_version = next(
            (int(str(v)) for v in head.objects(head_subjects[0], DCT.hasVersion)
             if str(v).isdigit()),
            1,
        )
        if version <= head_version or version not in entries:
            unversioned.append(license_id)

    for license_id in unversioned:
        report.error(
            f"{license_id}: the model changed since HEAD but was not versioned "
            f"(run: python scripts/review/bump_version.py {license_id} --summary \"...\")"
        )
    LOG.info(
        "history: %d record(s) past version 1, %d archived version file(s)%s",
        versioned,
        archived_total,
        ", compared with HEAD" if against_git else "",
    )


def validate_shared_history(report: Report) -> None:
    """The dependency graphs and the vocabulary carry the same kind of history.

    ``dg_default`` and the vocabulary keep ``changelog.yaml``; every other shipped
    dependency graph keeps ``<id>-changelog.yaml`` beside its archived versions in the
    same folder.  A shipped graph that has never been versioned has neither, and that is
    allowed; one that has an archive needs a change log that describes it.
    """
    histories = [("dependencygraph", "dg_default", "changelog.yaml", True)]
    histories += [
        ("dependencygraph", graph_id, f"{graph_id}-changelog.yaml", False)
        for graph_id in SHIPPED_DEPENDENCY_GRAPHS
        if graph_id != "dg_default"
    ]
    histories.append(("vocabulary", "dalicc-ns", "changelog.yaml", True))
    for name, stem, log_name, required in histories:
        folder = HISTORY_DIR / name
        if not folder.is_dir():
            report.error(f"licensedata/history/{name}: missing")
            continue
        archived = sorted(folder.glob(f"{stem}-v*.ttl"))
        if not archived and not required and not (folder / log_name).is_file():
            continue
        if not archived:
            report.error(f"licensedata/history/{name}: no archived version of {stem}")
        for path in archived:
            if check_encoding(path, report) is None:
                continue
            try:
                rdflib.Graph().parse(path, format="turtle")
            except Exception as exc:
                report.error(f"{path.relative_to(REPO_ROOT)}: Turtle parse error: {exc}")
        changelog = folder / log_name
        if not changelog.is_file():
            report.error(f"licensedata/history/{name}/{log_name}: missing")
            continue
        versions = _changelog_versions(changelog, report) or []
        expected = list(range(2, len(archived) + 2))
        if versions != expected:
            report.error(
                f"licensedata/history/{name}/{log_name}: describes versions "
                f"{versions}, expected {expected}"
            )


def validate_retired_axioms(dependency: rdflib.Graph, report: Report) -> None:
    """The share-alike against grant-use contradiction stays out of the dependency graph."""
    for triple in RETIRED_DEPENDENCY_AXIOMS:
        if triple in dependency:
            subject, predicate, obj = triple
            report.error(
                f"dg_default.ttl: <{subject}> <{predicate}> <{obj}> was removed by the "
                f"2026-09-15 review and must not come back"
            )


def validate_spdx_mapping(licenses: rdflib.Graph, canonical: dict[str, str],
                          report: Report) -> None:
    """``licensedata/spdx-mapping.json`` still agrees with the records."""
    if not SPDX_MAPPING_FILE.is_file():
        report.warn(
            f"{SPDX_MAPPING_FILE.relative_to(REPO_ROOT)}: missing "
            f"(run: python scripts/review/build_spdx_mapping.py)"
        )
        return
    try:
        payload = json.loads(SPDX_MAPPING_FILE.read_text(encoding="utf-8"))
    except ValueError as exc:
        report.error(f"{SPDX_MAPPING_FILE.relative_to(REPO_ROOT)}: not valid JSON ({exc})")
        return
    expected = {}
    for identifier in canonical:
        license_id = identifier[len(str(DALICCLIB)):]
        values = sorted(str(v) for v in licenses.objects(DALICCLIB[license_id], SPDX_LICENSE_ID))
        if values:
            expected[license_id] = values[0]
    if payload.get("dalicc_to_spdx") != expected:
        report.warn(
            f"{SPDX_MAPPING_FILE.relative_to(REPO_ROOT)}: out of date "
            f"(run: python scripts/review/build_spdx_mapping.py)"
        )
    else:
        LOG.info("spdx-mapping.json: current (%d of %d records mapped)",
                 len(expected), len(canonical))


def validate_usage_counts(
    licenses: rdflib.Graph,
    dependency: rdflib.Graph,
    vocabulary: rdflib.Graph,
    per_license: Counter[str],
    license_total: int,
    report: Report,
    *,
    write: bool = False,
) -> dict[str, object]:
    """Compute -- and optionally rewrite -- ``vocabulary/usage-counts.json``.

    The ``/ns`` vocabulary page shows how often each term is used.  Parsing the 1.2 MB
    library at application startup just for that would be wasteful, so the counts are
    precomputed here and read from a small JSON file at runtime.  A normal validation run
    only *checks* that the file is current.
    """
    triples: Counter[str] = Counter()
    for triple in licenses:
        for node in triple:
            if isinstance(node, rdflib.URIRef) and str(node).startswith(str(DALICC)):
                triples[str(node)] += 1
    dependency_counts: Counter[str] = Counter()
    for triple in dependency:
        for node in triple:
            if isinstance(node, rdflib.URIRef) and str(node).startswith(str(DALICC)):
                dependency_counts[str(node)] += 1

    known = {str(s) for s in vocabulary.subjects(RDFS.isDefinedBy, DALICC[""])}
    every_term = sorted(known | set(per_license) | set(triples) | set(dependency_counts))
    payload: dict[str, object] = {
        "comment": (
            "Generated by scripts/validate_data.py --write-usage-counts. Do not edit by "
            "hand. `licenses` counts the licensedata/licenses/*.ttl files that mention the "
            "term, `triples` the triples of the license library that do, and "
            "`dependency_graph` the triples of dg_default.ttl that do."
        ),
        "license_total": license_total,
        "terms": {
            iri: {
                "licenses": per_license.get(iri, 0),
                "triples": triples.get(iri, 0),
                "dependency_graph": dependency_counts.get(iri, 0),
            }
            for iri in every_term
        },
    }

    serialised = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    if write:
        USAGE_COUNTS_FILE.write_text(serialised, encoding="utf-8")
        LOG.info("wrote %s (%d terms)", USAGE_COUNTS_FILE.relative_to(REPO_ROOT), len(every_term))
        return payload

    if not USAGE_COUNTS_FILE.exists():
        report.warn(
            f"{USAGE_COUNTS_FILE.relative_to(REPO_ROOT)}: missing "
            f"(run: python scripts/validate_data.py --write-usage-counts)"
        )
    elif USAGE_COUNTS_FILE.read_text(encoding="utf-8") != serialised:
        report.warn(
            f"{USAGE_COUNTS_FILE.relative_to(REPO_ROOT)}: out of date "
            f"(run: python scripts/validate_data.py --write-usage-counts)"
        )
    else:
        LOG.info("usage-counts.json: current (%d terms)", len(every_term))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="per-file detail")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument(
        "--write-usage-counts",
        action="store_true",
        help="rewrite licensedata/vocabulary/usage-counts.json from the data",
    )
    parser.add_argument(
        "--against-git",
        action="store_true",
        help=(
            "also compare every record with HEAD and fail when a changed model was not "
            "versioned (needs the full history: actions/checkout with fetch-depth: 0)"
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    report = Report()

    for ttl in (LIBRARY_FILE, DEPENDENCY_FILE, VOCABULARY_FILE):
        if ttl.exists():
            check_graph_file(ttl, report)

    union, canonical, per_license = validate_licenses(report)
    validate_library(canonical, report)
    dependency = validate_dependency_graph(report)
    vocabulary = validate_vocabulary(report)
    validate_vocabulary_coverage(union, dependency, vocabulary, report)
    validate_vocabulary_use(union, vocabulary, report)
    reviews = load_reviews(report)
    validate_review_coverage(union, canonical, reviews, report)
    validate_ports(union, canonical, reviews, report)
    validate_variants(union, canonical, reviews, report)
    validate_review_decisions(union, canonical, report)
    validate_history(union, canonical, report, against_git=args.against_git)
    validate_shared_history(report)
    validate_retired_axioms(dependency, report)
    validate_spdx_mapping(union, canonical, report)
    validate_usage_counts(
        union,
        dependency,
        vocabulary,
        per_license,
        len(canonical),
        report,
        write=args.write_usage_counts,
    )

    LOG.info("=" * 60)
    LOG.info("validate_data: %d error(s), %d warning(s)", len(report.errors), len(report.warnings))
    if report.errors:
        return 1
    if report.warnings and args.strict:
        LOG.error("--strict: failing because of %d warning(s)", len(report.warnings))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
