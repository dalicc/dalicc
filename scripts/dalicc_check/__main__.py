# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Check one license record offline, the way the data gate and the API read it.

Run from the root of a checkout of https://github.com/dalicc/dalicc, with ``scripts/``
on the module path::

    PYTHONPATH=scripts python -m dalicc_check licensedata/licenses/MIT.ttl
    PYTHONPATH=scripts python -m dalicc_check my-draft.ttl --graph dg_eu
    PYTHONPATH=scripts python -m dalicc_check MIT Apache-2.0 --json
    PYTHONPATH=scripts python -m dalicc_check --release

A record is a Turtle file, or the identifier of a record of the library, which names
``licensedata/licenses/<id>.ttl``.  Each record goes through four checks, and nothing
needs a network, a triple store or the reasoner:

1.  it parses as Turtle and holds exactly one ``odrl:Set``;
2.  every ``dalicc:`` term it uses is defined in ``licensedata/vocabulary/dalicc-ns.ttl``,
    every ``odrl:action`` comes from ODRL, Creative Commons or that vocabulary, and a
    deprecated term is named with its replacement;
3.  the consistency rule set of ``POST /licenselibrary/consistencycheck`` finds no
    conflict, under the dependency graph ``--graph`` (``dg_default`` unless told);
4.  the family rules of ``scripts/review/family_rules.py`` that apply to it hold.  They
    compare records of one family, so they run over the library with this record in
    it, in place of the library's own copy when there is one.  Rule 14 is reported and
    not counted, as in ``make family-rules``.

Then it prints the record's content hash, computed exactly as the API computes
``content_hash`` of ``https://api.dalicc.net/v2/licenses/<id>``, and says whether the
library's own copy of the record hashes the same.

``--release`` prints the release identifier of the checkout and its three parts
(``data-``, ``lib-``, ``dg-``, ``ns-``), as ``scripts/build_release_manifest.py``
computes them, without writing a manifest.

Exit status: 0 when every record passes, 1 when a check fails, 2 when a record cannot
be found.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "review"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from rdflib import Graph, Literal, URIRef  # noqa: E402
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS  # noqa: E402

from dalicc_check import c14n, consistency  # noqa: E402

LICENSEDATA = REPO_ROOT / "licensedata"
LICENSES_DIR = LICENSEDATA / "licenses"
VOCABULARY_FILE = LICENSEDATA / "vocabulary" / "dalicc-ns.ttl"
GRAPHS_DIR = LICENSEDATA / "dependencygraph"

LICENSE_BASE = "https://dalicc.net/licenselibrary/"
API_RECORD = "https://api.dalicc.net/v2/licenses/"
DALICC_NS = "https://dalicc.net/ns#"
LEGACY_DALICC_NS = "http://dalicc.net/ns#"
ODRL_NS = "http://www.w3.org/ns/odrl/2/"
CC_NS = "http://creativecommons.org/ns#"
ODRL_SET = URIRef(ODRL_NS + "Set")
ODRL_ACTION = URIRef(ODRL_NS + "action")
ODRL_ACTION_CLASS = URIRef(ODRL_NS + "Action")


class RecordMissing(Exception):
    """A record named on the command line is neither a file nor a library identifier."""


# ---------------------------------------------------------------------------
# the four checks
# ---------------------------------------------------------------------------


def locate(name: str) -> Path:
    """The file a command-line argument names: a path, or a library identifier."""
    path = Path(name)
    if path.is_file():
        return path
    by_id = LICENSES_DIR / f"{name}.ttl"
    if "/" not in name and by_id.is_file():
        return by_id
    raise RecordMissing(f"{name} is neither a file nor the identifier of a library record")


def record_subject(graph: Graph, stem: str) -> tuple[URIRef | None, list[str]]:
    """The one ``odrl:Set`` of a record, and what is wrong when there is not one."""
    sets = sorted(
        (node for node in graph.subjects(RDF.type, ODRL_SET) if isinstance(node, URIRef)),
        key=str,
    )
    if not sets:
        return None, ["the file holds no odrl:Set, so it is not a license record"]
    if len(sets) > 1:
        preferred = URIRef(LICENSE_BASE + stem)
        chosen = preferred if preferred in sets else sets[0]
        return chosen, [
            f"the file holds {len(sets)} odrl:Set documents; a record is one, and "
            f"{chosen} is the one checked"
        ]
    return sets[0], []


def record_id(subject: URIRef, stem: str) -> str:
    """The identifier of a record: the end of its address, or else the file name."""
    text = str(subject)
    return text[len(LICENSE_BASE):] if text.startswith(LICENSE_BASE) else stem


def stated_version(graph: Graph, subject: URIRef) -> int | None:
    """``dct:hasVersion`` of the record, when it states a whole number from 1 up."""
    for value in graph.objects(subject, DCTERMS.hasVersion):
        text = str(value).strip()
        if text.isdigit() and int(text) >= 1:
            return int(text)
    return None


def vocabulary_problems(graph: Graph, vocabulary: Graph) -> tuple[list[str], list[str], int]:
    """``(errors, warnings, DALICC terms used)`` of one record against the vocabulary.

    The same reading as the data gate (``scripts/validate_data.py``): a ``dalicc:`` IRI
    has to be a defined term, an action has to be one of the vocabulary's actions or come
    from ODRL or Creative Commons, the ``http://`` spelling of the namespace is refused,
    and a deprecated term is allowed but named with what replaces it.
    """
    defined = {str(s) for s in vocabulary.subjects(RDFS.isDefinedBy, URIRef(DALICC_NS))}
    actions = {str(s) for s in vocabulary.subjects(RDF.type, ODRL_ACTION_CLASS)}
    deprecated = {str(s) for s in vocabulary.subjects(OWL.deprecated, Literal(True))}
    errors: list[str] = []
    warnings: list[str] = []
    used: set[str] = set()
    for triple in graph:
        for node in triple:
            if not isinstance(node, URIRef):
                continue
            text = str(node)
            if text.startswith(LEGACY_DALICC_NS):
                errors.append(f"<{text}> uses the retired http:// spelling of the namespace")
            elif text.startswith(DALICC_NS) and text != DALICC_NS:
                used.add(text)
    for term in sorted(used - defined):
        errors.append(f"<{term}> is not defined in {VOCABULARY_FILE.name}")
    for action in sorted({str(o) for o in graph.objects(None, ODRL_ACTION)}):
        if action in actions or action.startswith(DALICC_NS):
            continue  # a DALICC term that is not defined is reported above
        if not action.startswith((ODRL_NS, CC_NS)):
            errors.append(
                f"the action <{action}> is outside the ODRL, Creative Commons and DALICC "
                "action vocabularies"
            )
    for term in sorted(used & deprecated):
        replacement = next(
            (str(o) for o in vocabulary.objects(URIRef(term), DCTERMS.isReplacedBy)), ""
        )
        warnings.append(
            f"<{term}> is deprecated" + (f"; use <{replacement}> instead" if replacement else "")
        )
    return errors, warnings, len(used)


def dependency_triples(graph_id: str) -> list[tuple[str, str, str]]:
    """Every statement of one shipped dependency graph, read from its file."""
    path = GRAPHS_DIR / f"{graph_id}.ttl"
    if not path.is_file():
        raise RecordMissing(f"no dependency graph {graph_id} in {GRAPHS_DIR}")
    graph = Graph()
    graph.parse(path.as_posix(), format="turtle")
    return [(str(s), str(p), str(o)) for s, p, o in graph]


def library_records() -> list:
    """Every record of the library, in the shape the family rules read."""
    import family_rules

    return [family_rules.load(path) for path in sorted(LICENSES_DIR.glob("*.ttl"))]


def family_results(path: Path, identifier: str, library: list) -> list[dict[str, Any]]:
    """The family rules that apply to one record, run over the library with it in.

    A rule applies when it checks one more or one fewer record with this one in the
    library than without it, or when it names this record as breaking it.
    """
    import family_rules

    record = family_rules.load(path)
    record.identifier = identifier
    others = [item for item in library if item.identifier != identifier]
    without = {entry["rule"]: entry for entry in family_rules.rules(others)}
    out = []
    for entry in family_rules.rules([*others, record]):
        named = [
            offender for offender in entry["offenders"]
            if offender == identifier or offender.startswith(identifier + " ")
        ]
        before = without.get(entry["rule"], {"checked": 0})
        if not named and entry["checked"] == before["checked"]:
            continue
        counted = entry["rule"] not in family_rules.DEFAULT_SKIPPED
        out.append({
            "rule": entry["rule"],
            "title": entry["title"],
            "expectation": entry["expectation"],
            "holds": not named,
            "counted": counted,
            "violations": named,
        })
    return out


def check_record(
    name: str,
    *,
    graph_id: str,
    vocabulary: Graph,
    triples: list[tuple[str, str, str]],
    library: list | None,
) -> dict[str, Any]:
    """Run the four checks and the hash over one record; the result as a dictionary."""
    path = locate(name)
    result: dict[str, Any] = {"file": path.as_posix(), "errors": [], "warnings": []}
    graph = Graph()
    try:
        graph.parse(path.as_posix(), format="turtle")
    except Exception as exc:  # rdflib raises several unrelated types for bad Turtle
        result["errors"].append(f"the file does not parse as Turtle: {exc}")
        result["ok"] = False
        return result
    result["triples"] = len(graph)

    subject, problems = record_subject(graph, path.stem)
    if subject is None:
        result["errors"].extend(problems)
        result["ok"] = False
        return result
    result["warnings"].extend(problems)
    identifier = record_id(subject, path.stem)
    result.update(id=identifier, subject=str(subject), version=stated_version(graph, subject))

    errors, warnings, used = vocabulary_problems(graph, vocabulary)
    result["vocabulary"] = {"terms": used, "errors": errors, "warnings": warnings}
    result["errors"].extend(errors)
    result["warnings"].extend(warnings)

    conflicts = [conflict.as_dict() for conflict in consistency.consistency_check(graph, triples)]
    result["consistency"] = {"graph": graph_id, "conflicts": conflicts}
    result["errors"].extend(f"{c['kind']}: {c['reason']}" for c in conflicts)

    if library is not None:
        rules = family_results(path, identifier, library)
        result["family_rules"] = rules
        for rule in rules:
            for offender in rule["violations"]:
                line = f"family rule {rule['rule']} ({rule['title']}): {offender}"
                (result["errors"] if rule["counted"] else result["warnings"]).append(
                    line if rule["counted"] else line + ", reported and not counted"
                )

    digest = c14n.content_hash(c14n.record_closure(graph, subject))
    result["content_hash"] = digest
    result["hash_algorithm"] = c14n.ALGORITHM
    own = LICENSES_DIR / f"{identifier}.ttl"
    if own.is_file() and own.resolve() != path.resolve():
        copy = Graph()
        copy.parse(own.as_posix(), format="turtle")
        copy_subject = URIRef(LICENSE_BASE + identifier)
        copy_hash = c14n.content_hash(c14n.record_closure(copy, copy_subject))
        result["library"] = {
            "file": own.relative_to(REPO_ROOT).as_posix(),
            "version": stated_version(copy, copy_subject),
            "content_hash": copy_hash,
            "same": copy_hash == digest,
        }
    elif own.is_file():
        result["library"] = {
            "file": own.relative_to(REPO_ROOT).as_posix(),
            "version": result["version"],
            "content_hash": digest,
            "same": True,
        }
    else:
        result["library"] = None
    result["api"] = API_RECORD + identifier
    result["ok"] = not result["errors"]
    return result


# ---------------------------------------------------------------------------
# the release identifier
# ---------------------------------------------------------------------------


def release_ids() -> dict[str, str]:
    """The four identifiers of the data in this checkout, as the manifest script names them."""
    import build_release_manifest

    manifest = build_release_manifest.build(LICENSEDATA, application_version="", date="")
    return {
        "release": manifest["release"],
        "library": manifest["library"]["id"],
        "graphs": manifest["graphs"]["id"],
        "vocabulary": manifest["vocabulary"]["id"],
    }


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def _text(result: dict[str, Any]) -> str:
    lines = [result["file"]]
    if "id" not in result:
        lines += [f"  error         {line}" for line in result["errors"]]
        lines.append("  result        FAILED")
        return "\n".join(lines)
    version = f", version {result['version']}" if result["version"] else ", no dct:hasVersion"
    lines.append(f"  record        {result['subject']}{version}")
    lines.append(f"  parse         ok, {result['triples']} triples")
    vocabulary = result["vocabulary"]
    lines.append(
        f"  vocabulary    {'ok' if not vocabulary['errors'] else 'FAILED'}, "
        f"{vocabulary['terms']} DALICC terms used"
    )
    conflicts = result["consistency"]["conflicts"]
    lines.append(
        f"  consistency   {'ok' if not conflicts else 'FAILED'} under "
        f"{result['consistency']['graph']}"
        + (f", {len(conflicts)} conflict(s)" if conflicts else "")
    )
    if "family_rules" in result:
        rules = result["family_rules"]
        broken = [rule["rule"] for rule in rules if not rule["holds"]]
        holding = [rule["rule"] for rule in rules if rule["holds"]]
        summary = f"{len(rules)} apply"
        if holding:
            summary += f", holding: {', '.join(holding)}"
        if broken:
            summary += f", broken: {', '.join(broken)}"
        lines.append(f"  family rules  {summary}")
    lines.append(f"  content hash  {result['content_hash']} ({result['hash_algorithm']})")
    library = result["library"]
    if library is None:
        lines.append("                not a record of this library")
    elif library["same"]:
        version = f", version {library['version']}" if library["version"] else ""
        lines.append(f"                the same as {library['file']}{version}")
    else:
        version = f" version {library['version']}" if library["version"] else ""
        lines.append(
            f"                differs from {library['file']}{version}: "
            f"{library['content_hash']}"
        )
    if library is not None:
        lines.append(f"                compare with content_hash of {result['api']}")
    lines += [f"  error         {line}" for line in result["errors"]]
    lines += [f"  warning       {line}" for line in result["warnings"]]
    lines.append(f"  result        {'ok' if result['ok'] else 'FAILED'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dalicc_check",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "records",
        nargs="*",
        metavar="RECORD",
        help="a Turtle file, or the identifier of a record of the library",
    )
    parser.add_argument(
        "--graph",
        default="dg_default",
        help="the shipped dependency graph the consistency check reads (default: dg_default)",
    )
    parser.add_argument(
        "--no-family-rules",
        action="store_true",
        help="leave out the family rules, which read the whole library",
    )
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    parser.add_argument(
        "--release",
        action="store_true",
        help="print the release identifier of this checkout and its three parts",
    )
    args = parser.parse_args(argv)

    if args.release:
        ids = release_ids()
        if args.json:
            sys.stdout.write(json.dumps(ids, indent=2) + "\n")
        else:
            sys.stdout.write("".join(f"{key:<11}{value}\n" for key, value in ids.items()))
        if not args.records:
            return 0
    if not args.records:
        parser.error("name at least one record, or pass --release")

    try:
        triples = dependency_triples(args.graph)
    except RecordMissing as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    vocabulary = Graph()
    vocabulary.parse(VOCABULARY_FILE.as_posix(), format="turtle")
    library = None if args.no_family_rules else library_records()

    results = []
    for name in args.records:
        try:
            results.append(
                check_record(
                    name,
                    graph_id=args.graph,
                    vocabulary=vocabulary,
                    triples=triples,
                    library=library,
                )
            )
        except RecordMissing as exc:
            sys.stderr.write(f"{exc}\n")
            return 2

    if args.json:
        sys.stdout.write(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write("\n\n".join(_text(result) for result in results) + "\n")
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
