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

Usage
-----
    python scripts/review/consistency_sweep.py            # human-readable report
    python scripts/review/consistency_sweep.py --json     # machine-readable
    python scripts/review/consistency_sweep.py --expected DataExplorationLicence,DeveloperLicense

Exit status is 0 when the set of conflicting records equals ``--expected``, 1 otherwise.
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

from dalicc_check.consistency import consistency_check  # noqa: E402

#: The two evaluation licences the review confirmed as faithful, not as modelling errors.
DEFAULT_EXPECTED = ("DataExplorationLicence", "DeveloperLicense")

LOG = logging.getLogger("consistency_sweep")


def dependency_relations(path: Path = DEPENDENCY_FILE) -> list[tuple[str, str, str]]:
    """Read the dependency-graph axioms from the data, with no triple store involved."""
    if not path.is_file():
        LOG.warning("No dependency graph available at %s", path)
        return []
    graph = Graph()
    graph.parse(path.as_posix(), format="turtle")
    return [(str(s), str(p), str(o)) for s, p, o in graph]


def sweep(licenses_dir: Path) -> dict[str, list[dict]]:
    """Return the conflicts of every record, keyed by license identifier."""
    triples = dependency_relations()
    LOG.info("dependency graph: %d axioms", len(triples))
    result: dict[str, list[dict]] = {}
    for path in sorted(licenses_dir.glob("*.ttl")):
        graph = Graph()
        graph.parse(path.as_posix(), format="turtle")
        result[path.stem] = [conflict.as_dict() for conflict in consistency_check(graph, triples)]
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the sweep and compare it with the expected set of conflicting records."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument(
        "--expected",
        default=",".join(DEFAULT_EXPECTED),
        help="comma-separated identifiers allowed to conflict (empty string: none)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = sweep(LICENSES_DIR)
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

    unexpected = sorted(set(conflicting) - expected)
    missing = sorted(expected - set(conflicting))
    for name in unexpected:
        LOG.error("unexpected conflict in %s", name)
    for name in missing:
        LOG.error("expected a conflict in %s and found none", name)
    return 1 if unexpected or missing else 0


if __name__ == "__main__":
    sys.exit(main())
