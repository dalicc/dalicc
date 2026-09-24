# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Two licences that each keep the whole work under themselves.

GPL-2.0-only and GPL-3.0-only, the ODbL and CC BY-SA 4.0, the Business Source License
and GPL-3.0-only: each pair forbids nothing the other permits, so the permission against
prohibition rules never meet, and the check used to answer "no conflict". The share-alike
reciprocity rule reports them, and leaves alone the pairs a path links: the same licence
text, an "or later" option that reaches the other's version, a compatibility clause.

The facts below are the ones the three licence atoms and ``&getLicenseProfile`` produce
for the library records, cut down to what the rules read. ``query.lp`` runs as it ships
under plain ``clingo``, with the external-atom rules dropped, as in the tests next door.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.conflicts import DIRECT_REASONS, build_conflict_response
from app.profiles import profile_from_rows, version_key

clingo = pytest.importorskip("clingo")

ODRL = "http://www.w3.org/ns/odrl/2/"
CC = "http://creativecommons.org/ns#"
DALICC = "https://dalicc.net/ns#"
LIB = "https://dalicc.net/licenselibrary/"

PROGRAM = Path(__file__).resolve().parents[1] / "app" / "programs" / "query.lp"


def q(value: str) -> str:
    """A quoted ASP string."""
    return '"' + value + '"'


def duty(iri: str, rule_action: str, duty_action: str) -> str:
    """A licenseDuty/4 fact for a duty hanging on a permission."""
    return f"licenseDuty({q(iri)},{q(ODRL + 'permission')},{q(rule_action)},{q(duty_action)})."


def whole_work(name: str) -> list[str]:
    """A licence with the licence-wide share-alike duty and the relicensing ban."""
    iri = LIB + name
    return [
        f"license({q(iri)},{q(ODRL + 'duty')},{q(CC + 'ShareAlike')}).",
        f"license({q(iri)},{q(ODRL + 'prohibition')},{q(DALICC + 'ChangeLicense')}).",
    ]


def derivative_bound(name: str) -> list[str]:
    """Share alike on every derivative and no relicensing: the BUSL-1.1 shape."""
    iri = LIB + name
    return [
        f"license({q(iri)},{q(ODRL + 'permission')},{q(ODRL + 'derive')}).",
        duty(iri, ODRL + "derive", CC + "ShareAlike"),
        f"license({q(iri)},{q(ODRL + 'prohibition')},{q(DALICC + 'ChangeLicense')}).",
    ]


def file_level(name: str) -> list[str]:
    """Share alike on Modify only, relicensing permitted: file-level reciprocity."""
    iri = LIB + name
    return [
        f"license({q(iri)},{q(ODRL + 'permission')},{q(ODRL + 'modify')}).",
        duty(iri, ODRL + "modify", CC + "ShareAlike"),
    ]


def permissive(name: str) -> list[str]:
    """Relicensing permitted with the compliant-license duty: the MIT shape."""
    iri = LIB + name
    return [
        f"license({q(iri)},{q(ODRL + 'permission')},{q(DALICC + 'ChangeLicense')}).",
        duty(iri, DALICC + "ChangeLicense", DALICC + "compliantLicense"),
    ]


def compliant(name: str) -> list[str]:
    """Whole-work share alike with a compatibility clause: the EUPL shape."""
    iri = LIB + name
    return [
        f"license({q(iri)},{q(ODRL + 'duty')},{q(CC + 'ShareAlike')}).",
        *permissive(name),
    ]


def profile(name: str, family: str, version: str, option: str) -> str:
    """The licenseProfile/4 fact of one licence."""
    return f"licenseProfile({q(LIB + name)},{q(family)},{q(version_key(version))},{q(option)})."


def solve(*groups: list[str] | str) -> list[str]:
    """The shown atoms of the first answer set."""
    facts: list[str] = []
    for group in groups:
        facts.extend([group] if isinstance(group, str) else group)
    rules = "\n".join(
        line for line in PROGRAM.read_text(encoding="utf-8").splitlines() if "&get" not in line
    )
    control = clingo.Control(["--warn=none"])
    control.add("base", [], rules + "\n" + "\n".join(facts))
    control.ground([("base", [])])
    with control.solve(yield_=True) as handle:
        for model in handle:
            return sorted(str(symbol) for symbol in model.symbols(shown=True))
    return []


def reciprocity(atoms: list[str]) -> list[str]:
    """The share-alike reciprocity conflicts among the shown atoms."""
    return [atom for atom in atoms if '"share-alike-reciprocity"' in atom]


def test_gpl_2_only_and_gpl_3_only_cannot_be_combined() -> None:
    """Same family, different versions, neither offers a later one."""
    atoms = solve(
        whole_work("GPL-2.0-only"),
        whole_work("GPL-3.0-only"),
        profile("GPL-2.0-only", "GPL", "2.0", "only"),
        profile("GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1


def test_the_pair_is_reported_once_whichever_order_it_is_given_in() -> None:
    """The IRIs order the pair, not the request."""
    first = solve(whole_work("GPL-3.0-only"), whole_work("GPL-2.0-only"))
    second = solve(whole_work("GPL-2.0-only"), whole_work("GPL-3.0-only"))
    assert reciprocity(first) == reciprocity(second)
    assert len(reciprocity(first)) == 1
    assert reciprocity(first)[0].startswith(f'directConflict("{LIB}GPL-2.0-only"')


def test_odbl_and_cc_by_sa_cannot_be_combined() -> None:
    """Two families, no stated compatibility between them in the records."""
    atoms = solve(
        whole_work("OdcOpenDatabaseLicense"),
        whole_work("CC-BY-SA-4.0"),
        profile("OdcOpenDatabaseLicense", "ODbL", "1.0", "only"),
        profile("CC-BY-SA-4.0", "CC-BY-SA", "4.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1


def test_busl_and_gpl_3_only_cannot_be_combined() -> None:
    """Share alike on every derivative plus a relicensing ban binds the whole work too."""
    atoms = solve(
        derivative_bound("BUSL-1.1"),
        whole_work("GPL-3.0-only"),
        profile("BUSL-1.1", "BUSL", "1.1", "only"),
        profile("GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1


def test_gpl_2_or_later_reaches_gpl_3_only() -> None:
    """An "or later" option that reaches the other version is a path."""
    atoms = solve(
        whole_work("GPL-2.0-or-later"),
        whole_work("GPL-3.0-only"),
        profile("GPL-2.0-or-later", "GPL", "2.0", "or-later"),
        profile("GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert reciprocity(atoms) == []


def test_gpl_3_or_later_does_not_reach_back_to_gpl_2_only() -> None:
    """A later-version option runs forward only."""
    atoms = solve(
        whole_work("GPL-3.0-or-later"),
        whole_work("GPL-2.0-only"),
        profile("GPL-3.0-or-later", "GPL", "3.0", "or-later"),
        profile("GPL-2.0-only", "GPL", "2.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1


def test_the_same_licence_text_is_a_path() -> None:
    """An exception or a port of the same version keeps the base text."""
    atoms = solve(
        whole_work("GPL-2.0-only-with-Classpath-exception-2.0"),
        whole_work("GPL-2.0-only"),
        profile("GPL-2.0-only-with-Classpath-exception-2.0", "GPL", "2.0", "only"),
        profile("GPL-2.0-only", "GPL", "2.0", "only"),
    )
    assert reciprocity(atoms) == []


def test_a_compatibility_clause_is_a_path() -> None:
    """The EUPL shape: the work may move to a licence that complies with it."""
    atoms = solve(compliant("EUPL-1.2"), whole_work("GPL-3.0-only"))
    assert reciprocity(atoms) == []


def test_one_whole_work_licence_alone_is_no_conflict() -> None:
    """Reciprocity needs two licences that each keep the work."""
    assert reciprocity(solve(whole_work("GPL-3.0-only"))) == []


def test_file_level_share_alike_is_not_reciprocity() -> None:
    """Share alike on Modify leaves the rest of the combined work free."""
    atoms = solve(file_level("MPL-2.0"), whole_work("GPL-3.0-only"))
    assert reciprocity(atoms) == []


def test_a_permissive_licence_meets_a_copyleft_one_on_change_license_only() -> None:
    """MIT + GPL-3.0-only: the permission against prohibition finding, nothing else."""
    atoms = solve(permissive("MIT"), whole_work("GPL-3.0-only"))
    assert reciprocity(atoms) == []
    direct = [atom for atom in atoms if atom.startswith("directConflict")]
    assert len(direct) == 1
    assert direct[0].endswith(',"direct")')


def test_the_reason_names_the_reading() -> None:
    """The service turns the atom into the published shape with its own sentence."""
    from app.answersets import parse_atoms

    atoms = solve(whole_work("GPL-2.0-only"), whole_work("GPL-3.0-only"))
    response = build_conflict_response(parse_atoms(" ".join(atoms)))
    entry = response["conflicting_statements"]["direct"]["0"]
    assert entry["reason"] == DIRECT_REASONS["share-alike-reciprocity"]
    assert entry["statement_1"] == [LIB + "GPL-2.0-only", ODRL + "duty", CC + "ShareAlike"]
    assert entry["statement_2"] == [LIB + "GPL-3.0-only", ODRL + "duty", CC + "ShareAlike"]


# ---------------------------------------------------------------------------
# the profile a record is given
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([{"id": "GPL-3.0-only", "version": "3.0"}], ("GPL", "3.0", "only")),
        ([{"id": "GPL-2.0-or-later", "orlater": "true"}], ("GPL", "2.0", "or-later")),
        (
            [{"id": "GPL-2.0-or-later WITH Classpath-exception-2.0", "orlater": "1"}],
            ("GPL", "2.0", "or-later"),
        ),
        ([{"id": "CC-BY-SA-3.0-AT", "version": "3.0"}], ("CC-BY-SA", "3.0", "only")),
        (
            [
                {
                    "id": "CC-BY-SA-3.0",
                    "qualifier": "this License, a later version of this License with the "
                    "same License Elements",
                }
            ],
            ("CC-BY-SA", "3.0", "or-later"),
        ),
        ([{"portid": "CC-BY-SA-4.0", "version": "3.0"}], ("CC-BY-SA", "3.0", "only")),
        ([{"id": "GFDL-1.3-no-invariants-only"}], ("GFDL-no-invariants", "1.3", "only")),
        ([{"id": "ODbL-1.0"}], ("ODbL", "1.0", "only")),
        ([{"id": "BUSL-1.1"}], ("BUSL", "1.1", "only")),
    ],
)
def test_a_record_is_placed_by_its_identifier(rows, expected) -> None:
    """Family, version and option come from what the record states."""
    family, version, option = expected
    assert profile_from_rows(rows) == (family, version_key(version), option)


def test_a_record_without_an_identifier_or_version_is_not_placed() -> None:
    """No profile, so only the same licence or a clause can link it."""
    assert profile_from_rows([{"version": "1.0"}]) is None
    assert profile_from_rows([{"id": "NGPL"}]) is None


def test_version_keys_sort_like_the_numbers() -> None:
    """2.1 < 2.10 < 10.0, which a plain string comparison gets wrong."""
    assert version_key("2.1") < version_key("2.10") < version_key("10.0")
    assert version_key("draft") == ""


# ---------------------------------------------------------------------------
# compatibility a licence grants by name (dalicc:compatibleWith)
# ---------------------------------------------------------------------------
#
# The records below carry dalicc:compatibleWith the way namedCompatibility/5 hands it to
# the program: the licence, the named licence and the named record's profile. They are
# fixtures, not the library records, so the tests do not depend on what the data says.


def named(name: str, other: str, family: str, version: str, option: str) -> str:
    """A namedCompatibility/5 fact: a work under ``name`` may go under ``other``."""
    key = version_key(version) if family != "unplaced" else "unplaced"
    return (
        f"namedCompatibility({q(LIB + name)},{q(LIB + other)},{q(family)},"
        f"{q(key)},{q(option)})."
    )


def direction(atoms: list[str]) -> list[tuple[str, str]]:
    """``(from, to)`` of every share-alike-direction entry among the shown atoms."""
    out = []
    for atom in atoms:
        if '"share-alike-direction"' not in atom:
            continue
        args = atom[len("directConflict(") : -1].split(",")
        assert args[1] == q(DALICC + "compatibleWith")
        out.append((args[0].strip('"')[len(LIB) :], args[2].strip('"')[len(LIB) :]))
    return sorted(out)


def gpl_family(name: str, version: str, option: str = "only") -> list[str]:
    """A whole-work licence of the GPL family with its profile."""
    return [*whole_work(name), profile(name, "GPL", version, option)]


def test_lgpl_3_named_into_gpl_3_clears_with_a_direction() -> None:
    """LGPL-3.0-only names GPL-3.0-only: no conflict, the work goes to GPL-3.0."""
    atoms = solve(
        whole_work("LGPL-3.0-only"),
        profile("LGPL-3.0-only", "LGPL", "3.0", "only"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("LGPL-3.0-only", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == [("LGPL-3.0-only", "GPL-3.0-only")]


def test_agpl_3_and_gpl_3_name_each_other_and_clear_both_ways() -> None:
    """Section 13 of each: one direction entry each way, no conflict."""
    atoms = solve(
        whole_work("AGPL-3.0-only"),
        profile("AGPL-3.0-only", "AGPL", "3.0", "only"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("AGPL-3.0-only", "GPL-3.0-only", "GPL", "3.0", "only"),
        named("GPL-3.0-only", "AGPL-3.0-only", "AGPL", "3.0", "only"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == [
        ("AGPL-3.0-only", "GPL-3.0-only"),
        ("GPL-3.0-only", "AGPL-3.0-only"),
    ]


def test_cc_by_sa_4_named_into_gpl_3_clears_towards_gpl_3_only() -> None:
    """The Creative Commons list names GPL-3.0; nothing leads back."""
    atoms = solve(
        whole_work("CC-BY-SA-4.0"),
        profile("CC-BY-SA-4.0", "CC-BY-SA", "4.0", "only"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("CC-BY-SA-4.0", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == [("CC-BY-SA-4.0", "GPL-3.0-only")]


def test_gpl_2_only_and_gpl_3_only_still_conflict_beside_a_named_licence() -> None:
    """A name that reaches neither licence of the pair clears nothing."""
    atoms = solve(
        gpl_family("GPL-2.0-only", "2.0"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("GPL-2.0-only", "GPL-2.0-with-autoconf", "GPL", "2.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1
    assert direction(atoms) == []


def test_odbl_and_cc_by_sa_4_still_conflict() -> None:
    """Neither record names the other."""
    atoms = solve(
        whole_work("OdcOpenDatabaseLicense"),
        profile("OdcOpenDatabaseLicense", "ODbL", "1.0", "only"),
        whole_work("CC-BY-SA-4.0"),
        profile("CC-BY-SA-4.0", "CC-BY-SA", "4.0", "only"),
        named("CC-BY-SA-4.0", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert len(reciprocity(atoms)) == 1
    assert direction(atoms) == []


def test_one_hop_through_an_or_later_option() -> None:
    """LGPL-2.1 names GPL-2.0-or-later, whose option reaches GPL-3.0-only."""
    atoms = solve(
        whole_work("LGPL-2.1-only"),
        profile("LGPL-2.1-only", "LGPL", "2.1", "only"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("LGPL-2.1-only", "GPL-2.0-or-later", "GPL", "2.0", "or-later"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == [("LGPL-2.1-only", "GPL-3.0-only")]


def test_one_hop_through_the_same_licence_text() -> None:
    """A named record of the same text as the bundle's licence reaches it."""
    atoms = solve(
        whole_work("CC-BY-SA-4.0"),
        profile("CC-BY-SA-4.0", "CC-BY-SA", "4.0", "only"),
        gpl_family("GPL-3.0-only-with-exception", "3.0"),
        named("CC-BY-SA-4.0", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert direction(atoms) == [("CC-BY-SA-4.0", "GPL-3.0-only-with-exception")]


def test_an_or_later_option_does_not_reach_back() -> None:
    """A name of GPL-3.0-or-later does not reach GPL-2.0-only."""
    atoms = solve(
        whole_work("CC-BY-SA-4.0"),
        profile("CC-BY-SA-4.0", "CC-BY-SA", "4.0", "only"),
        gpl_family("GPL-2.0-only", "2.0"),
        named("CC-BY-SA-4.0", "GPL-3.0-or-later", "GPL", "3.0", "or-later"),
    )
    assert len(reciprocity(atoms)) == 1
    assert direction(atoms) == []


def test_an_unplaced_named_licence_matches_by_its_iri_only() -> None:
    """A named record without a profile is matched by its IRI."""
    atoms = solve(
        whole_work("OdcOpenDatabaseLicense"),
        whole_work("Cdla-Sharing-1.0"),
        named("Cdla-Sharing-1.0", "OdcOpenDatabaseLicense", "unplaced", "", "unplaced"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == [("Cdla-Sharing-1.0", "OdcOpenDatabaseLicense")]


def test_a_pair_linked_otherwise_gets_no_direction() -> None:
    """GPL-2.0-or-later with GPL-3.0-only needs no name, so no direction is added."""
    atoms = solve(
        gpl_family("GPL-2.0-or-later", "2.0", "or-later"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("GPL-2.0-or-later", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    assert reciprocity(atoms) == []
    assert direction(atoms) == []


def test_the_direction_entry_reads_as_the_record_states_it() -> None:
    """The first statement is the record's compatibleWith triple, with its reason."""
    from app.answersets import parse_atoms

    atoms = solve(
        whole_work("LGPL-3.0-only"),
        gpl_family("GPL-3.0-only", "3.0"),
        named("LGPL-3.0-only", "GPL-3.0-only", "GPL", "3.0", "only"),
    )
    response = build_conflict_response(parse_atoms(" ".join(atoms)))
    entries = list(response["conflicting_statements"]["direct"].values())
    assert entries == [
        {
            "statement_1": [
                LIB + "LGPL-3.0-only",
                DALICC + "compatibleWith",
                LIB + "GPL-3.0-only",
            ],
            "statement_2": [LIB + "GPL-3.0-only", ODRL + "duty", CC + "ShareAlike"],
            "reason": DIRECT_REASONS["share-alike-direction"],
        }
    ]


def test_compatibility_rows_group_the_named_records() -> None:
    """One tuple per named licence, with its profile or unplaced."""
    from app.profiles import UNPLACED, compatibility_rows

    rows = [
        {"other": LIB + "GPL-3.0-only", "id": "GPL-3.0-only"},
        {"other": LIB + "GPL-3.0-only", "version": "3.0"},
        {"other": LIB + "Mystery"},
        {"id": "no-other"},
    ]
    assert compatibility_rows(LIB + "LGPL-3.0-only", rows) == [
        (LIB + "LGPL-3.0-only", LIB + "GPL-3.0-only", "GPL", version_key("3.0"), "only"),
        (LIB + "LGPL-3.0-only", LIB + "Mystery", UNPLACED, UNPLACED, UNPLACED),
    ]
