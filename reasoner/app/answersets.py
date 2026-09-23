# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Tolerant parser for the answer sets printed by ``hexlite``.

``hexlite`` prints one answer set per line as ``{atom,atom,...}`` and sends
every warning, ``info:`` note and traceback to *stderr*.  The historical
implementation used ``stdout.split("{")[1].split("}")[0].split("),")`` which

* raised ``IndexError`` (HTTP 500) as soon as stdout contained no ``{`` -- for
  instance whenever the solver failed and printed nothing at all;
* mis-split any atom whose arguments contain a comma (legal inside an IRI);
* silently truncated the last atom of the set.

This module replaces it with a small quote-aware scanner that never raises on
unexpected input and returns ``[]`` instead.
"""

from __future__ import annotations

from typing import NamedTuple

__all__ = ["Atom", "extract_answer_sets", "parse_atoms", "unquote_term"]


class Atom(NamedTuple):
    """A ground atom ``name(arg, ...)`` from an answer set."""

    name: str
    args: tuple[str, ...]


def extract_answer_sets(stdout: str) -> list[str]:
    """Return the bodies of every top-level ``{...}`` block found in *stdout*.

    Quoted strings are honoured, so a ``}`` inside an IRI cannot end a block.
    Unterminated blocks are ignored.
    """
    if not stdout:
        return []
    blocks: list[str] = []
    index = 0
    length = len(stdout)
    while index < length:
        if stdout[index] != "{":
            index += 1
            continue
        cursor = index + 1
        depth = 1
        in_string = False
        while cursor < length:
            char = stdout[cursor]
            if in_string:
                if char == "\\":
                    cursor += 2
                    continue
                if char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        if cursor >= length:
            break  # unterminated block -- ignore the rest
        blocks.append(stdout[index + 1 : cursor])
        index = cursor + 1
    return blocks


def _split_top_level(text: str) -> list[str]:
    """Split *text* on commas that are outside quotes, parentheses and braces."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if in_string:
            current.append(char)
            if char == "\\" and index + 1 < length:
                current.append(text[index + 1])
                index += 2
                continue
            if char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current)
    if tail.strip() or parts:
        parts.append(tail)
    return [part.strip() for part in parts if part.strip()]


def unquote_term(term: str) -> str:
    """Strip the surrounding quotes of an ASP string term and unescape it."""
    term = term.strip()
    if len(term) >= 2 and term.startswith('"') and term.endswith('"'):
        body = term[1:-1]
        out: list[str] = []
        index = 0
        while index < len(body):
            char = body[index]
            if char == "\\" and index + 1 < len(body):
                out.append(body[index + 1])
                index += 2
                continue
            out.append(char)
            index += 1
        return "".join(out)
    return term


def parse_atoms(answer_set_body: str) -> list[Atom]:
    """Parse the body of one ``{...}`` block into :class:`Atom` values.

    Terms that are not of the form ``name(...)`` (propositional atoms, integers)
    are returned with an empty argument tuple.  Malformed terms are skipped.
    """
    atoms: list[Atom] = []
    for term in _split_top_level(answer_set_body):
        open_paren = term.find("(")
        if open_paren <= 0 or not term.endswith(")"):
            name = term.strip()
            if name:
                atoms.append(Atom(name, ()))
            continue
        name = term[:open_paren].strip()
        if not name:
            continue
        args = tuple(unquote_term(arg) for arg in _split_top_level(term[open_paren + 1 : -1]))
        atoms.append(Atom(name, args))
    return atoms
