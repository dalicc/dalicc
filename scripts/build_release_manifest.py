#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Write the release manifest of the curated data in this checkout.

A release of the data is the version and the content hash of every curated licence
record, every shipped dependency graph and the vocabulary.  This script computes that
set from ``licensedata/`` alone (no triple store, so composed licences are not part of
it; no database, so versions published on a running server are not either, which is
right for a release cut from the repository), names it with the four identifiers the
API uses (``data-``, ``lib-``, ``dg-``, ``ns-``) and writes
``licensedata/releases/<data-id>.json``.

The identifiers are content addresses and are computed exactly as
``app/services/releases.py`` computes them for a running server; a unit test holds the
two to the same answer.  The only import from the service is the content hash, so the
public data repository runs the same script with its copy of that module.

Usage
-----
    python scripts/build_release_manifest.py                        # write and print the ids
    python scripts/build_release_manifest.py --application-version 2.0.0
    python scripts/build_release_manifest.py --check                # CI after a cut

``--check`` writes nothing and exits 1 when the newest registered manifest does not name
the state of the checkout (a record, graph or vocabulary changed after the cut, or no
release was registered).  Exit status is 0 otherwise.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from rdflib import Graph, URIRef  # noqa: E402
from rdflib.namespace import RDF  # noqa: E402
import yaml  # noqa: E402

from dalicc_check.c14n import ALGORITHM, content_hash, record_closure  # noqa: E402

LICENSE_BASE = "https://dalicc.net/licenselibrary/"
ODRL_SET = URIRef("http://www.w3.org/ns/odrl/2/Set")
HAS_VERSION = URIRef("http://purl.org/dc/terms/hasVersion")
DEPRECATED = URIRef("http://www.w3.org/2002/07/owl#deprecated")
VOCABULARY_ID = "dalicc-ns"
_VERSION_RE = re.compile(r'^\s*version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _lines(entries: dict[str, dict]) -> str:
    ordered = sorted(entries, key=lambda key: key.encode("utf-8"))
    return "".join(f"{key}\t{entries[key]['version']}\t{entries[key]['hash']}\n" for key in ordered)


def _changelog(path: Path) -> tuple[int | None, str]:
    """``(current_version, newest date)`` of one change log, ``(None, "")`` without one."""
    if not path.is_file():
        return None, ""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None, ""
    entries = [item for item in (data.get("entries") or []) if isinstance(item, dict)]
    dates = [str(item.get("date") or "").strip() for item in entries]
    versions = [int(item["version"]) for item in entries if str(item.get("version", "")).isdigit()]
    current = data.get("current_version")
    if not str(current or "").isdigit():
        current = max(versions) if versions else None
    return (int(current) if current else None), max(dates, default="")


def _record(path: Path, history: Path) -> dict:
    graph = Graph().parse(path, format="turtle")
    subject = URIRef(LICENSE_BASE + path.stem)
    if (subject, None, None) not in graph:
        subject = next(
            (node for node in graph.subjects(RDF.type, ODRL_SET) if isinstance(node, URIRef)),
            subject,
        )
    stated = next(
        (int(str(obj).strip()) for obj in graph.objects(subject, HAS_VERSION)
         if str(obj).strip().isdigit() and int(str(obj).strip()) >= 1),
        None,
    )
    logged, date = _changelog(history / "licenses" / path.stem / "changelog.yaml")
    withdrawn = any(
        str(obj).strip().lower() == "true" for obj in graph.objects(subject, DEPRECATED)
    )
    return {
        "date": date,
        "hash": content_hash(record_closure(graph, subject)),
        "status": "withdrawn" if withdrawn else "current",
        "version": stated or logged or 1,
    }


def _whole(path: Path, changelog: Path, *, status: bool = True) -> dict:
    logged, date = _changelog(changelog)
    entry = {
        "date": date,
        "hash": content_hash(Graph().parse(path, format="turtle")),
        "version": logged or 1,
    }
    if status:
        entry["status"] = "current"
    return entry


def build(licensedata: Path, *, application_version: str, date: str) -> dict:
    """The manifest document of the checkout at ``licensedata``."""
    history = licensedata / "history"
    records = {
        path.stem: _record(path, history)
        for path in sorted((licensedata / "licenses").glob("*.ttl"))
    }
    graphs = {}
    for path in sorted((licensedata / "dependencygraph").glob("*.ttl")):
        name = "changelog.yaml" if path.stem == "dg_default" else f"{path.stem}-changelog.yaml"
        graphs[path.stem] = _whole(path, history / "dependencygraph" / name)
    vocabulary = _whole(
        licensedata / "vocabulary" / "dalicc-ns.ttl",
        history / "vocabulary" / "changelog.yaml",
        status=False,
    )
    library_id = "lib-" + _hex(_lines(records))
    graphs_id = "dg-" + _hex(_lines(graphs))
    ns_id = "ns-" + _hex(f"{VOCABULARY_ID}\t{vocabulary['version']}\t{vocabulary['hash']}\n")
    return {
        "algorithm": ALGORITHM,
        "application_version": application_version,
        "date": date,
        "release": "data-" + _hex(f"{library_id}\n{graphs_id}\n{ns_id}\n"),
        "library": {"id": library_id, "records": records},
        "graphs": {"id": graphs_id, "graphs": graphs},
        "vocabulary": {"id": ns_id, **vocabulary},
    }


def newest_registered(licensedata: Path) -> dict | None:
    """The newest manifest under ``licensedata/releases``, or ``None``."""
    found = []
    for path in sorted((licensedata / "releases").glob("data-*.json")):
        try:
            found.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    found.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("release") or "")))
    return found[-1] if found else None


def _default_version() -> str:
    try:
        match = _VERSION_RE.search((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except OSError:
        return ""
    return match.group(1) if match else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--licensedata", type=Path, default=REPO_ROOT / "licensedata")
    parser.add_argument("--application-version", default="")
    parser.add_argument("--date", default="", help="the day of the cut (default: today)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    manifest = build(
        args.licensedata,
        application_version=args.application_version or _default_version(),
        date=args.date or dt.date.today().isoformat(),
    )
    ids = (
        manifest["release"],
        manifest["library"]["id"],
        manifest["graphs"]["id"],
        manifest["vocabulary"]["id"],
    )
    if args.check:
        registered = newest_registered(args.licensedata)
        if registered is None:
            sys.stderr.write("no release is registered under licensedata/releases\n")
            return 1
        if registered.get("release") != manifest["release"]:
            sys.stderr.write(
                f"the checkout is {manifest['release']}, the newest registered release is "
                f"{registered.get('release')}\n"
            )
            return 1
        sys.stdout.write(f"the checkout is the registered release {manifest['release']}\n")
        return 0

    target = args.licensedata / "releases" / f"{manifest['release']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target.write_text(text, encoding="utf-8")
    sys.stdout.write("".join(value + "\n" for value in ids) + f"wrote {target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
