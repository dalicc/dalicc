# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""IRI validation and safe encoding helpers for the DALICC reasoner.

Every licence identifier that reaches this service comes from the public
``POST /compatibilitycheck/`` body, is written into an ASP (answer-set
programming) source file and is interpolated into a SPARQL query inside the
hexlite plugin.  Both of those are textual languages, so an unvalidated value
is a code-injection primitive:

* an unescaped ``"`` closes the ASP string literal in ``license("...").`` and
  lets the caller append arbitrary clingo rules (including ``#script (python)``
  blocks -- remote code execution inside the reasoner container);
* an unescaped ``>`` closes the ``<...>`` IRI reference in the plugin's
  ``FILTER (?s = <...>)`` and lets the caller rewrite the SPARQL query.

This module makes both impossible by construction:

1. :func:`validate_license_iri` accepts only absolute ``http(s)`` IRIs built
   from a conservative character allow-list *and* rejects a deny-list of
   characters that terminate an ASP string or a SPARQL IRI reference.
2. :func:`encode_license_token` turns the validated IRI into a hexadecimal
   token (``[0-9a-f]+``) which is what actually appears in the logic program.
   The plugin calls :func:`decode_license_token`, which re-validates the
   decoded IRI before it is used.  Even if the validator were bypassed, the
   only thing the solver ever sees is ``[0-9a-f]+``.
"""

from __future__ import annotations

import re

__all__ = [
    "DEPENDENCY_GRAPH_PREFIXES",
    "LICENSE_IRI_RE",
    "MAX_IRI_LENGTH",
    "IriValidationError",
    "asp_string_literal",
    "decode_license_token",
    "encode_license_token",
    "sparql_iri_ref",
    "validate_dependency_graph_iri",
    "validate_license_iri",
]

#: Maximum accepted IRI length.  Long enough for every DALICC licence IRI
#: (the longest in the library is < 120 characters) with a wide safety margin.
MAX_IRI_LENGTH = 512

#: Absolute ``http(s)`` IRI built from the unreserved / reserved character set
#: of RFC 3986.  Note that this allows a few characters that
#: :func:`validate_license_iri` rejects afterwards (``'``, ``(``, ``)``); the
#: deny-list below is authoritative.
LICENSE_IRI_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")

#: Characters that terminate or escape inside an ASP string literal, a SPARQL
#: ``<...>`` IRI reference or a SPARQL string literal.  None of them may ever
#: appear in a licence IRI handled by this service.
FORBIDDEN_CHARS = frozenset('"\'`\\<>{}|^()' + "\t\n\r\x0b\x0c ")

#: A ``.`` directly followed by whitespace terminates an ASP rule.  Whitespace
#: is already forbidden, but the check is kept explicit so that a future
#: relaxation of the character set cannot silently reintroduce the hole.
_DOT_WHITESPACE_RE = re.compile(r"\.\s")


class IriValidationError(ValueError):
    """Raised when a caller-supplied licence identifier is not acceptable."""


def validate_license_iri(value: object) -> str:
    """Return *value* as a validated absolute ``http(s)`` licence IRI.

    :raises IriValidationError: with a human-readable reason if *value* is not
        a string, is empty, is too long, contains a character that could
        terminate an ASP fact or a SPARQL IRI reference, or does not match
        :data:`LICENSE_IRI_RE`.
    """
    if not isinstance(value, str):
        raise IriValidationError(
            f"license entries must be strings, got {type(value).__name__}"
        )
    if not value:
        raise IriValidationError("license entries must not be empty")
    if len(value) > MAX_IRI_LENGTH:
        raise IriValidationError(
            f"license IRI is longer than {MAX_IRI_LENGTH} characters"
        )

    bad = sorted({c for c in value if c in FORBIDDEN_CHARS or ord(c) < 0x20 or ord(c) == 0x7F})
    if bad:
        rendered = ", ".join(repr(c) for c in bad)
        raise IriValidationError(
            f"license IRI must not contain quotes, whitespace, backslashes, "
            f"parentheses or angle brackets (found: {rendered})"
        )
    if _DOT_WHITESPACE_RE.search(value):
        raise IriValidationError("license IRI must not contain '.' followed by whitespace")
    if not LICENSE_IRI_RE.match(value):
        raise IriValidationError(
            "license IRI must be an absolute http(s) IRI matching "
            "^https?://[A-Za-z0-9._~:/?#[]@!$&'()*+,;=%-]+$"
        )

    authority = value.split("//", 1)[1].split("/", 1)[0]
    if not authority:
        raise IriValidationError("license IRI must have a non-empty host")
    return value


def asp_string_literal(value: str) -> str:
    r"""Return *value* as a quoted ASP string literal.

    ``\\`` and ``"`` are escaped.  After :func:`validate_license_iri` neither
    can be present, so this is defence in depth for any other caller.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def sparql_iri_ref(value: str) -> str:
    r"""Return *value* as a SPARQL ``<...>`` IRI reference.

    Percent-encodes the characters SPARQL forbids inside ``IRIREF`` (``<``,
    ``>``, ``"``, ``{``, ``}``, ``|``, ``^``, ``` ` ```, ``\\`` and anything
    ``<= 0x20``) so that the reference cannot be closed early.
    """
    out = []
    for ch in value:
        if ch in '<>"{}|^`\\' or ord(ch) <= 0x20:
            out.append("".join(f"%{b:02X}" for b in ch.encode("utf-8")))
        else:
            out.append(ch)
    return "<" + "".join(out) + ">"


def encode_license_token(iri: str) -> str:
    """Return a hexadecimal token for *iri* (``[0-9a-f]+``).

    The token, not the IRI, is what is written into the logic program, so no
    byte of caller-controlled input can ever reach the ASP parser.
    """
    return iri.encode("utf-8").hex()


def decode_license_token(token: str) -> str:
    """Inverse of :func:`encode_license_token`, re-validating the result.

    :raises IriValidationError: if *token* is not lowercase hexadecimal or does
        not decode to a valid licence IRI.
    """
    if not isinstance(token, str) or not re.fullmatch(r"(?:[0-9a-f]{2})+", token):
        raise IriValidationError("license token must be an even-length hex string")
    try:
        decoded = bytes.fromhex(token).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:  # pragma: no cover - guarded by regex
        raise IriValidationError(f"license token is not valid UTF-8: {exc}") from exc
    return validate_license_iri(decoded)


#: The two IRI spaces a caller-supplied dependency graph may live in: a published
#: graph, and one belonging to an account.  A per-request override may not point the
#: solver at an arbitrary named graph of the triple store, which is why this is an
#: allow-list rather than a plain IRI check.
DEPENDENCY_GRAPH_PREFIXES = (
    "https://dalicc.net/dependencygraph/",
    "https://dalicc.net/users/",
)


def validate_dependency_graph_iri(
    value: object, prefixes: tuple[str, ...] = DEPENDENCY_GRAPH_PREFIXES
) -> str:
    """Return *value* as a validated dependency-graph IRI.

    Everything :func:`validate_license_iri` refuses is refused here too (it is written
    into a SPARQL ``FROM`` clause inside the plugin), plus anything outside
    :data:`DEPENDENCY_GRAPH_PREFIXES`.

    :raises IriValidationError: with a human-readable reason.
    """
    iri = validate_license_iri(value)
    if not iri.startswith(tuple(prefixes)):
        allowed = " or ".join(prefixes)
        raise IriValidationError(
            f"dependency_graph must be an IRI under {allowed}"
        )
    return iri
