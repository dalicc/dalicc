# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Complete dependency graphs built from the core graph and a difference file.

Every published dependency graph is complete: it holds every axiom and every default
rule a check under it reads, and the reasoner follows no link to another graph.  A
jurisdiction graph is nevertheless written down as a **difference** from the core graph,
because that is what a legal reviewer reads and what changes when a law changes:

``licensedata/dependencygraph/differences/<id>.ttl``
    the graph's own metadata (title, description, the jurisdiction concept as
    ``dct:coverage`` and ``dalicc:basedOnGraph <core>``), the default rules it adds,
    the core axioms it removes (a ``dalicc:AxiomRemoval`` naming the axiom with
    ``rdf:subject``, ``rdf:predicate`` and ``rdf:object``) and the core default rules
    it replaces (a rule with ``dalicc:replacesRule <core rule>``).  Every rule and every
    removal carries a ``dalicc:ruleBasis`` and a ``dalicc:ruleExplanation``.

``licensedata/dependencygraph/<id>.ttl``
    the complete graph :func:`build` generates from the core and the difference:
    the core axioms without the removed ones, the core rules without the replaced ones,
    the added and replacing rules, the removal records (so that the page of the graph
    can say what it removes and why) and the metadata, with
    ``dalicc:basedOnVersion`` naming the core version it was built from.  This is the
    file the loader loads, the site serves and the download hands out.

:func:`extract` turns a complete graph back into a difference, so a jurisdiction graph
edited on the server can be folded back into its difference file.  The two directions
are exact inverses for every shipped graph, and a test holds them to it.

The writer is canonical: the same input always gives the same bytes, so ``--check`` in
``scripts/build_dependency_graphs.py`` can tell a stale file from a current one by
comparing text.  Nothing in a graph is legal advice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import datetime as dt
from pathlib import Path
import re
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.term import Node
import yaml

from dalicc_check import vocab
from dalicc_check.consistency import (
    P_DATE,
    P_EXTENDS_GRAPH,
    P_LABEL,
    P_RDF_TYPE,
    P_RULE_BASIS,
    P_RULE_EXPLANATION,
    P_RULE_STATUS,
    Rule,
    normalise_iri,
    rules_from_triples,
    sorted_rules,
)

__all__ = [
    "CORE_ID",
    "C_AXIOM_REMOVAL",
    "P_BASED_ON_GRAPH",
    "P_BASED_ON_VERSION",
    "P_COVERAGE",
    "BuildError",
    "Difference",
    "GraphSummary",
    "Removal",
    "build",
    "compose",
    "extract",
    "file_version",
    "graph_summary",
    "parse_difference",
    "removals_from_triples",
    "render_complete",
    "render_difference",
    "render_graph",
    "summary_line",
]

_DALICC = vocab.NAMESPACES["dalicc"]
_DCT = "http://purl.org/dc/terms/"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"

P_BASED_ON_GRAPH = _DALICC + "basedOnGraph"
P_BASED_ON_VERSION = _DALICC + "basedOnVersion"
P_COVERAGE = _DCT + "coverage"
P_TITLE = _DCT + "title"
P_DESCRIPTION = _DCT + "description"
C_AXIOM_REMOVAL = _DALICC + "AxiomRemoval"
P_SUBJECT = _RDF + "subject"
P_PREDICATE = _RDF + "predicate"
P_OBJECT = _RDF + "object"

#: The graph every shipped jurisdiction graph is built from.
CORE_ID = "dg_default"

#: Where the shipped graphs are addressed, whatever host a deployment runs on.
GRAPH_NAMESPACE = "https://dalicc.net/dependencygraph/"

#: The four relations of an axiom, in the order the tables use.
_RELATIONS = (
    "http://www.w3.org/ns/odrl/2/includedIn",
    "http://www.w3.org/ns/odrl/2/implies",
    "http://www.w3.org/2002/07/owl#sameAs",
    _DALICC + "contradicts",
)

#: What the build writes itself and :func:`extract` therefore drops from the metadata.
_GENERATED_METADATA = (P_BASED_ON_VERSION, P_DATE)

#: The metadata of a graph node, in the order the writer puts it.
_METADATA_ORDER = (
    P_TITLE,
    P_DESCRIPTION,
    P_COVERAGE,
    P_DATE,
    P_BASED_ON_GRAPH,
    P_BASED_ON_VERSION,
)

#: The prefix block of the core graph file, which every generated file repeats; the
#: BPI country prefix follows only when a statement of the file names a country.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("rdf", _RDF),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("dct", _DCT),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"),
    ("odrl", "http://www.w3.org/ns/odrl/2/"),
    ("cc", "http://creativecommons.org/ns#"),
    ("dalicc", _DALICC),
    ("owl", "http://www.w3.org/2002/07/owl#"),
)
_BPI = ("bpicounty", vocab.NAMESPACES["bpicounty"])

_COMMENT_WIDTH = 90


class BuildError(ValueError):
    """A difference that cannot be applied, or a graph that cannot be expressed as one."""


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Removal:
    """A core axiom a graph leaves out, with the legal reason for it."""

    iri: str
    subject: str
    relation: str
    object: str
    basis: str = ""
    explanation: str = ""
    status: str = vocab.RULE_STATUS_PROPOSED
    date: str = ""
    label: str = ""

    @property
    def triple(self) -> tuple[str, str, str]:
        """The axiom the removal names."""
        return (self.subject, self.relation, self.object)

    @property
    def statement(self) -> str:
        """The axiom in CURIE form, as a change log and a page write it."""
        return " ".join(vocab.compact_iri(part) for part in self.triple)

    @property
    def status_label(self) -> str:
        """``Adopted`` or ``Proposed``."""
        return vocab.RULE_STATUSES.get(self.status) or vocab.humanize_local_name(self.status)

    def as_row(self) -> dict[str, Any]:
        """One dictionary, as the pages and the JSON answers want it."""
        return {
            "iri": self.iri,
            "subject": self.subject,
            "subject_curie": vocab.compact_iri(self.subject),
            "subject_label": vocab.action_label(self.subject),
            "predicate": self.relation,
            "relation_curie": vocab.compact_iri(self.relation),
            "object": self.object,
            "object_curie": vocab.compact_iri(self.object),
            "object_label": vocab.action_label(self.object),
            "statement": self.statement,
            "basis": self.basis,
            "explanation": self.explanation,
            "status": self.status,
            "status_label": self.status_label,
            "adopted": self.status == vocab.RULE_STATUS_ADOPTED,
            "date": self.date,
            "label": self.label,
        }


@dataclass(frozen=True)
class Difference:
    """What one graph adds to, removes from and replaces in the graph it is based on."""

    graph_id: str
    iri: str
    metadata: tuple[tuple[str, Node], ...] = ()
    rules: tuple[Rule, ...] = ()
    removals: tuple[Removal, ...] = ()
    comment: str = ""

    @property
    def based_on(self) -> str:
        """The IRI of the graph this one is built from."""
        for predicate, term in self.metadata:
            if predicate == P_BASED_ON_GRAPH:
                return str(term)
        return ""

    @property
    def added_rules(self) -> list[Rule]:
        """The rules that replace nothing."""
        return [rule for rule in self.rules if not rule.replaces]

    @property
    def replacing_rules(self) -> list[Rule]:
        """The rules that take the place of a rule of the base."""
        return [rule for rule in self.rules if rule.replaces]


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def _triples(graph: Graph) -> list[tuple[str, str, str]]:
    return [(str(s), str(p), str(o)) for s, p, o in graph]


def removals_from_triples(triples: Iterable[tuple[str, str, str]]) -> list[Removal]:
    """The ``dalicc:AxiomRemoval`` records among some triples, in a stable order."""
    fields: dict[str, dict[str, str]] = {}
    typed: set[str] = set()
    for subject, predicate, obj in triples:
        if predicate == P_RDF_TYPE and obj == C_AXIOM_REMOVAL:
            typed.add(subject)
        fields.setdefault(subject, {})[predicate] = obj
    out: list[Removal] = []
    for iri in typed:
        values = fields.get(iri, {})
        subject = values.get(P_SUBJECT, "")
        relation = values.get(P_PREDICATE, "")
        obj = values.get(P_OBJECT, "")
        if not (subject and relation and obj):
            continue
        out.append(
            Removal(
                iri=normalise_iri(iri),
                subject=normalise_iri(subject),
                relation=normalise_iri(relation),
                object=normalise_iri(obj),
                basis=" ".join(values.get(P_RULE_BASIS, "").split()),
                explanation=" ".join(values.get(P_RULE_EXPLANATION, "").split()),
                status=normalise_iri(values.get(P_RULE_STATUS, ""))
                or vocab.RULE_STATUS_PROPOSED,
                date=values.get(P_DATE, "").strip(),
                label=values.get(P_LABEL, "").strip(),
            )
        )
    return sorted(out, key=lambda item: (item.statement, item.iri))


def _metadata(graph: Graph, iri: str) -> tuple[tuple[str, Node], ...]:
    """What a graph says about itself, in the writer's order."""
    pairs = [(str(p), o) for p, o in graph.predicate_objects(URIRef(iri))]
    order = {predicate: index for index, predicate in enumerate(_METADATA_ORDER)}
    return tuple(
        sorted(pairs, key=lambda item: (order.get(item[0], 99), item[0], str(item[1])))
    )


def leading_comment(text: str) -> str:
    """The comment block a Turtle file opens with, without the ``#`` marks."""
    lines: list[str] = []
    for line in (text or "").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line[2:] if line.startswith("# ") else line[1:])
    return "\n".join(lines).strip("\n")


def graph_iri_for(graph_id: str) -> str:
    """Where a shipped graph is addressed."""
    return GRAPH_NAMESPACE + graph_id


def parse_difference(text: str, graph_id: str) -> Difference:
    """Read one difference file."""
    graph = Graph()
    try:
        graph.parse(data=text, format="turtle")
    except Exception as exc:  # rdflib raises a family of parser errors
        raise BuildError(f"The difference file of {graph_id} is not valid Turtle: {exc}") from exc
    iri = graph_iri_for(graph_id)
    triples = _triples(graph)
    return Difference(
        graph_id=graph_id,
        iri=iri,
        metadata=_metadata(graph, iri),
        rules=tuple(rules_from_triples(triples)),
        removals=tuple(removals_from_triples(triples)),
        comment=leading_comment(text),
    )


def axioms_of(triples: Iterable[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """The axioms among some triples, as IRI triples, in canonical order."""
    out = {
        (normalise_iri(s), normalise_iri(p), normalise_iri(o))
        for s, p, o in triples
        if normalise_iri(p) in _RELATIONS
    }
    return sorted(out, key=_axiom_key)


# ---------------------------------------------------------------------------
# composing
# ---------------------------------------------------------------------------

#: A NotWaivable rule reports a finding and supplies nothing, so it is a different kind
#: of rule from the three that supply a statement, and the two kinds may meet on one
#: action: that is how a graph says that an exception cannot be contracted away.
_FINDING_OUTCOME = _DALICC + "NotWaivable"


def _kind(rule: Rule) -> str:
    return "finding" if rule.outcome == _FINDING_OUTCOME else "statement"


def _overlap(first: str, second: str) -> bool:
    """True when two territories overlap: the same one, or one of them worldwide."""
    return first == second or vocab.JURISDICTION_WORLDWIDE in (first, second)


def rule_problems(rules: Sequence[Rule]) -> list[str]:
    """Why a set of rules cannot stand in one generated graph, if it cannot."""
    problems: list[str] = []
    seen: dict[str, Rule] = {}
    for rule in rules:
        if rule.iri in seen:
            problems.append(f"two rules have the address <{rule.iri}>")
        seen[rule.iri] = rule
        if not rule.basis.strip():
            problems.append(f"<{rule.iri}> names no dalicc:ruleBasis")
        if not rule.explanation.strip():
            problems.append(f"<{rule.iri}> carries no dalicc:ruleExplanation")
    ordered = list(rules)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            if (
                first.action == second.action
                and _kind(first) == _kind(second)
                and _overlap(first.jurisdiction, second.jurisdiction)
            ):
                problems.append(
                    f"<{first.iri}> and <{second.iri}> are two default rules for "
                    f"{vocab.compact_iri(first.action)} in one territory; the second has "
                    "to replace the first (dalicc:replacesRule)"
                )
    return problems


def compose(
    core_axioms: Sequence[tuple[str, str, str]],
    core_rules: Sequence[Rule],
    difference: Difference,
) -> tuple[list[tuple[str, str, str]], list[Rule]]:
    """The axioms and rules of the complete graph, or :class:`BuildError`.

    Refused: a removal of an axiom the core does not hold, a replacement of a rule the
    core does not hold or of a rule about another action, an added rule with the
    address of a core rule, a rule or a removal without a basis or an explanation, and
    a result that holds two rules of one kind for one action in one territory.
    """
    problems: list[str] = []
    core_triples = set(core_axioms)
    core_by_iri = {rule.iri: rule for rule in core_rules}
    removed: set[tuple[str, str, str]] = set()
    for removal in difference.removals:
        if removal.triple not in core_triples:
            problems.append(
                f"the removal <{removal.iri}> names {removal.statement}, which the core "
                "graph does not hold"
            )
        if not removal.basis.strip():
            problems.append(f"the removal <{removal.iri}> names no dalicc:ruleBasis")
        if not removal.explanation.strip():
            problems.append(f"the removal <{removal.iri}> carries no dalicc:ruleExplanation")
        removed.add(removal.triple)
    replaced: set[str] = set()
    for rule in difference.rules:
        if rule.iri in core_by_iri:
            problems.append(
                f"<{rule.iri}> is a rule of the core graph; a difference adds rules of its "
                "own and replaces a core rule with dalicc:replacesRule"
            )
        if not rule.replaces:
            continue
        target = core_by_iri.get(rule.replaces)
        if target is None:
            problems.append(
                f"<{rule.iri}> replaces <{rule.replaces}>, which is not a rule of the core graph"
            )
            continue
        if target.action != rule.action:
            problems.append(
                f"<{rule.iri}> replaces a rule about {vocab.compact_iri(target.action)} "
                f"but is about {vocab.compact_iri(rule.action)}"
            )
        replaced.add(rule.replaces)
    axioms = [triple for triple in axioms_of(core_axioms) if triple not in removed]
    rules = sorted_rules(
        [rule for rule in core_rules if rule.iri not in replaced] + list(difference.rules)
    )
    problems.extend(rule_problems(rules))
    if problems:
        raise BuildError(
            f"{difference.graph_id}: " + "; ".join(dict.fromkeys(problems)) + "."
        )
    return axioms, rules


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------


def _curie(iri: str) -> str:
    """A CURIE when a prefix of the block covers the IRI, else ``<iri>``."""
    for prefix, namespace in (*_PREFIXES, _BPI):
        if iri.startswith(namespace):
            local = iri[len(namespace) :]
            if local and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", local):
                return f"{prefix}:{local}"
    return f"<{iri}>"


def _axiom_line(triple: tuple[str, str, str]) -> str:
    return " ".join(_curie(part) for part in triple) + " ."


def _axiom_key(triple: tuple[str, str, str]) -> tuple[str, str]:
    """The canonical order of axioms: by their CURIE line, ignoring case."""
    line = _axiom_line(triple)
    return (line.lower(), line)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _literal(term: Node) -> str:
    """One literal or IRI object as the writer spells it."""
    if isinstance(term, Literal):
        text = str(term)
        if "\n" in text or len(text) > 200:
            body = '"""' + text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + '"""'
        else:
            body = f'"{_escape(text)}"'
        if term.language:
            return f"{body}@{term.language}"
        if term.datatype is not None:
            return f"{body}^^{_curie(str(term.datatype))}"
        return body
    return _curie(str(term))


def _block(subject: str, pairs: Sequence[tuple[str, str]]) -> list[str]:
    """``<subject> p o ; p o .`` with one pair per line."""
    lines = [f"{_curie(subject)} {pairs[0][0]} {pairs[0][1]}"]
    for predicate, obj in pairs[1:]:
        lines[-1] += " ;"
        lines.append(f"    {predicate} {obj}")
    lines[-1] += " ."
    return lines


def _rule_block(rule: Rule) -> list[str]:
    pairs: list[tuple[str, str]] = [("a", "dalicc:DefaultRule")]
    if rule.label:
        pairs.append(("rdfs:label", f'"{_escape(rule.label)}"@en'))
    if rule.replaces:
        pairs.append(("dalicc:replacesRule", _curie(rule.replaces)))
    pairs.append(("dalicc:appliesTo", _curie(rule.action)))
    pairs.append(("dalicc:defaultOutcome", _curie(rule.outcome)))
    pairs.append(("dalicc:inJurisdiction", _curie(rule.jurisdiction)))
    if rule.basis:
        pairs.append(("dalicc:ruleBasis", f'"{_escape(rule.basis)}"'))
    if rule.explanation:
        pairs.append(("dalicc:ruleExplanation", f'"{_escape(rule.explanation)}"@en'))
    if rule.date:
        pairs.append(("dct:date", f'"{rule.date}"^^xsd:date'))
    pairs.append(("dalicc:ruleStatus", _curie(rule.status)))
    return _block(rule.iri, pairs)


def _removal_block(removal: Removal) -> list[str]:
    pairs: list[tuple[str, str]] = [("a", "dalicc:AxiomRemoval")]
    if removal.label:
        pairs.append(("rdfs:label", f'"{_escape(removal.label)}"@en'))
    pairs.append(("rdf:subject", _curie(removal.subject)))
    pairs.append(("rdf:predicate", _curie(removal.relation)))
    pairs.append(("rdf:object", _curie(removal.object)))
    if removal.basis:
        pairs.append(("dalicc:ruleBasis", f'"{_escape(removal.basis)}"'))
    if removal.explanation:
        pairs.append(("dalicc:ruleExplanation", f'"{_escape(removal.explanation)}"@en'))
    if removal.date:
        pairs.append(("dct:date", f'"{removal.date}"^^xsd:date'))
    pairs.append(("dalicc:ruleStatus", _curie(removal.status)))
    return _block(removal.iri, pairs)


def _comment(text: str) -> list[str]:
    """``text`` as comment lines; a paragraph longer than a line is wrapped."""
    out: list[str] = []
    for paragraph in (text or "").split("\n"):
        if not paragraph.strip():
            out.append("#")
            continue
        words = paragraph.split()
        line = ""
        for word in words:
            if line and len(line) + 1 + len(word) > _COMMENT_WIDTH - 2:
                out.append(f"# {line}")
                line = word
            else:
                line = f"{line} {word}" if line else word
        if line:
            out.append(f"# {line}")
    return out


def _prefix_block(body: str) -> list[str]:
    prefixes = list(_PREFIXES)
    if "bpicounty:" in body:
        prefixes.append(_BPI)
    return [f"@prefix {prefix}: <{namespace}> ." for prefix, namespace in prefixes]


def _document(
    comment: str,
    iri: str,
    metadata: Sequence[tuple[str, Node]],
    sections: Sequence[tuple[str, list[str]]],
) -> str:
    """The canonical text of one graph or difference file."""
    body: list[str] = []
    if metadata:
        body.extend(_block(iri, [(_curie(p), _literal(o)) for p, o in metadata]))
    for heading, lines in sections:
        if not lines:
            continue
        body.append("")
        if heading:
            body.append(f"# {heading}")
            body.append("")
        body.extend(lines)
    text = "\n".join(body)
    head = _comment(comment)
    return "\n".join([*head, *_prefix_block(text), "", text.strip("\n"), ""])


def _blocks(items: Iterable[list[str]]) -> list[str]:
    out: list[str] = []
    for block in items:
        if out:
            out.append("")
        out.extend(block)
    return out


def version_sentence(graph_id: str, version: int, date: str, reviewer: str) -> str:
    """The first line of a generated file, in the style of the core graph."""
    if version <= 1:
        earlier = "The change log is in"
    elif version == 2:
        earlier = "Version 1 and the change log are in"
    elif version == 3:
        earlier = "Versions 1 and 2 and the change log are in"
    else:
        earlier = f"Versions 1 to {version - 1} and the change log are in"
    reviewed = f" Reviewer: {reviewer}." if reviewer else ""
    return (
        f"Version {version} of the {graph_id} dependency graph, {date}. {earlier} "
        f"licensedata/history/dependencygraph/.{reviewed}"
    )


def render_graph(
    difference: Difference,
    axioms: Sequence[tuple[str, str, str]],
    rules: Sequence[Rule],
    *,
    version: int,
    date: str,
    reviewer: str,
    core_version: int,
) -> str:
    """The complete graph file, byte for byte what the build writes."""
    metadata = [
        (predicate, term)
        for predicate, term in difference.metadata
        if predicate not in _GENERATED_METADATA
    ]
    metadata.append((P_DATE, Literal(date, datatype=URIRef(_XSD_DATE))))
    metadata.append((P_BASED_ON_VERSION, Literal(str(core_version))))
    order = {predicate: index for index, predicate in enumerate(_METADATA_ORDER)}
    metadata.sort(key=lambda item: (order.get(item[0], 99), item[0], str(item[1])))
    base = difference.based_on or graph_iri_for(CORE_ID)
    base_id = base.rstrip("/").rsplit("/", 1)[-1]
    comment = "\n".join(
        [
            version_sentence(difference.graph_id, version, date, reviewer),
            "",
            f"GENERATED by scripts/build_dependency_graphs.py from the core graph "
            f"{base_id}.ttl (version {core_version}) and the difference file "
            f"differences/{difference.graph_id}.ttl. Edit the difference file and run the "
            "build; an edit made here is overwritten. The graph is complete: it holds "
            "every axiom and every default rule a check under it reads, and it names no "
            "graph the reasoner would have to follow.",
            "",
            difference.comment,
        ]
    ).rstrip("\n")
    sections = [
        ("", [_axiom_line(triple) for triple in sorted(axioms, key=_axiom_key)]),
        ("The default rules of this graph.", _blocks(_rule_block(r) for r in sorted_rules(rules))),
        (
            "The core axioms this graph removes, and why. None of them is in the graph above.",
            _blocks(_removal_block(r) for r in difference.removals),
        ),
    ]
    return _document(comment, difference.iri, metadata, sections)


def render_difference(difference: Difference) -> str:
    """The difference file, byte for byte what :func:`extract` writes."""
    metadata = [
        (predicate, term)
        for predicate, term in difference.metadata
        if predicate not in _GENERATED_METADATA
    ]
    sections = [
        (
            "The default rules this graph adds.",
            _blocks(_rule_block(r) for r in sorted_rules(difference.added_rules)),
        ),
        (
            "The core default rules this graph replaces.",
            _blocks(_rule_block(r) for r in sorted_rules(difference.replacing_rules)),
        ),
        (
            "The core axioms this graph removes.",
            _blocks(_removal_block(r) for r in difference.removals),
        ),
    ]
    return _document(difference.comment, difference.iri, metadata, sections)


# ---------------------------------------------------------------------------
# the other direction
# ---------------------------------------------------------------------------


def extract(
    complete_text: str,
    graph_id: str,
    core_axioms: Sequence[tuple[str, str, str]],
    core_rules: Sequence[Rule],
    *,
    comment: str = "",
) -> Difference:
    """Derive the difference file of a complete graph from it and the core graph.

    The rules the graph holds and the core does not are added (or replacing, when they
    say so); the removal records it holds are kept, and a core axiom the graph lacks
    without a record gets one with an empty basis and explanation, which the build then
    refuses until somebody writes them.  Refused here: an axiom the core does not hold
    and a core rule the graph dropped without replacing it, because a difference file
    cannot say either.
    """
    graph = Graph()
    try:
        graph.parse(data=complete_text, format="turtle")
    except Exception as exc:  # rdflib raises a family of parser errors
        raise BuildError(f"The graph {graph_id} is not valid Turtle: {exc}") from exc
    iri = graph_iri_for(graph_id)
    triples = _triples(graph)
    axioms = set(axioms_of(triples))
    core = set(axioms_of(core_axioms))
    extra = sorted(axioms - core, key=_axiom_key)
    if extra:
        raise BuildError(
            f"{graph_id} holds axioms the core graph does not "
            f"({', '.join(_axiom_line(t)[:-2] for t in extra)}); a difference file cannot "
            "add an axiom, so add it to the core graph or remove it from this one."
        )
    removals = {removal.triple: removal for removal in removals_from_triples(triples)}
    for triple in sorted(core - axioms, key=_axiom_key):
        if triple not in removals:
            local = "-".join(vocab.compact_iri(part).replace(":", "-") for part in triple)
            removals[triple] = Removal(
                iri=f"{GRAPH_NAMESPACE}removals/{graph_id}-{local}",
                subject=triple[0],
                relation=triple[1],
                object=triple[2],
            )
    rules = rules_from_triples(triples)
    core_iris = {rule.iri for rule in core_rules}
    held = {rule.iri for rule in rules}
    replaced = {rule.replaces for rule in rules if rule.replaces}
    dropped = sorted(core_iris - held - replaced)
    if dropped:
        raise BuildError(
            f"{graph_id} no longer holds the core rule(s) {', '.join(dropped)} and names "
            "nothing that replaces them; add a rule with dalicc:replacesRule."
        )
    return Difference(
        graph_id=graph_id,
        iri=iri,
        metadata=tuple(
            (p, o) for p, o in _metadata(graph, iri) if p not in (*_GENERATED_METADATA,)
            and p != P_EXTENDS_GRAPH
        ),
        rules=tuple(sorted_rules(rule for rule in rules if rule.iri not in core_iris)),
        removals=tuple(sorted(removals.values(), key=lambda r: (r.statement, r.iri))),
        comment=comment,
    )


# ---------------------------------------------------------------------------
# what a graph is, against the one it is based on
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphSummary:
    """The counts a list line, the API index and a graph page show."""

    axioms: int = 0
    rules: int = 0
    based_on: str = ""
    based_on_version: int = 0
    added_rules: int = 0
    removed_axioms: int = 0
    replaced_rules: int = 0
    added: tuple[Rule, ...] = ()
    replacing: tuple[Rule, ...] = ()
    inherited: tuple[Rule, ...] = ()
    removals: tuple[Removal, ...] = field(default=())

    @property
    def is_derived(self) -> bool:
        """True for a graph built from another one."""
        return bool(self.based_on)


def graph_summary(
    triples: Sequence[tuple[str, str, str]],
    base_triples: Sequence[tuple[str, str, str]] | None = None,
) -> GraphSummary:
    """Count what a graph adds, removes and replaces against the graph it is based on.

    ``base_triples`` are the statements of the graph ``dalicc:basedOnGraph`` names;
    without them a derived graph counts every rule that replaces nothing as added.
    """
    rules = rules_from_triples(triples)
    axioms = axioms_of(triples)
    based_on = ""
    version = 0
    for _subject, predicate, obj in triples:
        if predicate == P_BASED_ON_GRAPH:
            based_on = obj
        elif predicate == P_BASED_ON_VERSION and str(obj).isdigit():
            version = int(obj)
    if not based_on:
        return GraphSummary(axioms=len(axioms), rules=len(rules), inherited=tuple(rules))
    base_rules = {rule.iri for rule in rules_from_triples(base_triples or [])}
    added = tuple(r for r in rules if not r.replaces and r.iri not in base_rules)
    replacing = tuple(r for r in rules if r.replaces)
    inherited = tuple(r for r in rules if r.iri in base_rules)
    removals = tuple(removals_from_triples(triples))
    return GraphSummary(
        axioms=len(axioms),
        rules=len(rules),
        based_on=based_on,
        based_on_version=version,
        added_rules=len(added),
        removed_axioms=len(removals),
        replaced_rules=len(replacing),
        added=added,
        replacing=replacing,
        inherited=inherited,
        removals=removals,
    )


def _count(number: int, singular: str, plural: str) -> str:
    return f"{number} {singular if number == 1 else plural}"


def summary_line(summary: GraphSummary) -> str:
    """"the core graph plus 9 default rules; removes 2 axioms; replaces 1 rule".

    Zeros are left out; a graph that is based on nothing has no line.
    """
    if not summary.is_derived:
        return ""
    parts = ["the core graph"]
    if summary.added_rules:
        parts[0] += " plus " + _count(summary.added_rules, "default rule", "default rules")
    if summary.removed_axioms:
        parts.append("removes " + _count(summary.removed_axioms, "axiom", "axioms"))
    if summary.replaced_rules:
        parts.append("replaces " + _count(summary.replaced_rules, "rule", "rules"))
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# the build over the repository
# ---------------------------------------------------------------------------


def file_version(history_dir: Path, graph_id: str) -> dict[str, Any]:
    """``{version, date, reviewer}`` of the newest change-log entry of one graph."""
    name = "changelog.yaml" if graph_id == CORE_ID else f"{graph_id}-changelog.yaml"
    path = history_dir / name
    if not path.is_file():
        return {"version": 1, "date": dt.date.today().isoformat(), "reviewer": ""}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    version = int(data.get("current_version") or 1)
    entry = next(
        (item for item in data.get("entries") or [] if item.get("version") == version),
        {},
    )
    return {
        "version": version,
        "date": str(entry.get("date") or ""),
        "reviewer": str(entry.get("reviewer") or ""),
    }


def core_statements(core_text: str) -> tuple[list[tuple[str, str, str]], list[Rule]]:
    """The axioms and rules of the core graph file."""
    graph = Graph()
    graph.parse(data=core_text, format="turtle")
    triples = _triples(graph)
    return axioms_of(triples), rules_from_triples(triples)


def build(
    core_text: str,
    difference_text: str,
    graph_id: str,
    *,
    version: int,
    date: str,
    reviewer: str,
    core_version: int,
) -> str:
    """The complete graph of one difference file, as the build writes it."""
    core_axioms, core_rules = core_statements(core_text)
    difference = parse_difference(difference_text, graph_id)
    axioms, rules = compose(core_axioms, core_rules, difference)
    return render_graph(
        difference,
        axioms,
        rules,
        version=version,
        date=date,
        reviewer=reviewer,
        core_version=core_version,
    )


def _is_graph_node(iri: str) -> bool:
    """True for the address of a shipped graph itself, not of a rule or a removal."""
    return iri.startswith(GRAPH_NAMESPACE) and "/" not in iri[len(GRAPH_NAMESPACE) :]


def statement_changes(before_text: str, after_text: str) -> list[dict[str, str]]:
    """What changed between two versions of a graph, as change-log entries.

    Axioms, rules (by address, with a changed outcome, basis or explanation reported as
    changed) and removal records are compared; the version, the date and the comments
    are not statements and are not.
    """
    def read(text: str) -> tuple[set, dict[str, Rule], dict[str, Removal], dict[str, str]]:
        graph = Graph()
        if text:
            graph.parse(data=text, format="turtle")
        triples = _triples(graph)
        meta = {
            p: str(o)
            for s, p, o in triples
            if p in (P_BASED_ON_VERSION, P_TITLE, P_DESCRIPTION) and _is_graph_node(s)
        }
        return (
            set(axioms_of(triples)),
            {rule.iri: rule for rule in rules_from_triples(triples)},
            {removal.iri: removal for removal in removals_from_triples(triples)},
            meta,
        )

    before_axioms, before_rules, before_removals, before_meta = read(before_text)
    after_axioms, after_rules, after_removals, after_meta = read(after_text)
    changes: list[dict[str, str]] = []
    for triple in sorted(after_axioms - before_axioms, key=_axiom_key):
        changes.append({"action": "added", "statement": _axiom_line(triple)[:-2]})
    for triple in sorted(before_axioms - after_axioms, key=_axiom_key):
        changes.append({"action": "removed", "statement": _axiom_line(triple)[:-2]})
    for iri in sorted(set(after_rules) - set(before_rules)):
        changes.append({"action": "added", "statement": "rule " + after_rules[iri].statement})
    for iri in sorted(set(before_rules) - set(after_rules)):
        changes.append({"action": "removed", "statement": "rule " + before_rules[iri].statement})
    for iri in sorted(set(before_rules) & set(after_rules)):
        if before_rules[iri] != after_rules[iri]:
            changes.append(
                {
                    "action": "changed",
                    "statement": "rule " + after_rules[iri].statement,
                    "previous": "rule " + before_rules[iri].statement,
                }
            )
    for iri in sorted(set(after_removals) - set(before_removals)):
        changes.append(
            {"action": "added", "statement": "removal of " + after_removals[iri].statement}
        )
    for iri in sorted(set(before_removals) - set(after_removals)):
        changes.append(
            {"action": "removed", "statement": "removal of " + before_removals[iri].statement}
        )
    for predicate in (P_TITLE, P_DESCRIPTION, P_BASED_ON_VERSION):
        if before_meta.get(predicate, "") != after_meta.get(predicate, ""):
            name = vocab.compact_iri(predicate)
            changes.append(
                {
                    "action": "changed",
                    "statement": f"{name} {after_meta.get(predicate, '')}".strip(),
                    "previous": f"{name} {before_meta.get(predicate, '')}".strip(),
                }
            )
    return changes


#: The predicates a rule block or a removal block writes itself.
_BLOCK_PREDICATES = frozenset(
    {
        P_RDF_TYPE,
        P_LABEL,
        P_DATE,
        P_RULE_BASIS,
        P_RULE_EXPLANATION,
        P_RULE_STATUS,
        _DALICC + "appliesTo",
        _DALICC + "defaultOutcome",
        _DALICC + "inJurisdiction",
        _DALICC + "replacesRule",
        P_SUBJECT,
        P_PREDICATE,
        P_OBJECT,
    }
)


def render_complete(graph: Graph, graph_iri: str, *, comment: str = "") -> str:
    """Any complete graph in the canonical layout, for a download.

    The metadata of ``graph_iri``, the axioms, the default rules and the removal
    records are written the way the build writes them; any other statement follows
    at the end, one per line, so nothing the graph holds is left out.
    """
    triples = _triples(graph)
    rules = rules_from_triples(triples)
    removals = removals_from_triples(triples)
    axioms = axioms_of(triples)
    written = {rule.iri for rule in rules} | {removal.iri for removal in removals}
    axiom_set = set(axioms)
    # A rule or a removal block writes the statements of the model; any other statement
    # about the same node, such as the dct:contributor of an adopted rule, follows below.
    rest = sorted(
        f"{s.n3()} {p.n3()} {o.n3()} ."
        for s, p, o in graph
        if str(s) != graph_iri
        and not (str(s) in written and str(p) in _BLOCK_PREDICATES)
        and (normalise_iri(str(s)), normalise_iri(str(p)), normalise_iri(str(o))) not in axiom_set
    )
    sections = [
        ("", [_axiom_line(triple) for triple in axioms]),
        ("The default rules of this graph.", _blocks(_rule_block(r) for r in sorted_rules(rules))),
        (
            "The axioms of the graph it is based on that this graph removes, and why.",
            _blocks(_removal_block(r) for r in removals),
        ),
        ("Other statements of this graph.", rest),
    ]
    return _document(comment, graph_iri, _metadata(graph, graph_iri), sections)
