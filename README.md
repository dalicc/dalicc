# DALICC

DALICC (Data Licenses Clearance Center) makes software and data licenses machine
readable so that rights clearance can be automated. A license is modelled as an ODRL
policy over a controlled vocabulary of actions, and a reasoner decides from those models
whether a bundle of licenses can be combined.

This repository holds the part of DALICC that is useful on its own: the license data, the
reasoning service that works on it, and the tooling that keeps both checkable. The API
service and the website that run on top of them are developed privately for the moment.

## What is here

`licensedata/` is the library. 581 license records as Turtle, one file per record, each
with a review record beside it that says how it was checked against the legal text it
models. 290 of the records are jurisdiction ports, translations or editions of another
record and say so in the data, so the library describes 291 distinct licenses. The
directory also holds the controlled vocabulary, at version 7, the eight deontic
dependency graphs the reasoner works from, the SPDX mapping, and the archived version of
every record that was ever superseded.

The core graph, `licensedata/dependencygraph/dg_default.ttl`, holds the 46 axioms that
relate one action to another and one adopted default rule, which says what applies to an
action a license is silent about. Seven jurisdiction graphs beside it, `dg_eu`, `dg_us`,
`dg_cn`, `dg_gb`, `dg_jp`, `dg_in` and `dg_br`, hold the default rules proposed for one
market each. Every rule in those seven is a proposal for the association's legal
reviewer, none of them is the default for any check, and nothing any of them states is
legal advice. docs/DATA.md describes the mechanism and docs/LICENSE_REVIEW.md lists every
rule with the statute or principle it rests on.

`reasoner/` is the answer-set-programming service that finds the conflicts. It reduces
each license in a request to statements about actions, including the duties attached to a
permission, runs them against the dependency graph with clingo, and reports which pairs
of statements cannot hold at once and why. It reads the graph's default rules too, so an
action the license is silent about is decided by the rule rather than left out, and every
conflict says which side came from the license text and which from a rule. It is a
FastAPI service with its own Dockerfile and its own test suite.

`scripts/` is the tooling. The validator is the gate the data has to pass, the consistency
sweep runs the rule set of the composer over every record, the family rules check that
licenses of one family are modelled the same way, and the rest build the derived files:
the combined library document, the SPDX mapping, the change logs and the version archive.
`scripts/load_data.sh` loads the data into a Virtuoso container if you want to serve it
yourself.

## Where the service runs

The API answers at <https://api.dalicc.net>, and its interactive documentation is at
<https://api.dalicc.net/docs>. The website that carries the user guide, the vocabulary
pages and the What's new page is being moved to this generation of the code; until that is
done <https://dalicc.net> redirects to the API documentation, and the vocabulary and the
dependency graph are readable as static pages at <https://dalicc.github.io>.

## Using the data

Every record has an identifier, and the identifier is the file name: `Apache-2.0` lives in
`licensedata/licenses/Apache-2.0.ttl` and is the subject
`https://dalicc.net/licenselibrary/Apache-2.0` inside it. Identifiers are never reused and
never renamed.

The records are Turtle. `licensedata/licenselibrary/licenselibrary.ttl` is the same data
as one document, generated from the per-record files, and it is what gets loaded into a
triple store; never edit it by hand. Each `.ttl` that is loaded carries a `.ttl.graph`
file beside it naming the named graph it belongs to. Over the API the same records come
back as JSON-LD, Turtle or RDF/XML.

`licensedata/spdx-mapping.json` maps between DALICC identifiers and SPDX ones in both
directions, and it carries aliases, so `GPL-2.0` and `GPL-2.0-only` both find the record
they mean. 276 of the 581 records carry an SPDX identifier; most of the rest are
jurisdiction ports that the SPDX license list does not define.

Every correction to a record is versioned. The superseded version is archived under
`licensedata/history/licenses/<id>/v<n>.ttl` with a `changelog.yaml` beside it that says
what changed, why and who decided it, and the record itself carries `dct:hasVersion`. The
dependency graph and the vocabulary are versioned the same way under
`licensedata/history/`.

If you redistribute the data or build on it, credit it as:

```
DALICC License Library, DALICC association, https://dalicc.net, CC BY 4.0
```

CC BY 4.0 covers the DALICC description of a license, not the license being described. The
record for Apache-2.0 is a model of that license; it grants no rights in the Apache
license text, and using the record is not the same as complying with the license it
models.

## Running the checks

You need Python 3.12 and the two packages in `requirements.txt`.

```bash
make venv
make validate        # the gate: parsing, the canonical comparison, the conventions
make canonical       # the combined document is what the per-record files produce
make sweep           # the consistency rule set over every record
make family-rules    # the family conventions over every record
```

`make check` runs all four, which is what the `data` workflow does on every push.
`make validate` proves that the per-record files and the combined document say the same
thing triple for triple, that every record carries the fields the model requires, that
every action comes from ODRL, Creative Commons or the DALICC vocabulary, and that every
record has a review record. It prints warnings for the known gaps, which docs/DATA.md
lists and explains.

## Running the reasoner

```bash
make reasoner-test
```

That builds a virtualenv under `reasoner/`, installs the solver and runs the reasoner's
own suite. The solver is installed with `--no-deps` on purpose: its packaging pins a
clingo version that has no wheel for this Python, and `reasoner/requirements.txt` pins the
versions it is actually run against instead. Without the solver the tests that need it
skip themselves and the rest still run. `reasoner/README.md` explains what the service
computes, which programs it runs and how it is configured, and `reasoner/Dockerfile`
builds it.

## If a record is wrong

The records are a reading of legal texts, and a reading can be wrong. Write to
<giray.havur@ustp.at> or <tassilo.pellegrini@ustp.at> with the identifier, what the record
says and what the text says. Once the site serves this generation of the code, each record
page will also carry a correction form that opens the same review queue.

Nothing in this repository is legal advice.

## The Python client

<https://github.com/dalicc/python-sdk> is the client for the API, under Apache-2.0. It is
a separate repository because a client that only talks to a public API has no reason to
carry the library or the service's terms with it.

## The static mirror

<https://dalicc.github.io> mirrors the vocabulary and the dependency graph as static
pages, generated from this data. The live pages may be newer.

## Documentation

| Document | What it covers |
|---|---|
| [docs/DATA.md](docs/DATA.md) | The data model: the namespaces, the shape of one record, ports and variants, the action vocabulary, the census, the versioning rules, and how to load, export and validate |
| [docs/LICENSE_REVIEW.md](docs/LICENSE_REVIEW.md) | The content review behind the current library: the method, the coverage, the family map, the library-wide decisions, the open questions |
| [licensedata/README.md](licensedata/README.md) | The data as files: what is in the directory, how it is built and validated, and the terms it is published under |
| [licensedata/reviews/README.md](licensedata/reviews/README.md) | The review records: one YAML file per license, holding the result of checking it against the legal text it models |
| [reasoner/README.md](reasoner/README.md) | The reasoner: what it computes, its programs and external atoms, its endpoints and its configuration |
| [LICENSING.md](LICENSING.md) | Who owns what and under which terms |
| [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) | The commercial licence the association offers as an alternative to the AGPL |

## Licensing

| Part | Licence |
|---|---|
| `licensedata/` | CC BY 4.0 |
| `reasoner/`, `scripts/`, `docs/` and everything else here | AGPL-3.0-only, with a commercial licence available from the association |
| the code this repository held until 2024, at the tag `release-2023` | MIT |

The full texts are in [LICENSE](LICENSE) and [licensedata/LICENSE](licensedata/LICENSE),
the overview in [LICENSING.md](LICENSING.md), and the commercial option in
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md). Nothing about the 2023 release is
withdrawn: it is still there, at the tag, under the MIT licence it was published with.

## The association

DALICC is run by DALICC - Verein zur Förderung der Rechtssicherheit in der
Datenbewirtschaftung (ZVR 1249185710), Campus-Platz 1, 3100 St. Pölten, Austria. It was
funded by the Austrian Research Promotion Agency (FFG) and by netidee. Write to
<tassilo.pellegrini@ustp.at> or <giray.havur@ustp.at>.
