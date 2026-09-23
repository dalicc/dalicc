# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The public ``/compatibilitycheck/`` response shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.answersets import extract_answer_sets, parse_atoms
from app.conflicts import (
    build_conflict_response,
    build_dependency_graph_rows,
    empty_conflict_response,
)
from tests.conftest import CONFLICT_STDOUT, DEPGRAPH_STDOUT, NO_CONFLICT_STDOUT

#: Snapshot of the live api.dalicc.net response, captured by the contract suite of the
#: API service.  The reasoner is also published on its own, in the public repository
#: that carries the license data, and that suite is not beside it there, so the one test
#: that reads this file skips instead of failing for a reason that has nothing to do
#: with the reasoner.
SNAPSHOT = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "contract"
    / "snapshots"
    / "compatibilitycheck_statscanada_ukogl.json"
)


def _response(stdout: str) -> dict:
    blocks = extract_answer_sets(stdout)
    return build_conflict_response(parse_atoms(blocks[0]) if blocks else [])


def test_empty_response_shape() -> None:
    assert empty_conflict_response() == {
        "conflicting_statements": {"direct": {}, "derived": {}}
    }


def test_no_conflict_answer_set_yields_the_empty_object() -> None:
    assert _response(NO_CONFLICT_STDOUT) == {
        "conflicting_statements": {"direct": {}, "derived": {}}
    }


def test_conflict_response_uses_stringified_integer_keys() -> None:
    response = _response(CONFLICT_STDOUT)
    direct = response["conflicting_statements"]["direct"]
    derived = response["conflicting_statements"]["derived"]
    assert list(direct) == ["0"]
    assert list(derived) == ["0"]
    assert direct["0"] == {
        "statement_1": [
            "https://dalicc.net/licenselibrary/A",
            "http://www.w3.org/ns/odrl/2/permission",
            "http://www.w3.org/ns/odrl/2/distribute",
        ],
        "statement_2": [
            "https://dalicc.net/licenselibrary/B",
            "http://www.w3.org/ns/odrl/2/prohibition",
            "http://www.w3.org/ns/odrl/2/distribute",
        ],
        "reason": "Direct permission-prohibition conflict.",
    }


def test_derived_reason_string_matches_the_legacy_wording() -> None:
    derived = _response(CONFLICT_STDOUT)["conflicting_statements"]["derived"]["0"]
    assert derived["reason"] == (
        "Derived permission-prohibition conflict. "
        "(http://www.w3.org/ns/odrl/2/modify,"
        "http://www.w3.org/ns/odrl/2/includedIn,"
        "http://www.w3.org/ns/odrl/2/derive) "
        "is derived from the statements in the dependency graph."
    )


def test_derived_provenance_tail_swap_is_preserved() -> None:
    """``R = "derived"`` renders "is given in the dependency graph." (sic)."""
    stdout = (
        '{derivedConflict("l1","p","x","l2","pr","y","sameAs","x","y","derived")}'
    )
    derived = _response(stdout)["conflicting_statements"]["derived"]["0"]
    assert derived["reason"] == (
        "Derived permission-prohibition conflict. "
        "(x,http://www.w3.org/2002/07/owl#sameAs,y) "
        "is given in the dependency graph."
    )


def test_relation_prefixes() -> None:
    cases = {
        "sameAs": "http://www.w3.org/2002/07/owl#",
        "implies": "http://www.w3.org/ns/odrl/2/",
        "includedIn": "http://www.w3.org/ns/odrl/2/",
        "contradicts": "https://dalicc.net/ns#",
    }
    for relation, prefix in cases.items():
        stdout = (
            f'{{derivedConflict("l1","p","x","l2","pr","y","{relation}","x","y","dependencygraph")}}'
        )
        reason = _response(stdout)["conflicting_statements"]["derived"]["0"]["reason"]
        assert f"(x,{prefix}{relation},y)" in reason


def test_multiple_direct_conflicts_are_indexed_in_solver_order() -> None:
    stdout = (
        '{directConflict("l1","p","a","l2","pr","a","direct"),'
        'directConflict("l1","p","b","l2","pr","b","direct")}'
    )
    direct = _response(stdout)["conflicting_statements"]["direct"]
    assert list(direct) == ["0", "1"]
    assert direct["0"]["statement_1"][2] == "a"
    assert direct["1"]["statement_1"][2] == "b"


def test_malformed_conflict_atoms_are_skipped_not_fatal() -> None:
    stdout = '{directConflict("l1","p"),directConflict("l1","p","a","l2","pr","a","direct")}'
    direct = _response(stdout)["conflicting_statements"]["direct"]
    assert list(direct) == ["0"]


@pytest.mark.skipif(
    not SNAPSHOT.is_file(), reason="the API service's contract snapshot is not in this checkout"
)
def test_matches_the_live_production_snapshot_structure() -> None:
    snapshot = json.loads(SNAPSHOT.read_text())
    stdout = (
        '{directConflict("https://dalicc.net/licenselibrary/'
        'UkOpenGovernmentLicenseForPublicSectorInformation",'
        '"http://www.w3.org/ns/odrl/2/permission","http://www.w3.org/ns/odrl/2/derive",'
        '"https://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement",'
        '"http://www.w3.org/ns/odrl/2/prohibition","http://www.w3.org/ns/odrl/2/derive",'
        '"direct"),'
        'directConflict("https://dalicc.net/licenselibrary/'
        'UkOpenGovernmentLicenseForPublicSectorInformation",'
        '"http://www.w3.org/ns/odrl/2/permission","http://www.w3.org/ns/odrl/2/modify",'
        '"https://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement",'
        '"http://www.w3.org/ns/odrl/2/prohibition","http://www.w3.org/ns/odrl/2/modify",'
        '"direct")}'
    )
    assert _response(stdout) == snapshot


# --- dependency graph -------------------------------------------------------


def test_dependency_graph_legacy_shape_keeps_quotes_and_trailing_paren() -> None:
    rows = build_dependency_graph_rows(DEPGRAPH_STDOUT, legacy=True)
    assert rows == [
        [
            '"http://www.w3.org/ns/odrl/2/modify"',
            '"http://www.w3.org/ns/odrl/2/includedIn"',
            '"http://www.w3.org/ns/odrl/2/derive")',
        ]
    ]


def test_dependency_graph_normalized_shape_is_clean() -> None:
    rows = build_dependency_graph_rows(DEPGRAPH_STDOUT, legacy=False)
    assert rows == [
        [
            "http://www.w3.org/ns/odrl/2/modify",
            "http://www.w3.org/ns/odrl/2/includedIn",
            "http://www.w3.org/ns/odrl/2/derive",
        ]
    ]


def test_dependency_graph_empty_stdout() -> None:
    assert build_dependency_graph_rows("", legacy=True) == []
    assert build_dependency_graph_rows("{}", legacy=False) == []


def test_a_contradiction_between_two_permissions_says_so() -> None:
    """``contradicts`` is the one relation whose two statements are both permissions.

    The dependency graph says the two acts cannot both be allowed of the same asset, so
    a bundle that permits both is in conflict although nothing is forbidden anywhere.
    Calling that a permission-prohibition conflict would be untrue, so it gets its own
    opening sentence; the rest of the wire format is the one every conflict uses.
    """
    exclusivity = "http://www.w3.org/ns/odrl/2/ensureExclusivity"
    commercialize = "http://www.w3.org/ns/odrl/2/commercialize"
    stdout = (
        '{derivedConflict("https://dalicc.net/licenselibrary/B",'
        '"http://www.w3.org/ns/odrl/2/permission",'
        f'"{exclusivity}",'
        '"https://dalicc.net/licenselibrary/A",'
        '"http://www.w3.org/ns/odrl/2/permission",'
        f'"{commercialize}","contradicts","{exclusivity}","{commercialize}",'
        '"dependencygraph")}'
    )
    derived = _response(stdout)["conflicting_statements"]["derived"]["0"]
    assert derived["statement_1"][1] == "http://www.w3.org/ns/odrl/2/permission"
    assert derived["statement_2"][1] == "http://www.w3.org/ns/odrl/2/permission"
    assert derived["reason"] == (
        "Derived conflict between two permissions. "
        f"({exclusivity},https://dalicc.net/ns#contradicts,{commercialize}) "
        "is derived from the statements in the dependency graph."
    )
