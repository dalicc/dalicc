# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Translation of solver atoms into the public ``/compatibilitycheck/`` shape.

The wire format is part of the DALICC public API contract and is reproduced
byte-for-byte here, including the two quirks it inherited from the original
implementation:

* the ``direct`` / ``derived`` members are JSON *objects* keyed by stringified
  integer indices (``"0"``, ``"1"``, ...), not arrays;
* the trailing sentence of a derived reason is swapped -- ``R = "derived"``
  renders "is given in the dependency graph." and ``R = "dependencygraph"``
  renders "is derived from the statements in the dependency graph.".  Clients
  match on these strings, so the swap is preserved deliberately.
"""

from __future__ import annotations

import logging
from typing import Any

from .answersets import Atom, extract_answer_sets, parse_atoms

__all__ = [
    "CONTRADICTION_HEADLINE",
    "DEFAULT_KINDS",
    "DEFAULT_RULE_REASON",
    "DERIVED_HEADLINE",
    "DIRECT_REASON",
    "DIRECT_REASONS",
    "NOT_WAIVABLE_REASON",
    "ORIGIN_FROM_DEFAULT_RULE",
    "ORIGIN_FROM_TEXT",
    "atoms_from_stdout",
    "build_conflict_response",
    "build_defaults",
    "build_dependency_graph_rows",
    "empty_conflict_response",
]

logger = logging.getLogger(__name__)

DIRECT_REASON = "Direct permission-prohibition conflict."

#: The last argument of ``directConflict/7`` says which reading produced it, and this
#: maps it onto the sentence the client reads.  ``direct`` is the permission against
#: prohibition case and keeps the sentence it has always had, so no client sees a
#: change.  The other two come from the duties a licence hangs on one of its rules,
#: which the program could not see before.
DIRECT_REASONS = {
    "direct": DIRECT_REASON,
    "duty-prohibited": (
        "Direct duty-prohibition conflict. The action is required as a duty and "
        "prohibited, so the duty can never be discharged."
    ),
    "duty-on-prohibition": (
        "Direct conflict. The action is prohibited, so the duties attached to it can "
        "never apply."
    ),
    "share-alike-escape": (
        "Direct conflict. Share alike is required for the whole work while changing "
        "the license is permitted without a duty to use a compliant license, so the "
        "work could leave the license that requires it to stay."
    ),
    "share-alike-reciprocity": (
        "Direct conflict. Both licenses require the whole work, or every work derived "
        "from it, to stay under themselves, and no later-version option or "
        "compatibility clause leads from one to the other, so one combined work cannot "
        "satisfy both."
    ),
    "share-alike-direction": (
        "Direct restriction. Both licenses require the whole work to stay under "
        "themselves, and the first names the second as a license a work under it may be "
        "released under, so the combined work has to be released under the second."
    ),
}

#: The two values ``dalicc:statementOrigin`` takes in an answer.  Every statement a
#: licence makes is ``FromText``; a statement a default rule supplied for an action the
#: licence is silent about is ``FromDefaultRule``, and the rule that supplied it is
#: named beside it so a reader can look it up.
ORIGIN_FROM_TEXT = "https://dalicc.net/ns#FromText"
ORIGIN_FROM_DEFAULT_RULE = "https://dalicc.net/ns#FromDefaultRule"

#: ``odrl`` predicate -> the word the ``defaults`` array uses for it.
DEFAULT_KINDS = {
    "http://www.w3.org/ns/odrl/2/permission": "permission",
    "http://www.w3.org/ns/odrl/2/prohibition": "prohibition",
    "http://www.w3.org/ns/odrl/2/duty": "duty",
}

#: The sentence a derived statement carries.  It says what the statement is and where
#: it came from, and it never claims that the licence says it.
DEFAULT_RULE_REASON = (
    "This license says nothing about the action. The statement comes from a default "
    "rule of the dependency graph, not from the text."
)

#: The sentence a dalicc:NotWaivable finding carries.  Such a rule adds nothing: it
#: reports that the licence states something the law of that jurisdiction does not let
#: it state, and the record is left as it is.
NOT_WAIVABLE_REASON = (
    "This license states the action, and a default rule of the dependency graph says "
    "that a license cannot decide it in that jurisdiction. The statement is reported "
    "and not overridden."
)

PREFIX_BY_RELATION = {
    "sameAs": "http://www.w3.org/2002/07/owl#",
    "implies": "http://www.w3.org/ns/odrl/2/",
    "contradicts": "https://dalicc.net/ns#",
    "includedIn": "http://www.w3.org/ns/odrl/2/",
}


def atoms_from_stdout(stdout: str) -> list[Atom]:
    """Return the atoms of the first answer set in *stdout* (``[]`` if none)."""
    blocks = extract_answer_sets(stdout)
    if not blocks:
        return []
    if len(blocks) > 1:
        logger.warning("solver returned %d answer sets; using the first", len(blocks))
    return parse_atoms(blocks[0])


def empty_conflict_response() -> dict[str, Any]:
    """The normalised empty result."""
    return {"conflicting_statements": {"direct": {}, "derived": {}}}


def _relation_prefix(relation: str) -> str:
    for key, prefix in PREFIX_BY_RELATION.items():
        if key in relation:
            return prefix
    return ""


#: Opening sentence of a derived reason, by the relation that produced it.  The
#: ``contradicts`` case is the only one where both statements are permissions: two acts
#: the graph says cannot both be allowed of the same asset.  It has a sentence of its
#: own because calling that a permission-prohibition conflict would be untrue.
DERIVED_HEADLINE = "Derived permission-prohibition conflict."
CONTRADICTION_HEADLINE = "Derived conflict between two permissions."


def _derived_reason(args: tuple[str, ...]) -> str:
    relation, due_to_1, due_to_2, provenance = args[6], args[7], args[8], args[9]
    prefix = _relation_prefix(relation)
    if provenance == "derived":
        tail = "is given in the dependency graph."
    else:
        tail = "is derived from the statements in the dependency graph."
    headline = CONTRADICTION_HEADLINE if "contradicts" in relation else DERIVED_HEADLINE
    return f"{headline} ({due_to_1},{prefix}{relation},{due_to_2}) {tail}"


def build_defaults(atoms: list[Atom]) -> list[dict[str, Any]]:
    """The ``defaults`` array: what the default rules said about each licence.

    One entry per derived statement and per ``dalicc:NotWaivable`` finding, sorted so
    that the same answer always comes back in the same order.  The array is additive:
    it is left out of the answer entirely when no rule fired, so a deployment whose
    graph carries no rules gets the answer it has always got.
    """
    out: list[dict[str, Any]] = []
    for atom in atoms:
        if atom.name == "defaultStatement":
            if len(atom.args) < 4:
                logger.warning("skipping malformed defaultStatement/%d", len(atom.args))
                continue
            licence, predicate, action, rule = atom.args[:4]
            out.append(
                {
                    "license": licence,
                    "kind": DEFAULT_KINDS.get(predicate, "statement"),
                    "statement": [licence, predicate, action],
                    "action": action,
                    "origin": ORIGIN_FROM_DEFAULT_RULE,
                    "rule": rule,
                    "reason": DEFAULT_RULE_REASON,
                }
            )
        elif atom.name == "defaultFinding":
            if len(atom.args) < 4:
                logger.warning("skipping malformed defaultFinding/%d", len(atom.args))
                continue
            licence, action, rule, predicate = atom.args[:4]
            out.append(
                {
                    "license": licence,
                    "kind": "finding",
                    "statement": [licence, predicate, action],
                    "action": action,
                    "origin": ORIGIN_FROM_DEFAULT_RULE,
                    "rule": rule,
                    "reason": NOT_WAIVABLE_REASON,
                }
            )
    out.sort(key=lambda entry: (entry["license"], entry["kind"], entry["action"], entry["rule"]))
    return out


def build_conflict_response(atoms: list[Atom]) -> dict[str, Any]:
    """Build ``{"conflicting_statements": {"direct": ..., "derived": ...}}``.

    When the dependency graph carries default rules that fired, the answer also holds
    an additive ``defaults`` array, and every conflict carries ``origin_1``,
    ``origin_2``, ``rule_1`` and ``rule_2``, which say for each side whether it came
    from the text of the licence or from one of those rules.  Neither is present when
    no rule fired, so the historical answer is unchanged byte for byte.
    """
    response = empty_conflict_response()
    direct = response["conflicting_statements"]["direct"]
    derived = response["conflicting_statements"]["derived"]

    defaults = build_defaults(atoms)
    supplied = {
        (entry["statement"][0], entry["statement"][1], entry["statement"][2]): entry["rule"]
        for entry in defaults
        if entry["kind"] != "finding"
    }

    def origins(statement_1: list[str], statement_2: list[str]) -> dict[str, str]:
        """``origin_n`` and ``rule_n`` for the two sides of one conflict."""
        out: dict[str, str] = {}
        for position, statement in ((1, statement_1), (2, statement_2)):
            rule = supplied.get(tuple(statement), "")
            out[f"origin_{position}"] = (
                ORIGIN_FROM_DEFAULT_RULE if rule else ORIGIN_FROM_TEXT
            )
            out[f"rule_{position}"] = rule
        return out

    direct_index = 0
    derived_index = 0
    for atom in atoms:
        if atom.name == "directConflict":
            if len(atom.args) < 6:
                logger.warning("skipping malformed directConflict/%d", len(atom.args))
                continue
            kind = atom.args[6] if len(atom.args) > 6 else "direct"
            statement_1 = [atom.args[0], atom.args[1], atom.args[2]]
            statement_2 = [atom.args[3], atom.args[4], atom.args[5]]
            direct[str(direct_index)] = {
                "statement_1": statement_1,
                "statement_2": statement_2,
                "reason": DIRECT_REASONS.get(kind, DIRECT_REASON),
                **(origins(statement_1, statement_2) if defaults else {}),
            }
            direct_index += 1
        elif atom.name == "derivedConflict":
            if len(atom.args) < 10:
                logger.warning("skipping malformed derivedConflict/%d", len(atom.args))
                continue
            statement_1 = [atom.args[0], atom.args[1], atom.args[2]]
            statement_2 = [atom.args[3], atom.args[4], atom.args[5]]
            derived[str(derived_index)] = {
                "statement_1": statement_1,
                "statement_2": statement_2,
                "reason": _derived_reason(atom.args),
                **(origins(statement_1, statement_2) if defaults else {}),
            }
            derived_index += 1
    if defaults:
        response["defaults"] = defaults
    return response


def build_dependency_graph_rows(stdout: str, *, legacy: bool) -> list[list[str]]:
    """Return the ``t/3`` atoms of ``getdepgraph.lp`` as triples.

    ``legacy=True`` reproduces the historical string shape exactly: every term
    keeps its surrounding double quotes and the object of the *last* triple
    keeps the trailing ``)`` that the old ``split("),")`` parser left behind.
    ``legacy=False`` returns clean, unquoted IRIs.
    """
    atoms = [atom for atom in atoms_from_stdout(stdout) if atom.name == "t" and len(atom.args) == 3]
    if not legacy:
        return [list(atom.args) for atom in atoms]

    rows: list[list[str]] = []
    for position, atom in enumerate(atoms):
        subject, predicate, obj = (f'"{value}"' for value in atom.args)
        if position == len(atoms) - 1:
            obj = f"{obj})"
        rows.append([subject, predicate, obj])
    return rows
