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

Nothing this module reports is legal advice.  A conflict is a statement about the model
of a license, reached by the rules written here and by the axioms of the dependency
graph; what the license means is decided by its text.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from dalicc_check import vocab

__all__ = [
    "DUTY",
    "LICENSE_WIDE_DUTY",
    "PERMISSION",
    "PROHIBITION",
    "Conflict",
    "DependencyTriples",
    "consistency_check",
    "statements_from_input",
]


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

    def as_dict(self) -> dict[str, Any]:
        """JSON shape published by ``POST /licenselibrary/consistencycheck``.

        ``statements`` and ``chain`` were added later and are always present; the six
        keys before them are unchanged.
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
        }


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
    if isinstance(subject, Graph):
        statements = _statements_from_graph(subject)
    elif isinstance(subject, _Statements):
        statements = subject
    else:
        statements = statements_from_input(subject)
    triples = (
        list(dependency_graph_triples) if dependency_graph_triples is not None else []
    )
    index = _relation_index(triples)
    conflicts: list[Conflict] = []

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
                )
            )

    return conflicts
