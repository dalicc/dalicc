#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Run the consistency check over every record in the license library.

``app.services.consistency.consistency_check`` is the rule set behind
``POST /licenselibrary/consistencycheck``: it reports a license that permits and
prohibits the same action, a duty that can never be discharged because its action is
prohibited, a share-alike condition next to a permission to relicense, and the same
three closed under the dependency graph.  That module needs nothing but rdflib,
``app/services/vocab.py`` and the data, so this script runs without the service: it
reads the dependency graph straight from ``licensedata/dependencygraph/dg_default.ttl``
rather than through a SPARQL client.

The 2026-09-15 review ran it per record.  This script runs it over the whole library in
one go, so that a data change can be checked against the expected baseline.  Two records
are expected to conflict, and the review confirmed both against their texts: the Ordnance
Survey evaluation licences allow building something with the data and forbid supplying
it, which the model can only express as ``odrl:derive`` permitted while
``cc:DerivativeWorks`` is prohibited.

A dependency graph also carries default rules, which say what applies to an action a
license is silent about.  ``--graph`` runs the sweep under one of the graphs that ship
instead of the core one, which is how the effect of a jurisdiction proposal is measured
before anybody adopts it; ``--all-graphs`` runs it under each of them in turn and prints
what each adds.  Only the core graph is a baseline: a jurisdiction graph holds proposals
and is expected to report more.

Usage
-----
    python scripts/review/consistency_sweep.py            # human-readable report
    python scripts/review/consistency_sweep.py --json     # machine-readable
    python scripts/review/consistency_sweep.py --expected DataExplorationLicence,DeveloperLicense
    python scripts/review/consistency_sweep.py --graph dg_eu
    python scripts/review/consistency_sweep.py --all-graphs

Exit status is 0 when the set of conflicting records equals ``--expected``, 1 otherwise.
``--all-graphs`` reports and always exits 0 for the jurisdiction graphs, because a
proposal that changes nothing would not be worth proposing.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licensedata" / "licenses"
DEPENDENCY_FILE = REPO_ROOT / "licensedata" / "dependencygraph" / "dg_default.ttl"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dalicc_check.consistency import (  # noqa: E402
    consistency_check,
    default_statements,
    rules_from_triples,
)

#: The two evaluation licences the review confirmed as faithful, not as modelling errors.
DEFAULT_EXPECTED = ("DataExplorationLicence", "DeveloperLicense")

LOG = logging.getLogger("consistency_sweep")


#: Every dependency graph that ships, the core one first.  The seven others are complete
#: graphs generated from the core one and a difference file each, and add the default
#: rules proposed for one market.
SHIPPED_GRAPHS = ("dg_default", "dg_eu", "dg_us", "dg_cn", "dg_gb", "dg_jp", "dg_in", "dg_br")


def graph_file(graph_id: str = "dg_default") -> Path:
    """Where one shipped graph lives."""
    return REPO_ROOT / "licensedata" / "dependencygraph" / f"{graph_id}.ttl"


def dependency_relations(path: Path = DEPENDENCY_FILE) -> list[tuple[str, str, str]]:
    """Read the statements of one graph from the data, with no triple store involved.

    Every shipped graph is complete, so one file is read and no link is followed,
    exactly as the service and the reasoner read it.
    """
    if not path.is_file():
        LOG.warning("No dependency graph available at %s", path)
        return []
    graph = Graph()
    graph.parse(path.as_posix(), format="turtle")
    return [(str(s), str(p), str(o)) for s, p, o in graph]


def records(licenses_dir: Path) -> list[tuple[str, Graph]]:
    """Every record, parsed once.  Reading the library is what the sweep costs."""
    out: list[tuple[str, Graph]] = []
    for path in sorted(licenses_dir.glob("*.ttl")):
        graph = Graph()
        graph.parse(path.as_posix(), format="turtle")
        out.append((path.stem, graph))
    return out


def sweep(
    licenses_dir: Path,
    graph_id: str = "dg_default",
    parsed: list[tuple[str, Graph]] | None = None,
) -> dict[str, list[dict]]:
    """Return the conflicts of every record, keyed by license identifier."""
    triples = dependency_relations(graph_file(graph_id))
    rules = rules_from_triples(triples)
    LOG.info(
        "%s: %d statements, %d default rule(s)", graph_id, len(triples), len(rules)
    )
    return {
        name: [conflict.as_dict() for conflict in consistency_check(graph, triples)]
        for name, graph in (parsed if parsed is not None else records(licenses_dir))
    }


def defaults_sweep(
    licenses_dir: Path,
    graph_id: str,
    parsed: list[tuple[str, Graph]] | None = None,
) -> dict[str, int]:
    """How many derived statements and findings each record gets under one graph."""
    triples = dependency_relations(graph_file(graph_id))
    return {
        name: len(default_statements(graph, triples))
        for name, graph in (parsed if parsed is not None else records(licenses_dir))
    }


def main(argv: list[str] | None = None) -> int:
    """Run the sweep and compare it with the expected set of conflicting records."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument(
        "--graph", default="dg_default", help="the shipped dependency graph to reason with"
    )
    parser.add_argument(
        "--all-graphs",
        action="store_true",
        help="run the sweep under every shipped graph and report what each one adds",
    )
    parser.add_argument(
        "--expected",
        default=",".join(DEFAULT_EXPECTED),
        help="comma-separated identifiers allowed to conflict (empty string: none)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.all_graphs:
        return _report_every_graph()

    result = sweep(LICENSES_DIR, args.graph)
    conflicting = {name: conflicts for name, conflicts in result.items() if conflicts}
    expected = {name for name in args.expected.split(",") if name}

    if args.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        LOG.info("records checked: %d", len(result))
        LOG.info("records with at least one conflict: %d", len(conflicting))
        for name, conflicts in sorted(conflicting.items()):
            for conflict in conflicts:
                LOG.info("  %s [%s] %s", name, conflict["kind"], conflict["reason"])

    if args.graph != "dg_default":
        LOG.info("a jurisdiction graph holds proposals, so its result is a report only")
        return 0

    unexpected = sorted(set(conflicting) - expected)
    missing = sorted(expected - set(conflicting))
    for name in unexpected:
        LOG.error("unexpected conflict in %s", name)
    for name in missing:
        LOG.error("expected a conflict in %s and found none", name)
    return 1 if unexpected or missing else 0


def _report_every_graph() -> int:
    """Print, per shipped graph, how much it adds to the core reading."""
    parsed = records(LICENSES_DIR)
    baseline = sweep(LICENSES_DIR, "dg_default", parsed)
    base_conflicts = {name for name, conflicts in baseline.items() if conflicts}
    for graph_id in SHIPPED_GRAPHS:
        result = (
            baseline if graph_id == "dg_default" else sweep(LICENSES_DIR, graph_id, parsed)
        )
        conflicting = {name for name, conflicts in result.items() if conflicts}
        derived = defaults_sweep(LICENSES_DIR, graph_id, parsed)
        LOG.info(
            "%s: %d record(s) with a conflict (%d more than the core graph), "
            "%d derived statement(s) over %d record(s)",
            graph_id,
            len(conflicting),
            len(conflicting - base_conflicts),
            sum(derived.values()),
            len([name for name, count in derived.items() if count]),
        )
        for name in sorted(conflicting - base_conflicts):
            for conflict in result[name]:
                LOG.info("    %s [%s] %s", name, conflict["kind"], conflict["reason"][:110])
    return 0


if __name__ == "__main__":
    sys.exit(main())
