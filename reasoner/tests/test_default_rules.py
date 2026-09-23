# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""What the program concludes about an action a licence does not mention.

A dependency graph carries a second kind of statement beside its axioms: a
``dalicc:DefaultRule``, which names one action, what applies to it when the licence is
silent, the territory it holds in and the legal source it rests on.  The program reads
those rules, supplies the statement each one calls for, and lets it take part in the
conflict rules exactly as a statement of the text does, while saying on every finding
which side is which.

``query.lp`` is read as it ships and run under plain ``clingo``, like the shape tests
next door.  Nothing asserted here is legal advice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.answersets import Atom
from app.conflicts import build_conflict_response

clingo = pytest.importorskip("clingo")

ODRL = "http://www.w3.org/ns/odrl/2/"
DALICC = "https://dalicc.net/ns#"
LIB = "https://dalicc.net/licenselibrary/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

PROGRAM = Path(__file__).resolve().parents[1] / "app" / "programs" / "query.lp"

RULE = "https://dalicc.net/dependencygraph/rules/endorsement-worldwide"


def rules_only() -> str:
    """``query.lp`` without the rules that call an external atom."""
    return "\n".join(
        line for line in PROGRAM.read_text(encoding="utf-8").splitlines() if "&get" not in line
    )


def fact(name: str, *args: str) -> str:
    """One ASP fact with quoted string arguments."""
    return f"{name}({','.join(chr(34) + arg + chr(34) for arg in args)})."


def rule_facts(iri: str, action: str, outcome: str) -> list[str]:
    """The ``dg/3`` facts one default rule grounds to."""
    return [
        fact("dg", iri, RDF_TYPE, DALICC + "DefaultRule"),
        fact("dg", iri, DALICC + "appliesTo", action),
        fact("dg", iri, DALICC + "defaultOutcome", outcome),
        fact("dg", iri, DALICC + "inJurisdiction", DALICC + "worldwide"),
        fact("dg", iri, DALICC + "ruleStatus", DALICC + "Adopted"),
    ]


def solve(*facts: str) -> list[str]:
    """The shown atoms of the first answer set."""
    control = clingo.Control(["--warn=none"])
    control.add("base", [], rules_only() + "\n" + "\n".join(facts))
    control.ground([("base", [])])
    with control.solve(yield_=True) as handle:
        for model in handle:
            return sorted(str(symbol) for symbol in model.symbols(shown=True))
    return []


def atoms_of(shown: list[str]) -> list[Atom]:
    """The shown atoms parsed back into the shape ``conflicts.py`` reads."""
    out = []
    for text in shown:
        name, _, rest = text.partition("(")
        args = tuple(part.strip().strip('"') for part in rest[:-1].split('","'))
        args = tuple(part.strip('"') for part in args)
        out.append(Atom(name=name, args=args))
    return out


SILENT = [fact("license", LIB + "Silent")]
PERMITTING = [
    fact("license", LIB + "Permitting"),
    fact("license", LIB + "Permitting", ODRL + "permission", DALICC + "promote"),
]


def test_a_silent_licence_gets_the_statement_the_rule_supplies() -> None:
    """The endorsement rule turns silence into a prohibition, and says it did."""
    shown = solve(*SILENT, *rule_facts(RULE, DALICC + "promote", DALICC + "NotGrantedByDefault"))
    assert shown == [
        f'defaultStatement("{LIB}Silent","{ODRL}prohibition","{DALICC}promote","{RULE}")'
    ]


def test_a_licence_that_states_the_action_gets_nothing() -> None:
    """A rule reaches silence and nothing else."""
    shown = solve(
        *PERMITTING, *rule_facts(RULE, DALICC + "promote", DALICC + "NotGrantedByDefault")
    )
    assert not [atom for atom in shown if atom.startswith("defaultStatement")]


def test_a_silent_licence_meets_one_that_permits_the_action() -> None:
    """The bundle of the two conflicts, and the finding names the rule on one side."""
    shown = solve(
        *SILENT,
        *PERMITTING,
        *rule_facts(RULE, DALICC + "promote", DALICC + "NotGrantedByDefault"),
    )
    conflicts = [atom for atom in shown if atom.startswith("directConflict")]
    assert len(conflicts) == 1

    answer = build_conflict_response(atoms_of(shown))
    entry = answer["conflicting_statements"]["direct"]["0"]
    assert entry["statement_1"] == [LIB + "Permitting", ODRL + "permission", DALICC + "promote"]
    assert entry["statement_2"] == [LIB + "Silent", ODRL + "prohibition", DALICC + "promote"]
    assert entry["reason"] == "Direct permission-prohibition conflict."
    assert entry["origin_1"] == DALICC + "FromText"
    assert entry["rule_1"] == ""
    assert entry["origin_2"] == DALICC + "FromDefaultRule"
    assert entry["rule_2"] == RULE

    defaults = answer["defaults"]
    assert [item["kind"] for item in defaults] == ["prohibition"]
    assert defaults[0]["license"] == LIB + "Silent"
    assert defaults[0]["rule"] == RULE


def test_the_answer_is_unchanged_when_no_rule_fires() -> None:
    """A deployment whose graph carries no rule gets the answer it always got."""
    shown = solve(*SILENT, *PERMITTING)
    answer = build_conflict_response(atoms_of(shown))
    assert set(answer) == {"conflicting_statements"}


@pytest.mark.parametrize(
    ("outcome", "predicate"),
    [
        ("NotGrantedByDefault", "prohibition"),
        ("GrantedByDefault", "permission"),
        ("RequiredByDefault", "duty"),
    ],
)
def test_each_outcome_supplies_its_own_predicate(outcome, predicate) -> None:
    """Three of the four outcomes add a statement; the fourth reports a finding."""
    shown = solve(*SILENT, *rule_facts(RULE, ODRL + "distribute", DALICC + outcome))
    assert shown == [
        f'defaultStatement("{LIB}Silent","{ODRL}{predicate}","{ODRL}distribute","{RULE}")'
    ]


def test_not_waivable_reports_the_permission_the_law_does_not_allow() -> None:
    """With no companion rule, a permission is the statement to the contrary."""
    facts = rule_facts(RULE, DALICC + "moralRightsRestriction", DALICC + "NotWaivable")
    permitting = [
        fact("license", LIB + "Waiving"),
        fact("license", LIB + "Waiving", ODRL + "permission", DALICC + "moralRightsRestriction"),
    ]
    shown = solve(*permitting, *facts)
    assert shown == [
        f'defaultFinding("{LIB}Waiving","{DALICC}moralRightsRestriction","{RULE}",'
        f'"{ODRL}permission")'
    ]
    answer = build_conflict_response(atoms_of(shown))
    assert answer["defaults"][0]["kind"] == "finding"
    assert "not overridden" in answer["defaults"][0]["reason"]


def test_not_waivable_reports_the_prohibition_where_an_exception_is_kept_open() -> None:
    """A GrantedByDefault companion turns the contrary statement into a prohibition."""
    granted = "https://dalicc.net/dependencygraph/rules/granted"
    unwaivable = "https://dalicc.net/dependencygraph/rules/unwaivable"
    facts = rule_facts(granted, DALICC + "textAndDataMining", DALICC + "GrantedByDefault")
    facts += rule_facts(unwaivable, DALICC + "textAndDataMining", DALICC + "NotWaivable")
    forbidding = [
        fact("license", LIB + "Forbidding"),
        fact("license", LIB + "Forbidding", ODRL + "prohibition", DALICC + "textAndDataMining"),
    ]
    shown = solve(*forbidding, *facts)
    findings = [atom for atom in shown if atom.startswith("defaultFinding")]
    assert findings == [
        f'defaultFinding("{LIB}Forbidding","{DALICC}textAndDataMining","{unwaivable}",'
        f'"{ODRL}prohibition")'
    ]


def test_silence_is_read_through_the_dependency_graph() -> None:
    """Permitting an act settles what it entails, so no rule fires for it."""
    axioms = [
        fact("dg", ODRL + "derive", ODRL + "implies", DALICC + "ModifiedWorks"),
    ]
    facts = rule_facts(RULE, DALICC + "ModifiedWorks", DALICC + "NotGrantedByDefault")
    deriving = [
        fact("license", LIB + "Deriving"),
        fact("license", LIB + "Deriving", ODRL + "permission", ODRL + "derive"),
    ]
    shown = solve(*deriving, *axioms, *facts)
    assert not [atom for atom in shown if atom.startswith("defaultStatement")]
