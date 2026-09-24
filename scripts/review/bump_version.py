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

One record or several.  A review that changes one sentence of one licence changes one
record; a library-wide decision changes hundreds, and starting a process per record
would spend most of its time importing rdflib and calling ``git show``.  Several
identifiers, or ``--from-file``, run in one process: the committed texts are read with a
single ``git cat-file --batch``, every record is read and diffed before anything is
written, and a record that cannot be versioned is reported and skipped rather than
leaving the batch half applied.

Usage
-----
    python scripts/review/bump_version.py MIT --summary "..."
    python scripts/review/bump_version.py MIT --summary "..." --reviewer "Giray Havur"
    python scripts/review/bump_version.py MIT --summary "..." --dry-run
    python scripts/review/bump_version.py MIT --summary "..." --base-file before.ttl
    python scripts/review/bump_version.py MIT Apache-2.0 BSD-3-Clause --summary "..."
    python scripts/review/bump_version.py --from-file ids.txt --summary "..."
    python scripts/review/bump_version.py --from-file ids.txt --summary "..." \
        --notes notes.json

A library-wide change still owes every record a summary in its own words, and a change
that the triples alone do not explain (a quote added to a permission reads the same as
the permission did) owes it a reason.  ``--notes`` names a JSON file of the form
``{"<id>": {"summary": "...", "reasons": {"<statement>": "..."}}}``: a record listed
there gets its own summary instead of ``--summary``, and each change whose statement is
a key of ``reasons`` gets that reason instead of the generic one.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
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


def git_show_head_batch(license_ids: list[str]) -> dict[str, str | None]:
    """The committed text of many records, read in one ``git cat-file --batch``.

    One process instead of one per record: over several hundred records the process
    starts were most of the wall clock.  A record that is not committed yet comes back
    as ``None``, exactly as :func:`git_show_head` reports it.
    """
    if not license_ids:
        return {}
    request = "".join(f"HEAD:licensedata/licenses/{name}.ttl\n" for name in license_ids)
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPO_ROOT,
        input=request.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        LOG.warning("git cat-file failed; falling back to one git show per record")
        return {name: git_show_head(name) for name in license_ids}

    out: dict[str, str | None] = {}
    data = result.stdout
    position = 0
    for name in license_ids:
        end = data.find(b"\n", position)
        if end < 0:
            out[name] = None
            continue
        header = data[position:end].decode("utf-8", "replace")
        position = end + 1
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            # "<object> missing", or a tree where a blob was expected.
            out[name] = None
            continue
        size = int(parts[2])
        out[name] = data[position : position + size].decode("utf-8")
        position += size + 1  # the newline git writes after the object
    return out


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


def plan_one(
    license_id: str, committed_text: str | None, args: argparse.Namespace,
    notes: dict | None = None,
) -> tuple[dict, str] | str:
    """Work out what versioning one record would do, without writing anything.

    Returns the plan, or one sentence saying why the record cannot be versioned.  The
    whole batch is planned before any of it is written, so a record that cannot be
    versioned stops itself rather than the records around it.
    """
    path = LICENSES_DIR / f"{license_id}.ttl"
    if not path.is_file():
        return f"no such record: {_rel(path)}"
    if committed_text is None:
        return (
            f"{license_id} is not committed yet, so there is no version to archive; "
            f"commit it first"
        )

    working_text = path.read_text(encoding="utf-8")
    working = rdflib.Graph()
    working.parse(data=working_text, format="turtle")
    committed = rdflib.Graph()
    committed.parse(data=committed_text, format="turtle")

    subject = license_subject(working)
    committed_subject = license_subject(committed)
    if subject is None or committed_subject is None:
        return f"{license_id}: a version of this record holds no odrl:Set"

    changes = diff_statements(
        statements_of(committed, committed_subject), statements_of(working, subject)
    )
    if not changes:
        return (
            f"{license_id} is identical to HEAD apart from its version metadata; "
            f"nothing to version"
        )

    version = committed_version(committed_text)
    folder = HISTORY_DIR / "licenses" / license_id
    archive = folder / f"v{version}.ttl"
    if archive.is_file() and archive.read_text(encoding="utf-8") != committed_text:
        return (
            f"{_rel(archive)} already exists and differs from the version being "
            f"archived; the history is inconsistent"
        )

    title = next(
        (str(v) for v in working.objects(subject, rdflib.URIRef("http://purl.org/dc/terms/title"))),
        license_id,
    )
    changelog_path = folder / "changelog.yaml"
    changelog = load_changelog(changelog_path, license_id, title)
    new_version = version + 1
    if any(entry.get("version") == new_version for entry in changelog["entries"]):
        return f"{license_id}: the changelog already holds an entry for version {new_version}"
    changelog["title"] = title
    changelog["current_version"] = new_version
    notes = notes or {}
    reasons = notes.get("reasons") or {}
    changelog["entries"].append(
        {
            "version": new_version,
            "date": args.date,
            "reviewer": args.reviewer,
            "summary": notes.get("summary") or args.summary,
            "changes": [
                {
                    "action": change.action,
                    "statement": change.statement,
                    **({"previous": change.previous} if change.previous else {}),
                    "reason": reasons.get(change.statement) or MANUAL_REASON,
                    "source": "manual",
                }
                for change in changes
            ],
        }
    )
    plan = {
        "id": license_id,
        "path": path,
        "folder": folder,
        "archive": archive,
        "archive_text": committed_text,
        "changelog_path": changelog_path,
        "changelog": changelog,
        "version": version,
        "new_version": new_version,
        "changes": changes,
    }
    return (plan, f"{license_id}: version {version} -> {new_version}, {len(changes)} change(s)")


def apply_one(plan: dict, args: argparse.Namespace) -> None:
    """Write what :func:`plan_one` worked out."""
    record = Record.parse(plan["path"])
    for predicate in ("dct:hasVersion", "dct:modified", "dalicc:versionHistory"):
        record.remove_predicate(predicate)
    record.set_single_object("dct:hasVersion", f'"{plan["new_version"]}"')
    record.set_single_object("dct:modified", f'"{args.date}"^^xsd:date')
    record.set_single_object(
        "dalicc:versionHistory",
        f"<https://dalicc.net/licenselibrary/{plan['id']}/versions>",
    )
    plan["folder"].mkdir(parents=True, exist_ok=True)
    plan["archive"].write_text(plan["archive_text"], encoding="utf-8", newline="")
    plan["changelog_path"].write_text(dump_yaml(plan["changelog"]), encoding="utf-8", newline="")
    record.write()


def main(argv: list[str] | None = None) -> int:
    """Archive the committed version of each record and open its changelog entry."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "license_id", nargs="*", help="the record(s) to version, e.g. MIT Apache-2.0"
    )
    parser.add_argument("--summary", required=True, help="one sentence: what changed and why")
    parser.add_argument("--reviewer", default=REVIEWER, help="who made the change")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="do not write anything")
    parser.add_argument(
        "--from-file",
        default="",
        help="a file with one record identifier per line, for a library-wide change; "
             "blank lines and lines beginning with # are ignored",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="a JSON file giving a record its own summary and a change its own reason: "
             '{"<id>": {"summary": "...", "reasons": {"<statement>": "..."}}}',
    )
    parser.add_argument(
        "--base-file",
        default="",
        help="the record as it stood before this edit, when the working tree already "
             "carries a version that is not committed yet; defaults to HEAD. Only for "
             "a single record",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    license_ids = list(args.license_id)
    if args.from_file:
        listing = Path(args.from_file)
        if not listing.is_file():
            LOG.error("no such file: %s", _rel(listing))
            return 1
        for line in listing.read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name and not name.startswith("#"):
                license_ids.append(name)
    seen: set[str] = set()
    license_ids = [name for name in license_ids if not (name in seen or seen.add(name))]
    if not license_ids:
        LOG.error("name at least one record, or pass --from-file")
        return 1
    if args.base_file and len(license_ids) > 1:
        LOG.error("--base-file applies to one record; name one, or drop the option")
        return 1

    if args.base_file:
        base_path = Path(args.base_file)
        if not base_path.is_file():
            LOG.error("no such base file: %s", _rel(base_path))
            return 1
        committed = {license_ids[0]: base_path.read_text(encoding="utf-8")}
    else:
        committed = git_show_head_batch(license_ids)

    notes: dict = {}
    if args.notes:
        notes_path = Path(args.notes)
        if not notes_path.is_file():
            LOG.error("no such notes file: %s", _rel(notes_path))
            return 1
        notes = json.loads(notes_path.read_text(encoding="utf-8"))

    plans: list[dict] = []
    problems: list[str] = []
    for license_id in license_ids:
        outcome = plan_one(license_id, committed.get(license_id), args, notes.get(license_id))
        if isinstance(outcome, str):
            problems.append(outcome)
            LOG.error("%s", outcome)
            continue
        plan, line = outcome
        plans.append(plan)
        LOG.info("%s", line)
        for change in plan["changes"]:
            LOG.debug("  %-8s %s", change.action, change.statement[:96])

    if not plans:
        return 1
    if args.dry_run:
        LOG.info("dry run: %d record(s) would be versioned, nothing written", len(plans))
        return 1 if problems else 0

    for plan in plans:
        apply_one(plan, args)
    LOG.info(
        "versioned %d record(s); now run build_licenselibrary.py and validate_data.py",
        len(plans),
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
