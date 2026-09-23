#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Bring the usage notes of the DALICC vocabulary back in line with the data.

``licensedata/vocabulary/dalicc-ns.ttl`` carries two kinds of note that make a claim
about the library:

* ``"Defined in the 2022 documentation; not used by any license in the current library."``
  on the terms the 2022 vocabulary documentation published and no record used;
* ``"... Defined here so the gap is named; the review applied it to no license record."``
  on the terms the 2026-09-15 content review defined for a gap it did not fill.

Both go out of date the moment a record starts using the term, and both are read by
``app/services/vocab.py``: a term whose note says no license uses it is resolved for
display but never offered for authoring.  The standard-license addition put nine of those
terms to work, so the notes had to be rewritten rather than left to mislead.

The counts come from ``licensedata/vocabulary/usage-counts.json``, which
``scripts/validate_data.py --write-usage-counts`` regenerates from the records, so this
script is run after that one and never invents a number.

Usage
-----
    python scripts/validate_data.py --write-usage-counts
    python scripts/review/refresh_vocab_notes.py
    python scripts/review/refresh_vocab_notes.py --check
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
VOCABULARY = REPO_ROOT / "licensedata" / "vocabulary" / "dalicc-ns.ttl"
USAGE_COUNTS = REPO_ROOT / "licensedata" / "vocabulary" / "usage-counts.json"

LOG = logging.getLogger("refresh_vocab_notes")

DALICC = "https://dalicc.net/ns#"

UNUSED_2022 = "not used by any license in the current library"
UNUSED_REVIEW = "the review applied it to no license record"
UNUSED_ADDITION = "in the review records named in its scope note"

#: ``dalicc:<name> a ...`` down to the start of the next term or section heading.  The
#: boundary cannot be "any line that starts in column 0", because the long string
#: literals of ``rdfs:comment`` wrap that way themselves.
BLOCK_RE = re.compile(
    r"^(dalicc:([A-Za-z]+) a .*?)(?=^dalicc:[A-Za-z]+ a |^odrl:|^owl:|^#####|\Z)",
    re.M | re.S,
)
NOTE_RE = re.compile(r'(\s+skos:note )"((?:[^"\\]|\\.)*)"(@en)')


def used_by(counts: dict, name: str) -> int:
    entry = counts["terms"].get(DALICC + name)
    return int(entry["licenses"]) if entry else 0


def rewrite_note(note: str, name: str, licenses: int) -> str:
    """The note ``name`` should carry now that ``licenses`` records use it."""
    if licenses == 0:
        if UNUSED_ADDITION in note:
            return note.split(UNUSED_ADDITION)[0] + "and no license record uses it yet."
        return note
    plural = "record" if licenses == 1 else "records"
    applied = (
        f"Applied to {licenses} license {plural} by the standard-license addition of "
        f"2026-09-15."
    )
    if UNUSED_2022 in note:
        head = note.split(";")[0]
        return f"{head}; used by {licenses} license {plural} since 2026-09-15."
    if UNUSED_REVIEW in note:
        head = note.split("Defined here so the gap is named")[0].strip()
        return f"{head} {applied}"
    if UNUSED_ADDITION in note:
        head = note.split(", which recorded")[0].strip()
        return f"{head}, which recorded the clause as a vocabulary gap. {applied}"
    return note


def refresh(text: str, counts: dict) -> tuple[str, list[str]]:
    changed: list[str] = []

    def replace_block(match: re.Match[str]) -> str:
        block, name = match.group(1), match.group(2)
        licenses = used_by(counts, name)

        def replace_note(note_match: re.Match[str]) -> str:
            note = note_match.group(2)
            new = rewrite_note(note, name, licenses)
            if new != note:
                changed.append(f"dalicc:{name} ({licenses} record(s))")
            return f'{note_match.group(1)}"{new}"{note_match.group(3)}'

        return NOTE_RE.sub(replace_note, block)

    return BLOCK_RE.sub(replace_block, text), changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 if stale")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not USAGE_COUNTS.is_file():
        LOG.error("%s is missing (run: python scripts/validate_data.py "
                  "--write-usage-counts)", USAGE_COUNTS.name)
        return 1
    counts = json.loads(USAGE_COUNTS.read_text(encoding="utf-8"))
    text = VOCABULARY.read_text(encoding="utf-8")
    new_text, changed = refresh(text, counts)

    if not changed:
        LOG.info("every usage note already agrees with the data")
        return 0
    for line in changed:
        LOG.info("  %s", line)
    if args.check:
        LOG.error("%d note(s) are out of date (run: python scripts/review/"
                  "refresh_vocab_notes.py)", len(changed))
        return 1
    VOCABULARY.write_text(new_text, encoding="utf-8", newline="")
    LOG.info("rewrote %d note(s) in %s", len(changed), VOCABULARY.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
