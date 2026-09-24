# The license data and its terms

Part of the [documentation index](../README.md#documentation). Everything DALICC knows
about licenses, as files, for anyone editing or redistributing the data.

The data is published under the **Creative Commons Attribution 4.0 International** licence
(CC BY 4.0). The legal code is in [LICENSE](LICENSE); a plain summary is at
<https://creativecommons.org/licenses/by/4.0/>. The code that builds, validates and loads
it, in `scripts/`, is AGPL-3.0-only like the rest of the repository. The full picture is in
[LICENSING.md](../LICENSING.md).

Nothing on this page is legal advice.

## Layout

| Path | What it holds |
|---|---|
| `licenses/` | 581 license records, one Turtle file per license. The source of truth |
| `reviews/` | 581 review records, one YAML file per license. See [reviews/README.md](reviews/README.md) |
| `licenselibrary/licenselibrary.ttl` | the combined document, generated from `licenses/` by `scripts/build_licenselibrary.py`. Never edited by hand |
| `dependencygraph/` | the eight shipped dependency graphs: `dg_default.ttl`, the 46 axioms and the adopted default rule the reasoner works from, and the seven jurisdiction graphs `dg_eu`, `dg_us`, `dg_cn`, `dg_gb`, `dg_jp`, `dg_in` and `dg_br`, each generated from it and a difference file in `differences/` |
| `vocabulary/dalicc-ns.ttl` | the `https://dalicc.net/ns#` vocabulary, plus `usage-counts.json` |
| `history/licenses/<id>/` | the archived versions of one record, `v1.ttl` up to the version before the current one, and a `changelog.yaml` with one entry per version from 2 upwards |
| `history/dependencygraph/`, `history/vocabulary/` | the same archive for the eight graphs (`dg_<id>-v<n>.ttl` and a change log each) and the vocabulary |
| `releases/<data-id>.json` | the manifest of each registered data release: the version and content hash of every record, graph and the vocabulary, written by `scripts/build_release_manifest.py` when a release is cut. None is registered yet |
| `spdx-mapping.json` | the SPDX identifier lookup table, generated from the records by `scripts/review/build_spdx_mapping.py` |
| `deprecated/` | superseded files, kept for reference and never loaded |

Every `.ttl` that is loaded into the triple store has a `.ttl.graph` sidecar naming the
named graph it belongs to. `scripts/load_data.sh` reads those.

[docs/DATA.md](../docs/DATA.md) is the reference: the namespaces, the shape of one record,
ports and variants, the action vocabulary, the census, the versioning rules, and how to
load, export and validate. This page does not repeat it.

## Editing the data

`licenses/*.ttl` is authoritative and `licenselibrary.ttl` is generated, so a change to a
record is followed by a rebuild and a validation run:

```bash
python scripts/build_licenselibrary.py      # rebuild licenselibrary.ttl from licenses/*.ttl
python scripts/validate_data.py             # the gate: parses, compares, checks conventions
scripts/load_data.sh --clear                # reload a running stack
```

`validate_data.py` proves that the per-license files and the combined library agree triple
for triple, that every record still carries `dct:title`, `odrl:target`, `odrl:permission`
and `cc:jurisdiction`, that every `odrl:action` comes from ODRL, Creative Commons or the
DALICC vocabulary, that every record has a review file and every review file a record, and
that the encoding conventions hold. A new `dalicc:` term has to be defined in
`vocabulary/dalicc-ns.ttl` first, or the validator warns about an undefined term.

Never delete a license record, never change a license id or IRI, and never edit
`licenselibrary/licenselibrary.ttl` by hand. Keep files UTF-8 without a BOM, with LF line
endings and a final newline.

## Attribution

When you redistribute this data or build on it, credit it as:

```
DALICC License Library, DALICC - Verein zur Förderung der Rechtssicherheit in der
Datenbewirtschaftung, https://dalicc.net, CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/)
```

The licence is declared inside the data as well: every license record carries
`cc:license dalicclib:CC-BY-4.0`, and the vocabulary carries
`dct:license <http://creativecommons.org/licenses/by/4.0/>` on the ontology resource. The
RDF statements and this file have to stay in agreement.

## What CC BY 4.0 covers here

It covers DALICC's description of a license, not the license being described. The record
for Apache-2.0 is a machine-readable model of that license; it grants no rights in the
Apache license text, and using the record is not the same as complying with the license it
models. Where a record links to the original legal code (`cc:legalcode`, `dct:source`),
that text belongs to its publisher.
