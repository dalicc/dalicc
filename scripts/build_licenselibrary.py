#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Regenerate ``licensedata/licenselibrary/licenselibrary.ttl`` from the per-license files.

The DALICC license data exists in two representations:

* ``licensedata/licenses/<id>.ttl`` -- one file per license, the source of truth.
* ``licensedata/licenselibrary/licenselibrary.ttl`` -- all licenses in one Turtle
  document, the file that is bulk-loaded into the Virtuoso named graph
  ``https://dalicc.net/licenselibrary/``.

Historically both were maintained by hand and drifted apart (the combined file was not
even valid Turtle).  This script makes the combined file a build artefact: it is the
concatenation of the per-license bodies, sorted by license identifier, under one shared
prefix block, with a ``# <id>`` comment in front of every block.

The generator is purely textual on purpose.  Re-serialising with rdflib would rename the
~6,500 blank nodes and reorder every object list, producing a huge diff on every run and
losing the hand-curated formatting.  Concatenation keeps the combined file byte-stable
and makes ``git diff`` on it readable.

Usage
-----
    python scripts/build_licenselibrary.py              # write the file
    python scripts/build_licenselibrary.py --check      # fail if the file is out of date
    python scripts/build_licenselibrary.py --output /tmp/x.ttl

Exit status is 0 on success, 1 on a validation or --check failure.

The result is verified with rdflib before it is written: the generated document must
parse and must contain exactly one ``odrl:Set`` per input file.  ``scripts/validate_data.py``
additionally proves that the two representations carry the same triples.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
LICENSES_DIR = REPO_ROOT / "licensedata" / "licenses"
LIBRARY_FILE = REPO_ROOT / "licensedata" / "licenselibrary" / "licenselibrary.ttl"

HEADER = """\
# Title: The machine-readable representation of all licenses in the DALICC license library
# Author: DALICC
# Source: https://github.com/dalicc/dalicc_production
# Licensed under: Attribution 4.0 International (CC BY 4.0)
#
# GENERATED FILE -- do not edit by hand.
#   Source of truth: licensedata/licenses/*.ttl (one file per license)
#   Regenerate with: python scripts/build_licenselibrary.py
#   Verify with:     python scripts/validate_data.py
#
# This document is bulk-loaded into the named graph <https://dalicc.net/licenselibrary/>
# (see licenselibrary.ttl.graph).
"""

LOG = logging.getLogger("build_licenselibrary")


class BuildError(RuntimeError):
    """Raised when the inputs are not shaped the way the generator requires."""


def split_license_file(path: Path) -> tuple[list[str], str]:
    """Split one license file into its ``@prefix`` block and its body.

    The four-line ``# Title/Author/Source/Licensed under`` provenance header is dropped:
    the combined file carries its own header.  Returns ``(prefix_lines, body)`` where
    ``body`` is everything after the prefix block, stripped of surrounding blank lines.
    """
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BuildError(f"{path}: UTF-8 BOM (run the encoding normalisation first)")
    if b"\r" in raw:
        raise BuildError(f"{path}: CR/CRLF line endings (expected LF only)")

    lines = raw.decode("utf-8").split("\n")
    index = 0
    while index < len(lines) and (lines[index].startswith("#") or not lines[index].strip()):
        index += 1

    prefixes: list[str] = []
    while index < len(lines) and (lines[index].startswith("@prefix") or not lines[index].strip()):
        if lines[index].startswith("@prefix"):
            prefixes.append(lines[index].rstrip())
        index += 1

    if not prefixes:
        raise BuildError(f"{path}: no @prefix block found")

    body = "\n".join(lines[index:]).strip("\n")
    if not body:
        raise BuildError(f"{path}: no statements after the @prefix block")
    if not body.rstrip().endswith("."):
        raise BuildError(f"{path}: body does not end with a '.' statement terminator")
    return prefixes, body


def build(licenses_dir: Path) -> str:
    """Return the full text of the combined license library document."""
    files = sorted(licenses_dir.glob("*.ttl"), key=lambda p: p.stem)
    if not files:
        raise BuildError(f"{licenses_dir}: no *.ttl files found")

    shared_prefixes: list[str] | None = None
    blocks: list[str] = []
    for path in files:
        prefixes, body = split_license_file(path)
        if shared_prefixes is None:
            shared_prefixes = prefixes
        elif prefixes != shared_prefixes:
            raise BuildError(
                f"{path}: @prefix block differs from {files[0].name}; "
                "all license files must share one prefix block"
            )
        blocks.append(f"# {path.stem}\n{body}\n")

    assert shared_prefixes is not None  # guarded by the empty-dir check above
    parts = [HEADER, "\n", "\n".join(shared_prefixes), "\n\n"]
    parts.append("\n".join(blocks))
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    LOG.info("built %d license blocks from %s", len(blocks), licenses_dir)
    return text


def verify(text: str, expected_sets: int) -> None:
    """Parse the generated document and assert it holds ``expected_sets`` odrl:Set subjects."""
    import rdflib  # imported late so --help works without rdflib installed
    from rdflib.namespace import RDF, Namespace

    odrl = Namespace("http://www.w3.org/ns/odrl/2/")
    graph = rdflib.Graph()
    graph.parse(data=text, format="turtle")
    subjects = set(graph.subjects(RDF.type, odrl.Set))
    if len(subjects) != expected_sets:
        raise BuildError(
            f"generated document has {len(subjects)} odrl:Set subjects, expected {expected_sets}"
        )
    LOG.info("generated document parses: %d triples, %d odrl:Set subjects",
             len(graph), len(subjects))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--licenses-dir", type=Path, default=LICENSES_DIR,
                        help="directory holding the per-license .ttl files")
    parser.add_argument("--output", type=Path, default=LIBRARY_FILE,
                        help="path of the combined library file to write")
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if the output file is out of date")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        text = build(args.licenses_dir)
        verify(text, expected_sets=len(list(args.licenses_dir.glob("*.ttl"))))
    except BuildError as exc:
        LOG.error("%s", exc)
        return 1

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        if current == text:
            LOG.info("%s is up to date", args.output)
            return 0
        LOG.error("%s is OUT OF DATE -- run: python scripts/build_licenselibrary.py", args.output)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="")
    LOG.info("wrote %s (%d bytes)", args.output, args.output.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
