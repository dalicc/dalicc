# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Which licence a record is a version of, as the share-alike reciprocity rule reads it.

Two licences that each require the combined work to stay under themselves cannot both
be satisfied, unless a path leads from one to the other: they are the same licence text,
or one offers "this version or any later version" and the other is such a later version
of the same licence.  The program decides that from one fact per licence,

    licenseProfile(Licence, Family, VersionKey, Option)

where ``Family`` names the licence without its version ("GPL", "CC-BY-SA"),
``VersionKey`` is the version as a string that sorts correctly ("00002.00000.00000"),
and ``Option`` is ``or-later`` or ``only``.  Comparing version numbers and cutting an
SPDX identifier apart are string work the answer-set program should not do, so it is
done here, from what the record states:

* the family and the version come from ``spdx:licenseId``, with the ``-only`` and
  ``-or-later`` suffixes, an SPDX ``WITH`` exception and a two-letter jurisdiction
  suffix taken off; a jurisdiction port without an identifier of its own borrows its
  parent's family and keeps its own ``dalicc:licenseVersion``;
* the option is ``or-later`` when the record sets ``dalicc:orLaterVersionOption``, when
  its identifier ends in ``-or-later``, or when its ``dalicc:shareAlikeVersionQualifier``
  accepts "a later version" of the licence, which is how the Creative Commons records
  state the clause.

A record the rules cannot place gets no profile, and then only the other paths (the
same licence, a compatibility clause) can link it to another licence.  This module is
imported by the hexlite plugin and by the tests, so it needs no solver.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

__all__ = [
    "COMPATIBILITY_FIELDS",
    "OPTION_ONLY",
    "OPTION_OR_LATER",
    "PROFILE_FIELDS",
    "UNPLACED",
    "LicenseProfile",
    "compatibility_rows",
    "profile_from_rows",
    "profile_rows",
    "version_key",
]

OPTION_OR_LATER = "or-later"
OPTION_ONLY = "only"

#: The columns of :data:`app.queries.LICENSE_PROFILE_QUERY_TEMPLATE`, in order.
PROFILE_FIELDS = ("id", "version", "orlater", "qualifier", "portid")

#: The columns of :data:`app.queries.LICENSE_COMPATIBILITY_QUERY_TEMPLATE`.
COMPATIBILITY_FIELDS = ("other", *PROFILE_FIELDS)

#: The family, version and option given to a named licence that cannot be placed, so
#: the atom keeps its arity; the program matches such a licence by its IRI only.
UNPLACED = "unplaced"

_SPDX_ID = re.compile(
    r"^(?P<family>[A-Za-z][A-Za-z0-9.+]*(?:-[A-Za-z][A-Za-z0-9.+]*)*?)"
    r"-(?P<version>\d+(?:\.\d+)*)(?P<rest>(?:-[A-Za-z][A-Za-z0-9]*)*)$"
)
_JURISDICTION_SUFFIX = re.compile(r"-[A-Z]{2}$")
_LATER_VERSION = re.compile(r"\blater version\b", re.IGNORECASE)
_TRUE = {"true", "1"}


class LicenseProfile(tuple):
    """``(family, version key, option)`` of one licence."""

    __slots__ = ()

    def __new__(cls, family: str, version: str, option: str) -> LicenseProfile:
        """Build the profile from its three parts."""
        return super().__new__(cls, (family, version, option))

    @property
    def family(self) -> str:
        """The licence without its version, e.g. ``GPL``."""
        return self[0]

    @property
    def version(self) -> str:
        """The version as a sortable key."""
        return self[1]

    @property
    def option(self) -> str:
        """``or-later`` or ``only``."""
        return self[2]


def version_key(version: str) -> str:
    """A version number as a string that sorts like the number: ``2.1`` -> ``00002.00001.00000``.

    Returns ``""`` for anything that is not dotted digits.
    """
    parts = (version or "").strip().split(".")
    if not parts or not all(part.isdigit() for part in parts) or len(parts) > 3:
        return ""
    parts += ["0"] * (3 - len(parts))
    return ".".join(f"{int(part):05d}" for part in parts)


def _split_identifier(identifier: str) -> tuple[str, str, str]:
    """``(family, version, option)`` read from an SPDX identifier, or empty strings."""
    base = identifier.split(" WITH ", 1)[0].strip()
    match = _SPDX_ID.match(base)
    if not match:
        return "", "", ""
    rest = match.group("rest")
    option = ""
    if rest.endswith("-or-later"):
        option, rest = OPTION_OR_LATER, rest[: -len("-or-later")]
    elif rest.endswith("-only"):
        option, rest = OPTION_ONLY, rest[: -len("-only")]
    rest = _JURISDICTION_SUFFIX.sub("", rest)
    return match.group("family") + rest, match.group("version"), option


def profile_from_rows(rows: Iterable[Mapping[str, str]]) -> LicenseProfile | None:
    """The profile of one licence from the rows of the profile query, or ``None``."""
    rows = list(rows)

    def values(name: str) -> list[str]:
        return sorted({str(row[name]).strip() for row in rows if row.get(name)})

    family = version = option = ""
    for identifier in values("id"):
        family, version, option = _split_identifier(identifier)
        if family:
            break
    if not family:
        for identifier in values("portid"):
            family, version, _ = _split_identifier(identifier)
            if family:
                # A port models its own version; the parent may be a later one.
                version = next(iter(values("version")), "") or version
                break
    if not family:
        return None
    key = version_key(version) or version_key(next(iter(values("version")), ""))
    if not key:
        return None
    later = (
        option == OPTION_OR_LATER
        or any(value.lower() in _TRUE for value in values("orlater"))
        or any(_LATER_VERSION.search(value) for value in values("qualifier"))
    )
    return LicenseProfile(family, key, OPTION_OR_LATER if later else OPTION_ONLY)


def profile_rows(
    license_iri: str, rows: Iterable[Mapping[str, str]]
) -> list[tuple[str, str, str, str]]:
    """The ``licenseProfile/4`` tuples for one licence: none or one."""
    profile = profile_from_rows(rows)
    if profile is None:
        return []
    return [(license_iri, profile.family, profile.version, profile.option)]


def compatibility_rows(
    license_iri: str, rows: Iterable[Mapping[str, str]]
) -> list[tuple[str, str, str, str, str]]:
    """The ``namedCompatibility/5`` tuples for one licence, one per named licence.

    ``(licence, named licence, family, version key, option)``, where the last three are
    the profile of the named record, or :data:`UNPLACED` three times.
    """
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        other = str(row.get("other") or "").strip()
        if other:
            grouped.setdefault(other, []).append(row)
    out: list[tuple[str, str, str, str, str]] = []
    for other in sorted(grouped):
        profile = profile_from_rows(grouped[other])
        if profile is None:
            out.append((license_iri, other, UNPLACED, UNPLACED, UNPLACED))
        else:
            out.append((license_iri, other, profile.family, profile.version, profile.option))
    return out
