# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The tolerant answer-set parser that replaced ``split("{")[1]``."""

from __future__ import annotations

from app.answersets import Atom, extract_answer_sets, parse_atoms, unquote_term
from tests.conftest import (
    CONFLICT_STDOUT,
    DEPGRAPH_STDOUT,
    NO_CONFLICT_STDOUT,
    WARNING_NOISE,
)


def test_conflict_sample_yields_one_answer_set() -> None:
    blocks = extract_answer_sets(CONFLICT_STDOUT)
    assert len(blocks) == 1
    atoms = parse_atoms(blocks[0])
    assert [atom.name for atom in atoms] == ["directConflict", "derivedConflict"]
    assert len(atoms[0].args) == 7
    assert len(atoms[1].args) == 10
    assert atoms[0].args[0] == "https://dalicc.net/licenselibrary/A"


def test_no_conflict_sample_is_an_empty_answer_set() -> None:
    blocks = extract_answer_sets(NO_CONFLICT_STDOUT)
    assert blocks == [""]
    assert parse_atoms(blocks[0]) == []


def test_depgraph_sample() -> None:
    atoms = parse_atoms(extract_answer_sets(DEPGRAPH_STDOUT)[0])
    assert atoms == [
        Atom(
            "t",
            (
                "http://www.w3.org/ns/odrl/2/modify",
                "http://www.w3.org/ns/odrl/2/includedIn",
                "http://www.w3.org/ns/odrl/2/derive",
            ),
        )
    ]


def test_warning_noise_alone_yields_no_answer_set() -> None:
    assert extract_answer_sets(WARNING_NOISE) == []


def test_warning_noise_before_the_answer_set_is_ignored() -> None:
    blocks = extract_answer_sets(WARNING_NOISE + CONFLICT_STDOUT)
    assert len(blocks) == 1
    assert parse_atoms(blocks[0])[0].name == "directConflict"


def test_empty_and_garbage_stdout_never_raise() -> None:
    for sample in ["", "\n", "UNSATISFIABLE\n", "Traceback (most recent call last):"]:
        assert extract_answer_sets(sample) == []


def test_unterminated_block_is_ignored() -> None:
    assert extract_answer_sets('{directConflict("a","b"') == []


def test_commas_inside_quoted_iris_do_not_split_arguments() -> None:
    stdout = '{p("https://x/a,b","https://x/c")}'
    atoms = parse_atoms(extract_answer_sets(stdout)[0])
    assert atoms == [Atom("p", ("https://x/a,b", "https://x/c"))]


def test_braces_inside_quoted_terms_do_not_end_the_block() -> None:
    stdout = '{p("https://x/}y")}'
    assert extract_answer_sets(stdout) == ['p("https://x/}y")']


def test_last_atom_is_not_truncated() -> None:
    """The legacy ``split("),")`` dropped the closing paren of the last atom."""
    stdout = '{p("a","b"),q("c","d")}'
    atoms = parse_atoms(extract_answer_sets(stdout)[0])
    assert atoms[-1] == Atom("q", ("c", "d"))


def test_propositional_atoms_and_escapes() -> None:
    atoms = parse_atoms('a,b,p("x\\"y")')
    assert atoms[0] == Atom("a", ())
    assert atoms[1] == Atom("b", ())
    assert atoms[2] == Atom("p", ('x"y',))


def test_unquote_term_leaves_unquoted_terms_alone() -> None:
    assert unquote_term("foo") == "foo"
    assert unquote_term('"foo"') == "foo"
    assert unquote_term('"a\\\\b"') == "a\\b"
