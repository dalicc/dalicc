# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""What the program concludes about each shape a licence can state.

The composer's expert view lets a person build a permission with duties under it, a
prohibition, and duties of the licence as a whole; licence documents in the library
also carry duties under a prohibition and under another duty.  Every one of those has
to reach the program as a fact and has to be reasoned over, so one test per shape
pins the verdict: one licence that must conflict and one that must pass.

``query.lp`` is read as it ships and run under plain ``clingo``.  The three rules that
call an external atom are the only part ``clingo`` cannot parse, so they are dropped
and the facts they would have produced are given directly -- which is exactly what
``&getLicense`` and ``&getLicenseDuties`` hand the program at run time.  Skipped when
``clingo`` is missing, like the solver test next door.
"""

from __future__ import annotations

from pathlib import Path

import pytest

clingo = pytest.importorskip("clingo")

ODRL = "http://www.w3.org/ns/odrl/2/"
CC = "http://creativecommons.org/ns#"
DALICC = "https://dalicc.net/ns#"
OWL = "http://www.w3.org/2002/07/owl#"
LIB = "https://dalicc.net/licenselibrary/"

PROGRAM = Path(__file__).resolve().parents[1] / "app" / "programs" / "query.lp"


def rules_only() -> str:
    """``query.lp`` without the rules that call an external atom."""
    return "\n".join(
        line for line in PROGRAM.read_text(encoding="utf-8").splitlines() if "&get" not in line
    )


def fact(name: str, *args: str) -> str:
    """One ASP fact with quoted string arguments, as the plugin's output grounds to."""
    return f"{name}({','.join(chr(34) + arg + chr(34) for arg in args)})."


def solve(*facts: str) -> list[str]:
    """The shown atoms of the first answer set."""
    control = clingo.Control(["--warn=none"])
    control.add("base", [], rules_only() + "\n" + "\n".join(facts))
    control.ground([("base", [])])
    with control.solve(yield_=True) as handle:
        for model in handle:
            return sorted(str(symbol) for symbol in model.symbols(shown=True))
    return []


def kinds(atoms: list[str]) -> set[str]:
    """The reading that produced each direct conflict, as its last argument says."""
    out = set()
    for atom in atoms:
        if atom.startswith("directConflict"):
            out.add(atom.rsplit('"', 2)[-2])
    return out


# ---------------------------------------------------------------------------
# a permission with duties under it
# ---------------------------------------------------------------------------


def test_a_duty_under_a_permission_reaches_the_program() -> None:
    """It is a fact of its own, naming the permission it hangs on."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "distribute"),
        fact(
            "licenseDuty",
            LIB + "A",
            ODRL + "permission",
            ODRL + "distribute",
            CC + "Attribution",
        ),
        fact("license", LIB + "A", ODRL + "prohibition", CC + "Attribution"),
    )
    assert "duty-prohibited" in kinds(atoms)
    assert any(CC + "Attribution" in atom for atom in atoms)


def test_a_permission_with_duties_and_nothing_against_them_passes() -> None:
    """The commonest shape in the library is not a conflict."""
    assert (
        solve(
            fact("license", LIB + "A", ODRL + "permission", ODRL + "distribute"),
            fact(
                "licenseDuty",
                LIB + "A",
                ODRL + "permission",
                ODRL + "distribute",
                CC + "Attribution",
            ),
        )
        == []
    )


# ---------------------------------------------------------------------------
# a prohibition, with and without duties under it
# ---------------------------------------------------------------------------


def test_a_duty_under_a_prohibition_is_a_conflict() -> None:
    """The act the duty conditions is forbidden, so the duty can never apply."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "prohibition", ODRL + "sell"),
        fact("licenseDuty", LIB + "A", ODRL + "prohibition", ODRL + "sell", CC + "Attribution"),
    )
    assert kinds(atoms) == {"duty-on-prohibition"}


def test_a_prohibition_on_its_own_passes() -> None:
    """Forbidding an act nobody is permitted to do states no contradiction."""
    assert solve(fact("license", LIB + "A", ODRL + "prohibition", ODRL + "sell")) == []


# ---------------------------------------------------------------------------
# a duty under a duty
# ---------------------------------------------------------------------------


def test_a_duty_under_a_duty_is_still_required() -> None:
    """It is not flattened away: prohibiting it anywhere in the bundle conflicts."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "duty", CC + "Notice"),
        fact("licenseDuty", LIB + "A", ODRL + "duty", CC + "Notice", CC + "Attribution"),
        fact("license", LIB + "B", ODRL + "prohibition", CC + "Attribution"),
    )
    assert "duty-prohibited" in kinds(atoms)


def test_a_duty_under_a_duty_on_its_own_passes() -> None:
    """Nothing forbids it, so nothing is concluded."""
    assert (
        solve(
            fact("license", LIB + "A", ODRL + "duty", CC + "Notice"),
            fact("licenseDuty", LIB + "A", ODRL + "duty", CC + "Notice", CC + "Attribution"),
        )
        == []
    )


# ---------------------------------------------------------------------------
# duties of the licence as a whole
# ---------------------------------------------------------------------------


def test_a_licence_wide_duty_that_is_prohibited_conflicts() -> None:
    """The same reading as a nested duty, because the action is required either way."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "duty", CC + "ShareAlike"),
        fact("license", LIB + "B", ODRL + "prohibition", CC + "ShareAlike"),
    )
    assert "duty-prohibited" in kinds(atoms)


def test_a_licence_wide_duty_on_its_own_passes() -> None:
    """Share alike alone is what most reciprocal licences state."""
    assert solve(fact("license", LIB + "A", ODRL + "duty", CC + "ShareAlike")) == []


# ---------------------------------------------------------------------------
# the answers that were already there
# ---------------------------------------------------------------------------


def test_permission_against_prohibition_is_unchanged() -> None:
    """The oldest answer of the program keeps its wording marker."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "distribute"),
        fact("license", LIB + "B", ODRL + "prohibition", ODRL + "distribute"),
    )
    assert kinds(atoms) == {"direct"}


def test_two_permissions_the_graph_calls_contradictory_are_unchanged() -> None:
    """The generalised rule produces the permission-permission atom it always did."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "ensureExclusivity"),
        fact("license", LIB + "B", ODRL + "permission", ODRL + "commercialize"),
        fact("dg", ODRL + "ensureExclusivity", DALICC + "contradicts", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert len(derived) == 1
    assert ODRL + "permission" in derived[0]
    assert "contradicts" in derived[0]


def test_a_duty_can_contradict_a_permission() -> None:
    """Requiring an act asserts it, so the graph's contradiction reaches it too."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "commercialize"),
        fact(
            "licenseDuty",
            LIB + "B",
            ODRL + "permission",
            ODRL + "distribute",
            ODRL + "ensureExclusivity",
        ),
        fact("dg", ODRL + "ensureExclusivity", DALICC + "contradicts", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert len(derived) == 1
    assert ODRL + "duty" in derived[0]


# ---------------------------------------------------------------------------
# chains that cross from one relation of the graph into another
# ---------------------------------------------------------------------------


def test_a_synonym_carries_an_entailment_on() -> None:
    """Charging a licence fee entails commercializing, and that is commercial use."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", DALICC + "chargeLicenseFee"),
        fact("license", LIB + "B", ODRL + "prohibition", CC + "CommercialUse"),
        fact("dg", DALICC + "chargeLicenseFee", ODRL + "implies", ODRL + "commercialize"),
        fact("dg", CC + "CommercialUse", OWL + "sameAs", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert derived
    assert all("implies" in atom for atom in derived)


def test_a_synonym_carries_a_subsumption_on() -> None:
    """Selling a copy is selling, selling is commercializing, and that is commercial use."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", DALICC + "sellCopy"),
        fact("license", LIB + "B", ODRL + "prohibition", CC + "CommercialUse"),
        fact("dg", DALICC + "sellCopy", ODRL + "includedIn", ODRL + "sell"),
        fact("dg", ODRL + "sell", ODRL + "includedIn", ODRL + "commercialize"),
        fact("dg", CC + "CommercialUse", OWL + "sameAs", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert derived
    assert all("includedIn" in atom for atom in derived)


def test_a_synonym_carries_a_contradiction_on() -> None:
    """The axiom is written about one name and reaches the other name of that act."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "ensureExclusivity"),
        fact("license", LIB + "B", ODRL + "permission", CC + "CommercialUse"),
        fact("dg", ODRL + "ensureExclusivity", DALICC + "contradicts", ODRL + "commercialize"),
        fact("dg", CC + "CommercialUse", OWL + "sameAs", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert derived
    assert all("contradicts" in atom for atom in derived)


def test_a_synonym_carries_a_contradiction_to_a_required_act() -> None:
    """A duty nested under a prohibition asserts its act, synonym chain included."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "ensureExclusivity"),
        fact(
            "licenseDuty",
            LIB + "B",
            ODRL + "prohibition",
            ODRL + "distribute",
            CC + "CommercialUse",
        ),
        fact("dg", ODRL + "ensureExclusivity", DALICC + "contradicts", ODRL + "commercialize"),
        fact("dg", CC + "CommercialUse", OWL + "sameAs", ODRL + "commercialize"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert derived
    assert all("contradicts" in atom and ODRL + "duty" in atom for atom in derived)


def test_an_entailed_act_meets_a_prohibition_of_what_it_is_part_of() -> None:
    """Deriving entails a derivative work, and a derivative work is distributed."""
    atoms = solve(
        fact("license", LIB + "A", ODRL + "permission", ODRL + "derive"),
        fact("license", LIB + "B", ODRL + "prohibition", ODRL + "distribute"),
        fact("dg", ODRL + "derive", ODRL + "implies", CC + "DerivativeWorks"),
        fact("dg", CC + "DerivativeWorks", ODRL + "includedIn", ODRL + "distribute"),
    )
    derived = [atom for atom in atoms if atom.startswith("derivedConflict")]
    assert derived
    assert all("implies" in atom for atom in derived)


def test_a_chain_that_runs_the_wrong_way_stays_silent() -> None:
    """Permitting the wider act says nothing about a prohibition of the narrower one."""
    assert (
        solve(
            fact("license", LIB + "A", ODRL + "permission", ODRL + "sell"),
            fact("license", LIB + "B", ODRL + "prohibition", DALICC + "sellCopy"),
            fact("dg", DALICC + "sellCopy", ODRL + "includedIn", ODRL + "sell"),
        )
        == []
    )
