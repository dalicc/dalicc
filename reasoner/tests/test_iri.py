# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""IRI validation, ASP escaping and the hex token encoding."""

from __future__ import annotations

import pytest

from app.iri import (
    IriValidationError,
    asp_string_literal,
    decode_license_token,
    encode_license_token,
    sparql_iri_ref,
    validate_license_iri,
)

VALID = [
    "https://dalicc.net/licenselibrary/Apache-2.0",
    "https://dalicc.net/licenselibrary/MIT",
    "https://dalicc.net/licenselibrary/CC-BY-NC-SA-4.0",
    "http://example.org/a/b?c=d&e=f#frag",
    "https://dalicc.net/licenselibrary/" + "0" * 32,
    "https://dalicc.net/ns#ChangeLicense",
    "https://dalicc.net/licenselibrary/a~b._-!$&*+,;=%20x",
]


@pytest.mark.parametrize("iri", VALID)
def test_valid_iris_are_accepted(iri: str) -> None:
    assert validate_license_iri(iri) == iri


ASP_INJECTIONS = [
    # closes the string, terminates the fact, appends a python script block
    'https://dalicc.net/x").  #script (python) import os; os.system("id") #end. license("y',
    'https://dalicc.net/x"). directConflict(1,2,3,4,5,6,7). license("y',
    "https://dalicc.net/x\\",
    "https://dalicc.net/x. bad(1)",
    "https://dalicc.net/x\n#show foo/1.",
]


@pytest.mark.parametrize("payload", ASP_INJECTIONS)
def test_asp_injection_payloads_are_rejected(payload: str) -> None:
    with pytest.raises(IriValidationError):
        validate_license_iri(payload)


SPARQL_INJECTIONS = [
    "https://dalicc.net/x> . ?a ?b ?c . FILTER(?s = <y",
    "https://dalicc.net/x>} UNION {?s ?p ?o",
    "https://dalicc.net/x<y",
]


@pytest.mark.parametrize("payload", SPARQL_INJECTIONS)
def test_sparql_injection_payloads_are_rejected(payload: str) -> None:
    with pytest.raises(IriValidationError):
        validate_license_iri(payload)


NON_IRIS = [
    "",
    "Apache-2.0",
    "ftp://dalicc.net/x",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "//dalicc.net/x",
    "https://",
    "https:///nohost",
]


@pytest.mark.parametrize("payload", NON_IRIS)
def test_non_absolute_http_iris_are_rejected(payload: str) -> None:
    with pytest.raises(IriValidationError):
        validate_license_iri(payload)


@pytest.mark.parametrize("payload", [123, None, [], {"a": 1}, b"https://x/y"])
def test_non_string_entries_are_rejected(payload: object) -> None:
    with pytest.raises(IriValidationError, match="must be strings"):
        validate_license_iri(payload)


def test_overlong_iri_is_rejected() -> None:
    with pytest.raises(IriValidationError, match="longer than"):
        validate_license_iri("https://dalicc.net/" + "a" * 600)


def test_dot_followed_by_whitespace_is_rejected() -> None:
    with pytest.raises(IriValidationError):
        validate_license_iri("https://dalicc.net/x.\tfoo")


def test_control_characters_are_rejected() -> None:
    with pytest.raises(IriValidationError):
        validate_license_iri("https://dalicc.net/x\x00y")


# --- escaping ---------------------------------------------------------------


def test_asp_string_literal_quotes_and_escapes() -> None:
    assert asp_string_literal("https://x/y") == '"https://x/y"'
    assert asp_string_literal('a"b') == '"a\\"b"'
    assert asp_string_literal("a\\b") == '"a\\\\b"'


def test_sparql_iri_ref_percent_encodes_terminators() -> None:
    assert sparql_iri_ref("https://x/y") == "<https://x/y>"
    assert sparql_iri_ref("https://x/y>z") == "<https://x/y%3Ez>"
    assert sparql_iri_ref("https://x/y z") == "<https://x/y%20z>"
    for char in '<>"{}|^`\\':
        body = sparql_iri_ref(f"https://x/{char}")[1:-1]
        assert char not in body
        assert body == f"https://x/%{ord(char):02X}"


# --- token encoding ---------------------------------------------------------


@pytest.mark.parametrize("iri", VALID)
def test_token_round_trip(iri: str) -> None:
    token = encode_license_token(iri)
    assert token.isalnum() and all(c in "0123456789abcdef" for c in token)
    assert decode_license_token(token) == iri


def test_token_contains_no_asp_metacharacters() -> None:
    payload = "https://dalicc.net/licenselibrary/Apache-2.0"
    token = encode_license_token(payload)
    assert not set(token) & set('".()\\ \n')


@pytest.mark.parametrize("token", ["", "zz", "abc", "6e6f", "68747470"])
def test_bad_tokens_are_rejected(token: str) -> None:
    with pytest.raises(IriValidationError):
        decode_license_token(token)
