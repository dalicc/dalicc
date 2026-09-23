#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Generate ``licensedata/spdx-mapping.json`` from the license records.

The 2026-09-15 review added an SPDX identifier to every record whose license the SPDX
license list actually defines, and invented none.  This script turns those
``spdx:licenseId`` statements into a small lookup table so that SPDX-based tooling can
be pointed at a DALICC record and back:

``dalicc_to_spdx``
    DALICC identifier to SPDX identifier, one entry per record that has one.
``spdx_to_dalicc``
    the reverse index.  The value is a list, because two DALICC records can carry the
    same SPDX id (the Canadian government pair publishes one text under two institutions).
``aliases``
    the identifiers the SPDX license list has deprecated, and the ``+`` forms, mapped onto
    the identifier that replaced them.  GitHub and most package managers still report
    ``GPL-2.0`` and ``GPL-2.0+`` for the GNU licenses, so a lookup for either of them has
    to reach the record of ``GPL-2.0-only`` and ``GPL-2.0-or-later``.  The table is
    hand-kept here rather than derived from the SPDX list, so that the build needs no
    network and no vendored copy of ``licenses.json``; the 35 rows are the
    ``isDeprecatedLicenseId`` entries of SPDX 3.29.0 plus the ``+`` forms.  A row whose
    current identifier no record carries stays in the table and resolves to nothing.

The file is generated, never edited by hand; ``tests/unit/test_data_review.py`` proves
that it still agrees with the records.

Usage
-----
    python scripts/review/build_spdx_mapping.py            # write the file
    python scripts/review/build_spdx_mapping.py --check    # exit 1 if it is out of date
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import logging
from pathlib import Path
import sys

import rdflib
from rdflib.namespace import RDF, Namespace

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licensedata" / "licenses"
MAPPING_FILE = REPO_ROOT / "licensedata" / "spdx-mapping.json"

ODRL = Namespace("http://www.w3.org/ns/odrl/2/")
DALICCLIB = Namespace("https://dalicc.net/licenselibrary/")
SPDX_LICENSE_ID = rdflib.URIRef("http://spdx.org/rdf/terms#licenseId")

LOG = logging.getLogger("build_spdx_mapping")

#: Deprecated SPDX identifier (or ``+`` form) -> the identifier that replaced it.
#: Taken from the ``isDeprecatedLicenseId`` entries of SPDX license list 3.29.0 and from
#: the ``+`` suffix form, which SPDX replaced by the ``-or-later`` identifiers.  Two rows
#: map onto themselves, ``Nunit`` and ``eCos-2.0``, because SPDX deprecated them without
#: naming a successor; they are kept so that the table is the whole set.
DEPRECATED_ALIASES = {
    "AGPL-1.0": "AGPL-1.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
    "BSD-2-Clause-FreeBSD": "BSD-2-Clause",
    "BSD-2-Clause-NetBSD": "BSD-2-Clause",
    "GFDL-1.1": "GFDL-1.1-only",
    "GFDL-1.1+": "GFDL-1.1-or-later",
    "GFDL-1.2": "GFDL-1.2-only",
    "GFDL-1.2+": "GFDL-1.2-or-later",
    "GFDL-1.3": "GFDL-1.3-only",
    "GFDL-1.3+": "GFDL-1.3-or-later",
    "GPL-1.0": "GPL-1.0-only",
    "GPL-1.0+": "GPL-1.0-or-later",
    "GPL-2.0": "GPL-2.0-only",
    "GPL-2.0+": "GPL-2.0-or-later",
    "GPL-2.0-with-GCC-exception": "GPL-2.0-only WITH GCC-exception-2.0",
    "GPL-2.0-with-autoconf-exception": "GPL-2.0-only WITH Autoconf-exception-2.0",
    "GPL-2.0-with-bison-exception": "GPL-2.0-only WITH Bison-exception-2.2",
    "GPL-2.0-with-classpath-exception": "GPL-2.0-only WITH Classpath-exception-2.0",
    "GPL-2.0-with-font-exception": "GPL-2.0-only WITH Font-exception-2.0",
    "GPL-3.0": "GPL-3.0-only",
    "GPL-3.0+": "GPL-3.0-or-later",
    "GPL-3.0-with-GCC-exception": "GPL-3.0-only WITH GCC-exception-3.1",
    "GPL-3.0-with-autoconf-exception": "GPL-3.0-only WITH Autoconf-exception-3.0",
    "LGPL-2.0": "LGPL-2.0-only",
    "LGPL-2.0+": "LGPL-2.0-or-later",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-2.1+": "LGPL-2.1-or-later",
    "LGPL-3.0": "LGPL-3.0-only",
    "LGPL-3.0+": "LGPL-3.0-or-later",
    "Net-SNMP": "Net-SNMP-1.0",
    "Nunit": "Nunit",
    "StandardML-NJ": "SMLNJ",
    "bzip2-1.0.5": "bzip2-1.0.6",
    "eCos-2.0": "eCos-2.0",
    "wxWindows": "WXwindows",
}


def build(licenses_dir: Path) -> dict[str, object]:
    """Read every record and return the mapping payload."""
    forward: dict[str, str] = {}
    reverse: dict[str, list[str]] = defaultdict(list)
    total = 0
    for path in sorted(licenses_dir.glob("*.ttl")):
        total += 1
        graph = rdflib.Graph()
        graph.parse(path.as_posix(), format="turtle")
        subject = next(iter(graph.subjects(RDF.type, ODRL.Set)), None)
        if subject is None:
            continue
        identifiers = sorted(str(value) for value in graph.objects(subject, SPDX_LICENSE_ID))
        if not identifiers:
            continue
        if len(identifiers) > 1:
            LOG.warning("%s carries %d SPDX ids: %s", path.stem, len(identifiers), identifiers)
        local_name = str(subject)[len(str(DALICCLIB)):]
        forward[local_name] = identifiers[0]
        reverse[identifiers[0]].append(local_name)

    aliases = dict(sorted(DEPRECATED_ALIASES.items()))
    resolvable = sum(1 for current in aliases.values() if current in reverse)
    payload: dict[str, object] = {
        "comment": (
            "Generated by scripts/review/build_spdx_mapping.py. Do not edit by hand. "
            "dalicc_to_spdx maps a DALICC license identifier to the SPDX license list "
            "identifier the record carries in spdx:licenseId; spdx_to_dalicc is the "
            "reverse index and its values are lists because one SPDX id can describe "
            "more than one DALICC record; aliases maps a deprecated SPDX identifier, or "
            "a plus form such as GPL-2.0+, onto the identifier that replaced it, so that "
            "a lookup for what GitHub and the package managers still report reaches the "
            "record of the current identifier."
        ),
        "license_total": total,
        "mapped": len(forward),
        "aliases": aliases,
        "aliases_resolvable": resolvable,
        "dalicc_to_spdx": dict(sorted(forward.items())),
        "spdx_to_dalicc": {key: sorted(value) for key, value in sorted(reverse.items())},
    }
    LOG.info("%d of %d records carry an SPDX identifier (%d distinct ids)",
             len(forward), total, len(reverse))
    LOG.info("%d aliases, %d of them resolving to a record", len(aliases), resolvable)
    return payload


def main(argv: list[str] | None = None) -> int:
    """Write or check ``licensedata/spdx-mapping.json``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 if stale")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    serialised = json.dumps(build(LICENSES_DIR), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        current = MAPPING_FILE.read_text(encoding="utf-8") if MAPPING_FILE.exists() else None
        if current == serialised:
            LOG.info("%s is up to date", MAPPING_FILE.name)
            return 0
        LOG.error("%s is OUT OF DATE (run: python scripts/review/build_spdx_mapping.py)",
                  MAPPING_FILE.name)
        return 1

    MAPPING_FILE.write_text(serialised, encoding="utf-8", newline="")
    LOG.info("wrote %s", MAPPING_FILE.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
