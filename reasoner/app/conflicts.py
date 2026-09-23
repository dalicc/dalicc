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
    "DERIVED_HEADLINE",
    "DIRECT_REASON",
    "DIRECT_REASONS",
    "atoms_from_stdout",
    "build_conflict_response",
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
}

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


def build_conflict_response(atoms: list[Atom]) -> dict[str, Any]:
    """Build ``{"conflicting_statements": {"direct": ..., "derived": ...}}``."""
    response = empty_conflict_response()
    direct = response["conflicting_statements"]["direct"]
    derived = response["conflicting_statements"]["derived"]

    direct_index = 0
    derived_index = 0
    for atom in atoms:
        if atom.name == "directConflict":
            if len(atom.args) < 6:
                logger.warning("skipping malformed directConflict/%d", len(atom.args))
                continue
            kind = atom.args[6] if len(atom.args) > 6 else "direct"
            direct[str(direct_index)] = {
                "statement_1": [atom.args[0], atom.args[1], atom.args[2]],
                "statement_2": [atom.args[3], atom.args[4], atom.args[5]],
                "reason": DIRECT_REASONS.get(kind, DIRECT_REASON),
            }
            direct_index += 1
        elif atom.name == "derivedConflict":
            if len(atom.args) < 10:
                logger.warning("skipping malformed derivedConflict/%d", len(atom.args))
                continue
            derived[str(derived_index)] = {
                "statement_1": [atom.args[0], atom.args[1], atom.args[2]],
                "statement_2": [atom.args[3], atom.args[4], atom.args[5]],
                "reason": _derived_reason(atom.args),
            }
            derived_index += 1
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
