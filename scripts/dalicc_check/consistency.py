# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The consistency rule set: which deontic statements of a license cannot both hold.

This is the rule set behind ``POST /licenselibrary/consistencycheck`` and behind
``scripts/review/consistency_sweep.py``.  It reads a license as a set of deontic
statements -- what is permitted, what is prohibited, what is required as a duty and
which rule each duty hangs on -- and reports the pairs that contradict each other: the
same action permitted and prohibited, a duty whose action is prohibited, a prohibition
that carries duties, a share-alike condition on the whole work next to a free
permission to relicense, and the same readings closed under the dependency graph
(``odrl:includedIn``, ``odrl:implies``, ``owl:sameAs``, ``dalicc:contradicts``).

The rule set is a module of its own because the license data is checked without the
service.  ``scripts/review/consistency_sweep.py`` runs it over ``licensedata/licenses/``
with nothing but rdflib and the data, which is also how the published copy of the data
is checked.  Everything here therefore imports the standard library, rdflib and
:mod:`app.services.vocab` and nothing else: no pydantic, no HTTP client, no settings.
:func:`app.services.composer.load_dependency_relations` reads the axioms through a
SPARQL client and stays in the composer for that reason, and
:mod:`app.services.composer` re-exports the names below so that every caller it had
keeps working.

A dependency graph carries a second kind of statement beside its axioms: a
``dalicc:DefaultRule``, which says what applies to an action the license is silent
about, in which jurisdiction, and on the strength of which legal source.
:func:`default_statements` reads those rules, and :func:`consistency_check` lets what
they supply take part in every rule above exactly as a statement of the text does.
Every conflict says which side came from the text and which from a rule, and the
derived statements are returned in their own right so that a page can list them.

Nothing this module reports is legal advice.  A conflict is a statement about the model
of a license, reached by the rules written here and by the axioms of the dependency
graph; a default rule is a reading of a legal default, named with the source it rests
on; and what the license means is decided by its text.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import re
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from dalicc_check import vocab

__all__ = [
    "DEFAULT_DUTY",
    "DEFAULT_FINDING",
    "DEFAULT_PERMISSION",
    "DEFAULT_PROHIBITION",
    "DUTY",
    "LICENSE_WIDE_DUTY",
    "PERMISSION",
    "PROHIBITION",
    "Conflict",
    "DefaultStatement",
    "DependencyTriples",
    "Rule",
    "consistency_check",
    "default_statements",
    "extends_from_triples",
    "make_rule",
    "normalise_iri",
    "rule_triples",
    "rules_from_triples",
    "sorted_rules",
    "spoken_for",
    "statements_from_input",
]


# ---------------------------------------------------------------------------
# IRIs
# ---------------------------------------------------------------------------

#: Historical dumps spell the DALICC namespace with plain ``http``; accept both on the
#: way in and normalise to the ``https`` form the vocabulary uses.
_HTTP_DALICC = "http://dalicc.net/ns#"
_DALICC_NS = vocab.NAMESPACES["dalicc"]

_UNSAFE_IRI_RE = re.compile(r"""[\s<>"{}|\\^`]""")


def normalise_iri(value: str) -> str:
    """An IRI or CURIE as the canonical absolute IRI, or an empty string.

    :mod:`app.services.depgraph` imports this rather than keeping a second copy: the
    two modules have to agree on what a term is, or the form and the graph editor would
    read the same file differently.
    """
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if candidate.startswith(_HTTP_DALICC):
        candidate = _DALICC_NS + candidate[len(_HTTP_DALICC) :]
    if candidate.startswith(("http://", "https://")):
        return "" if _UNSAFE_IRI_RE.search(candidate) or len(candidate) > 2048 else candidate
    return vocab.expand_curie(candidate) or ""


_normalise_iri = normalise_iri


@dataclass(frozen=True, slots=True)
class Conflict:
    """One inconsistency found in a composed license."""

    kind: str
    reason: str
    action_1: str
    action_2: str = ""
    label_1: str = ""
    label_2: str = ""
    #: The statements of the license that clash, each written as the rule it belongs to
    #: and the action it names: "Permission: Distribute", "Prohibition: Distribute".
    #: A reader who sees only the reason has to find those statements in the form
    #: again, which is what this list saves them.
    statements: tuple[str, ...] = ()
    #: For a derived conflict, the steps of the dependency graph that connect the two
    #: statements ("Distribute is included in Use."); empty for a direct one.
    chain: str = ""
    #: Where each side of the conflict comes from: ``dalicc:FromText`` for a statement
    #: the license makes, ``dalicc:FromDefaultRule`` for one a default rule supplied
    #: because the license is silent.  A reader has to be able to tell them apart.
    origin_1: str = vocab.ORIGIN_FROM_TEXT
    origin_2: str = vocab.ORIGIN_FROM_TEXT
    #: The rule that supplied the side, when that side came from one.
    rule_1: str = ""
    rule_2: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON shape published by ``POST /licenselibrary/consistencycheck``.

        ``statements`` and ``chain`` were added later and are always present; the six
        keys before them are unchanged.  ``origin_1``, ``origin_2``, ``rule_1`` and
        ``rule_2`` came with the default rules and are always present too: the first
        two say ``dalicc:FromText`` for a statement the license makes, and the last two
        are empty unless that side came from a rule.
        """
        return {
            "kind": self.kind,
            "reason": self.reason,
            "action_1": self.action_1,
            "action_2": self.action_2,
            "label_1": self.label_1 or vocab.action_label(self.action_1),
            "label_2": (self.label_2 or vocab.action_label(self.action_2))
            if self.action_2
            else "",
            "statements": list(self.statements),
            "chain": self.chain,
            "origin_1": self.origin_1,
            "origin_2": self.origin_2,
            "rule_1": self.rule_1,
            "rule_2": self.rule_2,
        }

    @property
    def from_default_rule(self) -> bool:
        """True when either side of this conflict came from a default rule."""
        return vocab.ORIGIN_FROM_DEFAULT_RULE in (self.origin_1, self.origin_2)


#: How a statement is named in front of its action: the rule it belongs to.
PERMISSION = "Permission"
PROHIBITION = "Prohibition"
DUTY = "Duty"
LICENSE_WIDE_DUTY = "License-wide duty"


def _statement(rule: str, action: str) -> str:
    """One deontic statement, as the conflict list shows it."""
    return f"{rule}: {vocab.action_label(action)}"


def _rule_of(action: str, statements: _Statements) -> str:
    """Which rule of the license asserts ``action``, for the statement line.

    Used by the ``dalicc:contradicts`` check, where either side may be a permission or
    a duty.  A permission wins when the license states both, because that is the
    statement a reader is looking for.
    """
    if action in statements.permitted:
        return PERMISSION
    if action in statements.license_wide_required:
        return LICENSE_WIDE_DUTY
    return DUTY


DependencyTriples = Iterable[tuple[str, str, str]]

_P_INCLUDED_IN = vocab.NAMESPACES["odrl"] + "includedIn"
_P_IMPLIES = vocab.NAMESPACES["odrl"] + "implies"
_P_SAME_AS = vocab.NAMESPACES["owl"] + "sameAs"
_P_CONTRADICTS = vocab.NAMESPACES["dalicc"] + "contradicts"
#: Historical dumps carry a plain-http spelling of the DALICC namespace; accept both.
_P_CONTRADICTS_HTTP = "http://dalicc.net/ns#contradicts"


def _relation_index(triples: DependencyTriples) -> dict[str, dict[str, set[str]]]:
    """Group the axioms by predicate, symmetrising ``sameAs`` and ``contradicts``."""
    index: dict[str, dict[str, set[str]]] = {
        "includedIn": {},
        "implies": {},
        "sameAs": {},
        "contradicts": {},
    }
    for subject, predicate, obj in triples:
        if predicate == _P_INCLUDED_IN:
            index["includedIn"].setdefault(subject, set()).add(obj)
        elif predicate == _P_IMPLIES:
            index["implies"].setdefault(subject, set()).add(obj)
        elif predicate == _P_SAME_AS:
            index["sameAs"].setdefault(subject, set()).add(obj)
            index["sameAs"].setdefault(obj, set()).add(subject)
        elif predicate in {_P_CONTRADICTS, _P_CONTRADICTS_HTTP}:
            index["contradicts"].setdefault(subject, set()).add(obj)
            index["contradicts"].setdefault(obj, set()).add(subject)
    return index


def _synonyms(index: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
    """Every action with the names that denote the same act, itself included.

    ``owl:sameAs`` is followed to its end, so the three names of one act reach each
    other even where the graph relates them in a chain rather than pairwise.
    """
    out: dict[str, set[str]] = {}
    for start in index["sameAs"]:
        if start in out:
            continue
        group = {start}
        frontier = [start]
        while frontier:
            for target in index["sameAs"].get(frontier.pop(), ()):
                if target not in group:
                    group.add(target)
                    frontier.append(target)
        for member in group:
            out[member] = group
    return out


def _contradictions(
    index: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, tuple[str, str]]]:
    """``action -> other action -> the axiom the contradiction is written as``.

    ``dalicc:contradicts`` is never chained with itself, but a synonym of either side
    *is* that side: ``owl:sameAs`` says that every statement about one action is a
    statement about the other, so the axiom written about ``odrl:commercialize`` holds
    of ``cc:CommercialUse``, which is the term the license records actually use.  The
    axiom that produced each pair is kept so that the conflict can name it.
    """
    synonyms = _synonyms(index)
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for subject, objects in index["contradicts"].items():
        for obj in objects:
            for left in synonyms.get(subject, {subject}):
                for right in synonyms.get(obj, {obj}):
                    out.setdefault(left, {}).setdefault(right, (subject, obj))
    return out


def _contradiction_chain(action: str, other: str, stated: tuple[str, str]) -> str:
    """The steps of the graph that put ``action`` and ``other`` in contradiction."""
    left, right = stated
    steps = []
    if left != action:
        steps.append(
            f"{vocab.action_label(action)} is the same action as {vocab.action_label(left)}"
        )
    steps.append(
        f"{vocab.action_label(left)} contradicts {vocab.action_label(right)} in the "
        f"dependency graph"
    )
    if right != other:
        steps.append(
            f"{vocab.action_label(right)} is the same action as {vocab.action_label(other)}"
        )
    return ", and ".join(steps) + "."


def _closure(
    seeds: set[str], index: dict[str, dict[str, set[str]]], *, direction: str
) -> dict[str, list[tuple[str, str]]]:
    """Expand ``seeds`` through the dependency graph.

    ``direction="permits"`` follows ``implies`` and ``sameAs`` forwards: permitting an
    action also permits everything it entails.  ``direction="forbids"`` follows
    ``includedIn`` *backwards* and ``sameAs`` both ways: prohibiting an action also
    prohibits every action that is a special case of it.

    Returns ``derived action -> [(seed, explanation), ...]``.
    """
    reverse_included: dict[str, set[str]] = {}
    for subject, objects in index["includedIn"].items():
        for obj in objects:
            reverse_included.setdefault(obj, set()).add(subject)

    out: dict[str, list[tuple[str, str]]] = {}
    for seed in seeds:
        frontier = [(seed, "")]
        seen = {seed}
        while frontier:
            current, explanation = frontier.pop()
            if current != seed:
                out.setdefault(current, []).append((seed, explanation))
            steps: list[tuple[str, str]] = []
            for synonym in index["sameAs"].get(current, ()):
                steps.append((synonym, f"{vocab.action_label(current)} is the same action as "
                                       f"{vocab.action_label(synonym)}"))
            if direction == "permits":
                for implied in index["implies"].get(current, ()):
                    steps.append((implied, f"{vocab.action_label(current)} implies "
                                           f"{vocab.action_label(implied)}"))
            else:
                for special in reverse_included.get(current, ()):
                    steps.append((special, f"{vocab.action_label(special)} is included in "
                                           f"{vocab.action_label(current)}"))
            for target, step_text in steps:
                if target in seen:
                    continue
                seen.add(target)
                frontier.append((target, step_text if not explanation else
                                 f"{explanation}, and {step_text}"))
    return out


@dataclass(frozen=True, slots=True)
class _Statements:
    """The deontic statements of a license, flattened."""

    permitted: set[str]
    prohibited: set[str]
    required: set[str]
    duties_by_permission: dict[str, set[str]]
    prohibitions_with_duties: set[str]
    #: Duty actions that hang off the ``odrl:Set`` itself rather than off one
    #: permission.  A license-wide ``cc:ShareAlike`` says "the whole work stays under
    #: this license"; the same duty on ``odrl:modify`` says only "the file you changed
    #: does", and the two behave differently against a permission to relicense.
    license_wide_required: set[str] = field(default_factory=set)
    #: The duty actions hanging off a prohibition, so the conflict list can name them.
    #: Only a license document can carry these: the composer form never attaches a duty
    #: to a prohibition.
    duties_by_prohibition: dict[str, set[str]] = field(default_factory=dict)


_ODRL = vocab.NAMESPACES["odrl"]


def _statements_from_graph(graph: Graph) -> _Statements:
    permitted: set[str] = set()
    prohibited: set[str] = set()
    required: set[str] = set()
    duties_by_permission: dict[str, set[str]] = {}
    prohibitions_with_duties: set[str] = set()
    license_wide_required: set[str] = set()
    duties_by_prohibition: dict[str, set[str]] = {}

    action = URIRef(_ODRL + "action")
    duty = URIRef(_ODRL + "duty")

    for subject in graph.subjects(RDF.type, URIRef(_ODRL + "Set")):
        for node in graph.objects(subject, URIRef(_ODRL + "permission")):
            for act in graph.objects(node, action):
                permitted.add(str(act))
                bucket = duties_by_permission.setdefault(str(act), set())
                for duty_node in graph.objects(node, duty):
                    for duty_action in graph.objects(duty_node, action):
                        bucket.add(str(duty_action))
                        required.add(str(duty_action))
        for node in graph.objects(subject, URIRef(_ODRL + "prohibition")):
            for act in graph.objects(node, action):
                prohibited.add(str(act))
                if (node, duty, None) in graph:
                    prohibitions_with_duties.add(str(act))
                    bucket = duties_by_prohibition.setdefault(str(act), set())
                    for duty_node in graph.objects(node, duty):
                        for duty_action in graph.objects(duty_node, action):
                            bucket.add(str(duty_action))
        for node in graph.objects(subject, duty):
            for act in graph.objects(node, action):
                required.add(str(act))
                license_wide_required.add(str(act))
    return _Statements(
        permitted,
        prohibited,
        required,
        duties_by_permission,
        prohibitions_with_duties,
        license_wide_required,
        duties_by_prohibition,
    )


#: The seam between this module and :mod:`app.services.composer`.  A ``ComposerInput``
#: is a pydantic model that lives in the composer, and this module has to stay usable
#: with rdflib alone, so the model never crosses the line: ``data`` is read for the five
#: fields a composed license carries and for nothing else, which is why it is annotated
#: structurally rather than by class.  The composer re-exports ``consistency_check`` and
#: hands its ``ComposerInput`` straight through to it.
def statements_from_input(data: Any) -> _Statements:
    """Flatten a composed license into the statements the rules read.

    ``data`` is anything carrying the fields a composed license carries:
    ``permitted_actions``, ``prohibited_actions``, ``required_actions``, ``permissions``
    (each with an ``action`` and its ``duties``) and the license-wide ``duties``.
    """
    return _Statements(
        permitted=data.permitted_actions,
        prohibited=data.prohibited_actions,
        required=data.required_actions,
        duties_by_permission={p.action: set(p.duties) for p in data.permissions},
        prohibitions_with_duties=set(),
        license_wide_required=set(data.duties),
        duties_by_prohibition={},
    )


# ---------------------------------------------------------------------------
# the default rules
# ---------------------------------------------------------------------------

#: The predicates of a ``dalicc:DefaultRule``, and the two that describe the graph
#: itself.  A rule is not an axiom: an axiom relates two actions, and a rule says what
#: applies to one action a license is silent about.  Both live in the same named graph
#: because both are statements about actions and both are chosen together.
P_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
P_RULE_APPLIES_TO = _DALICC_NS + "appliesTo"
P_RULE_OUTCOME = _DALICC_NS + "defaultOutcome"
P_RULE_JURISDICTION = _DALICC_NS + "inJurisdiction"
P_RULE_BASIS = _DALICC_NS + "ruleBasis"
P_RULE_STATUS = _DALICC_NS + "ruleStatus"
P_EXTENDS_GRAPH = _DALICC_NS + "extendsGraph"
P_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
P_DATE = "http://purl.org/dc/terms/date"
C_DEFAULT_RULE = _DALICC_NS + "DefaultRule"

RULE_PREDICATES: tuple[str, ...] = (
    P_RULE_APPLIES_TO,
    P_RULE_OUTCOME,
    P_RULE_JURISDICTION,
    P_RULE_BASIS,
    P_RULE_STATUS,
)

#: A graph with more rules than this is refused, for the reason MAX_AXIOMS exists: the
#: reasoner loads every one of them for every check.
MAX_RULES = 200

_XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True, slots=True)
class Rule:
    """One default rule: what applies to an action a license does not mention.

    ``outcome`` is one of the four ``dalicc:DefaultOutcome`` concepts, ``jurisdiction``
    is ``dalicc:worldwide``, a region concept or a BPI country IRI, ``basis`` names the
    statute or principle in words and ``status`` says whether the rule is adopted or
    only proposed.  Nothing a rule states is legal advice.

    ``dalicc:NotWaivable`` is the one outcome whose reading depends on a second rule.
    "A statement to the contrary" means a prohibition where the same graph also says the
    action is granted by default, and a permission everywhere else: the law either keeps
    an exception open, in which case a license cannot close it, or keeps a protection in
    place, in which case a license cannot give it away.  The companion is looked up by
    action inside the graph the check runs under, and
    :func:`app.services.consistency.default_findings` and
    ``reasoner/app/programs/query.lp`` both read it that way.
    """

    iri: str
    action: str
    outcome: str
    jurisdiction: str
    basis: str = ""
    status: str = vocab.RULE_STATUS_PROPOSED
    date: str = ""
    label: str = ""

    @property
    def action_label(self) -> str:
        """The label of the action the rule is about."""
        return vocab.action_label(self.action)

    @property
    def action_curie(self) -> str:
        """The action as a CURIE."""
        return vocab.compact_iri(self.action)

    @property
    def outcome_label(self) -> str:
        """The label of the outcome, e.g. ``Not granted by default``."""
        return vocab.DEFAULT_OUTCOMES.get(self.outcome) or vocab.humanize_local_name(self.outcome)

    @property
    def outcome_curie(self) -> str:
        """The outcome as a CURIE."""
        return vocab.compact_iri(self.outcome)

    @property
    def jurisdiction_label(self) -> str:
        """The label of the territory the rule holds in."""
        return vocab.jurisdiction_label(self.jurisdiction)

    @property
    def status_label(self) -> str:
        """``Adopted`` or ``Proposed``."""
        return vocab.RULE_STATUSES.get(self.status) or vocab.humanize_local_name(self.status)

    @property
    def adopted(self) -> bool:
        """True when the rule takes part in a check the reader did not ask for."""
        return self.status == vocab.RULE_STATUS_ADOPTED

    @property
    def statement(self) -> str:
        """The rule in one line, as a change log writes it."""
        return (
            f"{self.action_curie} {self.outcome_curie} in "
            f"{vocab.compact_iri(self.jurisdiction)}"
        )

    def sentence(self) -> str:
        """The rule as a sentence a reader can check against its basis."""
        readings = {
            vocab.OUTCOME_NOT_GRANTED: (
                f"{self.action_label} is not permitted unless the license permits it"
            ),
            _DALICC_NS + "GrantedByDefault": (
                f"{self.action_label} is permitted unless the license prohibits it"
            ),
            _DALICC_NS + "RequiredByDefault": (
                f"{self.action_label} is required unless the license waives it"
            ),
            _DALICC_NS + "NotWaivable": (
                f"the license cannot decide {self.action_label}, and a statement to the "
                "contrary is reported as a finding"
            ),
        }
        reading = readings.get(self.outcome, f"{self.action_label} is {self.outcome_label}")
        return f"In {vocab.jurisdiction_phrase(self.jurisdiction)}, {reading}."

    def as_triples(self) -> list[tuple[str, str, str]]:
        """The rule as the triples the graph holds, literals as plain strings."""
        triples = [
            (self.iri, P_RDF_TYPE, C_DEFAULT_RULE),
            (self.iri, P_RULE_APPLIES_TO, self.action),
            (self.iri, P_RULE_OUTCOME, self.outcome),
            (self.iri, P_RULE_JURISDICTION, self.jurisdiction),
            (self.iri, P_RULE_STATUS, self.status),
        ]
        if self.basis:
            triples.append((self.iri, P_RULE_BASIS, self.basis))
        if self.date:
            triples.append((self.iri, P_DATE, self.date))
        if self.label:
            triples.append((self.iri, P_LABEL, self.label))
        return triples


def make_rule(
    iri: str,
    action: str,
    outcome: str,
    jurisdiction: str,
    basis: str = "",
    status: str = "",
    date: str = "",
    label: str = "",
) -> Rule:
    """Build a rule from IRIs or CURIEs, without validating the terms."""
    return Rule(
        iri=_normalise_iri(iri),
        action=_normalise_iri(action),
        outcome=_normalise_iri(outcome),
        jurisdiction=_normalise_iri(jurisdiction),
        basis=(basis or "").strip(),
        status=_normalise_iri(status) or vocab.RULE_STATUS_PROPOSED,
        date=(date or "").strip(),
        label=(label or "").strip(),
    )


def rules_from_triples(triples: DependencyTriples) -> list[Rule]:
    """Collect the ``dalicc:DefaultRule`` nodes out of a graph's triples.

    A node counts as a rule when it names an action, an outcome and a jurisdiction.
    ``rdf:type dalicc:DefaultRule`` is written by every graph this repository ships and
    is not required here, because the triple store and the solver both hand the triples
    over unordered and a rule that lost its type is still a rule a reader wrote.
    """
    collected: dict[str, dict[str, str]] = {}
    for subject, predicate, obj in triples:
        if predicate == P_RDF_TYPE and obj == C_DEFAULT_RULE:
            collected.setdefault(subject, {})
        elif predicate in RULE_PREDICATES or predicate in (P_LABEL, P_DATE):
            collected.setdefault(subject, {})[predicate] = obj
    out: list[Rule] = []
    for iri, fields in collected.items():
        action = fields.get(P_RULE_APPLIES_TO, "")
        outcome = fields.get(P_RULE_OUTCOME, "")
        jurisdiction = fields.get(P_RULE_JURISDICTION, "")
        if not (action and outcome and jurisdiction):
            continue
        out.append(
            Rule(
                iri=_normalise_iri(iri),
                action=_normalise_iri(action),
                outcome=_normalise_iri(outcome),
                jurisdiction=_normalise_iri(jurisdiction),
                basis=fields.get(P_RULE_BASIS, "").strip(),
                status=_normalise_iri(fields.get(P_RULE_STATUS, ""))
                or vocab.RULE_STATUS_PROPOSED,
                date=fields.get(P_DATE, "").strip(),
                label=fields.get(P_LABEL, "").strip(),
            )
        )
    return sorted_rules(out)


def sorted_rules(rules: Iterable[Rule]) -> list[Rule]:
    """A stable reading order: adopted first, then by action, jurisdiction and IRI."""
    return sorted(
        rules,
        key=lambda rule: (
            0 if rule.adopted else 1,
            rule.action_label.lower(),
            rule.jurisdiction_label.lower(),
            rule.iri,
        ),
    )


def rule_triples(rules: Iterable[Rule]) -> list[tuple[str, str, str]]:
    """Rules as the ``(s, p, o)`` triples the consistency check reads."""
    return [triple for rule in rules for triple in rule.as_triples()]


def extends_from_triples(triples: DependencyTriples) -> str:
    """The graph a graph is read together with, or an empty string.

    Only one is returned: a graph that names several is a graph nobody can reason
    about predictably, and the validator refuses it.
    """
    targets = sorted(
        {obj for _s, predicate, obj in triples if predicate == P_EXTENDS_GRAPH}
    )
    return targets[0] if len(targets) == 1 else ""


# ---------------------------------------------------------------------------
# what a license does not say
# ---------------------------------------------------------------------------

#: The kind of statement a default rule adds, beside the three a license states.
DEFAULT_PERMISSION = "permission"
DEFAULT_PROHIBITION = "prohibition"
DEFAULT_DUTY = "duty"
DEFAULT_FINDING = "finding"

_OUTCOME_GRANTED = vocab.NAMESPACES["dalicc"] + "GrantedByDefault"
_OUTCOME_NOT_GRANTED = vocab.NAMESPACES["dalicc"] + "NotGrantedByDefault"
_OUTCOME_REQUIRED = vocab.NAMESPACES["dalicc"] + "RequiredByDefault"
_OUTCOME_NOT_WAIVABLE = vocab.NAMESPACES["dalicc"] + "NotWaivable"

_KIND_BY_OUTCOME = {
    _OUTCOME_GRANTED: DEFAULT_PERMISSION,
    _OUTCOME_NOT_GRANTED: DEFAULT_PROHIBITION,
    _OUTCOME_REQUIRED: DEFAULT_DUTY,
}


@dataclass(frozen=True, slots=True)
class DefaultStatement:
    """One statement a default rule supplies, or one finding it reports.

    ``kind`` is ``permission``, ``prohibition`` or ``duty`` for a statement the rule
    adds because the license is silent, and ``finding`` for a ``dalicc:NotWaivable``
    rule, which adds nothing and reports that the license says something the law of
    that jurisdiction does not let it say.  ``origin`` is always
    ``dalicc:FromDefaultRule``: a statement the license itself makes never comes
    through here.
    """

    action: str
    rule: str
    outcome: str
    jurisdiction: str
    basis: str
    kind: str
    reason: str
    origin: str = vocab.ORIGIN_FROM_DEFAULT_RULE
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON shape of one entry of the additive ``defaults`` array."""
        return {
            "kind": self.kind,
            "action": self.action,
            "action_label": vocab.action_label(self.action),
            "origin": self.origin,
            "rule": self.rule,
            "outcome": self.outcome,
            "outcome_label": vocab.DEFAULT_OUTCOMES.get(self.outcome, ""),
            "jurisdiction": self.jurisdiction,
            "jurisdiction_label": vocab.jurisdiction_label(self.jurisdiction),
            "basis": self.basis,
            "reason": self.reason,
            "label": self.label,
        }


def _as_statements(subject: Graph | _Statements | Any) -> _Statements:
    """Read whatever a caller passes as the deontic statements of one license."""
    if isinstance(subject, Graph):
        return _statements_from_graph(subject)
    if isinstance(subject, _Statements):
        return subject
    return statements_from_input(subject)


def spoken_for(
    statements: _Statements, index: dict[str, dict[str, set[str]]]
) -> set[str]:
    """Every action the license settles, itself or through the dependency graph.

    An action is settled when the license permits it, prohibits it or requires it, and
    also when the graph carries one of those statements to it: permitting an act
    permits everything it entails and every other name for it, prohibiting an act
    prohibits every special case of it and every other name for it, and a duty carries
    to the other names of the act it requires.  Those are the two closures the derived
    conflicts already use, so silence is read with exactly the reasoning the rest of
    the check is built on.

    Everything else is silence, and silence is what a default rule speaks about.
    """
    spoken = set(statements.permitted) | set(statements.prohibited) | set(statements.required)
    spoken |= set(_closure(statements.permitted, index, direction="permits"))
    spoken |= set(_closure(statements.prohibited, index, direction="forbids"))
    synonyms = _synonyms(index)
    for action in statements.required:
        spoken |= synonyms.get(action, {action})
    return spoken


def default_statements(
    subject: Graph | _Statements | Any,
    dependency_graph_triples: DependencyTriples | None = None,
) -> list[DefaultStatement]:
    """What the default rules of one dependency graph say about one license.

    Every rule the graph carries takes part: the core graph holds only rules the
    library has adopted, and a jurisdiction graph holds proposals, so choosing it is
    the reader's request to see what they would do.

    A rule whose outcome is ``dalicc:NotGrantedByDefault``, ``dalicc:GrantedByDefault``
    or ``dalicc:RequiredByDefault`` adds a statement when, and only when, the license is
    silent about its action.  A ``dalicc:NotWaivable`` rule adds nothing and reports a
    finding when the license states the opposite: a prohibition where the same graph
    also says the action is granted by default, because there the law keeps an
    exception open that a license may not close, and a permission everywhere else,
    because there the law keeps a protection in place that a license may not give away.

    Nothing here is legal advice: a rule is a reading of a legal default, named with
    the source it rests on, and what a license means is decided by its text.
    """
    triples = list(dependency_graph_triples) if dependency_graph_triples is not None else []
    rules = rules_from_triples(triples)
    if not rules:
        return []
    statements = _as_statements(subject)
    index = _relation_index(triples)
    spoken = spoken_for(statements, index)
    granted_actions = {rule.action for rule in rules if rule.outcome == _OUTCOME_GRANTED}

    out: list[DefaultStatement] = []
    for rule in sorted_rules(rules):
        label = vocab.action_label(rule.action)
        where = vocab.jurisdiction_phrase(rule.jurisdiction)
        if rule.outcome == _OUTCOME_NOT_WAIVABLE:
            # The law either keeps an exception open, in which case a license may not
            # close it, or keeps a protection in place, in which case a license may not
            # give it away.  A GrantedByDefault rule for the same action in the same
            # graph is how the graph says which.
            exception_kept_open = rule.action in granted_actions
            stated = (
                rule.action in statements.prohibited
                if exception_kept_open
                else rule.action in statements.permitted
            )
            if not stated:
                continue
            said = "prohibited" if exception_kept_open else "permitted"
            reason = (
                f"{label} is {said} by this license, and in {where} a license cannot "
                f"decide it. The statement is reported and not overridden: the record "
                f"says what the text says."
            )
            out.append(
                DefaultStatement(
                    action=rule.action,
                    rule=rule.iri,
                    outcome=rule.outcome,
                    jurisdiction=rule.jurisdiction,
                    basis=rule.basis,
                    kind=DEFAULT_FINDING,
                    reason=reason,
                    label=rule.label,
                )
            )
            continue
        kind = _KIND_BY_OUTCOME.get(rule.outcome)
        if kind is None or rule.action in spoken:
            continue
        readings = {
            DEFAULT_PROHIBITION: (
                f"This license says nothing about {label}, and in {where} it is not "
                f"permitted unless the license permits it."
            ),
            DEFAULT_PERMISSION: (
                f"This license says nothing about {label}, and in {where} it is "
                f"permitted unless the license prohibits it."
            ),
            DEFAULT_DUTY: (
                f"This license says nothing about {label}, and in {where} it is "
                f"required unless the license waives it."
            ),
        }
        out.append(
            DefaultStatement(
                action=rule.action,
                rule=rule.iri,
                outcome=rule.outcome,
                jurisdiction=rule.jurisdiction,
                basis=rule.basis,
                kind=kind,
                reason=readings[kind],
                label=rule.label,
            )
        )
    return out


def _with_defaults(
    statements: _Statements, defaults: Sequence[DefaultStatement]
) -> tuple[_Statements, dict[tuple[str, str], str]]:
    """Add the derived statements to the license's own, and say where each came from.

    The second member maps ``(rule kind, action)`` onto the rule that supplied it, so a
    conflict can name which side is not in the text.  A derived statement takes part in
    every conflict rule exactly as a stated one does; it is only the reporting that
    keeps the two apart.
    """
    origins: dict[tuple[str, str], str] = {}
    permitted = set(statements.permitted)
    prohibited = set(statements.prohibited)
    required = set(statements.required)
    license_wide = set(statements.license_wide_required)
    for entry in defaults:
        if entry.kind == DEFAULT_PERMISSION:
            permitted.add(entry.action)
            origins[(PERMISSION, entry.action)] = entry.rule
        elif entry.kind == DEFAULT_PROHIBITION:
            prohibited.add(entry.action)
            origins[(PROHIBITION, entry.action)] = entry.rule
        elif entry.kind == DEFAULT_DUTY:
            required.add(entry.action)
            license_wide.add(entry.action)
            origins[(DUTY, entry.action)] = entry.rule
            origins[(LICENSE_WIDE_DUTY, entry.action)] = entry.rule
    merged = _Statements(
        permitted=permitted,
        prohibited=prohibited,
        required=required,
        duties_by_permission=statements.duties_by_permission,
        prohibitions_with_duties=statements.prohibitions_with_duties,
        license_wide_required=license_wide,
        duties_by_prohibition=statements.duties_by_prohibition,
    )
    return merged, origins


_SHARE_ALIKE = vocab.NAMESPACES["cc"] + "ShareAlike"
_CHANGE_LICENSE = vocab.NAMESPACES["dalicc"] + "ChangeLicense"
_COMPLIANT_LICENSE = vocab.NAMESPACES["dalicc"] + "compliantLicense"


def consistency_check(
    subject: Graph | _Statements | Any,
    dependency_graph_triples: DependencyTriples | None = None,
) -> list[Conflict]:
    """Check a composed license for conflicting deontic statements.

    Step 2 of the four-step composer workflow from *DALICC License Composer - Future
    Features and Workflow* ("the newly composed license undergoes a consistency check
    to ensure that no conflicting deontic statements are present").

    Direct rules, which need no dependency graph:

    1. the same action is both permitted and prohibited;
    2. an action required as a duty is prohibited, or a prohibition carries duties;
    3. share-alike is required *for the whole work* while changing the license is
       permitted *without* a ``dalicc:compliantLicense`` duty, so the work could leave
       the license that requires it to stay.  A compatibility clause -- a
       ``dalicc:ChangeLicense`` permission that carries the ``dalicc:compliantLicense``
       duty, as the EUPL, CeCILL and LiLiQ records do -- is not a conflict, and neither
       is a share-alike duty attached to ``odrl:modify``, ``odrl:derive`` or
       ``odrl:distribute``: file-level reciprocity leaves the rest of the product free.
       ``odrl:grantUse`` is not part of this rule at all: sublicensing on the same terms
       is the normal way to satisfy a share-alike condition, which is why the axiom
       ``cc:ShareAlike dalicc:contradicts odrl:grantUse`` was retired on 2026-09-15.

    Derived rules use the dependency graph (``odrl:includedIn``, ``odrl:implies``,
    ``owl:sameAs``, ``dalicc:contradicts``): the permitted set is closed under
    ``implies``/``sameAs``, the prohibited set under ``includedIn`` read backwards and
    ``sameAs``, and any overlap that is not already a direct conflict is reported with
    the chain that produced it.  ``dalicc:contradicts`` is read as it stands, never
    chained with itself, but a synonym of either side counts as that side, because
    ``owl:sameAs`` makes every statement about one action a statement about the other.

    Rule 3 is the one reading the graph cannot carry, and it stays here for that
    reason: its four relations hold between two actions, and nothing in them can say
    that a *permission* lacks a *duty*.  Everything else this function concludes is a
    statement of the graph or a chain of them, so a deployment that edits the graph
    edits the check.

    ``subject`` is an :class:`rdflib.Graph` holding one or more ``odrl:Set`` documents,
    a :class:`_Statements` value, or an object carrying the fields
    :func:`statements_from_input` reads.  The third case is how
    :mod:`app.services.composer` passes a ``ComposerInput`` through without this module
    having to know the model.

    Every conflict carries the statements it is about (``Conflict.statements``, for
    example ``["Permission: Distribute", "Prohibition: Distribute"]``) and, when the
    dependency graph was needed to find it, the steps that connect them
    (``Conflict.chain``).  The reason sentence stays what it was.
    """
    statements = _as_statements(subject)
    triples = (
        list(dependency_graph_triples) if dependency_graph_triples is not None else []
    )
    index = _relation_index(triples)
    defaults = default_statements(statements, triples)
    statements, origins = _with_defaults(statements, defaults)

    def origin_of(rule: str, action: str) -> tuple[str, str]:
        """``(origin, rule IRI)`` for one side of a conflict."""
        supplier = origins.get((rule, action), "")
        if supplier:
            return vocab.ORIGIN_FROM_DEFAULT_RULE, supplier
        return vocab.ORIGIN_FROM_TEXT, ""

    conflicts: list[Conflict] = []

    for entry in defaults:
        if entry.kind != DEFAULT_FINDING:
            continue
        conflicts.append(
            Conflict(
                kind="default",
                action_1=entry.action,
                reason=entry.reason,
                statements=(
                    _statement(
                        PROHIBITION
                        if entry.action in statements.prohibited
                        else PERMISSION,
                        entry.action,
                    ),
                ),
                origin_1=vocab.ORIGIN_FROM_TEXT,
                origin_2=vocab.ORIGIN_FROM_DEFAULT_RULE,
                rule_2=entry.rule,
            )
        )

    # --- direct -----------------------------------------------------------
    for action in sorted(statements.permitted & statements.prohibited, key=vocab.action_label):
        label = vocab.action_label(action)
        conflicts.append(
            Conflict(
                kind="direct",
                action_1=action,
                action_2=action,
                reason=f"{label} is permitted and prohibited at the same time.",
                statements=(
                    _statement(PERMISSION, action),
                    _statement(PROHIBITION, action),
                ),
                origin_1=origin_of(PERMISSION, action)[0],
                rule_1=origin_of(PERMISSION, action)[1],
                origin_2=origin_of(PROHIBITION, action)[0],
                rule_2=origin_of(PROHIBITION, action)[1],
            )
        )

    for action in sorted(statements.required & statements.prohibited, key=vocab.action_label):
        label = vocab.action_label(action)
        rule = LICENSE_WIDE_DUTY if action in statements.license_wide_required else DUTY
        conflicts.append(
            Conflict(
                kind="direct",
                action_1=action,
                action_2=action,
                reason=(
                    f"{label} is required as a duty but is prohibited, so the duty can "
                    f"never be discharged."
                ),
                statements=(_statement(rule, action), _statement(PROHIBITION, action)),
                origin_1=origin_of(rule, action)[0],
                rule_1=origin_of(rule, action)[1],
                origin_2=origin_of(PROHIBITION, action)[0],
                rule_2=origin_of(PROHIBITION, action)[1],
            )
        )

    for action in sorted(statements.prohibitions_with_duties, key=vocab.action_label):
        label = vocab.action_label(action)
        attached = sorted(statements.duties_by_prohibition.get(action, ()), key=vocab.action_label)
        conflicts.append(
            Conflict(
                kind="direct",
                action_1=action,
                reason=f"{label} is prohibited, so the duties attached to it can never apply.",
                statements=(
                    _statement(PROHIBITION, action),
                    *(_statement(DUTY, duty_action) for duty_action in attached),
                ),
            )
        )

    if (
        _SHARE_ALIKE in statements.license_wide_required
        and _CHANGE_LICENSE in statements.permitted
        and _COMPLIANT_LICENSE
        not in statements.duties_by_permission.get(_CHANGE_LICENSE, set())
    ):
        conflicts.append(
            Conflict(
                kind="direct",
                action_1=_SHARE_ALIKE,
                action_2=_CHANGE_LICENSE,
                reason=(
                    "Share alike is required for the whole work while changing the license "
                    "is permitted without a duty to use a compliant license, so the work "
                    "could leave the license that requires it to stay."
                ),
                statements=(
                    _statement(LICENSE_WIDE_DUTY, _SHARE_ALIKE),
                    _statement(PERMISSION, _CHANGE_LICENSE),
                ),
                origin_1=origin_of(LICENSE_WIDE_DUTY, _SHARE_ALIKE)[0],
                rule_1=origin_of(LICENSE_WIDE_DUTY, _SHARE_ALIKE)[1],
                origin_2=origin_of(PERMISSION, _CHANGE_LICENSE)[0],
                rule_2=origin_of(PERMISSION, _CHANGE_LICENSE)[1],
            )
        )

    # --- derived ----------------------------------------------------------
    direct_pairs = {(c.action_1, c.action_2) for c in conflicts}

    permitted_closure = _closure(statements.permitted, index, direction="permits")
    prohibited_closure = _closure(statements.prohibited, index, direction="forbids")

    for action in sorted(set(permitted_closure) | statements.permitted, key=vocab.action_label):
        if action not in prohibited_closure and action not in statements.prohibited:
            continue
        # A statement the license makes about this very action is a seed of its own,
        # next to the ones the graph reached.  Both are kept: once an action is both
        # named outright and reachable through the graph -- Derivative works, which
        # the Ordnance Survey records prohibit and which is also included in the
        # Distribute they prohibit -- dropping the outright one would hide the
        # plainest reading of the conflict behind the longer chain.
        permit_seeds = list(permitted_closure.get(action, ())) + (
            [(action, "")] if action in statements.permitted else []
        )
        forbid_seeds = list(prohibited_closure.get(action, ())) + (
            [(action, "")] if action in statements.prohibited else []
        )
        for permit_seed, permit_why in permit_seeds:
            for forbid_seed, forbid_why in forbid_seeds:
                if (permit_seed, forbid_seed) in direct_pairs or permit_seed == forbid_seed:
                    continue
                if not permit_why and not forbid_why:
                    continue
                chain = " ".join(
                    part for part in (f"{permit_why}." if permit_why else "",
                                      f"{forbid_why}." if forbid_why else "") if part
                )
                conflicts.append(
                    Conflict(
                        kind="derived",
                        action_1=permit_seed,
                        action_2=forbid_seed,
                        reason=(
                            f"{vocab.action_label(permit_seed)} is permitted while "
                            f"{vocab.action_label(forbid_seed)} is prohibited, and both "
                            f"cover {vocab.action_label(action)}. {chain}".strip()
                        ),
                        statements=(
                            _statement(PERMISSION, permit_seed),
                            _statement(PROHIBITION, forbid_seed),
                        ),
                        chain=chain,
                        origin_1=origin_of(PERMISSION, permit_seed)[0],
                        rule_1=origin_of(PERMISSION, permit_seed)[1],
                        origin_2=origin_of(PROHIBITION, forbid_seed)[0],
                        rule_2=origin_of(PROHIBITION, forbid_seed)[1],
                    )
                )
                direct_pairs.add((permit_seed, forbid_seed))

    asserted = statements.permitted | statements.required
    contradictions = _contradictions(index)
    reported: set[tuple[str, str]] = set()
    for action in sorted(asserted, key=vocab.action_label):
        for other, stated in sorted(contradictions.get(action, {}).items()):
            if other not in asserted or other == action:
                continue
            pair = tuple(sorted((action, other)))
            if pair in reported:
                continue
            reported.add(pair)  # type: ignore[arg-type]
            conflicts.append(
                Conflict(
                    kind="derived",
                    action_1=action,
                    action_2=other,
                    reason=(
                        f"{vocab.action_label(action)} contradicts "
                        f"{vocab.action_label(other)} in the dependency graph, and this "
                        f"license asserts both."
                    ),
                    statements=(
                        _statement(_rule_of(action, statements), action),
                        _statement(_rule_of(other, statements), other),
                    ),
                    chain=_contradiction_chain(action, other, stated),
                    origin_1=origin_of(_rule_of(action, statements), action)[0],
                    rule_1=origin_of(_rule_of(action, statements), action)[1],
                    origin_2=origin_of(_rule_of(other, statements), other)[0],
                    rule_2=origin_of(_rule_of(other, statements), other)[1],
                )
            )

    return conflicts
