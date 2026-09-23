#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Version one curated license model after it has been edited.

This is the governance half of the model history that
:mod:`scripts.review.build_history` created once from the repository.  From now on a
change to ``licensedata/licenses/<id>.ttl`` is made in three steps::

    $EDITOR licensedata/licenses/MIT.ttl
    python scripts/review/bump_version.py MIT --summary "Recorded the patent clause."
    python scripts/build_licenselibrary.py && python scripts/validate_data.py

What this script does, for the record named on the command line:

1.  reads the version the edit started from and refuses to do anything when the working
    file says the same thing.  That is normally the committed one
    (``git show HEAD:licensedata/licenses/<id>.ttl``); when the working tree already
    carries a bump that is not committed yet, the caller passes the pre-edit text with
    ``--base-file`` and that becomes the base instead;
2.  writes that base version to ``licensedata/history/licenses/<id>/v<n>.ttl``,
    where ``n`` is the ``dct:hasVersion`` the base version carries;
3.  raises ``dct:hasVersion`` to ``n + 1`` and sets ``dct:modified`` to today in the
    working file, and adds ``dalicc:versionHistory`` when it is missing;
4.  appends an entry to ``licensedata/history/licenses/<id>/changelog.yaml`` holding the
    summary given on the command line and the triple-level difference between the
    working file and the committed one.

Every change in that entry carries ``source: manual``, because a hand edit is exactly
what it is: the annotated sources (``review-finding``, ``consolidation-decision``,
``review-state``, ``ports-metadata``) belong to the 2026-09-15 sweep, which is recorded
once and is not repeated.  Write the reason into ``--summary``, and edit the entry
afterwards if a change needs a reason of its own.

``scripts/validate_data.py`` proves that the result is consistent, and the same check
with ``--against-git`` is the CI gate that a changed model was versioned at all.

Usage
-----
    python scripts/review/bump_version.py MIT --summary "..."
    python scripts/review/bump_version.py MIT --summary "..." --reviewer "Giray Havur"
    python scripts/review/bump_version.py MIT --summary "..." --dry-run
    python scripts/review/bump_version.py MIT --summary "..." --base-file before.ttl
"""

from __future__ import annotations

import argparse
from datetime import date
import logging
from pathlib import Path
import subprocess
import sys

import rdflib
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_history import (
    HISTORY_DIR,
    LICENSES_DIR,
    REPO_ROOT,
    REVIEWER,
    diff_statements,
    dump_yaml,
    license_subject,
    statements_of,
)
from ttl_record import Record

LOG = logging.getLogger("bump_version")

MANUAL_REASON = "Edited by hand; see the summary of this entry."


def _rel(path: Path) -> str:
    """``path`` relative to the repository, or as it is when it lies outside."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def git_show_head(license_id: str) -> str | None:
    """The committed text of one record, or ``None`` when it is not committed yet."""
    result = subprocess.run(
        ["git", "show", f"HEAD:licensedata/licenses/{license_id}.ttl"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return None if result.returncode != 0 else result.stdout.decode("utf-8")


def committed_version(text: str) -> int:
    """The ``dct:hasVersion`` of a record's text, defaulting to 1."""
    record = Record.parse_text(Path("committed.ttl"), text)
    for obj in record.objects("dct:hasVersion"):
        value = obj.strip('"')
        if value.isdigit():
            return int(value)
    return 1


def load_changelog(path: Path, license_id: str, title: str) -> dict:
    """The changelog of one record, or a fresh one."""
    if path.is_file():
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("entries", [])
            return payload
    return {"id": license_id, "title": title, "current_version": 1, "entries": []}


def main(argv: list[str] | None = None) -> int:
    """Archive the committed version of one record and open its changelog entry."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("license_id", help="the record to version, e.g. MIT")
    parser.add_argument("--summary", required=True, help="one sentence: what changed and why")
    parser.add_argument("--reviewer", default=REVIEWER, help="who made the change")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="do not write anything")
    parser.add_argument(
        "--base-file",
        default="",
        help="the record as it stood before this edit, when the working tree already "
             "carries a version that is not committed yet; defaults to HEAD",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    license_id = args.license_id
    path = LICENSES_DIR / f"{license_id}.ttl"
    if not path.is_file():
        LOG.error("no such record: %s", _rel(path))
        return 1

    if args.base_file:
        base_path = Path(args.base_file)
        if not base_path.is_file():
            LOG.error("no such base file: %s", _rel(base_path))
            return 1
        committed_text = base_path.read_text(encoding="utf-8")
    else:
        committed_text = git_show_head(license_id)
    if committed_text is None:
        LOG.error(
            "%s is not committed yet, so there is no version to archive; commit it first",
            license_id,
        )
        return 1

    working_text = path.read_text(encoding="utf-8")
    working = rdflib.Graph()
    working.parse(data=working_text, format="turtle")
    committed = rdflib.Graph()
    committed.parse(data=committed_text, format="turtle")

    subject = license_subject(working)
    committed_subject = license_subject(committed)
    if subject is None or committed_subject is None:
        LOG.error("%s: a version of this record holds no odrl:Set", license_id)
        return 1

    changes = diff_statements(
        statements_of(committed, committed_subject), statements_of(working, subject)
    )
    if not changes:
        LOG.error(
            "%s is identical to HEAD apart from its version metadata; nothing to version",
            license_id,
        )
        return 1

    version = committed_version(committed_text)
    folder = HISTORY_DIR / "licenses" / license_id
    archive = folder / f"v{version}.ttl"
    if archive.is_file() and archive.read_text(encoding="utf-8") != committed_text:
        LOG.error(
            "%s already exists and differs from the version being archived; the history "
            "is inconsistent",
            _rel(archive),
        )
        return 1

    title = next(
        (str(v) for v in working.objects(subject, rdflib.URIRef("http://purl.org/dc/terms/title"))),
        license_id,
    )
    changelog_path = folder / "changelog.yaml"
    changelog = load_changelog(changelog_path, license_id, title)
    new_version = version + 1
    if any(entry.get("version") == new_version for entry in changelog["entries"]):
        LOG.error("changelog already holds an entry for version %d", new_version)
        return 1
    changelog["title"] = title
    changelog["current_version"] = new_version
    changelog["entries"].append(
        {
            "version": new_version,
            "date": args.date,
            "reviewer": args.reviewer,
            "summary": args.summary,
            "changes": [
                {
                    "action": change.action,
                    "statement": change.statement,
                    **({"previous": change.previous} if change.previous else {}),
                    "reason": MANUAL_REASON,
                    "source": "manual",
                }
                for change in changes
            ],
        }
    )

    record = Record.parse(path)
    for predicate in ("dct:hasVersion", "dct:modified", "dalicc:versionHistory"):
        record.remove_predicate(predicate)
    record.set_single_object("dct:hasVersion", f'"{new_version}"')
    record.set_single_object("dct:modified", f'"{args.date}"^^xsd:date')
    record.set_single_object(
        "dalicc:versionHistory",
        f"<https://dalicc.net/licenselibrary/{license_id}/versions>",
    )

    LOG.info("%s: version %d -> %d, %d change(s)", license_id, version, new_version, len(changes))
    for change in changes:
        LOG.info("  %-8s %s", change.action, change.statement[:96])
    if args.dry_run:
        LOG.info("dry run: nothing written")
        return 0

    folder.mkdir(parents=True, exist_ok=True)
    archive.write_text(committed_text, encoding="utf-8", newline="")
    changelog_path.write_text(dump_yaml(changelog), encoding="utf-8", newline="")
    record.write()
    LOG.info(
        "wrote %s, %s and the bumped record; now run build_licenselibrary.py and "
        "validate_data.py",
        _rel(archive),
        _rel(changelog_path),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
