#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Build the model history of the curated license library.

Every curated model in ``licensedata/`` is versioned from 2026-09-15 on: the version
that stood before the content review is archived, and a changelog says what changed and
why.  This script produces that history once, from the repository itself, and is
idempotent: running it twice writes the same bytes.

What it writes
--------------
``licensedata/history/licenses/<id>/v1.ttl``
    The record exactly as commit ``1079c47`` held it, byte for byte.

``licensedata/history/licenses/<id>/changelog.yaml``
    ``{id, title, current_version, entries: [{version, date, reviewer, summary,
    changes: [{action, statement, previous, reason, source}]}]}``.

``licensedata/history/dependencygraph/dg_default-v1.ttl`` and ``changelog.yaml``
    The 41-axiom graph and the pair of axioms review decision 5 removed.

``licensedata/history/vocabulary/dalicc-ns-v1.ttl`` and ``changelog.yaml``
    The vocabulary before the review added its terms.

How the change list is derived
------------------------------
Not from the review records: from the data.  Both versions of a record are parsed and
compared by the canonical form of every statement about the ``odrl:Set`` (blank-node
subtrees rendered order-independently, exactly the way ``scripts/validate_data.py``
compares the two representations of the library).  An added and a removed form that
describe the same predicate and the same ``odrl:action`` are folded into one ``changed``
entry, so a permission that only gained a duty reads as one change and not as two.

Every change is then *annotated*, in this order:

1.  the review state (``dalicc:reviewStatus``, ``dalicc:reviewedOn``) and the port
    metadata (``dalicc:jurisdictionPortOf``, ``dalicc:variantKind``,
    ``dalicc:licenseVersion``), which the consolidation wrote onto every record;
2.  the seventeen library-wide review decisions, recognised with the same rules
    :mod:`apply_decisions` applied them with, so the two can never disagree;
3.  the ``applied`` findings of ``licensedata/reviews/<id>.yaml``, matched by field and
    by the action term the finding names;
4.  anything left over is ``source: manual`` and is listed in the console report.

The three version predicates themselves (``dct:hasVersion``, ``dct:modified``,
``dalicc:versionHistory``) are excluded from the comparison.  They say which version a
record is, not what the model says, and excluding them is what makes a second run of
this script produce the same changelog as the first.

Usage
-----
    python scripts/review/build_history.py             # write history and stamp records
    python scripts/review/build_history.py --dry-run   # report only
    python scripts/review/build_history.py --no-stamp  # history only, leave the records

Afterwards, in this order::

    python scripts/build_licenselibrary.py
    python scripts/validate_data.py --write-usage-counts
    python scripts/validate_data.py
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
import subprocess
import sys

import rdflib
from rdflib.namespace import RDF
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttl_record import Record

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licensedata" / "licenses"
REVIEWS_DIR = REPO_ROOT / "licensedata" / "reviews"
HISTORY_DIR = REPO_ROOT / "licensedata" / "history"
DEPENDENCY_FILE = REPO_ROOT / "licensedata" / "dependencygraph" / "dg_default.ttl"
VOCABULARY_FILE = REPO_ROOT / "licensedata" / "vocabulary" / "dalicc-ns.ttl"

#: The commit that holds the library as it stood before the 2026-09-15 content review.
BASE_COMMIT = "1079c47"
CHANGE_DATE = "2026-09-15"
REVIEWER = "Giray Havur"

LOG = logging.getLogger("build_history")

# ---------------------------------------------------------------------------
# CURIEs
# ---------------------------------------------------------------------------

#: The prefix block every license record shares, plus the two the vocabulary adds.
PREFIXES: tuple[tuple[str, str], ...] = (
    ("dalicclib", "https://dalicc.net/licenselibrary/"),
    ("dalicc", "https://dalicc.net/ns#"),
    ("bpicounty", "http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#"),
    ("cc", "http://creativecommons.org/ns#"),
    ("dcmitype", "http://purl.org/dc/dcmitype/"),
    ("dct", "http://purl.org/dc/terms/"),
    ("foaf", "http://xmlns.com/foaf/0.1/"),
    ("odrl", "http://www.w3.org/ns/odrl/2/"),
    ("osl", "http://opensource.org/licenses/"),
    ("scho", "http://schema.org/"),
    ("spdxlicense", "http://spdx.org/licenses/"),
    ("spdx", "http://spdx.org/rdf/terms#"),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"),
    ("owl", "http://www.w3.org/2002/07/owl#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("skos", "http://www.w3.org/2004/02/skos/core#"),
)

ODRL = rdflib.Namespace("http://www.w3.org/ns/odrl/2/")
DCT = rdflib.Namespace("http://purl.org/dc/terms/")
DALICC = rdflib.Namespace("https://dalicc.net/ns#")
CC = rdflib.Namespace("http://creativecommons.org/ns#")

#: Excluded from every comparison: they record which version a model is, not what it says.
VERSION_PREDICATES = frozenset({DCT.hasVersion, DCT.modified, DALICC.versionHistory})


def curie(iri: str) -> str:
    """Shorten an IRI to the CURIE the library writes, or return it in angle brackets."""
    for prefix, namespace in PREFIXES:
        if iri.startswith(namespace):
            return f"{prefix}:{iri[len(namespace):]}"
    return f"<{iri}>"


def term(node: rdflib.term.Node) -> str:
    """Render one RDF term the way a compact Turtle statement would."""
    if isinstance(node, rdflib.URIRef):
        return curie(str(node))
    if isinstance(node, rdflib.Literal):
        text = str(node).replace("\\", "\\\\").replace('"', '\\"')
        if node.language:
            return f'"{text}"@{node.language}'
        if node.datatype is not None:
            return f'"{text}"^^{curie(str(node.datatype))}'
        return f'"{text}"'
    return str(node)


# ---------------------------------------------------------------------------
# statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Statement:
    """One statement about the license, independent of blank-node identity."""

    #: CURIE of the predicate, e.g. ``odrl:permission``.
    predicate: str
    #: Canonical, order-independent key used to compare two versions.
    key: str
    #: Human rendering, e.g. ``permission odrl:distribute with duties [cc:Attribution]``.
    text: str
    #: The ``odrl:action`` of the node itself, when it has one.
    action: str = ""
    #: The duty actions hanging off the node, sorted.
    duties: tuple[str, ...] = ()


def _subtree(graph: rdflib.Graph, node: rdflib.term.Node, depth: int = 0) -> str:
    """Order-independent rendering of a node and everything below it."""
    if not isinstance(node, rdflib.BNode) or depth > 16:
        return term(node)
    parts = sorted(
        f"{curie(str(p))} {_subtree(graph, o, depth + 1)}"
        for p, o in graph.predicate_objects(node)
    )
    return "[ " + " ; ".join(parts) + " ]"


def _node_action(graph: rdflib.Graph, node: rdflib.term.Node) -> str:
    """The ``odrl:action`` of a blank node, as a CURIE (empty when it has none)."""
    for value in graph.objects(node, ODRL.action):
        return term(value)
    return ""


def _node_duties(graph: rdflib.Graph, node: rdflib.term.Node) -> tuple[str, ...]:
    """The actions of the duties hanging off a blank node, sorted."""
    duties = [
        _node_action(graph, duty) for duty in graph.objects(node, ODRL.duty)
    ]
    return tuple(sorted(duty for duty in duties if duty))


#: How a rule node reads in the change list.
_RULE_WORD = {
    "odrl:permission": "permission",
    "odrl:prohibition": "prohibition",
    "odrl:duty": "duty",
}


def _describe(graph: rdflib.Graph, predicate: str, obj: rdflib.term.Node) -> Statement:
    """Render one ``predicate object`` pair as a :class:`Statement`."""
    key = f"{predicate} {_subtree(graph, obj)}"
    if not isinstance(obj, rdflib.BNode):
        return Statement(predicate=predicate, key=key, text=f"{predicate} {term(obj)}")

    action = _node_action(graph, obj)
    duties = _node_duties(graph, obj)
    word = _RULE_WORD.get(predicate)
    if word and action:
        text = f"{word} {action}"
        if duties:
            text += " with duties [" + ", ".join(duties) + "]"
        return Statement(predicate, key, text, action=action, duties=duties)

    if predicate == "odrl:target":
        types = sorted(term(value) for value in graph.objects(obj, DCT.type))
        text = "target asset types [" + ", ".join(types) + "]" if types else "target (untyped)"
        return Statement(predicate, key, text)

    return Statement(predicate=predicate, key=key, text=f"{predicate} {_subtree(graph, obj)}")


def statements_of(graph: rdflib.Graph, subject: rdflib.term.Node) -> dict[str, Statement]:
    """Every statement about ``subject``, keyed by its canonical form."""
    out: dict[str, Statement] = {}
    for predicate, obj in graph.predicate_objects(subject):
        if predicate in VERSION_PREDICATES or predicate == RDF.type:
            continue
        statement = _describe(graph, curie(str(predicate)), obj)
        out[statement.key] = statement
    return out


def license_subject(graph: rdflib.Graph) -> rdflib.term.Node | None:
    """The one ``odrl:Set`` of a license document."""
    for subject in graph.subjects(RDF.type, ODRL.Set):
        return subject
    return None


# ---------------------------------------------------------------------------
# the change list
# ---------------------------------------------------------------------------


@dataclass
class Change:
    """One line of a changelog entry."""

    action: str
    statement: str
    predicate: str
    previous: str = ""
    term_action: str = ""
    added_duties: tuple[str, ...] = ()
    removed_duties: tuple[str, ...] = ()
    reason: str = ""
    source: str = ""

    def as_yaml(self) -> dict[str, str]:
        """The mapping the changelog file holds."""
        entry: dict[str, str] = {"action": self.action, "statement": self.statement}
        if self.previous:
            entry["previous"] = self.previous
        entry["reason"] = self.reason
        entry["source"] = self.source
        return entry


_ALTERNATIVE = "dct:alternative"


def _pair_key(statement: Statement) -> tuple[str, str]:
    """What makes an added and a removed statement two halves of one change."""
    if statement.action:
        return (statement.predicate, statement.action)
    if statement.predicate == _ALTERNATIVE:
        return (statement.predicate, statement.text.lower())
    return (statement.predicate, "")


def diff_statements(
    old: dict[str, Statement], new: dict[str, Statement]
) -> list[Change]:
    """Compare two versions of one record and fold matching pairs into ``changed``."""
    removed = [s for key, s in old.items() if key not in new]
    added = [s for key, s in new.items() if key not in old]

    by_key: dict[tuple[str, str], tuple[list[Statement], list[Statement]]] = {}
    for statement in removed:
        by_key.setdefault(_pair_key(statement), ([], []))[0].append(statement)
    for statement in added:
        by_key.setdefault(_pair_key(statement), ([], []))[1].append(statement)

    changes: list[Change] = []
    for _key, (gone, fresh) in sorted(by_key.items()):
        while gone and fresh:
            before = gone.pop(0)
            after = fresh.pop(0)
            changes.append(
                Change(
                    action="changed",
                    statement=after.text,
                    predicate=after.predicate,
                    previous=before.text,
                    term_action=after.action,
                    added_duties=tuple(d for d in after.duties if d not in before.duties),
                    removed_duties=tuple(d for d in before.duties if d not in after.duties),
                )
            )
        for statement in gone:
            changes.append(
                Change(
                    action="removed",
                    statement=statement.text,
                    predicate=statement.predicate,
                    term_action=statement.action,
                    removed_duties=statement.duties,
                )
            )
        for statement in fresh:
            changes.append(
                Change(
                    action="added",
                    statement=statement.text,
                    predicate=statement.predicate,
                    term_action=statement.action,
                    added_duties=statement.duties,
                )
            )
    changes.sort(key=lambda change: (change.predicate, change.statement))
    return changes


# ---------------------------------------------------------------------------
# annotation
# ---------------------------------------------------------------------------

REVIEW_STATE_PREDICATES = frozenset({"dalicc:reviewStatus", "dalicc:reviewedOn"})
PORT_PREDICATES = frozenset(
    {
        "dalicc:jurisdictionPortOf",
        "dalicc:translationOf",
        "dalicc:variantKind",
        "dalicc:licenseVersion",
    }
)

CC0_RECORD = "Cc010Universal"
OPEN_DATA_SUBLICENSE_RECORDS = ("OdcOpenDatabaseLicense", "OpenDataCommonsAttributionLicenseV10")
GNU_OR_LATER_RECORDS = ("GPL-2.0-only", "GPL-3.0-only", "LGPL-3.0-only", "AGPL-3.0")
CDDL_RECORD = "CommonDevelopmentAndDistributionLicense10"
ODC_BY_RECORD = "OpenDataCommonsAttributionLicenseV10"
ND_PATTERN = re.compile(r"NoDeriv|Noderiv", re.IGNORECASE)

DECISION_REASONS: dict[int, str] = {
    1: (
        "Review decision 1: every Creative Commons record except the CC0 dedication, plus "
        "the Open Database License and the Open Data Commons Attribution License, forbids "
        "sublicensing in as many words."
    ),
    2: (
        "Review decision 2: a NoDerivatives license grants no right to modify, so the "
        "modification permissions and the duties hanging off them were removed and the "
        "prohibition on derivatives made explicit."
    ),
    5: (
        "Review decision 5: passing the same terms on is the normal way to satisfy a "
        "share-alike condition, not a contradiction of it."
    ),
    6: (
        "Review decision 6: the four GNU records model the '-only' reading, so the "
        "or-later option is recorded as false rather than left unsaid."
    ),
    8: (
        "Review decision 8: the MIT license states one condition and it is not a change "
        "log, so the modification notice duty was removed."
    ),
    9: (
        "Review decision 9: the Open Data Commons Attribution License is attribution only "
        "and imposes no share-alike condition."
    ),
    10: (
        "Review decision 10: sections 3.1 and 3.2 are file-level reciprocity, so the "
        "share-alike duty hangs on the acts that trigger it and relicensing is prohibited, "
        "aligning the record with the Mozilla Public License 2.0."
    ),
    11: (
        "Review decision 11: the record models the generic four-clause text, not the "
        "Berkeley variant, so the advertising clause, the disclaimer and the publisher were "
        "set to the generic wording."
    ),
    13: (
        "Review decision 13: the record is a composer or test fixture rather than a "
        "published license, and says so instead of being deleted."
    ),
    14: (
        "Review decision 14: section 5 of the Georgian port warrants rather than disclaims, "
        "so the clause moved to the additional clauses."
    ),
    15: (
        "Review decision 15: Creative Commons and SPDX both name the port '3.0 United "
        "States'."
    ),
    16: "Review decision 16: the ISO country code in the alternative title is upper case.",
}

REVIEW_STATE_REASON = (
    "Every record records how far it has come in the editorial workflow and when it was "
    "last checked against the legal text."
)
PORT_REASON = (
    "The 2026-09-15 review made the relation between a jurisdiction port and the record it "
    "was adapted from explicit in the data."
)


@dataclass
class RecordContext:
    """What the decision rules need to know about one record."""

    license_id: str
    is_creative_commons: bool
    is_no_derivatives: bool
    review: dict


def _mentions(text: str, needle: str) -> bool:
    """Whether a finding's prose names a term, by CURIE or by local name."""
    if not needle:
        return False
    local = needle.split(":", 1)[-1]
    return needle in text or re.search(rf"\b{re.escape(local)}\b", text) is not None


def _decision(context: RecordContext, change: Change) -> int | None:
    """The library-wide review decision a change comes from, if any."""
    license_id = context.license_id
    predicate = change.predicate
    action = change.term_action

    if predicate == "dalicc:recordStatus":
        return 13
    if predicate == "dalicc:orLaterVersionOption" and license_id in GNU_OR_LATER_RECORDS:
        return 6
    if (
        predicate == "odrl:prohibition"
        and action == "dalicc:sublicense"
        and change.action == "added"
        and (
            (context.is_creative_commons and license_id != CC0_RECORD)
            or license_id in OPEN_DATA_SUBLICENSE_RECORDS
        )
    ):
        return 1
    if context.is_no_derivatives:
        if (
            predicate == "odrl:permission"
            and change.action == "removed"
            and action in {"odrl:modify", "dalicc:ModifiedWorks"}
        ):
            return 2
        if (
            predicate == "odrl:prohibition"
            and change.action == "added"
            and action in {"odrl:derive", "cc:DerivativeWorks"}
        ):
            return 2
    if license_id == "MIT" and "dalicc:modificationNotice" in change.removed_duties:
        return 8
    if (
        license_id == ODC_BY_RECORD
        and predicate == "odrl:duty"
        and change.action == "removed"
        and action == "cc:ShareAlike"
    ):
        return 9
    if license_id == CDDL_RECORD:
        if "cc:ShareAlike" in change.added_duties:
            return 10
        if predicate == "odrl:permission" and action == "dalicc:ChangeLicense":
            return 10
        if predicate == "odrl:prohibition" and action in {
            "dalicc:ChangeLicense",
            "cc:ShareAlike",
        }:
            return 10
    if license_id == "BSD-4-Clause" and predicate in {
        "dalicc:additionalClauses",
        "dalicc:WarrantyDisclaimer",
        "dct:publisher",
    }:
        return 11
    if license_id.endswith("30Georgia") and predicate in {
        "dalicc:WarrantyDisclaimer",
        "dalicc:additionalClauses",
    }:
        return 14
    if license_id.endswith("30UnitedStatesofAmerica") and predicate == "dct:title":
        return 15
    if (
        predicate == _ALTERNATIVE
        and change.action == "changed"
        and change.previous.lower() == change.statement.lower()
    ):
        return 16
    return None


#: Fields a reviewer treats as one question, so a finding about one of them explains a
#: change to another.  Moving a clause from the warranty disclaimer into the additional
#: clauses is recorded once, under the field the text used to sit in; the identification
#: of the license (its SPDX id and the two URLs of its legal text) is one rubric-1 question
#: and a reviewer writes it up under whichever of the three fields prompted it.
FIELD_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "dalicc:WarrantyDisclaimer",
            "dalicc:LiabilityLimitation",
            "dalicc:WarrantyOrLiabilityAcceptance",
            "dalicc:additionalClauses",
            "dalicc:PromotionSpecification",
        }
    ),
    frozenset({"dct:source", "cc:legalcode", "spdx:licenseId"}),
)


def _finding_match(context: RecordContext, change: Change) -> tuple[str, str] | None:
    """The applied review finding a change comes from, as ``(source, reason)``."""
    fields = {change.predicate}
    if change.added_duties or change.removed_duties:
        fields.add("odrl:duty")
    if change.predicate == "odrl:target":
        fields.add("dct:type")
    for group in FIELD_GROUPS:
        if change.predicate in group:
            fields |= set(group)

    wanted = [t for t in (change.term_action, *change.added_duties, *change.removed_duties) if t]
    best: tuple[int, dict] | None = None
    for finding in context.review.get("findings") or []:
        if not isinstance(finding, dict) or finding.get("action") != "applied":
            continue
        field_name = str(finding.get("field") or "").strip()
        prose = f"{finding.get('description') or ''}\n{finding.get('change') or ''}"
        score = 0
        if field_name in fields:
            score += 2
        elif field_name == "record":
            score += 1
        if wanted and any(_mentions(prose, value) for value in wanted):
            score += 3
        elif not wanted and field_name in fields:
            score += 1
        if score < 3:
            continue
        if best is None or score > best[0]:
            best = (score, finding)
    if best is None:
        return None
    finding = best[1]
    rubric = finding.get("rubric")
    field_name = str(finding.get("field") or "record").strip()
    reason = " ".join(str(finding.get("description") or "").split())
    return (f"review-finding {rubric}/{field_name}", reason)


def annotate(context: RecordContext, changes: list[Change]) -> None:
    """Give every change a reason and a source."""
    for change in changes:
        if change.predicate in REVIEW_STATE_PREDICATES:
            change.source, change.reason = "review-state", REVIEW_STATE_REASON
            continue
        if change.predicate in PORT_PREDICATES:
            change.source, change.reason = "ports-metadata", PORT_REASON
            continue
        decision = _decision(context, change)
        if decision is not None:
            change.source = f"consolidation-decision {decision}"
            change.reason = DECISION_REASONS[decision]
            continue
        match = _finding_match(context, change)
        if match is not None:
            change.source, change.reason = match
            continue
        change.source = "manual"
        change.reason = (
            "Recorded by the 2026-09-15 content review without a separate finding of its own."
        )


# ---------------------------------------------------------------------------
# the summary sentence
# ---------------------------------------------------------------------------

CATEGORY_WORDS: dict[str, tuple[str, str]] = {
    "odrl:permission": ("permission", "permissions"),
    "odrl:prohibition": ("prohibition", "prohibitions"),
    "odrl:duty": ("license-wide duty", "license-wide duties"),
    "odrl:target": ("asset target", "asset targets"),
    _ALTERNATIVE: ("alternative title", "alternative titles"),
}
CLAUSE_PREDICATES = frozenset(
    {
        "dalicc:WarrantyDisclaimer",
        "dalicc:LiabilityLimitation",
        "dalicc:WarrantyOrLiabilityAcceptance",
        "dalicc:additionalClauses",
        "dalicc:PromotionSpecification",
    }
)
IDENTIFICATION_PREDICATES = frozenset(
    {
        "spdx:licenseId",
        "dct:source",
        "cc:legalcode",
        "dct:title",
        "dct:publisher",
        "cc:attributionName",
        "foaf:logo",
        "foaf:img",
    }
)


def _plural(count: int, singular: str, plural: str) -> str:
    """``1 permission`` / ``3 permissions``."""
    return f"{count} {singular if count == 1 else plural}"


def summarise(changes: list[Change]) -> str:
    """One sentence naming the categories of change, for the changelog entry."""
    buckets: Counter[tuple[str, str]] = Counter()
    flags: set[str] = set()
    for change in changes:
        if change.predicate in REVIEW_STATE_PREDICATES:
            flags.add("review")
            continue
        if change.predicate in PORT_PREDICATES:
            flags.add("ports")
            continue
        if change.predicate in CLAUSE_PREDICATES:
            buckets[(change.action, "clause")] += 1
            continue
        if change.predicate in IDENTIFICATION_PREDICATES:
            buckets[(change.action, "identification")] += 1
            continue
        if change.predicate in CATEGORY_WORDS:
            buckets[(change.action, change.predicate)] += 1
            continue
        buckets[(change.action, "statement")] += 1

    words = {
        "clause": ("clause text", "clause texts"),
        "identification": ("identification detail", "identification details"),
        "statement": ("statement", "statements"),
        **CATEGORY_WORDS,
    }
    clauses: list[str] = []
    for verb in ("added", "removed", "changed"):
        parts = [
            _plural(count, *words[kind])
            for (action, kind), count in sorted(buckets.items())
            if action == verb
        ]
        if parts:
            clauses.append(f"{verb} " + _join(parts))
    if "ports" in flags:
        clauses.append("recorded the relation to the record this one was adapted from")
    if "review" in flags:
        clauses.append("recorded the review state")
    if not clauses:
        return f"The content review of {CHANGE_DATE} left the model unchanged."
    return f"The content review of {CHANGE_DATE} " + _join(clauses) + "."


def _join(parts: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def git_show(path: str) -> str | None:
    """The content of ``path`` at :data:`BASE_COMMIT`, or ``None`` when it did not exist."""
    result = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8")


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------


def dump_yaml(payload: dict) -> str:
    """Serialise a changelog the way the review records are serialised."""
    return yaml.safe_dump(
        payload, sort_keys=False, allow_unicode=True, default_flow_style=False, width=96
    )


def write_if_changed(path: Path, text: str, *, dry_run: bool) -> bool:
    """Write ``text`` to ``path`` when it differs; return whether it would change."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    return True


# ---------------------------------------------------------------------------
# the licenses
# ---------------------------------------------------------------------------


@dataclass
class Outcome:
    """What the sweep did, for the console report."""

    versioned: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    sources: Counter[str] = field(default_factory=Counter)
    manual: list[str] = field(default_factory=list)
    files: int = 0


def _context(license_id: str, graph: rdflib.Graph, review: dict) -> RecordContext:
    """Assemble what the decision rules need, with the rules apply_decisions used."""
    subject = license_subject(graph)
    legalcodes = [str(v) for v in graph.objects(subject, CC.legalcode)]
    titles = [str(v) for v in graph.objects(subject, DCT.title)]
    family = str((review or {}).get("family") or "")
    is_nd = (
        bool(ND_PATTERN.search(license_id))
        or any(ND_PATTERN.search(title) for title in titles)
        or bool(re.search(r"\bNC-ND\b|\bND\b", family))
    )
    return RecordContext(
        license_id=license_id,
        is_creative_commons=any("creativecommons.org" in url for url in legalcodes),
        is_no_derivatives=is_nd,
        review=review or {},
    )


def build_licenses(outcome: Outcome, *, dry_run: bool) -> dict[str, int]:
    """Archive and describe every record that changed since :data:`BASE_COMMIT`."""
    versions: dict[str, int] = {}
    for path in sorted(LICENSES_DIR.glob("*.ttl")):
        license_id = path.stem
        current_text = path.read_text(encoding="utf-8")
        base_text = git_show(f"licensedata/licenses/{license_id}.ttl")

        current = rdflib.Graph()
        current.parse(data=current_text, format="turtle")
        subject = license_subject(current)
        if subject is None:
            LOG.error("%s: no odrl:Set", license_id)
            continue
        title = next((str(v) for v in current.objects(subject, DCT.title)), license_id)

        if base_text is None:
            versions[license_id] = 1
            outcome.created.append(license_id)
            continue

        base = rdflib.Graph()
        base.parse(data=base_text, format="turtle")
        base_subject = license_subject(base)
        changes = diff_statements(
            statements_of(base, base_subject) if base_subject is not None else {},
            statements_of(current, subject),
        )
        if not changes:
            versions[license_id] = 1
            outcome.unchanged.append(license_id)
            continue

        review_path = REVIEWS_DIR / f"{license_id}.yaml"
        review = {}
        if review_path.is_file():
            review = yaml.safe_load(review_path.read_text(encoding="utf-8")) or {}
        annotate(_context(license_id, current, review), changes)

        for change in changes:
            outcome.sources[change.source.split(" ", 1)[0]] += 1
            if change.source == "manual":
                outcome.manual.append(f"{license_id}: {change.action} {change.statement}")

        folder = HISTORY_DIR / "licenses" / license_id
        if write_if_changed(folder / "v1.ttl", base_text, dry_run=dry_run):
            outcome.files += 1
        payload = {
            "id": license_id,
            "title": title,
            "current_version": 2,
            "entries": [
                {
                    "version": 2,
                    "date": CHANGE_DATE,
                    "reviewer": REVIEWER,
                    "summary": summarise(changes),
                    "changes": [change.as_yaml() for change in changes],
                }
            ],
        }
        if write_if_changed(folder / "changelog.yaml", dump_yaml(payload), dry_run=dry_run):
            outcome.files += 1
        versions[license_id] = 2
        outcome.versioned.append(license_id)
    return versions


# ---------------------------------------------------------------------------
# stamping the records
# ---------------------------------------------------------------------------

LICENSE_VERSION_RE = re.compile(r'^"\d+(?:\.\d+)+"$')


def stamp_records(versions: dict[str, int], *, dry_run: bool) -> int:
    """Write ``dct:hasVersion``, ``dct:modified`` and ``dalicc:versionHistory``.

    A record that already carried ``dct:hasVersion "3.0"`` carried the version of the
    *license text*, which the consolidation added for the jurisdiction ports.  That
    value moves to ``dalicc:licenseVersion`` so that ``dct:hasVersion`` can say which
    version of the *model* a reader is looking at, the way it already does for a
    composed license.
    """
    written = 0
    for path in sorted(LICENSES_DIR.glob("*.ttl")):
        license_id = path.stem
        record = Record.parse(path)
        before = record.render()

        text_version = [
            obj for obj in record.objects("dct:hasVersion") if LICENSE_VERSION_RE.match(obj)
        ] or record.objects("dalicc:licenseVersion")

        # Remove first, then insert: ttl_record places a *new* statement where the
        # library's predicate order says it belongs, so a rebuilt statement is put back
        # in the right place instead of being left wherever an earlier run appended it.
        for predicate in ("dct:hasVersion", "dct:modified", "dalicc:versionHistory",
                          "dalicc:licenseVersion"):
            record.remove_predicate(predicate)
        if text_version:
            record.set_single_object("dalicc:licenseVersion", text_version[0])

        version = versions.get(license_id, 1)
        record.set_single_object("dct:hasVersion", f'"{version}"')
        if version > 1:
            record.set_single_object("dct:modified", f'"{CHANGE_DATE}"^^xsd:date')
        record.set_single_object(
            "dalicc:versionHistory",
            f"<https://dalicc.net/licenselibrary/{license_id}/versions>",
        )
        if record.render() != before:
            if not dry_run:
                record.write()
            written += 1
    return written


# ---------------------------------------------------------------------------
# the dependency graph and the vocabulary
# ---------------------------------------------------------------------------

DEPENDENCY_SUMMARY = (
    "The content review of 2026-09-15 removed the pair of axioms that made a reciprocal "
    "license which also grants sublicensing contradict itself."
)
DEPENDENCY_VERSION_COMMENT = (
    "# Version 2 of the dependency graph, 2026-09-15. Version 1 and the change log are in\n"
    "# licensedata/history/dependencygraph/. Reviewer: Giray Havur.\n"
)


def build_dependency_history(*, dry_run: bool) -> int:
    """Archive the pre-review dependency graph and describe what decision 5 removed."""
    base_text = git_show("licensedata/dependencygraph/dg_default.ttl")
    if base_text is None:
        LOG.error("the dependency graph does not exist at %s", BASE_COMMIT)
        return 0
    folder = HISTORY_DIR / "dependencygraph"
    written = 0
    if write_if_changed(folder / "dg_default-v1.ttl", base_text, dry_run=dry_run):
        written += 1

    base = rdflib.Graph()
    base.parse(data=base_text, format="turtle")
    current = rdflib.Graph()
    current.parse(DEPENDENCY_FILE.as_posix(), format="turtle")

    def forms(graph: rdflib.Graph) -> set[str]:
        return {
            f"{term(s)} {term(p)} {term(o)}"
            for s, p, o in graph
            if isinstance(s, rdflib.URIRef)
        }

    removed = sorted(forms(base) - forms(current))
    added = sorted(forms(current) - forms(base))
    changes = [
        {
            "action": "removed",
            "statement": statement,
            "reason": DECISION_REASONS[5],
            "source": "consolidation-decision 5",
        }
        for statement in removed
    ] + [
        {
            "action": "added",
            "statement": statement,
            "reason": DECISION_REASONS[5],
            "source": "consolidation-decision 5",
        }
        for statement in added
    ]
    payload = {
        "id": "dg_default",
        "title": "DALICC deontic dependency graph",
        "current_version": 2,
        "entries": [
            {
                "version": 2,
                "date": CHANGE_DATE,
                "reviewer": REVIEWER,
                "summary": DEPENDENCY_SUMMARY,
                "changes": changes,
            }
        ],
    }
    if write_if_changed(folder / "changelog.yaml", dump_yaml(payload), dry_run=dry_run):
        written += 1

    # A reader who opens the graph itself must find the pointer to its history.
    text = DEPENDENCY_FILE.read_text(encoding="utf-8")
    if "licensedata/history/dependencygraph/" not in text:
        lines = text.split("\n")
        index = 0
        while index < len(lines) and lines[index].startswith("#"):
            index += 1
        head = "\n".join(lines[:index])
        if head:
            head += "\n"
        updated = head + DEPENDENCY_VERSION_COMMENT + "\n".join(lines[index:])
        if write_if_changed(DEPENDENCY_FILE, updated, dry_run=dry_run):
            written += 1
    return written


#: Terms the model history itself needed, rather than the content review.
MODEL_HISTORY_TERMS = frozenset({"versionHistory", "licenseVersion"})

VOCABULARY_SUMMARY = (
    "The content review of 2026-09-15 defined the terms the license texts need and the "
    "review itself writes, restated the definitions it had taken from the 2022 "
    "documentation and kept the misspelled royalty term as a deprecated alias, and the "
    "model history added the two terms a versioned model needs."
)


def build_vocabulary_history(*, dry_run: bool) -> int:
    """Archive the pre-review vocabulary and describe the terms the review added."""
    base_text = git_show("licensedata/vocabulary/dalicc-ns.ttl")
    if base_text is None:
        LOG.error("the vocabulary does not exist at %s", BASE_COMMIT)
        return 0
    folder = HISTORY_DIR / "vocabulary"
    written = 0
    if write_if_changed(folder / "dalicc-ns-v1.ttl", base_text, dry_run=dry_run):
        written += 1

    base = rdflib.Graph()
    base.parse(data=base_text, format="turtle")
    current = rdflib.Graph()
    current.parse(VOCABULARY_FILE.as_posix(), format="turtle")

    is_defined_by = rdflib.URIRef("http://www.w3.org/2000/01/rdf-schema#isDefinedBy")
    comment = rdflib.URIRef("http://www.w3.org/2000/01/rdf-schema#comment")
    deprecated = rdflib.URIRef("http://www.w3.org/2002/07/owl#deprecated")
    namespace = rdflib.URIRef("https://dalicc.net/ns#")

    old_terms = {str(s) for s in base.subjects(is_defined_by, namespace)}
    new_terms = {str(s) for s in current.subjects(is_defined_by, namespace)}

    changes: list[dict[str, str]] = [
        {
            "action": "changed",
            "statement": 'owl:versionInfo "2.0"',
            "previous": 'owl:versionInfo "1.2.0"',
            "reason": (
                "The vocabulary is versioned like every other curated model: version 1 is "
                "archived next to this change log and owl:priorVersion names it."
            ),
            "source": "model-history",
        }
    ]
    for iri in sorted(new_terms - old_terms):
        if iri.rsplit("#", 1)[-1] in MODEL_HISTORY_TERMS:
            changes.append(
                {
                    "action": "added",
                    "statement": f"term {curie(iri)}",
                    "reason": (
                        "Defined so that a curated model can name the list of its versions "
                        "and so that the version of a license text stays readable next to "
                        "the version of the model of that text."
                    ),
                    "source": "model-history",
                }
            )
            continue
        changes.append(
            {
                "action": "added",
                "statement": f"term {curie(iri)}",
                "reason": (
                    "Defined by the 2026-09-15 content review, which recorded the clause "
                    "the license texts state and the model could not express."
                ),
                "source": "consolidation-decision 8",
            }
        )
    for iri in sorted(new_terms & old_terms):
        subject = rdflib.URIRef(iri)
        old_comment = {str(v) for v in base.objects(subject, comment)}
        new_comment = {str(v) for v in current.objects(subject, comment)}
        if old_comment != new_comment:
            changes.append(
                {
                    "action": "changed",
                    "statement": f"rdfs:comment of {curie(iri)}",
                    "reason": (
                        "The definition was reconciled with the vocabulary documentation "
                        "published in 2022 and with the composer help texts."
                    ),
                    "source": "review-finding 8/vocabulary",
                }
            )
    for subject in sorted(current.subjects(deprecated, rdflib.Literal(True)), key=str):
        if subject in set(base.subjects(deprecated, rdflib.Literal(True))):
            continue
        changes.append(
            {
                "action": "changed",
                "statement": f"{curie(str(subject))} owl:deprecated true",
                "reason": (
                    "The 2022 documentation misspells 'royalty'. The alias keeps "
                    "dereferencing and names its replacement, so data written against the "
                    "published documentation does not break."
                ),
                "source": "review-finding 8/vocabulary",
            }
        )

    payload = {
        "id": "dalicc-ns",
        "title": "DALICC vocabulary",
        "current_version": 2,
        "entries": [
            {
                "version": 2,
                "date": CHANGE_DATE,
                "reviewer": REVIEWER,
                "summary": VOCABULARY_SUMMARY,
                "changes": changes,
            }
        ],
    }
    if write_if_changed(folder / "changelog.yaml", dump_yaml(payload), dry_run=dry_run):
        written += 1
    return written


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Build the history and report what it found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="do not write anything")
    parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="write the history but leave dct:hasVersion and friends alone",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    outcome = Outcome()
    versions = build_licenses(outcome, dry_run=args.dry_run)
    outcome.files += build_dependency_history(dry_run=args.dry_run)
    outcome.files += build_vocabulary_history(dry_run=args.dry_run)

    stamped = 0
    if not args.no_stamp:
        stamped = stamp_records(versions, dry_run=args.dry_run)

    LOG.info("records with a history: %d", len(outcome.versioned))
    LOG.info("records unchanged since %s: %d", BASE_COMMIT, len(outcome.unchanged))
    LOG.info("records created by the review: %d (%s)", len(outcome.created),
             ", ".join(outcome.created) or "none")
    LOG.info("changelog entries by source:")
    for source, count in sorted(outcome.sources.items(), key=lambda kv: (-kv[1], kv[0])):
        LOG.info("  %-24s %d", source, count)
    LOG.info("unmatched ('manual') changes: %d", len(outcome.manual))
    for line in outcome.manual[:40]:
        LOG.warning("  %s", line)
    if len(outcome.manual) > 40:
        LOG.warning("  ... and %d more", len(outcome.manual) - 40)
    LOG.info("history files written: %d, records stamped: %d", outcome.files, stamped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
