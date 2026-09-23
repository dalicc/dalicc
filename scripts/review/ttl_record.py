# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""A minimal, format-preserving editor for one DALICC license record.

Every file in ``licensedata/licenses/`` follows the same restricted Turtle shape::

    # four provenance comment lines
    @prefix ... .            (one shared prefix block, identical in every file)

    dalicclib:<id> a odrl:Set ;
        <predicate> <object> ,
            <object> ;
        ...
        <predicate> <object> .

``scripts/build_licenselibrary.py`` concatenates those bodies textually, and
``docs/DATA.md`` promises that the hand-curated formatting survives an edit.  Re-writing
a record with rdflib would rename every blank node and reorder every object list, so the
consolidation edits the Turtle source instead and uses rdflib only to verify the result.

This module is the surgical instrument for that: it splits a record into its header,
its prefix block and a list of ``Statement`` objects (one predicate with its object
list, each object kept verbatim), offers the handful of operations the review decisions
need, and renders the record back in exactly the library's layout.  Parsing and
rendering an untouched record is byte-identical; ``--self-test`` proves it over the
whole library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
import sys

LOG = logging.getLogger("ttl_record")

#: Indentation the library uses: four spaces for a predicate, eight for a continuation
#: object of the same predicate.
PREDICATE_INDENT = " " * 4
OBJECT_INDENT = " " * 8

#: Where a newly inserted predicate belongs.  Only used for predicates that are not in
#: the record yet; existing statements are never reordered.
PREDICATE_ORDER = (
    "a",
    "cc:license",
    "spdx:licenseId",
    "cc:attributionName",
    "cc:jurisdiction",
    "cc:legalcode",
    "dalicc:LiabilityLimitation",
    "dalicc:WarrantyDisclaimer",
    "dalicc:WarrantyOrLiabilityAcceptance",
    "dalicc:PromotionSpecification",
    "dalicc:additionalClauses",
    "dalicc:validityType",
    "dalicc:orLaterVersionOption",
    "dalicc:terminatesOnBreach",
    "dalicc:curePeriod",
    "dalicc:sublicenseSurvival",
    "dalicc:sourcePublicationPeriod",
    "dalicc:governingLaw",
    "dalicc:governmentRightsLimitation",
    "dalicc:compatibleLicenseTest",
    "dalicc:reciprocityScope",
    "dalicc:shareAlikeVersionQualifier",
    "dalicc:alternativeConditionSet",
    "dalicc:fieldOfUseRestriction",
    "dalicc:composedOf",
    "dalicc:jurisdictionPortOf",
    "dalicc:translationOf",
    "dalicc:variantKind",
    "dalicc:variantOf",
    "dalicc:licenseVersion",
    "dalicc:recordStatus",
    "dalicc:reviewStatus",
    "dalicc:reviewedOn",
    "dalicc:versionHistory",
    "dct:alternative",
    "dct:hasVersion",
    "dct:isVersionOf",
    "dct:language",
    "dct:modified",
    "dct:publisher",
    "dct:source",
    "dct:title",
    "odrl:assignee",
    "odrl:duty",
    "odrl:permission",
    "odrl:prohibition",
    "odrl:target",
    "scho:startDate",
    "scho:endDate",
    "foaf:img",
    "foaf:logo",
)


class RecordError(RuntimeError):
    """Raised when a record does not have the shape this module can edit."""


def _split_top_level(text: str, separator: str) -> list[str]:
    """Split ``text`` on ``separator`` outside of brackets, parentheses and strings."""
    parts: list[str] = []
    depth = 0
    index = 0
    start = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            if text.startswith('"""', index):
                end = text.find('"""', index + 3)
                while end != -1 and text[end - 1] == "\\":
                    end = text.find('"""', end + 1)
                if end == -1:
                    raise RecordError("unterminated long string literal")
                index = end + 3
                continue
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                index += 1
            continue
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


@dataclass
class Statement:
    """One ``predicate object, object`` group of a record."""

    predicate: str
    objects: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Render the statement with the library's indentation, without a terminator."""
        head = f"{PREDICATE_INDENT}{self.predicate} {self.objects[0]}"
        tail = "".join(f",\n{OBJECT_INDENT}{obj}" for obj in self.objects[1:])
        return head + tail


@dataclass
class Record:
    """One license file: provenance header, prefix block, subject and statements."""

    path: Path
    header: str
    prefixes: list[str]
    subject: str
    statements: list[Statement]

    # -- reading -----------------------------------------------------------

    @classmethod
    def parse(cls, path: Path) -> Record:
        """Read and split one license file."""
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RecordError(f"{path}: UTF-8 BOM")
        if b"\r" in raw:
            raise RecordError(f"{path}: CR line endings")
        return cls.parse_text(path, raw.decode("utf-8"))

    @classmethod
    def parse_text(cls, path: Path, text: str) -> Record:
        """Split one license record held in memory, to be written to ``path`` later."""
        lines = text.split("\n")

        index = 0
        while index < len(lines) and (lines[index].startswith("#") or not lines[index].strip()):
            index += 1
        header = "\n".join(lines[:index])

        prefixes: list[str] = []
        while index < len(lines) and (
            lines[index].startswith("@prefix") or not lines[index].strip()
        ):
            if lines[index].startswith("@prefix"):
                prefixes.append(lines[index].rstrip())
            index += 1
        if not prefixes:
            raise RecordError(f"{path}: no @prefix block")

        body = "\n".join(lines[index:]).strip("\n")
        if not body.rstrip().endswith("."):
            raise RecordError(f"{path}: body does not end with '.'")
        body = body.rstrip()[:-1].rstrip()

        match = re.match(r"^(\S+)\s+a\s+odrl:Set\s*;", body)
        if not match:
            raise RecordError(f"{path}: body does not start with '<subject> a odrl:Set ;'")
        subject = match.group(1)
        rest = body[match.end():]

        statements = [Statement("a", ["odrl:Set"])]
        for chunk in _split_top_level(rest, ";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            predicate, _, objects_text = chunk.partition(" ")
            objects = [obj.strip() for obj in _split_top_level(objects_text, ",")]
            objects = [obj for obj in objects if obj]
            if not objects:
                raise RecordError(f"{path}: predicate {predicate} has no object")
            statements.append(Statement(predicate, objects))
        return cls(path=path, header=header, prefixes=prefixes, subject=subject,
                   statements=statements)

    # -- rendering ---------------------------------------------------------

    def render(self) -> str:
        """Render the whole file."""
        first = self.statements[0]
        if first.predicate != "a":
            raise RecordError(f"{self.path}: lost the rdf:type statement")
        lines = [f"{self.subject} a {first.objects[0]} ;"]
        rendered = [statement.render() for statement in self.statements[1:]]
        lines.append(" ;\n".join(rendered) + " .")
        return (
            self.header
            + "\n"
            + "\n".join(self.prefixes)
            + "\n\n"
            + "\n".join(lines)
            + "\n"
        )

    def write(self) -> None:
        """Write the record back to its file with LF endings and a final newline."""
        self.path.write_text(self.render(), encoding="utf-8", newline="")

    # -- queries -----------------------------------------------------------

    def statement(self, predicate: str) -> Statement | None:
        """The statement for ``predicate``, or ``None``."""
        for statement in self.statements:
            if statement.predicate == predicate:
                return statement
        return None

    def objects(self, predicate: str) -> list[str]:
        """The verbatim object texts of ``predicate`` (empty when absent)."""
        statement = self.statement(predicate)
        return list(statement.objects) if statement else []

    def has_object(self, predicate: str, needle: str) -> bool:
        """Whether any object of ``predicate`` contains ``needle``."""
        return any(needle in obj for obj in self.objects(predicate))

    # -- editing -----------------------------------------------------------

    def _insert_position(self, predicate: str) -> int:
        """Index at which a new ``predicate`` statement belongs."""
        try:
            rank = PREDICATE_ORDER.index(predicate)
        except ValueError:
            return len(self.statements)
        position = len(self.statements)
        for index, statement in enumerate(self.statements):
            try:
                other = PREDICATE_ORDER.index(statement.predicate)
            except ValueError:
                continue
            if other > rank:
                position = index
                break
        return position

    def add_object(self, predicate: str, obj: str) -> bool:
        """Append ``obj`` to ``predicate``, creating the statement if needed.

        Returns ``True`` when the record changed.
        """
        statement = self.statement(predicate)
        if statement is None:
            self.statements.insert(self._insert_position(predicate), Statement(predicate, [obj]))
            return True
        if obj in statement.objects:
            return False
        statement.objects.append(obj)
        return True

    def set_single_object(self, predicate: str, obj: str) -> bool:
        """Make ``predicate`` carry exactly ``obj``."""
        statement = self.statement(predicate)
        if statement is None:
            self.statements.insert(self._insert_position(predicate), Statement(predicate, [obj]))
            return True
        if statement.objects == [obj]:
            return False
        statement.objects = [obj]
        return True

    def remove_predicate(self, predicate: str) -> bool:
        """Drop the whole ``predicate`` statement."""
        before = len(self.statements)
        self.statements = [s for s in self.statements if s.predicate != predicate]
        return len(self.statements) != before

    def remove_objects(self, predicate: str, matches) -> int:
        """Drop every object of ``predicate`` for which ``matches(obj)`` is true."""
        statement = self.statement(predicate)
        if statement is None:
            return 0
        kept = [obj for obj in statement.objects if not matches(obj)]
        removed = len(statement.objects) - len(kept)
        if not removed:
            return 0
        if kept:
            statement.objects = kept
        else:
            self.statements = [s for s in self.statements if s is not statement]
        return removed

    def map_objects(self, predicate: str, transform) -> int:
        """Rewrite every object of ``predicate`` through ``transform``."""
        statement = self.statement(predicate)
        if statement is None:
            return 0
        changed = 0
        new_objects = []
        for obj in statement.objects:
            replacement = transform(obj)
            if replacement != obj:
                changed += 1
            new_objects.append(replacement)
        statement.objects = new_objects
        return changed

    def add_prefix(self, prefix_line: str) -> bool:
        """Add one ``@prefix`` line, keeping the block sorted the way the library is."""
        if prefix_line in self.prefixes:
            return False
        self.prefixes.append(prefix_line)
        return True


#: ``odrl:action <term>`` inside a blank node, used to recognise a permission or
#: prohibition node by the action it carries.
ACTION_RE = re.compile(r"odrl:action\s+([A-Za-z0-9_:.-]+)")


def node_action(obj: str) -> str | None:
    """The first ``odrl:action`` value of a blank-node object, or ``None``."""
    match = ACTION_RE.search(obj)
    return match.group(1) if match else None


def top_level_action(obj: str) -> str | None:
    """The ``odrl:action`` of the node itself, ignoring nested duty actions."""
    inner = obj.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        return None
    inner = inner[1:-1]
    for part in _split_top_level(inner, ";"):
        part = part.strip()
        if part.startswith("odrl:action"):
            return part.split(None, 1)[1].strip()
    return None


def permission_node(action: str, duties: list[str] | None = None) -> str:
    """Render a permission blank node in the library's layout."""
    return _deontic_node("odrl:Permission", action, duties or [])


def prohibition_node(action: str) -> str:
    """Render a prohibition blank node in the library's layout."""
    return _deontic_node("odrl:Prohibition", action, [])


def duty_node(action: str) -> str:
    """Render a license-wide duty blank node in the library's layout."""
    return _deontic_node("odrl:Duty", action, [])


def _deontic_node(node_type: str, action: str, duties: list[str]) -> str:
    body = f"[ a {node_type} ;\n{' ' * 12}odrl:action {action}"
    if duties:
        rendered = f",\n{' ' * 16}".join(
            f"[ a odrl:Duty ;\n{' ' * 20}odrl:action {duty} ]" for duty in duties
        )
        body += f" ;\n{' ' * 12}odrl:duty {rendered}"
    return body + " ]"


def add_duty_to_node(obj: str, action: str) -> str:
    """Return ``obj`` with one more ``odrl:duty`` for ``action`` (idempotent)."""
    inner = obj.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise RecordError("not a blank-node object")
    body = inner[1:-1]
    parts = [part.strip() for part in _split_top_level(body, ";")]
    duty_index = next((i for i, part in enumerate(parts) if part.startswith("odrl:duty")), None)
    new_duty = f"[ a odrl:Duty ;\n{' ' * 20}odrl:action {action} ]"
    if duty_index is None:
        parts.append(f"odrl:duty {new_duty}")
    else:
        duties = [d.strip() for d in _split_top_level(parts[duty_index][len("odrl:duty"):], ",")]
        if any(f"odrl:action {action}" in d for d in duties):
            return obj
        duties.append(new_duty)
        parts[duty_index] = "odrl:duty " + f",\n{' ' * 16}".join(duties)
    joined = f" ;\n{' ' * 12}".join(parts)
    return f"[ {joined} ]"


def remove_duty_from_node(obj: str, action: str) -> str:
    """Return ``obj`` without the ``odrl:duty`` whose action is ``action``."""
    inner = obj.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise RecordError("not a blank-node object")
    body = inner[1:-1]
    parts = [part.strip() for part in _split_top_level(body, ";")]
    duty_index = next((i for i, part in enumerate(parts) if part.startswith("odrl:duty")), None)
    if duty_index is None:
        return obj
    duties = [d.strip() for d in _split_top_level(parts[duty_index][len("odrl:duty"):], ",")]
    kept = [d for d in duties if f"odrl:action {action}" not in d]
    if len(kept) == len(duties):
        return obj
    if kept:
        parts[duty_index] = "odrl:duty " + f",\n{' ' * 16}".join(kept)
    else:
        parts.pop(duty_index)
    joined = f" ;\n{' ' * 12}".join(parts)
    return f"[ {joined} ]"


def self_test(licenses_dir: Path) -> int:
    """Parse and re-render every record; report the ones that are not byte-identical."""
    differing: list[str] = []
    for path in sorted(licenses_dir.glob("*.ttl")):
        original = path.read_text(encoding="utf-8")
        try:
            record = Record.parse(path)
        except RecordError as exc:
            LOG.error("%s", exc)
            differing.append(path.name)
            continue
        if record.render() != original:
            differing.append(path.name)
    LOG.info("round trip: %d files, %d differ", len(list(licenses_dir.glob('*.ttl'))),
             len(differing))
    for name in differing:
        LOG.warning("  differs: %s", name)
    return 0 if not differing else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repo_root = Path(__file__).resolve().parents[2]
    sys.exit(self_test(repo_root / "licensedata" / "licenses"))
