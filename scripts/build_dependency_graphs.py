#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Generate the complete jurisdiction graphs from the core graph and their difference files.

``licensedata/dependencygraph/differences/<id>.ttl`` is the source of truth of a
jurisdiction graph: the default rules it adds, the core axioms it removes and the core
rules it replaces, each with its legal basis and a plain explanation.  This script
reads ``licensedata/dependencygraph/dg_default.ttl`` and every difference file and
writes the complete ``licensedata/dependencygraph/<id>.ttl`` the loader loads and the
site serves (:mod:`app.services.depgraph_build` holds the model and the writer).

Versioning
----------
A generated graph is a versioned model like the core graph.  When the build would
change what a generated graph states (a core change, which moves
``dalicc:basedOnVersion``, or a change of the difference file), it **refuses** to
overwrite the file and exits 1, naming the graphs, until ``--bump`` is given.  With
``--bump`` it archives the previous file as
``licensedata/history/dependencygraph/<id>-v<n>.ttl``, adds the change-log entry of
version n+1 to ``<id>-changelog.yaml`` (the summary names the cause: "Follows core graph
version 3." or "The difference file added a rule."; ``--summary`` and ``--reason``
override it, and ``{id}`` in either stands for the graph's identifier) and
writes the new version.  A change that touches only the comments or the layout is
written without a new version.  ``sync_repository_version`` moves a running
deployment's rows to the new numbers at its next start.

Usage
-----
    python scripts/build_dependency_graphs.py                 # write, refuse a changed graph
    python scripts/build_dependency_graphs.py --bump          # write and version what changed
    python scripts/build_dependency_graphs.py --check         # exit 1 when a file is stale
    python scripts/build_dependency_graphs.py --extract dg_eu # complete graph -> difference file
    python scripts/build_dependency_graphs.py --extract dg_eu --from export/dg_eu.ttl

``--extract`` is how a jurisdiction graph an administrator edited on the server is folded
back: ``make export-library`` writes the edited graph into ``licensedata``, and
``--extract`` derives its difference file from it and the core graph, keeping the
comment block of the difference file that is there.

Exit status: 0 = done (or current with ``--check``), 1 = stale, refused or invalid.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import datetime as dt
import logging
from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dalicc_check import depgraph_build as build_service  # noqa: E402

DATA_DIR = REPO_ROOT / "licensedata" / "dependencygraph"
DIFFERENCES_DIR = DATA_DIR / "differences"
HISTORY_DIR = REPO_ROOT / "licensedata" / "history" / "dependencygraph"

LOG = logging.getLogger("build_dependency_graphs")


def difference_ids(differences_dir: Path = DIFFERENCES_DIR) -> list[str]:
    """Every graph that has a difference file, in a stable order."""
    return sorted(path.stem for path in differences_dir.glob("*.ttl"))


def _core(data_dir: Path, history_dir: Path) -> tuple[str, int]:
    text = (data_dir / f"{build_service.CORE_ID}.ttl").read_text(encoding="utf-8")
    return text, build_service.file_version(history_dir, build_service.CORE_ID)["version"]


def generate(
    graph_id: str,
    *,
    data_dir: Path = DATA_DIR,
    differences_dir: Path = DIFFERENCES_DIR,
    history_dir: Path = HISTORY_DIR,
    version: int | None = None,
    date: str = "",
    reviewer: str = "",
) -> str:
    """The text the build writes for one graph at its current (or the given) version."""
    core_text, core_version = _core(data_dir, history_dir)
    current = build_service.file_version(history_dir, graph_id)
    return build_service.build(
        core_text,
        (differences_dir / f"{graph_id}.ttl").read_text(encoding="utf-8"),
        graph_id,
        version=version if version is not None else current["version"],
        date=date or current["date"],
        reviewer=reviewer if version is not None else current["reviewer"],
        core_version=core_version,
    )


def _cause(changes: list[dict[str, str]], core_version: int) -> str:
    """The summary of a new version, from what changed."""
    sentences: list[str] = []
    rest = [c for c in changes if not c["statement"].startswith("dalicc:basedOnVersion")]
    if len(rest) != len(changes):
        sentences.append(f"Follows core graph version {core_version}.")
    rules = [c for c in rest if c["statement"].startswith("rule ")]
    removals = [c for c in rest if c["statement"].startswith("removal of ")]
    phrases: list[str] = []
    for action in ("added", "removed", "changed"):
        count = sum(1 for c in rules if c["action"] == action)
        if count:
            phrases.append(f"{action} {'a rule' if count == 1 else f'{count} rules'}")
    for action in ("added", "removed"):
        count = sum(1 for c in removals if c["action"] == action)
        if count:
            what = "an axiom removal" if count == 1 else f"{count} axiom removals"
            phrases.append(f"{action} {what}")
    if any(c["statement"].startswith(("dct:title", "dct:description")) for c in rest):
        phrases.append("changed the graph's title or description")
    if phrases:
        sentences.append("The difference file " + ", ".join(phrases) + ".")
    elif rest and len(rest) == len(changes):
        sentences.append("The core graph changed what this graph states.")
    return " ".join(sentences) or "Rebuilt."


def bump(
    graph_id: str,
    new_body_at: Callable[[int, str, str], str],
    *,
    summary: str,
    reason: str,
    reviewer: str,
    date: str,
    core_version: int,
    data_dir: Path = DATA_DIR,
    history_dir: Path = HISTORY_DIR,
) -> int:
    """Archive the current file, log version n+1 and write it; returns n+1."""
    path = data_dir / f"{graph_id}.ttl"
    previous = path.read_text(encoding="utf-8")
    current = build_service.file_version(history_dir, graph_id)
    version = current["version"] + 1
    reviewer = reviewer or current["reviewer"]
    text = new_body_at(version, date, reviewer)
    changes = build_service.statement_changes(previous, text)
    summary = summary.replace("{id}", graph_id) if summary else _cause(changes, core_version)
    for change in changes:
        change["reason"] = reason.replace("{id}", graph_id) if reason else summary
        change["source"] = "build_dependency_graphs"
    (history_dir / f"{graph_id}-v{current['version']}.ttl").write_text(previous, encoding="utf-8")
    log_path = history_dir / f"{graph_id}-changelog.yaml"
    log = (
        yaml.safe_load(log_path.read_text(encoding="utf-8"))
        if log_path.is_file()
        else {"id": graph_id, "title": "", "current_version": 1, "entries": []}
    )
    log["current_version"] = version
    log.setdefault("entries", []).append(
        {
            "version": version,
            "date": date,
            "reviewer": reviewer,
            "summary": summary,
            "changes": [
                {key: change[key] for key in ("action", "statement", "previous", "reason", "source")
                 if change.get(key)}
                for change in changes
            ],
        }
    )
    log_path.write_text(
        yaml.safe_dump(log, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    path.write_text(text, encoding="utf-8")
    return version


def _statements_equal(first: str, second: str) -> bool:
    """True when two versions state the same (the date and comments aside)."""
    return not build_service.statement_changes(first, second) and _same_rdf(first, second)


def _same_rdf(first: str, second: str) -> bool:
    from rdflib import Graph
    from rdflib.compare import isomorphic

    def without_dates(text: str) -> Graph:
        graph = Graph()
        graph.parse(data=text, format="turtle")
        for triple in list(graph):
            if str(triple[1]) == "http://purl.org/dc/terms/date" and str(triple[0]).startswith(
                build_service.GRAPH_NAMESPACE
            ) and "/" not in str(triple[0])[len(build_service.GRAPH_NAMESPACE):]:
                graph.remove(triple)
        return graph

    return isomorphic(without_dates(first), without_dates(second))


def run_build(args: argparse.Namespace) -> int:
    ids = args.only or difference_ids(args.differences)
    _core_text, core_version = _core(args.data, args.history)
    refused: list[str] = []
    stale: list[str] = []
    for graph_id in ids:
        try:
            text = generate(
                graph_id,
                data_dir=args.data,
                differences_dir=args.differences,
                history_dir=args.history,
            )
        except build_service.BuildError as exc:
            LOG.error("%s", exc)
            return 1
        path = args.data / f"{graph_id}.ttl"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing == text:
            LOG.info("%s: current", graph_id)
            continue
        if args.check:
            stale.append(graph_id)
            continue
        if existing and _statements_equal(existing, text):
            path.write_text(text, encoding="utf-8")
            LOG.info("%s: rewritten, no statement changed, still version %s", graph_id,
                     build_service.file_version(args.history, graph_id)["version"])
            continue
        if not args.bump:
            refused.append(graph_id)
            continue
        date = args.date or dt.date.today().isoformat()

        def body(version: int, day: str, reviewer: str, graph_id: str = graph_id) -> str:
            return generate(
                graph_id,
                data_dir=args.data,
                differences_dir=args.differences,
                history_dir=args.history,
                version=version,
                date=day,
                reviewer=reviewer,
            )

        version = bump(
            graph_id,
            body,
            summary=args.summary,
            reason=args.reason,
            reviewer=args.reviewer,
            date=date,
            core_version=core_version,
            data_dir=args.data,
            history_dir=args.history,
        )
        LOG.info("%s: version %s written", graph_id, version)
    if stale:
        LOG.error("stale generated graph(s): %s (run scripts/build_dependency_graphs.py)",
                  ", ".join(stale))
        return 1
    if refused:
        LOG.error(
            "the build would change what %s state(s); run it again with --bump to give "
            "each a new version with a change-log entry",
            ", ".join(refused),
        )
        return 1
    return 0


def run_extract(args: argparse.Namespace) -> int:
    graph_id = args.extract
    source = Path(args.source) if args.source else args.data / f"{graph_id}.ttl"
    core_text, _ = _core(args.data, args.history)
    core_axioms, core_rules = build_service.core_statements(core_text)
    target = Path(args.output) if args.output else args.differences / f"{graph_id}.ttl"
    comment = (
        build_service.leading_comment(target.read_text(encoding="utf-8"))
        if target.is_file()
        else ""
    )
    try:
        difference = build_service.extract(
            source.read_text(encoding="utf-8"), graph_id, core_axioms, core_rules,
            comment=comment,
        )
    except build_service.BuildError as exc:
        LOG.error("%s", exc)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_service.render_difference(difference), encoding="utf-8")
    LOG.info("%s: wrote %s", graph_id, target)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when a file is stale")
    parser.add_argument("--bump", action="store_true", help="version every changed graph")
    parser.add_argument("--summary", default="", help="the change-log summary with --bump")
    parser.add_argument("--reason", default="", help="the reason of each change with --bump")
    parser.add_argument("--reviewer", default="", help="the reviewer named with --bump")
    parser.add_argument("--date", default="", help="the date of a new version (YYYY-MM-DD)")
    parser.add_argument("--only", nargs="*", default=None, help="build these graphs only")
    parser.add_argument("--extract", default="", help="derive this graph's difference file")
    parser.add_argument("--from", dest="source", default="", help="the complete graph to read")
    parser.add_argument("--output", default="", help="where --extract writes")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--differences", type=Path, default=DIFFERENCES_DIR,
                        help=argparse.SUPPRESS)
    parser.add_argument("--history", type=Path, default=HISTORY_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.extract:
        return run_extract(args)
    return run_build(args)


if __name__ == "__main__":
    sys.exit(main())
