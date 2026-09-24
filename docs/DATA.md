# DALICC data layer

The reference for `licensedata/`: what each directory and file holds, how a license record
is modelled, and how to add or change one. For anyone editing the data or the scripts that
build, validate, load and export it.

Part of the [documentation index](../README.md#documentation).

Contents: 1. what `licensedata/` holds; 2. the data model; 3. the two representations and
the validation gate; 4. model history and versioning; 5. loading into the triple store;
6. export, backup and restore; 7. encoding conventions; 8. known data-quality issues;
9. dependency graphs as data.

Nothing on this page is legal advice. The record-by-record review and the questions it left
open are in [LICENSE_REVIEW.md](LICENSE_REVIEW.md).

---

## 1. What `licensedata/` holds

```
licensedata/
├── licenses/                      581 × <id>.ttl     one file per license  (SOURCE OF TRUTH)
├── licenselibrary/
│   ├── licenselibrary.ttl                            all 581 licenses in one document (GENERATED)
│   └── licenselibrary.ttl.graph  → https://dalicc.net/licenselibrary/
├── dependencygraph/
│   ├── dg_default.ttl                                46 reasoning axioms + 1 default rule (version 2)
│   ├── dg_default.ttl.graph      → https://dalicc.net/dependencygraph/dg_default
│   ├── dg_eu|us|cn|gb|jp|in|br.ttl                   complete graph for one market each (version 2, GENERATED)
│   ├── dg_<id>.ttl.graph         → https://dalicc.net/dependencygraph/dg_<id>
│   └── differences/dg_<id>.ttl + README.md           what each adds, removes and replaces (source of truth)
├── vocabulary/
│   ├── dalicc-ns.ttl                                 the DALICC vocabulary, 142 terms (version 2)
│   ├── dalicc-ns.ttl.graph       → https://dalicc.net/ns
│   └── usage-counts.json                             how often each term is used (GENERATED)
├── history/                                          the model history; never loaded into the store
│   ├── licenses/<id>/v<n>.ttl                        each superseded version of a record
│   ├── licenses/<id>/changelog.yaml                  what every version changed, and why
│   ├── dependencygraph/dg_default-v<n>.ttl + changelog.yaml
│   ├── dependencygraph/dg_<id>-v<n>.ttl    + dg_<id>-changelog.yaml   the seven jurisdiction graphs
│   └── vocabulary/dalicc-ns-v<n>.ttl       + changelog.yaml
├── reviews/                       581 × <id>.yaml    the review record of one license
├── spdx-mapping.json              DALICC id ↔ SPDX id, both directions (GENERATED)
├── deprecated/                    pre-2023-04-24 identifiers and Drupal-era exports, never loaded
├── retired-identifiers.yaml       old id → successor for the 33 ids retired on 2023-04-24
├── LICENSE, README.md             the data is CC-BY-4.0; the README is its terms page
└── copy_ttls.sh                   deprecated shim → scripts/load_data.sh
```

`licenses/` and `reviews/` hold 581 files each, one pair per license, and
`scripts/validate_data.py` fails if either side has a file the other does not.

`history/`, `reviews/` and `spdx-mapping.json` are data *about* the data: they are not part
of the published RDF, are never bulk-loaded, and therefore have no `.graph` sidecar. The
review-record format is documented in
[`licensedata/reviews/README.md`](../licensedata/reviews/README.md).

Every `.ttl` that is bulk-loaded has a sibling `<file>.ttl.graph` holding exactly one
absolute IRI. That is the convention Virtuoso's `ld_dir()` loader uses to decide which named
graph a file belongs to. **Never add a loadable `.ttl` without its `.graph` file**;
`scripts/validate_data.py` fails the build if one is missing.

### Named graphs

| Graph IRI | Source | Read by |
|---|---|---|
| `https://dalicc.net/licenselibrary/` | `licenselibrary/licenselibrary.ttl` | `/licenselibrary/list`, `/licenselibrary/facetedsearch`, `/web/list`, `/web/searchresults` |
| `https://dalicc.net/dependencygraph/dg_default` | `dependencygraph/dg_default.ttl` | `/dependencygraph/list`, the reasoner, `/compatibilitycheck/` |
| `https://dalicc.net/ns` | `vocabulary/dalicc-ns.ttl` | the `/ns` vocabulary page; content negotiation on `dalicc:` terms |
| `https://dalicc.net/customlicenses/` | **runtime only**, written when a license is published | `/licenselibrary/license/{id}` fallback for composed licenses |
| `https://dalicc.net/users/{user_id}/drafts/` | **runtime only**, one per account, written when a draft is saved (`DALICC_USER_GRAPH_TEMPLATE`) | the owner's own pages and the checks they run |
| `https://dalicc.net/users/{user_id}/dependencygraphs/{graph_id}` | **runtime only**, one per unpublished graph of an account (`depgraph.user_graph_iri`) | the owner's editor, and a check that chooses that graph |
| `https://dalicc.net/dependencygraph/{graph_id}` | **runtime only**, one per published graph (`depgraph.core_graph_iri`; `dg_default` keeps the configured IRI) | `/dependencygraph/list`, the reasoner where that graph is chosen |

The corresponding settings are `DALICC_LICENSE_LIBRARY_GRAPH`, `DALICC_DEPENDENCY_GRAPH`,
`DALICC_CUSTOM_LICENSES_GRAPH` and `DALICC_USER_GRAPH_TEMPLATE`.

---

## 2. The data model

### Namespaces

The same prefix block appears at the head of every license file and of the combined library.
`scripts/build_licenselibrary.py` refuses to build if the blocks differ.

| Prefix | IRI | Role |
|---|---|---|
| `odrl:` | `http://www.w3.org/ns/odrl/2/` | the policy model: `Set`, `Permission`, `Prohibition`, `Duty`, `AssetCollection`, `action`, `target` |
| `cc:` | `http://creativecommons.org/ns#` | CC actions (`Attribution`, `Notice`, `ShareAlike`, `SourceCode`, `CommercialUse`, `DerivativeWorks`) and metadata (`jurisdiction`, `legalcode`, `license`, `attributionName`) |
| `dalicc:` | `https://dalicc.net/ns#` | DALICC-proprietary terms, defined in `licensedata/vocabulary/dalicc-ns.ttl` |
| `dalicclib:` | `https://dalicc.net/licenselibrary/` | the license IRIs themselves |
| `dct:` | `http://purl.org/dc/terms/` | `title`, `alternative`, `publisher`, `source`, `type`, `language`, `hasVersion`, `modified` |
| `dcmitype:` | `http://purl.org/dc/dcmitype/` | `Dataset`, `Software` asset types |
| `spdx:` | `http://spdx.org/rdf/terms#` | `licenseId` |
| `osl:` | `http://opensource.org/licenses/` | OSI legal-code IRIs |
| `foaf:` | `http://xmlns.com/foaf/0.1/` | `logo`, `img` |
| `scho:` | `http://schema.org/` | `startDate`, `endDate` |
| `bpicounty:` | `http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#` | country IRIs for `cc:jurisdiction` |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` | the datatype of `dalicc:reviewedOn` and `dct:modified` |
| `spdxlicense:` | `http://spdx.org/licenses/` | declared but never used |

> `bpicounty` in the data, `bpicountry` in `app/services/composer.py`: the same IRI spelled
> two ways. `app/services/vocab.py` accepts both. Watch for it when grepping.

### Shape of one license

A license is an `odrl:Set` whose IRI is `dalicclib:<id>`, where `<id>` is the file name.
Permissions, prohibitions and duties are blank nodes, at most three levels deep
(`Set → Permission → Duty`). A duty either hangs off one permission (a conditional duty, the
normal case) or off the `Set` itself (a license-wide duty, as share-alike is on AGPL-3.0).
181 records carry at least one license-wide duty.

```turtle
dalicclib:Apache-2.0 a odrl:Set ;
    cc:license      dalicclib:CC-BY-4.0 ;                # license of the METADATA RECORD
    dct:license     <https://creativecommons.org/licenses/by/4.0/> ;   # the same, by its canonical address
    spdx:licenseId  "Apache-2.0" ;
    cc:jurisdiction dalicc:worldwide ;
    cc:legalcode    <http://www.apache.org/licenses/LICENSE-2.0> ;
    dalicc:LiabilityLimitation "In no event …" ;         # verbatim clause text
    dalicc:WarrantyDisclaimer  "Unless required …" ;
    dalicc:validityType dalicc:perpetual ;
    dct:alternative "Apache 2.0", "Apache License 2.0" ;
    dct:publisher   "The Apache Software Foundation" ;
    dct:source      <http://www.apache.org/licenses/LICENSE-2.0> ;
    dct:title       "Apache License, Version 2.0"@en ;
    dalicc:variantKind  "version" ;
    dalicc:reviewStatus dalicc:Reviewed ;
    dalicc:reviewedOn   "2026-09-15"^^xsd:date ;
    odrl:permission [ a odrl:Permission ;
                      odrl:action odrl:distribute ;
                      odrl:duty [ a odrl:Duty ; odrl:action cc:Attribution ] ,
                                [ a odrl:Duty ; odrl:action cc:Notice ] ] ;
    odrl:prohibition [ a odrl:Prohibition ; odrl:action dalicc:promote ] ;
    odrl:target     [ a odrl:AssetCollection ;
                      dct:type dalicc:CreativeWork , dcmitype:Dataset , dcmitype:Software ] ;
    foaf:logo       <https://…/apache.png> .
```

One optional property is not on any curated record: `dalicc:licenseText`, which holds
the whole license in words. A record of the library points at the authoritative text with
`cc:legalcode` and quotes single clauses in the clause properties below; a license
composed with the License Composer may carry the text written for it, and its license
page renders that text after the clauses. It is a plain `xsd:string`, one per record, and
a license without one reads exactly as it always did.

`cc:license` on a record is the license of the **record**, not the license the record
models: every record carries `cc:license dalicclib:CC-BY-4.0`, which is what
`licensedata/LICENSE` says in prose. Beside it every record carries `dct:license
<https://creativecommons.org/licenses/by/4.0/>`, the same license by the address Creative
Commons publishes it at, because a consumer that looks for the canonical IRI does not find
DALICC's own record of the license. The statement is additive: `cc:license` keeps its value
and its meaning. `scripts/review/ttl_record.py` adds it whenever it writes a record that
carries `cc:license dalicclib:CC-BY-4.0`, `scripts/build_licenselibrary.py` refuses a
record that has the one without the other (`--name-record-licence` writes the missing
statement), and a record published from the administration pages gets it when its version
is stamped (`app.services.core_licenses.stamp_version`).

The composer writes the same predicate. Its question "Under which license do you provide
your license?" asks for the license of the document the author is about to publish, which
is the very thing `cc:license` states, so a composed license carries the author's choice
there and a curated record carries CC-BY-4.0. A record that has the predicate twice was
composed from a record that already had one: the only one in the library is the fixture
`SampleLicenseSl`, and it is listed under [modelling errors](#modelling-errors) below.
Read `cc:license` as "the terms this document is published under" and never as "the
terms this document grants".

**Where a statement comes from.** A permission, prohibition or duty node may say what it
rests on. The record page reads three properties from the node itself and shows nothing
extra when they are absent:

```turtle
odrl:permission [ a odrl:Permission ; odrl:action odrl:grantUse ;
    dalicc:evidence "Permission is hereby granted, free of charge, to any person ..." ] ,
  [ a odrl:Permission ; odrl:action dalicc:ChangeLicense ;
    odrl:duty [ a odrl:Duty ; odrl:action dalicc:compliantLicense ;
                dalicc:statementOrigin dalicc:FromConvention ;
                dalicc:convention "family rule 15: Permissive records permit relicensing" ] ;
    dalicc:statementOrigin dalicc:FromConvention ;
    dalicc:convention "family rule 15: Permissive records permit relicensing" ] .
```

| Property | Read as |
|---|---|
| `dalicc:evidence` | the sentence of the license text the statement rests on; the page quotes it in the statement's "?" bubble |
| `dalicc:statementOrigin dalicc:FromConvention` | the library states this by convention rather than because a sentence of the text says it; the page marks it *by library convention* |
| `dalicc:convention` | which convention, as a literal; the page names it in the bubble |

A node without `dalicc:statementOrigin` is read as a statement of the text and marked
*from the text*. Where several nodes state the same action, the statement counts as a
convention only when every one of them says so. `app.services.licenses` exposes the reading
as `origin`, `evidence` and `convention` on each `RuleDetail` and `DutyDetail`.

**What the records carry.** `scripts/review/record_evidence.py` wrote the three properties
onto the curated records from what the data already says, and nothing else:

* `dalicc:evidence` where a review finding (`applied`, `none` or `superseded`, never a
  proposal) quotes the text next to the statement's action, where a clause literal of the
  record holds a sentence about one of a few distinctive actions (endorsement,
  sublicensing, the database right, an excepted combination), or where an or-later,
  exception or rider record shares the statement with its base record. Every quote is
  looked up in the record's own legal text, fetched from `text_source` and the SPDX list
  into `build/legal-texts/` with `--fetch`, and what is written is the text's own sentence
  around it, with its own letters. A quote the text does not hold is not written, and an
  English sentence that does not speak about the act, or is not phrased as a statement of
  its kind, is left out. The script's docstring gives every rule.
* `dalicc:statementOrigin dalicc:FromConvention` with `dalicc:convention "family rule N:
  <title>"` on the `dalicc:ChangeLicense` permission and its `dalicc:compliantLicense`
  duty of every record family rule 15 covers (except the records whose text names the
  licenses a work may move to), on the `dalicc:compliantLicense` duty rule 13 asks of a
  whole-work copyleft record, and on any statement a change log says a family rule added.

| Statements | With evidence | By convention | Neither | All |
|---|---|---|---|---|
| Permissions | 256 | 111 | 5,309 | 5,676 |
| Prohibitions | 411 | 0 | 1,179 | 1,590 |
| License-wide duties | 35 | 0 | 148 | 183 |
| Duties on a permission | 452 | 106 | 3,842 | 4,400 |
| All | 1,154 | 217 | 10,478 | 11,849 |

**Every quote names the act it supports.** A spot check of 40 quotes drawn at random from
20 records (seed 20260924) found 12 that did not: the opening of a grant ("license to
exercise the following rights in the Work", "para ejercer derechos sobre la Obra") quoted
for `odrl:reproduce`, `odrl:display` or `odrl:distribute`, "keep intact all copyright
notices" quoted for `cc:Attribution`, a sentence about restricting the terms quoted for
`dalicc:ChangeLicense`. `scripts/review/check_evidence.py` holds every quote to the rule a
reader applies: the sentence names the act, by the word the review rubric uses for it or a
synonym, in the language of the text. On 2026-09-24 it removed 318 quotes from 129
records, each of them versioned with a change log entry that names the statements; the
statements stay and read as statements of the text without a linked quote. 112 quotes are
of acts its table does not list and were left as they are.
`tests/unit/test_data_review.py` runs the check over the records.

A statement with neither is read as a statement of the text without a linked quote. Most of
them are the core permissions of a grant ("to use, copy, modify, merge, publish,
distribute"), which the review confirmed without quoting a sentence per act.

### Clause texts

Four datatype properties carry the sentences of the legal text verbatim, so that a reader
can check the model against the words it was read out of:

| Property | Records | What it quotes |
|---|---|---|
| `dalicc:WarrantyDisclaimer` | 557 | the clause that disclaims warranties |
| `dalicc:LiabilityLimitation` | 525 | the clause that limits or excludes liability |
| `dalicc:additionalClauses` | 244 | any other clause worth keeping, 912 literals in all |
| `dalicc:WarrantyOrLiabilityAcceptance` | 62 | the clause that lets a redistributor accept warranty or liability |

Two rules hold for all four. The text is **quoted, never paraphrased**, and it is split the
way the license splits it: a disclaimer and a liability limitation that share one paragraph
in the source are stored as two literals, each starting at the sentence its own property
names. A clause the vocabulary cannot model deontically still belongs here in full, next to
whatever machine-readable property does exist for it.

### Ports and variants

Many records are the same license adapted to another legal system or reissued by another
body. The library carries 287 Creative Commons jurisdiction ports of versions 2.0 and 3.0
and three government-licence editions, which is why a library of 291 distinct licenses holds
581 records. The listings and the homepage show 290 and 289, because the two test-fixture
records are excluded and one of them is itself a port.

Nothing is ever deleted or renamed, because every identifier is a published IRI. The
relation is made explicit in the data instead:

```turtle
dalicclib:CreativeCommonsAttribution30Norway
    dalicc:jurisdictionPortOf dalicclib:CC-BY-4.0 ;   # sub-property of dct:isVersionOf
    dalicc:variantKind        "jurisdiction-port" ;
    dalicc:licenseVersion     "3.0" ;                 # of the license text, not of the model
    cc:jurisdiction           bpicounty:Norway .
```

| Predicate | Records | Meaning |
|---|---|---|
| `dalicc:jurisdictionPortOf` | 290 | the record this one was adapted from. A sub-property of `dct:isVersionOf`: the parent of every Creative Commons port is the **4.0 International** record of the same element set, so the relation carries a version difference as well as a jurisdiction difference. The library now also holds the unported 1.0 to 3.0 records, and re-pointing the ports at them is open item 10 of [LICENSE_REVIEW.md section 11](LICENSE_REVIEW.md#what-is-still-open). A port and its parent do not say the same thing: each port carries the termination clause of its own text (`dalicc:terminatesOnBreach true`, no cure period), the 4.0 records the 30-day reinstatement of their Section 6(b) (`dalicc:curePeriod "30 days"`), and only the 4.0 records state the database right with the conditions of Section 3(a) |
| `dalicc:licenseVersion` | 351 | the version of the *license text* the record models, so that the version difference above stays readable (`"2.0"` on 96 records and `"3.0"` on 224; on the 287 ports alone, 77 and 210). `dct:hasVersion` carries the version of the DALICC **model**, and the two meanings do not share a term |
| `dalicc:variantKind` | 415 | `jurisdiction-port` (287), `version` (84), `exception` (18), `version-option` (14), `edition` (11) or `rider` (1). 323 records have a parent: 287 ports, 3 editions and the 33 variants below; the other 92 are version or edition variants of a text whose earlier version the library does not hold, so they name their kind without naming a parent |
| `dalicc:variantOf` | 33 | the record this one is a **variant** of. A sub-property of `dct:relation`, not of `dct:isVersionOf`: a variant models the same legal text as its base with one thing changed. 14 are an or-later identifier, 18 are the base license read together with an SPDX exception, and one is Apache 2.0 with the Commons Clause rider |
| `dalicc:translationOf` | 0 | defined for the ports whose legal text is a translation; not yet written into any record |

The 290 ports hang off **nine parents**: the six Creative Commons 4.0 element sets, which
carry 287 between them, and `DataExplorationLicence`, `OpenGovernmentLicenceCanada` and
`UkOpenGovernmentLicenseForPublicSectorInformation`, which carry one edition each.

| Parent | Ports |
|---|---|
| `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-ND-4.0`, `CC-BY-NC-4.0`, `CC-BY-NC-ND-4.0` | 48 each |
| `CC-BY-NC-SA-4.0` | 47 |
| `DataExplorationLicence`, `OpenGovernmentLicenceCanada`, `UkOpenGovernmentLicenseForPublicSectorInformation` | 1 each |

`scripts/validate_data.py` proves that every parent exists, that no record is its own
parent, that no parent is itself a port, and that the relation agrees with the review
record. The relation is one level deep by design: a port of a port would make the grouping
in the site listing ambiguous.

**A variant is not a port and is listed like any other license.** An or-later identifier
(`GPL-2.0-or-later`), a license read together with an SPDX exception
(`GPL-2.0-only-with-Classpath-exception-2.0`) and a license with a rider
(`Apache-2.0-with-Commons-Clause`) each model the same legal text as the record they name,
with one thing changed:

```turtle
dalicclib:GPL-2.0-or-later
    dalicc:variantOf            dalicclib:GPL-2.0-only ;
    dalicc:variantKind          "version-option" ;
    dalicc:orLaterVersionOption true .
```

An or-later record says what its base says, statement for statement, and differs only in
the identifier, the title, the alternative names, the SPDX identifier, the flag and the
relation. An exception record and a rider record keep every statement of their base and add
what the exception or the rider changes: an exception adds a `dalicc:exceptedCombination`
permission and a `dalicc:reciprocityScope` literal saying how far the condition still
reaches, and the rider adds a `dalicc:sellCopy` prohibition. Family rules 16 and 17 of
`scripts/review/family_rules.py` check both, and the variant relation may be two steps long,
because an exception on an or-later identifier names the or-later record.

The license page lists the variants of a record under a heading of their own,
`app/services/ports.py` reads the relation, and the `ports=include|exclude|only` parameter
is untouched: it still selects jurisdiction ports, and a variant is an ordinary row of every
listing, search result and count.

**The Creative Commons ports share their parents' core statements.** Every one of them
carries the permissions, duties, prohibitions and license-wide duties of its parent that its
own text shares with the 4.0 text; they differ where the texts differ: the database right
with the conditions of Section 3(a) only on the 4.0 records, the 30-day reinstatement after a
breach only on the 4.0 records (the ports end on any breach, with no cure period), and the
endorsement prohibition only where a text says so. Among the ports, the one field that
differs is `odrl:target`: a port whose text licenses or waives a database
right carries `dcmitype:Dataset`, a port whose text is silent about databases does not.
Grouping them belongs in the presentation layer; see `app/services/ports.py` and the
`ports=include|exclude|only` parameter in API.md.

### Superseded and withdrawn

A composed license that is no longer current carries `owl:deprecated true` and
`dalicc:deprecatedOn`. The flag stands for two legal situations, and the page tells them
apart by one more triple:

| In the data | State | Set by | The page says |
|---|---|---|---|
| `owl:deprecated true` and `dct:isReplacedBy <newer>` | **superseded** | publishing a new version, or naming a successor when withdrawing | *A newer version exists*: replaced on the date by the newer version; rights already granted under this version are not affected |
| `owl:deprecated true` without `dct:isReplacedBy` | **withdrawn** | *Withdraw this license* on `/my/licenses/<id>`, `POST /my/licenses/<id>/deprecate` or `POST /licenselibrary/mine/<id>/deprecate` | *Withdrawn by its publisher*: from the date no longer offered for new uses; whether granted rights continue is decided by its own terms |

The routes keep the word *deprecate* and the flag keeps `owl:deprecated`, so no client
and no stored document changes. `LicenseDetail.is_superseded` and
`LicenseDetail.is_withdrawn` read the two states.

### Review state and record status

Every record says when it was last checked against the legal text of the license it models
and how far it has come in the editorial ladder:

```turtle
dalicclib:Apache-2.0
    dalicc:reviewStatus dalicc:Reviewed ;
    dalicc:reviewedOn   "2026-09-15"^^xsd:date .
```

`dalicc:reviewStatus` takes `dalicc:Created`, `dalicc:Reviewed`, `dalicc:Approved` or
`dalicc:Audited`; nothing sets the last two yet. All 581 records carry both triples. 343 are
`dalicc:Reviewed`; 238 are `dalicc:Created`, namely the 237 records written from a legal text
that no second reader has checked, and the composer fixture `SampleLicenseSl`, which has no
license text to check it against at all. What *Reviewed* means, who read the records and
what nobody has checked yet is in [LICENSE_REVIEW.md](LICENSE_REVIEW.md#what-reviewed-means):
a record marked Reviewed has been read against its text, and it is not a legal opinion.

The audit trail behind the state is `licensedata/reviews/<id>.yaml`, one file per record:
what was looked at, what was found, what was changed and what was only proposed. Its schema,
the ten-point rubric and the corrections policy are in
[`licensedata/reviews/README.md`](../licensedata/reviews/README.md); the results and the open
questions are in [LICENSE_REVIEW.md](LICENSE_REVIEW.md).

A record that is not a published license says so with `dalicc:recordStatus`:

```turtle
dalicclib:SampleLicenseSl dalicc:recordStatus dalicc:testFixture .
```

Exactly two records carry it, `SampleLicenseSl` and `DeveloperLicense`. Their IRIs keep
resolving; listings, search results and the homepage count leave them out.

### Census

581 licenses, 53,852 triples, 12,435 blank nodes.

| Class | Instances | | Predicate | Triples | On licenses |
|---|---|---|---|---|---|
| `odrl:Permission` | 5,667 | | `rdf:type` | 13,016 | 581 |
| `odrl:Duty` | 4,588 | | `odrl:action` | 11,854 | 0 (on blank nodes) |
| `odrl:Prohibition` | 1,599 | | `odrl:permission` | 5,667 | 581 |
| `odrl:Set` | 581 | | `odrl:duty` | 4,588 | 181 (license-wide) |
| `odrl:AssetCollection` | 581 | | `dct:alternative` | 4,274 | 577 |
| | | | `odrl:prohibition` | 1,599 | 540 |
| | | | `dalicc:additionalClauses` | 912 | 244 |
| | | | `dct:type` | 813 | 0 (on the target) |
| | | | `cc:license` | 582 | 581 |
| | | | `dct:title` / `cc:jurisdiction` / `odrl:target` | 581 | 581 |
| | | | `dalicc:validityType` | 581 | 581 |
| | | | `dalicc:reviewStatus` / `dalicc:reviewedOn` | 581 | 581 |
| | | | `dct:hasVersion` / `dalicc:versionHistory` | 581 | 581 |
| | | | `cc:legalcode` / `dct:source` / `dct:modified` | 580 | 580 |
| | | | `dalicc:WarrantyDisclaimer` | 557 | 557 |
| | | | `dalicc:LiabilityLimitation` | 525 | 525 |
| | | | `dct:publisher` | 510 | 510 |
| | | | `dalicc:variantKind` | 415 | 415 |
| | | | `dalicc:licenseVersion` | 351 | 351 |
| | | | `foaf:logo` / `foaf:img` | 330 / 287 | 330 / 287 |
| | | | `dalicc:jurisdictionPortOf` | 290 | 290 |
| | | | `spdx:licenseId` | **276** | **276** |
| | | | `dalicc:terminatesOnBreach` | 438 | 438 |
| | | | `cc:attributionName` | 95 | 95 |
| | | | `dalicc:WarrantyOrLiabilityAcceptance` | 62 | 62 |
| | | | `dalicc:orLaterVersionOption` | 58 | 58 |
| | | | `dalicc:reciprocityScope` | 47 | 47 |
| | | | `dalicc:curePeriod` | 49 | 49 |
| | | | `dalicc:variantOf` | 33 | 33 |
| | | | `dalicc:fieldOfUseRestriction` | 30 | 30 |
| | | | `dalicc:compatibleLicenseTest` | 23 | 23 |
| | | | `dalicc:governingLaw` | 20 | 20 |
| | | | `dalicc:sublicenseSurvival` | 17 | 17 |
| | | | `dalicc:shareAlikeVersionQualifier` | 8 | 8 |
| | | | `dalicc:PromotionSpecification` / `dct:language` / `dalicc:sourcePublicationPeriod` | 7 | 7 |
| | | | `dalicc:alternativeConditionSet` | 6 | 6 |
| | | | `dalicc:recordStatus` / `dalicc:governmentRightsLimitation` | 2 | 2 |
| | | | `dalicc:composedOf` / `dct:isVersionOf` | 1 | 1 |
| | | | `scho:startDate` / `scho:endDate` / `scho:validFor` / `odrl:assignee` | 1 | 1 |

38 distinct `cc:jurisdiction` values: `dalicc:worldwide` on 294 records plus 37 country
IRIs. 291 of the 581 records are a port of nothing; the other 290 are jurisdiction ports or
editions of the nine parents above. 33 of the 291 are a variant of another record and are
listed like any other license; see [ports and variants](#ports-and-variants).

### The `odrl:action` vocabulary

53 distinct actions occur in the data. `dalicc:` actions are defined in
`licensedata/vocabulary/dalicc-ns.ttl`; `odrl:` and `cc:` actions come from ODRL 2.2 and the
CC REL. The count is the number of `odrl:action` triples that use the term.

| Count | Action | Meaning |
|---|---|---|
| 1,448 | `cc:Notice` | keep the license and copyright notices with every copy |
| 1,388 | `cc:Attribution` | give credit to the copyright holders or authors, in the form the licensor asks for |
| 731 | `dalicc:modificationNotice` | document every change and how the result differs from the original |
| 581 | `odrl:derive` | create a new work from the existing one (translation, adaptation, ...) |
| 581 | `odrl:distribute` | provide copies of the work to the public or to anyone else |
| 581 | `odrl:reproduce` | make copies of the work in any form |
| 579 | `cc:CommercialUse` | use the work to generate income, directly or indirectly |
| 567 | `dalicc:ChangeLicense` | replace the license of the work or of an adaptation, or change its terms |
| 565 | `odrl:display` | show the work to the public without making a copy the viewer keeps |
| 564 | `odrl:present` | perform the work in public, including by broadcast |
| 541 | `dalicc:chargeDistributionFee` | charge a fee for providing a copy |
| 360 | `dalicc:promote` | use the name or trademarks of the licensor or contributors to endorse or promote a product |
| 475 | `odrl:modify` | alter the work without creating a new work (otherwise: `odrl:derive`) |
| 475 | `cc:DerivativeWorks` | distribute an adaptation and make it available to the public |
| 458 | `dalicc:ModifiedWorks` | distribute a modified version that is not a new, derivative work |
| 401 | `dalicc:sublicense` | grant a third party rights under a license of one's own, rather than passing the original on |
| 318 | `cc:SourceCode` | provide access to the source code with every copy distributed |
| 312 | `cc:ShareAlike` | license adaptations under the same license or one it names as compatible |
| 119 | `dalicc:addStatement` | attach additional terms or notices when redistributing |
| 119 | `dalicc:compliantLicense` | the replacement license must stay compliant with the original |
| 98 | `dalicc:suiGenerisDatabaseRights` | extract or reuse a substantial part of a database (label since version 2) |
| 91 | `dalicc:patentGrant` | the express patent license a contributor grants |
| 77 | `dalicc:patentRetaliationTermination` | a patent claim over the work ends the patent license, or the whole license; not a ban on suing |
| 70 | `dalicc:rename` | give the modified work a name of its own |
| 49 | `dalicc:chargeLicenseFee` | charge a fee for granting a license |
| 42 | `odrl:grantUse` | pass the license on to a third party (the same act as `dalicc:sublicense`) |
| 36 | `dalicc:noWarrantyNotice` | attach, or pass on, a notice that the work carries no warranty |
| 30 | `dalicc:networkUseTrigger` | running the work over a network fires the duties the license attaches |
| 25 | `dalicc:includeNoticeFile` | carry a named NOTICE file forward |
| 22 | `dalicc:addLimitation` | add a restriction downstream |
| 18 | `dalicc:exceptedCombination` | combine the work as an SPDX exception allows, outside the condition it lifts |
| 17 | `dalicc:useForModelTraining` | use the material to train an automated system |
| 13 | `dalicc:exemptedMaterial` | use material the license carves out of its grant |
| 20 more, each with fewer than 13 triples | | `dalicc:originalVersionOffer`, `dalicc:exportControlNotice`, `dalicc:royaltyCollectionReserved`, `dalicc:sellCopy`, `dalicc:applyTechnicalProtectionMeasures`, `dalicc:recipientAssent`, `dalicc:contributionGrantBack`, `dalicc:moralRightsRestriction`, `dalicc:patentFreedomCondition`, `dalicc:advertisingAcknowledgement`, `dalicc:provideUserData`, `dalicc:moralRightsNonAssertion`, `dalicc:standardsConformance`, `dalicc:covenantNotToSue`, `dalicc:computationalUseOnly`, `dalicc:publicationNonObstruction`, `dalicc:patentNotice`, `dalicc:trademarkNotice`, `dalicc:recipientRegistrationRequest`, `dalicc:conditionalAddLimitation` |

Every one of the 53 is defined in the DALICC vocabulary or comes from ODRL or Creative
Commons. `odrl:action dct:source`, which the GNU Free Documentation records carried and
`validate_data.py` warned about, is gone: the three duty nodes were removed on 2026-09-23
and `cc:SourceCode`, which sat beside each of them, carries the rule.

### The dependency graph

`licensedata/dependencygraph/dg_default.ttl` holds the axioms the compatibility checker
reasons with: 46 triples over four relations, hand-maintained, no blank nodes and no
literals. It also holds one default rule, which is a different kind of statement and is
described in [section 9](#9-dependency-graphs-as-data). It is at version 2; version 1 and
the change log are in `licensedata/history/dependencygraph/`.

| Relation | Triples | Semantics |
|---|---|---|
| `odrl:includedIn` | 24 | **Subsumption.** Exercising the subject action is a way of exercising the object action, so a statement about the object also covers the subject. `odrl:sell includedIn odrl:commercialize`. |
| `owl:sameAs` | 14 | **Synonymy.** The two actions denote the same act in different vocabularies. `cc:Attribution sameAs odrl:attribute`. Every pair is written both ways round. |
| `odrl:implies` | 7 | **Entailment.** Permitting the subject action necessarily permits the object action. `odrl:modify implies cc:SourceCode`. |
| `dalicc:contradicts` | 1 | **Conflict.** The two actions cannot both hold; this is what `POST /compatibilitycheck/` reports as a conflicting statement. `odrl:ensureExclusivity contradicts odrl:commercialize`. |

All four are declared as `dalicc:DependencyRelation` in the vocabulary, with the same
definitions in machine-readable form.

A chain may cross from one relation into another. `owl:sameAs` gives an action a second
name, so a subsumption, an entailment or a contradiction written about one name holds of
the other; and an entailment runs on into a subsumption, because permitting an act that
entails a second act collides with a prohibition of anything that second act is a special
case of. `dalicc:contradicts` is never chained with a second contradiction.

#### The 46 axioms, with the reason for each

| Axiom | Why |
|---|---|
| `cc:Attribution implies cc:Notice` | Crediting the author is done in a notice, so asking for credit asks for the notice that carries it |
| `cc:Attribution includedIn odrl:use` | Every act the graph relates sits under the umbrella action |
| `cc:Attribution sameAs odrl:attribute` | The Creative Commons and ODRL names for one act |
| `cc:CommercialUse sameAs odrl:commercialize` | "Income-generating use of any kind" and "use the asset in a business environment" are one act; this is the term 579 statements of the library name, and the axioms about selling and charging a fee reach it through this pair |
| `cc:DerivativeWorks includedIn odrl:distribute` | The term means "to distribute the derivative and making it available to the public", which is one kind of distribution |
| `cc:Notice includedIn odrl:use` | Under the umbrella |
| `cc:Notice sameAs odrl:AttachPolicy` | The two names for attaching the license to the work |
| `cc:ShareAlike includedIn odrl:use` | Under the umbrella |
| `cc:ShareAlike implies cc:SourceCode` | Passing the work on under the same license means passing on what the license requires, the source included |
| `cc:ShareAlike sameAs odrl:shareAlike` | The Creative Commons and ODRL names for one condition |
| `cc:SourceCode includedIn odrl:use` | Under the umbrella |
| `cc:SourceCode sameAs odrl:attachSource` | The two names for providing the source |
| `dalicc:ModifiedWorks includedIn odrl:distribute` | "Distributing a modified version of the work and making it available to the public" is distribution |
| `dalicc:chargeLicenseFee implies odrl:commercialize` | Charging for a license is income from the work |
| `dalicc:chargeLicenseFee implies odrl:sell` | A fee for a license is consideration for the work |
| `dalicc:chargeLicenseFee includedIn odrl:transfer` | Granting a license for money passes something on to a third party |
| `dalicc:modificationNotice includedIn odrl:AttachPolicy` | A modification notice is one of the notices a work carries |
| `dalicc:sellCopy includedIn odrl:sell` | Selling copies is one way of selling; through `odrl:sell` a ban on commercial use reaches it |
| `dalicc:sublicense sameAs odrl:grantUse` | The two names for passing a license on |
| `odrl:AttachPolicy sameAs cc:Notice` | The inverse spelling |
| `odrl:attachSource sameAs cc:SourceCode` | The inverse spelling |
| `odrl:attribute sameAs cc:Attribution` | The inverse spelling |
| `odrl:commercialize sameAs cc:CommercialUse` | The inverse spelling |
| `odrl:copy includedIn odrl:use` | Under the umbrella |
| `odrl:copy sameAs odrl:reproduce` | `odrl:copy` is the older ODRL name for reproducing |
| `odrl:derive implies cc:DerivativeWorks` | Deriving produces the derivative the term is about. Contested: see open issue 2 of the content review |
| `odrl:derive includedIn odrl:use` | Under the umbrella |
| `odrl:display includedIn odrl:present` | Showing a work publicly is one way of presenting it |
| `odrl:display includedIn odrl:use` | Under the umbrella |
| `odrl:distribute includedIn odrl:use` | Under the umbrella |
| `odrl:ensureExclusivity includedIn odrl:use` | Under the umbrella |
| `odrl:ensureExclusivity contradicts odrl:commercialize` | A work promised to one party alone cannot also be traded freely |
| `odrl:execute includedIn odrl:use` | Under the umbrella |
| `odrl:extract implies cc:SourceCode` | Taking a part out means having the part to take |
| `odrl:extract includedIn odrl:reproduce` | Copying a part is one way of copying, which is what the ODRL definition says |
| `odrl:extract includedIn odrl:use` | Under the umbrella |
| `odrl:grantUse sameAs dalicc:sublicense` | The inverse spelling |
| `odrl:modify implies cc:SourceCode` | Altering a work means having what is altered |
| `odrl:modify includedIn odrl:use` | Under the umbrella |
| `odrl:present includedIn odrl:use` | Under the umbrella |
| `odrl:print includedIn odrl:present` | A hard copy is one of the renditions ODRL places under presenting |
| `odrl:print includedIn odrl:use` | Under the umbrella |
| `odrl:reproduce sameAs odrl:copy` | The inverse spelling |
| `odrl:sell includedIn odrl:commercialize` | Trading the work for consideration is income from it |
| `odrl:sell includedIn odrl:transfer` | A sale passes the work to a third party |
| `odrl:shareAlike sameAs cc:ShareAlike` | The inverse spelling |

Two axioms of the graph are load-bearing and are pinned by `scripts/validate_data.py`:

* `cc:ShareAlike dalicc:contradicts odrl:grantUse`, and its inverse, must **not** be there.
  Passing the same terms on is the normal way to satisfy a share-alike condition, not a
  contradiction of it, and 29 records in the library grant sublicensing and require
  reciprocity in the same breath. Relicensing under *different* terms is still caught, by
  the direct rule of `consistency_check` and by the `dalicc:ChangeLicense` prohibition the
  reciprocal records carry.
* `dalicc:sublicense owl:sameAs odrl:grantUse`, and its inverse, must be there. Without them
  a bundle of CC-BY-4.0 and MIT answers "no conflict" although one forbids exactly what the
  other grants.

#### Share alike between two licenses

Two licenses that each keep the whole work under themselves conflict, although neither
forbids anything the other permits. The reasoner reads a record that way when it carries
the license-wide `odrl:duty cc:ShareAlike`, or `cc:ShareAlike` as a duty of its
`odrl:derive` permission together with an `odrl:prohibition` of `dalicc:ChangeLicense`
(the shape of BUSL-1.1, Elastic-2.0, the PolyForm and OFL records). Such a pair is
reported as `share-alike-reciprocity` unless a path leads from one license to the other:

| Path | What the records must state |
|---|---|
| the same license text | the same family and version, read from `spdx:licenseId` (an exception such as `GPL-2.0-only WITH Classpath-exception-2.0`, or a port such as `CC-BY-SA-3.0-AT`, keeps its base text); a port without an identifier borrows the family of its `dalicc:jurisdictionPortOf` parent and keeps its own `dalicc:licenseVersion` |
| a later-version option | `dalicc:orLaterVersionOption true`, an identifier ending in `-or-later`, or a `dalicc:shareAlikeVersionQualifier` that accepts "a later version", on the license with the lower version of the same family |
| a compatibility clause | a `dalicc:ChangeLicense` permission with the `dalicc:compliantLicense` duty under it (EUPL, CeCILL, LiLiQ-R+, CAL) |

**Compatibility granted by name.** Some license texts name the licenses a work may move
to: CC BY-SA 4.0 into GPL-3.0 (the Creative Commons compatibility list), LGPL into GPL,
AGPL-3.0 and GPL-3.0 through their section 13. A record states each such license with
`dalicc:compatibleWith`, and the reasoner reads the property in the direction it is
stated: `L1 dalicc:compatibleWith L2` lets a work under `L1` be released under `L2`, so
the pair is not reported as `share-alike-reciprocity`, and a `share-alike-direction`
entry says the combined work has to be released under `L2`. The object may be `L2`
itself or a record one hop from it, of the same license text or with an "or later"
option that reaches `L2` (LGPL-2.1 names GPL-2.0-or-later, which reaches GPL-3.0). The
mixer treats the direction as a restriction, and as a conflict when a target license is
chosen that no stated direction reaches. Compatibility no record states is still not
seen, and such a pair is reported as a conflict (CC BY-SA 3.0 and 4.0 are linked by the
later-version option instead). A jurisdiction port of CC BY-SA 3.0 does not carry the
qualifier of the unported record, so it does not reach 4.0 either.

**What the records state.** A `dalicc:compatibleWith` triple is written only where a license
text, or the licensor's own published list, names the other license, and each one has a
review finding (`field: dalicc:compatibleWith`, rubric 10) that quotes the sentence or names
the list. Compatibility that is only common opinion is not recorded. 18 records carry 56
triples:

| Record | Compatible with | Stated by |
|---|---|---|
| `LGPL-3.0-only`, `LGPL-3.0-or-later` | `GPL-3.0-only`, `GPL-3.0-or-later` | LGPL-3.0 section 2(b): a modified version may be conveyed "under the GNU GPL" |
| `LGPL-2.1-only`, `LGPL-2.1-or-later` | `GPL-2.0-only`, `GPL-2.0-or-later`, `GPL-3.0-only`, `GPL-3.0-or-later` | LGPL-2.1 section 3: the ordinary GPL version 2 may be applied instead, "or a newer version" |
| `AGPL-3.0`, `AGPL-3.0-or-later` and `GPL-3.0-only`, `GPL-3.0-or-later` | each other, both ways | section 13 of each text: a covered work may be combined with a work under the other license |
| `MozillaPublicLicenseVersion20` | GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0 and AGPL-3.0 records, `-only` and `-or-later` | MPL-2.0 sections 3.3 and 1.12, the Secondary Licenses "or any later versions of those licenses" |
| `CC-BY-SA-4.0` | `GPL-3.0-only` | the Creative Commons list of compatible licenses, one way |
| `CC-BY-SA-3.0` | `CC-BY-SA-4.0` | section 4(b), a later version with the same License Elements, and the same list |
| `CC-BY-SA-2.0`, `CC-BY-SA-2.5`, `CC-BY-NC-SA-2.0`, `CC-BY-NC-SA-2.5`, `CC-BY-NC-SA-3.0` | the 4.0 record of the same elements | their share-alike clause, which accepts a later version with the same License Elements |
| `EUPL-1.2` | GPL-2.0, GPL-3.0, AGPL-3.0, OSL-2.1, OSL-3.0, EPL-1.0, CeCILL-2.1, MPL-2.0, LGPL-2.1, LGPL-3.0, CC BY-SA 3.0, EUPL-1.1, LiLiQ-R and LiLiQ-R+ records | article 5 and the appendix of Compatible Licences |
| `EUPL-1.1` | `GPL-2.0-only`, `OSL-2.1`, `OSL-3.0`, `CPL-1.0`, `EclipsePublicLicense10` | article 5 and its appendix |

The appendices also name CeCILL 2.0, of which the library holds no record, so it is not
linked. The Creative Commons jurisdiction ports are not linked: their records carry neither
`dalicc:orLaterVersionOption` nor `dalicc:shareAlikeVersionQualifier`, and linking them
means reading the later-version clause of each port's own text first.

### The DALICC vocabulary

`licensedata/vocabulary/dalicc-ns.ttl` defines **142 terms** in 1444 triples. Each carries
`rdf:type`, `rdfs:label@en` in sentence case, `rdfs:comment@en`,
`rdfs:isDefinedBy <https://dalicc.net/ns#>` and, where an ODRL, CC or schema.org counterpart
exists, `rdfs:seeAlso` or `skos:closeMatch`. A property names its range where one datatype or
class holds all its values, and its domain where one class holds all its subjects. No two
terms share a label.

| Kind | Count | How it is typed |
|---|---|---|
| Actions | 51 | `odrl:Action`, `skos:Concept` and `owl:NamedIndividual`, plus `dalicc:RuleAction` (31) when the term may be the action of a permission or a prohibition and `dalicc:DutyAction` (23) when it may be the action of a duty. 3 are both; an action typed neither is read as a rule action |
| Classes | 15 | `owl:Class`: the asset types `dalicc:CreativeWork` and `dalicc:Hardware`, the classifiers `dalicc:AssetType`, `dalicc:Jurisdiction`, `dalicc:ValidityType`, `dalicc:DependencyRelation`, `dalicc:RecordStatus`, `dalicc:ReviewStatus`, `dalicc:RuleAction`, `dalicc:DutyAction`, and the default-rule layer: `dalicc:DefaultRule`, `dalicc:AxiomRemoval`, `dalicc:DefaultOutcome`, `dalicc:RuleStatus`, `dalicc:StatementOrigin` |
| Datatype properties | 28 | the clause texts (`dalicc:WarrantyDisclaimer`, `dalicc:LiabilityLimitation`, `dalicc:WarrantyOrLiabilityAcceptance`, `dalicc:additionalClauses`, `dalicc:PromotionSpecification`, `dalicc:licenseText`), `dalicc:licenseOwner`, the literal and boolean qualifiers of a record (`dalicc:curePeriod`, `dalicc:governingLaw`, `dalicc:terminatesOnBreach` and the rest, all with `rdfs:domain odrl:Set`), the history and rule literals (`dalicc:reviewedOn`, `dalicc:deprecatedOn`, `dalicc:basedOnVersion`, `dalicc:ruleBasis`, `dalicc:ruleExplanation`) and the two statement properties `dalicc:evidence` and `dalicc:convention` (`rdfs:domain odrl:Rule`) |
| Object properties | 18 | the record relations (`dalicc:validityType`, `dalicc:jurisdictionPortOf`, `dalicc:translationOf`, `dalicc:variantOf`, `dalicc:composedOf`, `dalicc:compatibleWith`, `dalicc:recordStatus`, `dalicc:reviewStatus`, `dalicc:versionHistory`), the default-rule relations (`dalicc:appliesTo`, `dalicc:defaultOutcome`, `dalicc:inJurisdiction`, `dalicc:ruleStatus`, `dalicc:replacesRule`, `dalicc:basedOnGraph`, the deprecated `dalicc:extendsGraph`), `dalicc:statementOrigin` and `dalicc:contradicts`, which is also `owl:SymmetricProperty` |
| Controlled values and policy qualities | 30 | `skos:Concept` and `owl:NamedIndividual`, most also an instance of their class: validity (`dalicc:perpetual`, `dalicc:specifyDate`, `dalicc:specifyPeriod`), jurisdictions (`dalicc:worldwide` and seven regions), default outcomes, rule statuses, statement origins, review and record statuses, and the qualities `dalicc:irrevocable`, `dalicc:royaltyFree` and the deprecated `dalicc:patentFree`, `dalicc:terminationOnBreach` and `dalicc:royalityFree` |

`scripts/validate_data.py` and `tests/unit/test_vocabulary_use.py` hold the file to its data:
every `dalicc:` IRI in a record, a dependency graph or a difference file, and every `dalicc:`
term the application, the reasoner's programs or the scripts name, is defined; a property used
with a literal is a datatype property and one used with an IRI an object property; and every
subject and object fits the declared domain and range. A `dalicc:` string in the code that is
not a term is listed with its reason in `APPLICATION_NON_TERMS`; the one left is the URN of a
SPARQL property path. A misspelt term is corrected in the code, never listed there.

**Version 1** is the vocabulary as the 2022 documentation and the data of 2023 left it.
**Version 2** holds everything the 2026 work added before the first deployment: the terms the
license review and the standard licenses needed, `dalicc:licenseText`, the variant relations
and `dalicc:exceptedCombination`, the default-rule layer with its seven regions, and the terms
of a graph built from another one; the change log lists each with its reason.

**Version 3** (2026-09-24):

* defines where a statement of a record comes from. `dalicc:FromConvention` joins
  `dalicc:FromText` and `dalicc:FromDefaultRule` as a `dalicc:StatementOrigin`: the statement
  is a library convention applied to every record of its kind, not a sentence of the license
  text. `dalicc:evidence` quotes the sentence of the legal text a statement rests on and
  `dalicc:convention` names the convention that put a statement there (a literal). A statement
  node that names no origin is read as `dalicc:FromText`;
* defines `dalicc:compatibleWith`, the directed relation from one record to another whose
  license a work under the first may be released under, alone or combined, as the first
  license's text or its licensor's published compatibility list says (LGPL-3.0 into GPL-3.0 by
  its section 2, CC BY-SA 4.0 into GPL-3.0 by the Creative Commons list). It is not symmetric;
* defines `dalicc:deprecatedOn`, which the License Composer already wrote;
* rewrites every action definition as one neutral sentence that describes the act, because
  the record page prints the same definition under Permissions and under Prohibitions. The
  2022 wording of the 19 terms that had one is kept verbatim as `skos:historyNote`, and
  remarks about modelling moved to `skos:scopeNote`. `dalicc:patentRetaliationTermination`
  is labelled "Patent license ends on a patent claim" and `dalicc:suiGenerisDatabaseRights`
  "Extract or reuse a substantial part of a database"; both IRIs stay;
* makes the nine literal-valued annotation properties datatype properties of `odrl:Set`, gives
  `dalicc:ruleExplanation` the range `rdf:langString`, labels the six value classes
  "... value" so none shares a label with its property, types every individual
  `owl:NamedIndividual` and states six `skos:closeMatch` alignments;
* deprecates seven published terms that duplicate another and that no record uses (below).

**Version 4** (2026-09-24) spells license with an s in the labels and comments of the five
terms whose words named it, as the rest of the site does; the label of
`dalicc:patentRetaliationTermination` is the one label that changed. The titles of licenses
that spell it with a c, such as the CERN Open Hardware Licence, keep it. No term changed its
meaning.

Every superseded version is archived next to its change log, as
`licensedata/history/vocabulary/dalicc-ns-v<n>.ttl`, and the change log says why each term
was added or changed.

**The file is the source of truth, not a second copy of one.** `app/services/vocab.py` reads
every `dalicc:` term from it at import: the label, the definition and the classification, and
the definition of every property (`vocab.PROPERTY_DESCRIPTIONS`, which the comparator glossary
shows beside each further term). Defining a term here is all it takes for the composer,
`GET /licenselibrary/actions`, `input_from_graph` and the consistency check to accept it. The
module supplies the ODRL and Creative Commons terms, which the file does not define, with
descriptions written the same way; its own copies of `dalicc:` definitions are only the
fallback for a checkout without the file.

#### Where the definitions come from

| Source | Carried as | Covers |
|---|---|---|
| The DALICC vocabulary documentation published at <https://dalicc.github.io/> (`index.md`, last updated 2022-03-15, served as `docs.dalicc.net`) | `skos:historyNote@en` **verbatim**, with `dct:source <https://dalicc.github.io/>`; `rdfs:comment` where the wording is still the definition (`dalicc:CreativeWork`, `dalicc:worldwide` and a few more) | 23 `dalicc:` terms, lawyer-written |
| The help texts of the original DALICC license composer, rewritten in 2026 | `rdfs:comment@en`, one sentence that describes the act and neither grants nor forbids it | every action |

The 2022 wording stays because it was published and data was written against it, and one
verbatim oddity is kept on purpose: the historical note of `dalicc:promote` ends in a double
full stop, exactly as published. The `/ns` page shows it under "2022 wording".

The `/ns` page of this application supersedes `docs.dalicc.net`: same introduction, same
information-model figure, same definitions, but generated from the file the triple store is
loaded with and annotated with real usage. The `docs.dalicc.net` vhost should proxy to `/ns`
rather than serve the old static build; the nginx change is in DEPLOYMENT.md
and nginx_confs/README.md.

#### Two namespace spellings

| Form | Status |
|---|---|
| `https://dalicc.net/ns#` | **canonical.** The only form allowed in new data; `validate_data.py` errors on anything else in `dg_default.ttl`. |
| `http://dalicc.net/ns#` | **legacy.** Used by the 2022 documentation and by a handful of axioms still resident in the live Virtuoso database. Recorded in the vocabulary as `owl:priorVersion <http://dalicc.net/ns#>` and explained in the ontology's `rdfs:comment`. It denotes the same terms. |

#### Deprecated terms

A deprecated term keeps dereferencing, because data written against a published version may
use it. It carries `owl:deprecated true`, `dct:isReplacedBy` and a comment that names the
replacement, and its label says "(deprecated)".

| Term | Replaced by | Why |
|---|---|---|
| `dalicc:royalityFree` | `dalicc:royaltyFree` | the 2022 documentation misspelt "royalty"; the two also carry `skos:exactMatch` |
| `dalicc:extendsGraph` | `dalicc:basedOnGraph` | every dependency graph became complete (section 9) |
| `dalicc:terminationOnBreach` | `dalicc:terminatesOnBreach` | the property a record carries says the same thing |
| `dalicc:patentFree` | `dalicc:patentGrant` | its 2022 definition is the scope of a contributor's patent license |
| `dalicc:chargeOffer` | `dalicc:chargeDistributionFee` | a fee for transferring a copy is a distribution fee |
| `dalicc:redistribute`, `dalicc:publish` | `odrl:distribute` | the same act |
| `dalicc:attributionNotice` | `cc:Attribution` | the library states attribution duties with it |
| `dalicc:permissionNotice` | `cc:Notice` | the library states notice duties with it |

`validate_data.py` enforces the pattern: every `owl:deprecated` term must name a replacement
with `dct:isReplacedBy` that is defined here or is an ODRL or Creative Commons term, and a
deprecated term that turns up in the data raises a warning.

#### The usage notes are generated, not asserted

Two kinds of `skos:note` make a claim about the library, and both go stale the moment a
record starts using the term:

* "Defined in the 2022 documentation; not used by any license in the current library." is on
  9 terms: `attachoffer`, `attributionNotice`, `chargeOffer`, `irrevocable`, `patentFree`,
  `permissionNotice`, `publish`, `redistribute`, `royaltyFree` (five of them deprecated since
  version 2). They are part of the
  published namespace and must keep dereferencing.
* The equivalent note on a vocabulary gap that is defined but applied nowhere is on 5 terms:
  `databaseRightWaiver`, `derivativeDatabaseAccess`, `downstreamOffer`,
  `terminationOnBreach`, `translationOf`.

`app/services/vocab.py` reads them: a term whose note says nobody uses it is resolved for
display but never offered for authoring.

```sh
python scripts/validate_data.py --write-usage-counts   # count first
python scripts/review/refresh_vocab_notes.py           # then rewrite the notes
python scripts/review/refresh_vocab_notes.py --check   # exit 1 if one is stale
```

#### Usage counts

`licensedata/vocabulary/usage-counts.json` is generated, never edited by hand:

```sh
python scripts/validate_data.py --write-usage-counts
```

For every term it records how many `licensedata/licenses/*.ttl` files mention it, how many
triples of the library do, and how many axioms of `dg_default.ttl` do. The `/ns` page reads
it for its "used in N of 581 licenses" column; parsing the 3.1 MB library on every
application start for one column is not worth it. A normal `validate_data.py` run warns when
the file is stale, so it cannot drift silently.

### The SPDX mapping

`licensedata/spdx-mapping.json` is generated and checked the same way:

```sh
python scripts/review/build_spdx_mapping.py            # write it
python scripts/review/build_spdx_mapping.py --check    # exit 1 if it is stale
```

It holds `dalicc_to_spdx` (276 of the 581 records carry an `spdx:licenseId`) and the reverse
index `spdx_to_dalicc`, whose values are lists because one SPDX identifier could describe
more than one record. Every identifier in it is on the SPDX license list with the record's
own legal-code URL among its `seeAlso` links. Most jurisdiction ports have no SPDX identifier
at all, and that absence is deliberate. It is served at `GET /licenselibrary/spdx-mapping`
and `GET /licenselibrary/spdx/{spdx_id}`.

Two kinds of identifier were added with the records of the licenses GitHub projects use.
The 18 records that model a license with an SPDX exception declare an **expression** rather
than a single identifier, with a space and an upper-case `WITH`:

```json
"GPL-2.0-only WITH Classpath-exception-2.0": ["GPL-2.0-only-with-Classpath-exception-2.0"]
```

And the file gained an **`aliases`** table: the 35 identifiers the SPDX license list has
deprecated, together with the `+` forms, mapped onto the identifier that replaced them.
GitHub and most package managers still report `GPL-2.0` and `GPL-2.0+`, so a lookup for
either of them resolves to the record of `GPL-2.0-only` and `GPL-2.0-or-later`; the answer
names the identifier the record itself declares. The table is hand-kept in
`scripts/review/build_spdx_mapping.py`, so the build needs neither the network nor a copy
of the SPDX list, and `aliases_resolvable` says how many rows reach a record today (26 of
35; the other nine name an identifier the library does not hold, and they answer 404 as
before).

---

## 3. Two representations, kept in sync by tooling

`licensedata/licenses/*.ttl` is the source of truth.
`licensedata/licenselibrary/licenselibrary.ttl` is a **generated artefact**: the
concatenation of the per-license bodies, sorted by identifier, under one shared prefix block,
with a `# <id>` comment in front of each block.

```bash
python scripts/build_licenselibrary.py           # regenerate
python scripts/build_licenselibrary.py --check   # exit 1 if it is out of date
python scripts/validate_data.py                  # prove the two agree, triple for triple
```

The generator is textual, not an rdflib re-serialisation: rdflib would rename all 12,490 blank
nodes and reorder every object list, producing a megabyte of diff on every run. Running the
generator twice produces byte-identical output. `scripts/review/ttl_record.py` edits a record
the same way, statement by statement, so that a library-wide sweep leaves every untouched
line exactly as it was; run with no arguments it is a self-test that re-renders all 581 files
and reports any that differ.

`scripts/validate_data.py` compares the two representations by a canonical form rather than
by blank-node identity. The DALICC blank-node structure is a tree, every blank node has
exactly one incoming edge and there are no cycles, so a recursive, order-independent
rendering of each `odrl:Set` and its subtree is an exact canonical form. That makes the
comparison linear (about a second) instead of a general graph-isomorphism run.

### What `validate_data.py` checks

Errors (exit 1):

1. Encoding hygiene: every `.ttl` is UTF-8 without BOM, LF only, with a final newline.
2. Every license file parses and declares exactly one `odrl:Set`.
3. The file name equals the local name of that `odrl:Set` IRI.
4. The library file parses and holds exactly the same licenses as the per-license files,
   triple for triple.
5. Every license carries `dct:title`, `odrl:target`, `odrl:permission` and `cc:jurisdiction`.
6. Every shipped dependency graph parses, uses only `https://dalicc.net/ns#` (never
   `http://`), and carries only the four relations, default rules, axiom removals and its
   own metadata, never the deprecated `dalicc:extendsGraph`. Every rule names an action, an
   outcome, a territory, a basis, an explanation and a status exactly once, and every
   removal names its axiom in full with a basis and an explanation; no graph holds an axiom
   it records as removed. Only the core graph adopts a rule. Each jurisdiction graph names
   `dg_default` and its current version with `dalicc:basedOnGraph` and
   `dalicc:basedOnVersion`, holds no two default rules of one kind for one action in one
   territory, and is byte for byte what `scripts/build_dependency_graphs.py` generates from
   the core graph and its difference file (the build's `--check`).
7. The vocabulary parses and every `owl:deprecated` term names a defined replacement.
8. Every loadable `.ttl` has a `.graph` sidecar holding an absolute IRI.
9. Every license has a review record and every review record a license; each parses as YAML
   with the required keys and a known verdict; every license carries `dalicc:reviewStatus`
   and `dalicc:reviewedOn`.
10. `dalicc:jurisdictionPortOf` resolves, no record is its own parent, no parent is itself a
    port, every port carries `dalicc:variantKind`, and the relation agrees with the review
    record. Every `dalicc:variantKind` value is a known one, and every version-option,
    exception and rider record names an existing base record with `dalicc:variantOf`.
11. The library-wide decisions still hold: no NoDerivatives record permits `odrl:modify` or
    `dalicc:ModifiedWorks` and every one of them prohibits derivatives; every Creative
    Commons record except the two dedications, plus ODbL and ODC-By, prohibits
    `dalicc:sublicense`; exactly the two known test fixtures carry `dalicc:recordStatus`.
12. `cc:ShareAlike dalicc:contradicts odrl:grantUse` stays out of the dependency graph.
13. The model history is consistent; see [section 4](#4-model-history-and-versioning).

Warnings: a missing `spdx:licenseId`, `dct:source` or `cc:legalcode`; an `odrl:target` with
no `dct:type`; `odrl:action` values outside ODRL, CC and DALICC; `dalicc:` terms used in the
data but not defined in the vocabulary; deprecated terms still used in the data;
`usage-counts.json` or `spdx-mapping.json` missing or out of date. The repository currently
reports **0 errors and 3 warnings**, all three of them counts of records without an optional
field: 305 without an `spdx:licenseId` and one, the composer fixture, without a `dct:source`
or a `cc:legalcode`.

CI runs `python scripts/validate_data.py --against-git`, which needs `fetch-depth: 0` on the
checkout. Use `--strict` to fail on warnings too, and `--write-usage-counts` to regenerate
`vocabulary/usage-counts.json` after a data change.

---

## 4. Model history and versioning

A curated model is not frozen. A record is corrected when a reading of the legal text turns
out to be wrong, and because the compatibility checker reasons over exactly those statements,
a correction changes the answers DALICC gives. Anyone who acted on an older answer has to be
able to see what the model said at the time, so every version of every curated model is kept.

**The rule: a changed record bumps `dct:hasVersion` and gains a changelog entry.**
`scripts/review/bump_version.py` does both, `scripts/validate_data.py` proves it was done,
and `make history-check` is the command that runs the proof.

### The layout

```
licensedata/history/
├── licenses/<id>/v<n>.ttl            the record as it stood at version n, verbatim
├── licenses/<id>/changelog.yaml      one entry per version from 2 upwards
├── dependencygraph/dg_default-v<n>.ttl + changelog.yaml
├── dependencygraph/dg_<id>-v<n>.ttl    + dg_<id>-changelog.yaml
└── vocabulary/dalicc-ns-v<n>.ttl       + changelog.yaml
```

581 records are past version 1 and 581 archived version files exist: every record is at
version 2 after the squash below, and a correction from now on is a version of its own.
`scripts/validate_data.py` prints the current figures on every run (`history: ...
record(s) past version 1, ... archived version file(s)`), and
`tests/unit/test_review_figures.py` fails when this paragraph falls behind them. An
archived version is
the **committed file, byte for byte**, never an rdflib re-serialisation: the hand-curated
Turtle layout is part of what was published, and a reader comparing two versions should see
the change and not thousands of renamed blank nodes.

### Two versions at the first deployment

The work of 2026 corrected many models more than once before any of it was deployed: a
record could reach version 6, the core graph version 6 and the vocabulary version 8, with
intermediate states nobody outside the project had read. Before the first deployment every
history was **squashed to two versions**, so that the deployment offers one prior version
and not a history of many at the start:

* **version 1** is the model as it was published before the 2026 work (for a model written
  in 2026, its first version), archived byte for byte and untouched by the squash;
* **version 2** is the model as it is now. Its one change-log entry is dated with the date of
  the last merged entry, names Giray Havur as reviewer, says in one or two sentences what
  changed overall, and lists the union of the merged change lists: every change with its
  source, duplicates removed, in the order the versions were written. A hand edit whose
  reason pointed at the summary of its entry carries that summary as its reason, so nothing
  that was recorded about a change was lost, only the intermediate states. The statements
  that carry nothing but a version number (the vocabulary's `owl:versionInfo`, a generated
  graph's `dalicc:basedOnVersion`) are restated for the new numbering, once each.

The entry carries a marker that says which versions it merged:

```yaml
- version: 2
  date: '2026-09-23'
  reviewer: Giray Havur
  summary: The content review of 2026-09-15 ... Later changes ...
  squashed_from: [2, 3, 4, 5]
  changes: [...]
```

The squash ran twice on 2026-09-24. The first run, after the content review, touched 220
records, the eight shipped dependency graphs and the vocabulary, removed 283 archived
versions and merged 512 change-log entries into 229. The corrections of the review that
followed moved 575 records to versions 3 to 6, the eight graphs to version 3 and the
vocabulary to version 4, so the second run merged them again: 575 records, the eight graphs
and the vocabulary, 1,290 archived versions removed and 1,874 change-log entries merged into
584, whose 6,641 changes are kept as 6,633 (the eight left out restated a version number a
second time). A version 2 entry the first run wrote keeps its changes, which come first, and
its marker becomes the union of the numbers it named and the numbers merged now, so a
stored graph row at a number either run merged is named in it. Models at one or two versions were
not touched. `scripts/review/squash_history.py` does it deterministically (`--dry-run`
reports what it would merge) and stays in the repository as the record of how it was done.
It may run any number of times **before the first deployment** and never after it, because
from then on every version is published and a published version is never renumbered
(DEVELOPMENT.md). A deployment whose accounts database
was written before a squash follows it at its next start (section 9).

### The change log

```yaml
id: Apache-2.0
title: Apache License, Version 2.0
current_version: 2
entries:
- version: 2
  date: '2026-09-15'
  reviewer: Giray Havur
  summary: Added 1 permission, changed 2 permissions, ...
  changes:
  - action: added
    statement: permission odrl:grantUse
    reason: 'Section 2 grants a "perpetual, worldwide, ... sublicense, and distribute the
      Work". Sublicensing was not modelled. Added odrl:grantUse.'
    source: review-finding 3/odrl:permission
```

The change list is **derived from the triples**, not written by hand: both versions are
parsed and compared by the canonical form of every statement about the `odrl:Set`, with
blank-node subtrees rendered order-independently. An added and a removed statement that
describe the same predicate and the same `odrl:action` are folded into one `changed` entry,
so a permission that only gained a duty reads as one change and not as two.

Each change names **why** it was made:

| `source` | Meaning |
|---|---|
| `review-finding <rubric>/<field>` | a finding of `licensedata/reviews/<id>.yaml` marked `applied`; `reason` is the finding's own description |
| `consolidation-decision <n>` | one of the seventeen consolidation decisions, the library-wide decisions listed in [LICENSE_REVIEW.md](LICENSE_REVIEW.md) |
| `review-state` | `dalicc:reviewStatus` and `dalicc:reviewedOn`, which every record carries |
| `ports-metadata` | `dalicc:jurisdictionPortOf`, `dalicc:variantKind`, `dalicc:licenseVersion` |
| `model-history` | the two vocabulary terms a versioned model needs |
| `manual` | a hand edit, whose reason is the summary of its entry |

The 581 entries hold 6,081 changes: 2,951 name a finding, a decision, the review state or
a port relation, and the 3,130 hand edits carry `manual`, with the reason `--notes` gave
them or, where that reason pointed at the summary of its entry, that summary (section
"Adding or changing a record" below).
`scripts/review/build_history.py` built the first history and printed anything it could not
attribute. It is retired and refuses to run without `--i-know`
(DEVELOPMENT.md).

### What a record says about itself

```turtle
dalicclib:Apache-2.0
    dct:hasVersion      "2" ;                     # of the DALICC model
    dct:modified        "2026-09-15"^^xsd:date ;
    dalicc:versionHistory <https://dalicc.net/licenselibrary/Apache-2.0/versions> .
```

`dct:hasVersion` is the version of the **model**, exactly as it already was on a license
composed with the License Composer. It is always one more than the number of archived
versions, which is what makes the two representations impossible to drift apart. Every
record is past version 1: all 581 at version 2. A record written from now on starts at
version 1 and archives nothing until it is corrected.

The version of the **license text** is a different fact and has its own term,
`dalicc:licenseVersion` (`"3.0"` on a Creative Commons 3.0 port).

A jurisdiction port is a record like any other: its own history, its own `dct:hasVersion`,
its own change log. A port is never versioned *through* its parent, because the two are
separate published URIs and may be corrected at different times. The dependency graph carries
a comment naming its version, and the vocabulary says so in its ontology header:

```turtle
<https://dalicc.net/ns#> a owl:Ontology ;
    dct:hasVersion  "2" ;
    owl:versionInfo "2.0" ;
    owl:priorVersion <https://dalicc.net/ns/versions/1> ,
        <http://dalicc.net/ns#> ;                 # the legacy namespace spelling, unrelated
    dalicc:versionHistory <https://dalicc.net/ns/versions> .
```

The last `owl:priorVersion` is the legacy `http://` **namespace** form of section 2 and has
nothing to do with the version history; both are kept because both are true.

### Adding or changing a record, end to end

```bash
# 1. write or edit the record
$EDITOR licensedata/licenses/MIT.ttl

# 2. write or update its review record (required; the validator fails without it)
$EDITOR licensedata/reviews/MIT.yaml

# 3. version the change (skip for a brand new record: it is version 1 and archives nothing)
python scripts/review/bump_version.py MIT --summary "Recorded the patent clause of ..."

# 4. regenerate everything that is derived from the records
python scripts/build_licenselibrary.py
python scripts/review/build_spdx_mapping.py
python scripts/validate_data.py --write-usage-counts
python scripts/review/refresh_vocab_notes.py

# 5. prove it
python scripts/validate_data.py                  # 0 errors
python scripts/review/family_rules.py --strict   # the twenty family rules, rule 14 not counted
python scripts/review/consistency_sweep.py       # the consistency check over every record
make history-check                               # every changed model really was versioned

git add licensedata && git commit
```

A new record needs a new `licenses/<id>.ttl` and a new `reviews/<id>.yaml` whose verdict is
`created`; the record starts at `dct:hasVersion "1"` with `dalicc:reviewStatus dalicc:Created`
and archives nothing. A new `dalicc:` term has to be defined in `vocabulary/dalicc-ns.ttl`
before it may appear in a record.

`bump_version.py` reads the committed version with `git show HEAD:...`, refuses when the
working file says the same thing, archives the committed version as `v<n>.ttl`, raises
`dct:hasVersion` to `n + 1`, sets `dct:modified` to today and appends a changelog entry
holding the summary from the command line and the triple-level difference. Every change in
that entry carries `source: manual`, because that is what a hand edit is; write the reason
into `--summary`, and edit the entry afterwards if one change needs a reason of its own.
A library-wide change passes `--from-file ids.txt --notes notes.json`, where the JSON file
gives each record a summary of its own and each changed statement a reason of its own
(`{"<id>": {"summary": "...", "reasons": {"<statement>": "..."}}}`), because a quote added
to a permission reads the same in the change list as the permission did before.
`--dry-run` reports without writing, `--reviewer` sets the name (it defaults to "Giray
Havur"), and `--base-file <path>` overrides what the new version supersedes, for the one case
`HEAD` gets wrong: a pass that corrects a record a second time before the first correction is
committed.

### The gate

`validate_data.py` proves that for every record `dct:hasVersion` equals one plus the number
of archived versions, that a record past version 1 carries as `dct:modified` the date of the
change log entry of its current version (the record page compares that date with
`dalicc:reviewedOn` to say that a record changed after its review), that the archived versions are numbered `1..n` and all parse, that
`dalicc:versionHistory` is present and correct, and that the change log holds exactly one
entry per version from 2 upwards with every key its schema requires. The dependency graph and
the vocabulary are held to the same rule.

```bash
python scripts/validate_data.py               # the consistency of the history itself
python scripts/validate_data.py --against-git # and: was a changed model versioned at all?
make history-check                            # the same thing
```

`--against-git` compares every record with `HEAD`, ignoring the three version predicates, and
fails when a model changed without `dct:hasVersion` being raised and a changelog entry being
written. It is what CI runs, which is why the checkout step of `.github/workflows/ci.yml`
uses `fetch-depth: 0`: a shallow clone has no `HEAD` to compare against. A record that does
not exist at `HEAD` is new, is version 1 and is exempt.

### Changing a record on a running server

The workflow above is the one that produces a commit, and it is the one to use whenever there
is a checkout. A correction that cannot wait for a release is made on the site instead, by an
administrator, at `/admin/licenses/core/{id}/edit` (see
ADMINISTRATION.md). It follows the
same rule: a summary, a reason, the actor's name, an immutable version, and the version it
replaces still retrievable.

What that version cannot do is commit itself. A server has no checkout and a file written
into a container image is lost at the next deployment, so the version is stored in the
account database (`core_versions`) and the library graph is updated. The site and the API
serve it at once, because `app/services/licenses.py` prefers a runtime version over the file
on disk and `app/services/history.py` merges the runtime change-log entries with the
file-based ones into one sequence.

Bringing them into git is one command, on a machine with a checkout and a connection to the
same database:

```bash
make export-library            # or: python scripts/export_library.py
git add licensedata && git commit
```

`scripts/export_library.py` writes, per record that has a runtime version, the newest version
as `licensedata/licenses/<id>.ttl`, every superseded version that is not archived yet as
`licensedata/history/licenses/<id>/v<n>.ttl`, and the merged `changelog.yaml`. It then
regenerates `licenselibrary.ttl` and runs `validate_data.py`, so what it leaves behind is
what the gate expects. It is idempotent: a second run writes nothing. `--dry-run` lists what
would change, and `/admin/licenses/core/export` shows the same list in the browser without
writing anything. Nothing is lost if the export is never run; the versions stay in the
database and the site keeps serving them.

### Reading it back

Nothing in `licensedata/history/` is loaded into Virtuoso. The application reads the folder
directly through `app/services/history.py`, which caches every parsed change log by
`(path, mtime, size)`, merges in the versions published on the server, and serves it at
`GET /licenselibrary/license/{id}/versions`, `.../versions/{n}`, `.../changelog`,
`GET /licenselibrary/history`, and the same three paths under `/dependencygraph` and `/ns`
(see API.md). On the site every license page, the dependency-graph page and `/ns`
carry a "History" section, an archived version renders read only at
`/license-library/{id}/versions/{n}`, and `/license-library/changes` lists recent changes
across the library (see WEBSITE.md).

### The content hash

Every version of a license record, a dependency graph and the vocabulary has a content
hash, `sha256:` followed by 64 hex digits, so that a reader can tell whether two copies of
a version say the same thing without comparing files. It is computed by
`app/services/content_hash.py` and published by the version 2 API
(API.md).

**What it covers.** The triples, never a serialisation: the same version served as Turtle,
JSON-LD, RDF/XML or N-Triples has one hash, and comments, prefixes and the layout of a file
play no part. For a license record the triples are the record's concise bounded
description: every triple whose subject is the record IRI, plus, recursively, every triple
whose subject is a blank node reached from it. That is exactly what
`licensedata/licenses/<id>.ttl` holds (a unit test proves it for every file), and it is
also what the record is inside the shared named graph of the store, so the file and the
store give the same hash. For a dependency graph and the vocabulary the triples are the
whole graph.

**The canonical form, `dalicc-c14n-1`.** The triples are written as N-Triples in one fixed
way: an IRI with the N-Triples escapes and nothing else; a literal with its lexical form
exactly as parsed, `xsd:string` dropped and a language tag in lower case; a blank node
named `b` plus the first 32 hex digits of the SHA-256 of its own sorted lines (predicate and
object, children first). The lines are deduplicated, sorted by their UTF-8 bytes and each
ends with LF. The hash is the SHA-256 of that text. The algorithm needs every blank node to
be the object of exactly one triple and no chain of blank nodes to loop; it refuses any
other graph (`NotTreeShaped`) instead of hashing it wrongly. All the Turtle the service
serves or archives meets that condition, and `tests/unit/test_content_hash.py` checks it on
every file together with four published test vectors.

**Where it is computed.** At request time, from what the service serves: an administrator
can publish a record or a graph version between deployments, so a hash written into the
repository would be wrong on a running server. The resolution of "version `n` of X" lives
in the same module and is the one every version 2 route uses: the current record through
the loader of the library (a runtime version, the file, or the composed-licence graph of
the store), an earlier one from `licensedata/history`; for a graph the stored version row,
the file of a core graph, the archived file; for the vocabulary its file or the archived
one. The hashes are cached by the source they come from (a file's path, modification time
and size; a runtime version, which never changes once written), and the cache is emptied
wherever the history cache is.

### Release manifests

A release of the data is the set of versions a server serves: the version and content hash
of every curated record, every published core dependency graph and the vocabulary. It is
named by four content addresses, each `<prefix>-` plus the first 16 hex digits of a SHA-256:

```
lib-   over "<id>\t<version>\t<hash>\n" for every record, sorted by the UTF-8 bytes of the id
dg-    the same over the core graphs
ns-    over "dalicc-ns\t<version>\t<hash>\n"
data-  over "<lib-id>\n<dg-id>\n<ns-id>\n"
```

The same state has the same name on every server and in every checkout, and a server where
an administrator published one more version has a different name at once. The application
version and a date travel beside the identifiers as labels and are not part of them.
Composed licenses and the graphs of accounts are never in a release. Test fixtures are,
with their record status, because the manifest has to equal `licensedata/`.

`app/services/releases.py` computes the state a server serves now (cached by a fingerprint
of its sources) and reads the registered ones. A registered release is a file,
`licensedata/releases/<data-id>.json`, with sorted keys and a two-space indent:

```json
{
  "algorithm": "dalicc-c14n-1",
  "application_version": "2.0.0",
  "date": "2026-09-25",
  "release": "data-...",
  "library": {"id": "lib-...", "records": {"0BSD": {"date": "...", "hash": "sha256:...", "status": "current", "version": 2}}},
  "graphs": {"id": "dg-...", "graphs": {"dg_default": {"date": "...", "hash": "sha256:...", "status": "current", "version": 2}}},
  "vocabulary": {"id": "ns-...", "date": "...", "hash": "sha256:...", "version": 2}
}
```

`date` in the file is the day the release was cut. `scripts/build_release_manifest.py`
writes it from the checkout alone, with no store and no database, which is right for a
release cut from the repository, and `--check` exits 1 when the newest registered manifest
no longer names the checkout. A registered release never changes; it is the fixed point
`GET /v2/changes?since=<release id>` answers against. The first one is written when 2.0.0
is cut (DEVELOPMENT.md, step 1b).

---

## 5. Loading into the triple store

`scripts/load_data.sh` loads the library, the dependency graph, the vocabulary and, when
asked, a custom-licenses file. (`licensedata/copy_ttls.sh` is a deprecation shim that calls
it.)

```bash
export VIRTUOSO_DBA_PASSWORD=…              # the variable docker-compose.yml uses
scripts/load_data.sh                        # append into the existing graphs
scripts/load_data.sh --clear                # CLEAR the shipped graphs, then load  (recommended)
scripts/load_data.sh --custom-licenses build/customlicenses.nt --clear
scripts/load_data.sh --custom-licenses build/dump.nt --clear-custom   # replace that graph
scripts/load_data.sh --dry-run              # show the plan and the isql script, touch nothing
```

Options: `--container` (default `virtuoso-db`), `--password`, `--data-dir` (default `/data`),
`--dump-dir` (default `ttl_dump`), `--ld-dir`, `--clear`, `--clear-custom`, `--skip-index`,
`--dry-run`.

What it does, and why each step is there:

1. Reads the target graph of every file from its `.graph` sidecar and refuses to run if a
   sidecar names an unexpected graph.
2. `docker cp`s the files into `<container>:/data/ttl_dump`, then hands that directory to
   `ld_dir()` as `./ttl_dump`. In the `tenforce/virtuoso` image `/data` is a *symlink* to the
   server's working directory and `virtuoso.ini` sets `DirsAllowed = .`; Virtuoso checks that
   list against the path as written, without resolving symlinks, so `ld_dir('/data/ttl_dump',
   …)` is refused with `FA003: Access … is denied` while `ld_dir('./ttl_dump', …)` is
   accepted. Override with `--ld-dir` if your image differs.
3. `DELETE FROM DB.DBA.load_list WHERE ll_file LIKE '%ttl_dump%'`. Without this the bulk
   loader skips files it has already seen and a second run silently loads nothing.
4. Prints the graphs it is about to clear and the triple count of
   `https://dalicc.net/customlicenses/`, then `SPARQL CLEAR GRAPH <…>` per graph on the
   list. `--clear` puts the graphs this repository ships on it: the library, the
   vocabulary, `dg_default` and the seven jurisdiction graphs. The custom-licenses graph
   is never on it unless `--clear-custom` is given, and the script refuses to run if it
   is (see below).
5. `ld_dir(…, '*.ttl', NULL)`, `ld_dir(…, '*.nt', NULL)`, `rdf_loader_run()`, `checkpoint`.
6. Prints any row of `DB.DBA.load_list` that carries an error, then one
   `SPARQL SELECT (COUNT(*) …) FROM <graph>` per graph so you can see the triple counts.
7. Rebuilds the full-text index (`DB.DBA.RDF_OBJ_FT_RULE_ADD` plus
   `DB.DBA.VT_INC_INDEX_DB_DBA_RDF_OBJ`) that the keyword search (`bif:contains`) needs. Skip
   with `--skip-index`.

**The loader appends.** Virtuoso's `rdf_loader_run()` adds triples; it never replaces a
graph. That is how the pre-2023 identifiers survived a rename in production for years, and it
is why you always use `--clear` when reloading a graph you have already loaded.

**`--clear` stops at the custom-licenses graph.** `https://dalicc.net/customlicenses/` holds
the licenses people compose on the running instance. It is in no file of this repository, the
history in `licensedata/history/` does not cover it, and only a backup of the store brings it
back. Until 2026-09-23 the clear list was every graph of the run, so `--clear` plus
`--custom-licenses` emptied it and loaded the dump back over it; twice in September 2026 that
deleted every license composed since the dump was taken. The clear list is now built from the
files this repository ships, and emptying that graph takes `--clear-custom`, which is refused
unless `--custom-licenses` names the file that refills it:

```bash
scripts/load_data.sh --clear                                       # keeps the composed licenses
scripts/load_data.sh --clear --custom-licenses build/dump.nt       # keeps them, appends the dump
scripts/load_data.sh --clear --custom-licenses build/dump.nt --clear-custom   # replaces them
scripts/load_data.sh --clear-custom                                # refused: nothing would refill it
```

The second line is rarely what you want: the loader gives the blank nodes of the dump fresh
labels, so a dump appended on top of the licenses it was taken from duplicates every rule in
it. Take a fresh export first (section 6) and use the third line. Every run prints the clear
list and the current triple count of the custom graph before it clears anything, and
`--dry-run` prints the same plan without a container.

The dba password comes from `--password`, else `VIRTUOSO_DBA_PASSWORD`, else the image
default `dba` **with a loud warning**. It is passed to the container through `docker exec -e`,
so it does not appear in the host's process list or shell history.

Expected counts after a clean `--clear` load:

| Graph | Triples |
|---|---|
| `https://dalicc.net/licenselibrary/` | 54,017 |
| `https://dalicc.net/dependencygraph/dg_default` | 46 |
| `https://dalicc.net/ns` | 966 |
| `https://dalicc.net/customlicenses/` | 965 (from the 2026-09-09 production dump) |

`licensedata/reviews/`, `licensedata/history/` and `licensedata/spdx-mapping.json` are never
loaded.

---

## 6. Export, backup and restore

```bash
scripts/export_graphs.sh                        # all four graphs -> backups/<UTC date>/
scripts/export_graphs.sh --graph https://dalicc.net/customlicenses/
scripts/export_graphs.sh --method sparql        # no container access needed
```

`backups/` is gitignored: a graph dump may contain user-submitted data.

Two methods:

* **`isql`** (default). Installs `DB.DBA.dalicc_dump_one_graph`, the dump procedure from the
  Virtuoso documentation (it is not part of the `tenforce/virtuoso` image), calls it per
  graph and copies the result out with `docker cp`. Output is Turtle plus a `.graph` sidecar,
  exactly the pair `load_data.sh` consumes. Not subject to `ResultSetMaxRows`, and blank-node
  structure survives.
* **`sparql`**. A paged `CONSTRUCT` over HTTP written as N-Triples; needs only `curl`.
  Virtuoso's `[SPARQL] ResultSetMaxRows = 10000` caps one response, so the query is paged with
  `LIMIT`/`OFFSET` and an `ORDER BY`. Blank nodes come back as `nodeID://` labels that are
  stable inside one store but are not guaranteed to restore as the same nodes. Use it for
  inspection, not for archival.

Restore: copy a dumped `<name>.ttl` (or `.nt`) and its `.graph` sidecar into
`<container>:/data/ttl_dump` and run `ld_dir` plus `rdf_loader_run`, or, for the graphs this
repository owns, simply `scripts/load_data.sh --clear`.

**Put the license library in the backup rotation.** The 2026-09-09 production backup contained
N-Triples dumps of the custom-licenses and dependency graphs but *not* of the library; the
library existed only inside a 73 MB `virtuoso.db`.

### The custom licenses

The 62 user-composed licenses written by `POST /web/wpcomposer` live only in
`https://dalicc.net/customlicenses/`. They are **user data and are not in this repository**;
do not commit a dump.

The production dump does not parse: the composer wrapped unvalidated form input in
`URIRef()`, so six triples carry relative IRIs (`<test>`, `<None>`, `<AUSTRALIA>`,
`<proprietary>`). `scripts/restore_custom_licenses.py` repairs and cleans it:

```bash
python scripts/restore_custom_licenses.py \
    /path/to/backup/S_dalicc.net_customlicenses.nt \
    --output build/customlicenses.nt [--drop-empty]
scripts/load_data.sh --custom-licenses build/customlicenses.nt --clear --clear-custom
```

`--clear-custom` is what replaces that graph with the repaired dump; without it the dump is
appended and every rule in it is duplicated. Give it only when the dump is a current export
of the graph you are about to empty (section 5).

* A relative IRI in the object of `dct:title`, `dct:alternative` or `dct:publisher` becomes a
  plain literal: it was free text all along.
* A relative IRI anywhere else drops the triple: it has no meaning outside the document that
  produced it.
* `--drop-empty` discards records with no `odrl:permission`, no `odrl:prohibition`, no
  `odrl:duty` **and** no `dct:title`, together with their blank-node subtrees.
* Output is sorted N-Triples with the input's blank-node labels preserved, so two runs over
  the same dump produce identical bytes and a round-trip restore keeps node identity.

Result for the 2026-09-09 production dump (970 lines):

| | |
|---|---|
| triples kept | 965 |
| relative IRIs turned into literals | 1 (`dct:title <test>` → `"test"`) |
| triples dropped (relative `cc:license` object) | 5 |
| license records | 62 |
| records with no permission, no prohibition and no duty | 21 |
| records with no `dct:title` | 8 |
| records with neither a policy statement nor a title (what `--drop-empty` removes) | 0 |

The script also reports records whose title looks like a test submission and questionable
`cc:jurisdiction` values. Review the list before loading: roughly 85 % of this graph is test
or spam traffic, because the composer's reCAPTCHA token was never verified server-side.

---

## 7. Encoding conventions

* **UTF-8, no BOM**, on every file.
* **LF line endings**, and a **final newline**.
* `.gitattributes` pins `*.ttl`, `*.nt`, `*.py`, `*.html`, `*.md`, `*.sh` and more to
  `text eol=lf`, and marks fonts and images `binary`.
* `.editorconfig` sets UTF-8, LF and a final newline repository-wide, 4-space indent for
  Python and 2-space for YAML, JSON, HTML, CSS and JavaScript. Trailing-whitespace trimming is
  disabled for `.ttl`, `.nt` and `.n3`: those files are generated or hand-laid-out and must
  not be reflowed.
* `scripts/validate_data.py` fails the build on a BOM, a CR, or a missing final newline.
* Markdown in this repository never carries an SPDX header, and the data files never carry a
  long dash. ASCII punctuation only, in the data and in the review records.

---

## 8. Known data-quality issues

These are documented, not fixed: changing them changes published RDF. Each entry says what it
costs. The backlog entry for each is in IMPROVEMENT_PLAN.md.

### Missing values

| Issue | Records | Effect |
|---|---|---|
| No `spdx:licenseId` | **305 of 581** | no interoperability with SPDX-based tooling. Most of the 305 are jurisdiction ports that the SPDX license list does not define, and the 17 model licenses have no SPDX identifier at all, which is why the absence is deliberate rather than a gap to close |
| No `dct:publisher` | 71 | the record names no steward. Placeholder values such as `N.N.` and `- not specified - ` were removed rather than left to look like data |
| No `odrl:prohibition` | 40 | expected for the short permissive licenses; the list is `MIT`, `IscLicense`, `WTFPL`, `Unlicense` and 36 more of that shape |
| No `dct:alternative` | 4 | keyword search finds these only by their exact title: `DeveloperLicense`, `InspireEndUserLicence`, `SampleLicenseSl`, `StatisticsCanadaOpenLicenceAgreement` |
| No `dct:source`, no `cc:legalcode`, no `dct:modified` | 1 | `SampleLicenseSl`, the composer fixture: **no link to a license text at all**, because there is none |

### Modelling errors

| Issue | Where | Effect |
|---|---|---|
| Two `cc:license` values | `SampleLicenseSl.ttl` | the composer writes the author's "licensed under" choice to the same predicate the library uses for the record's own license. Both statements are true of the fixture, which is published under CC-BY-4.0 and was composed with MIT as the answer to that question, so the predicate is right and only the duplication is odd; see [the shape of one license](#shape-of-one-license) above |
| Stray `odrl:assignee "Sample Licensee"` | `SampleLicenseSl.ttl` | a one-off; not part of the model and not rendered anywhere |
| `dalicc:CreativeWork` alongside `dcmitype:Dataset` and `dcmitype:Software` | 378 records | mixes a proprietary term with a standard vocabulary; `dcmitype:Text`, `Image` and `Sound` would have served. At least defined in `dalicc-ns.ttl` with `rdfs:seeAlso` to the DCMI types |
| Two test fixtures ship as production data | `SampleLicenseSl`, `DeveloperLicense` | removing them would remove published IRIs, so both carry `dalicc:recordStatus dalicc:testFixture` instead and every listing, search and count leaves them out while `GET /licenselibrary/license/{id}` keeps resolving |
| 575 clause literals carry a padding space inside their quotation marks | 287 Creative Commons ports plus `SampleLicenseSl` | cosmetic, changes no compatibility answer, and it is the one family rule that is not clean (rule 14). Fixing it takes 288 records to a new version in one sweep, so it wants its own commit. The one on `LatexProjectPublicLicenseVersion13c` was stripped on 2026-09-23 |

### `http://` against `https://dalicc.net/ns#` in the live store

The production N-Triples dumps of the dependency graph disagree with the repository: the
older `P_` dump has seven triples under `http://dalicc.net/ns#` where the current data uses
`https://`. `strings` on `virtuoso.db` finds **both** schemes resident, and because the loader
appends, the live graph very likely holds both variants, so the compatibility checker may be
matching on one scheme and silently missing the other.

The repository is consistent: `https://dalicc.net/ns#` everywhere, enforced by
`validate_data.py`. The fix on a live store is `scripts/load_data.sh --clear`, which empties
the graph before loading and therefore evicts the legacy IRIs. Verify afterwards:

```sparql
SELECT (COUNT(*) AS ?c) FROM <https://dalicc.net/dependencygraph/dg_default>
WHERE { ?s ?p ?o . FILTER (CONTAINS(STR(?s), "http://dalicc.net/ns#")
                        || CONTAINS(STR(?p), "http://dalicc.net/ns#")
                        || CONTAINS(STR(?o), "http://dalicc.net/ns#")) }
```

It must return 0.

### The 2023-04-24 identifier rename

33 old identifiers are gone: 27 were replaced by another identifier, 25 of them SPDX-style,
and six were test records that were dropped. Because the loader appends and the graph was
never cleared, **both sets may still be resident in production**, and every old IRI is a
permanently broken external link either way. The superseded data is kept under
`licensedata/deprecated/` and is never loaded.

*Removed:* `AcademicFreeLicense30`, `AdaptivePublicLicense10`, `AGPL`,
`ApplePublicSourceLicense20`, `ArtisticLicense20`, `AttributionAssuranceLicense`,
`BoostSoftwareLicense10`, `BSD-2`, `BSD-3`, `BSD-4`, `CC-BY_v4`, `CC-BY-3.0-NL`,
`CC-BY-NC_v4`, `CC-BY-NC-ND_v4`, `CC-BY-NC-SA_v4`, `CC-BY-ND_v4`, `CC-BY-SA_v4`,
`ComputerAssociatesTrustedOpenSourceLicense11`, `EclipsePublicLicense20`,
`FreePublicLicense100`, `GNU_GPL_v2`, `GNU_GPL_v3`, `LGPLv3`, `MS-PL`,
`NonCommercialGovernmentLicence`, `OpenSoftwareLicenseV30`, `Wtfpl`, and the test records
`Example`, `Test`, `Testlicense`, `TestLicenseFromAlex`, `TassilosLicense`,
`MyPersonalDataLicense`.

*Added:* `AFL-3.0`, `APSL-2.0`, `Artistic-2.0`, `BSL-1.0`, `BSD-2-Clause`, `BSD-3-Clause`,
`BSD-4-Clause`, `CC-BY-4.0`, `CC-BY-NC-4.0`, `CC-BY-NC-ND-4.0`, `CC-BY-NC-SA-4.0`,
`CC-BY-ND-4.0`, `CC-BY-SA-4.0`, `CreativeCommonsAttribution30Netherlands`, `EPL-2.0`,
`GPL-2.0-only`, `GPL-3.0-only`, `LGPL-3.0-only`, `MicrosoftPublicLicense`, `OSL-3.0`,
`WTFPL`, `0BSD`, `AAL`, `AGPL-3.0`, `APL-1.0`, `CATOSL-1.1`, `NCGL-UK-2.0`.

`licensedata/retired-identifiers.yaml` is the redirect table. It lists all 33 old
identifiers with their old title and the successor, matched by title, by the legal code URL
and by the SPDX identifier of the successor record: 27 have a successor, and the six test
and personal records (`Example`, `MyPersonalDataLicense`, `TassilosLicense`, `Test`,
`TestLicenseFromAlex`, `Testlicense`) have `successor: null`. It is data about the data,
like `spdx-mapping.json`, and is never loaded into the store.

The table is consulted only when an identifier does not resolve on its own, so nothing that
resolves today changes (`Wtfpl` still resolves to the WTFPL record through the
case-insensitive file lookup and is listed only for completeness):

| Request | Retired, with a successor | Retired, without one | An SPDX identifier a record declares |
|---|---|---|---|
| `GET /license-library/<id>` | `301` to `/license-library/<successor>` | `410` page: "The identifier ... was retired on 2023-04-24. No record in the library replaces it." | `303` to `/license-library/<record>` |
| `GET /licenselibrary/license/<id>` | `301` to `/licenselibrary/license/<successor>`, query string kept | `410` with a JSON `detail` saying the same | `303` to `/licenselibrary/license/<record>`, query string kept |

`GET /licenselibrary/<id>`, the dereference of the canonical IRI, redirects to one of these
two and so reaches the successor as well. `app.services.licenses.retired_identifier` reads
the table, case-insensitively. Any other identifier that resolves to nothing answers `404`,
and the page offers a library search for it.

---

## 9. Dependency graphs as data

`licensedata/dependencygraph/dg_default.ttl` is the **core** graph, the one every caller
reasons with unless it chooses otherwise, and it is no longer the only one: seven further
graphs ship with the service, and anybody with an account can keep a graph of their own.

A graph holds two kinds of statement.

An **axiom** relates two actions: triples of three IRIs, a subject action, one of the four
relations, an object action, with no blank nodes and no literals. That is the whole of the
model this section described before the core graph gained its first default rule.

A **default rule** says what applies to an action a license is silent about. It is a node of
type `dalicc:DefaultRule` carrying five statements, and it exists because a record states what
its text states while most texts are silent about most acts:

```turtle
<https://dalicc.net/dependencygraph/rules/endorsement-worldwide> a dalicc:DefaultRule ;
    rdfs:label "Endorsement is not granted by default"@en ;
    dalicc:appliesTo dalicc:promote ;
    dalicc:defaultOutcome dalicc:NotGrantedByDefault ;
    dalicc:inJurisdiction dalicc:worldwide ;
    dalicc:ruleBasis "Trademark and name rights are separate from copyright: Regulation (EU) 2017/1001 article 9 ... The library's evidence is Creative Commons 4.0 section 2(b)(2): Patent and trademark rights are not licensed under this Public License. ..." ;
    dalicc:ruleExplanation "A license that says nothing about endorsement is read as not allowing it: ..."@en ;
    dct:date "2026-09-23"^^xsd:date ;
    dct:contributor "Giray Havur, for the association's review, adopted this rule on 2026-09-23" ;
    dct:dateAccepted "2026-09-23"^^xsd:date ;
    dalicc:ruleStatus dalicc:Adopted .
```

An adopted rule names who adopted it and when. The vocabulary has no reviewer property for
rules, so the rule carries `dct:contributor`, a literal with the reviewer's name, the body he
reviewed for and the date, and `dct:dateAccepted`, the date of adoption; `dct:date` stays the
date the rule was written. `scripts/validate_data.py` accepts both predicates in a dependency
graph. They live in the core file and in the store only: the rule model of
`app/services/consistency.py` has no field for them, so the generated jurisdiction graphs, the
rule editor and the `defaults` entries of the API do not carry them.

`dalicc:defaultOutcome` takes one of four values. `dalicc:NotGrantedByDefault`: the action is
not permitted unless the license permits it. `dalicc:GrantedByDefault`: it is permitted unless
the license prohibits it, which is what a statutory exception does. `dalicc:RequiredByDefault`:
a duty applies unless the license waives it. `dalicc:NotWaivable`: a statement of the license
to the contrary has no effect there, and the reasoner reports it as a finding rather than
overriding the record. "To the contrary" is a prohibition where the same graph also says the
action is granted by default, and a permission everywhere else: the law either keeps an
exception open that a license may not close, or keeps a protection in place that a license may
not give away.

`dalicc:ruleStatus` is `dalicc:Adopted` or `dalicc:Proposed`. The core graph carries adopted
rules only; a jurisdiction graph carries proposals, is never the default for any check, and is
reached only by a reader who chooses it. `scripts/validate_data.py` refuses the other way
round in either file. Nothing a rule states is legal advice.

Every rule carries two texts. `dalicc:ruleBasis` is the citation a reader can check;
`dalicc:ruleExplanation` is the reading of it in two or three plain sentences: what the rule
does to a license that is silent, why the law of that jurisdiction leads there, and what a
person combining licenses will notice. The explanation is shown next to the rule on the
graph pages, in the comparator and in every check result where the rule fired, and the
`defaults` entries of the API carry it as `explanation`. `scripts/validate_data.py` refuses
a shipped rule without both texts.

### Complete graphs and difference files

Every published dependency graph is **complete**: it holds every axiom and every default rule
a check under it reads, and the reasoner reads that one graph and follows no link. A
jurisdiction graph is nevertheless written down as a **difference** from the core graph,
because that is what a legal reviewer reads and what changes when a law changes:
`licensedata/dependencygraph/differences/<id>.ttl` (with a README) is its source of truth. It
holds the graph's metadata (`dct:title`, `dct:description`, the jurisdiction concept as
`dct:coverage` and `dalicc:basedOnGraph <dg_default>`), the default rules it adds, the core
axioms it removes and the core rules it replaces:

```turtle
<https://dalicc.net/dependencygraph/removals/xx-sellcopy-sell> a dalicc:AxiomRemoval ;
    rdf:subject dalicc:sellCopy ;
    rdf:predicate odrl:includedIn ;
    rdf:object odrl:sell ;
    dalicc:ruleBasis "the statute and article" ;
    dalicc:ruleExplanation "Why the axiom does not hold there."@en ;
    dalicc:ruleStatus dalicc:Proposed .

<https://dalicc.net/dependencygraph/rules/xx-endorsement> a dalicc:DefaultRule ;
    dalicc:replacesRule <https://dalicc.net/dependencygraph/rules/endorsement-worldwide> ;
    dalicc:appliesTo dalicc:promote ;
    dalicc:defaultOutcome dalicc:GrantedByDefault ;
    dalicc:inJurisdiction dalicc:XX ;
    dalicc:ruleBasis "the statute and article" ;
    dalicc:ruleExplanation "What changes against the core rule."@en ;
    dalicc:ruleStatus dalicc:Proposed .
```

No shipped difference removes an axiom or replaces a rule: the reviewer knows of no source
under which one of the 46 axioms or the endorsement rule fails in one of the seven markets,
and an invented example would put a claim about the law into the data. The two blocks above
are the syntax, from the README.

`scripts/build_dependency_graphs.py` reads `dg_default.ttl` and every difference file and
writes the complete `licensedata/dependencygraph/<id>.ttl` deterministically: the core file's
prefix block, a header comment naming the version, the core version and the difference file,
the metadata with `dalicc:basedOnVersion` and `dct:date`, the axioms in canonical order (the
core's without the removed ones), the rules (the core's without the replaced ones, then the
added and replacing ones), and the removal records, so a graph's page can say what it removes
and why. It refuses a removal of an axiom the core graph does not hold, a replacement of a rule
it does not hold or of a rule about another action, a rule or removal without its two texts,
and a result with two default rules of one kind for one action in one territory (a
`dalicc:NotWaivable` rule beside a rule that supplies a statement is how a graph says that an
exception cannot be contracted away, and is allowed). `--check` exits 1 when a generated file
is stale, and `validate_data.py` runs it. `--extract <id>` goes the other way, from a complete
graph and the core graph to the difference file, keeping the comment block of the file that is
there; for every shipped graph the two directions reproduce each other byte for byte, which a
test holds them to. The generated files are what the loader loads, the site serves and the
download hands out, each with its `.graph` sidecar.

**Versioning.** A generated graph is versioned like the core graph. When the build would
change what a generated graph states, either because the core graph got a new version (which
moves `dalicc:basedOnVersion`) or because its difference file changed, it refuses to overwrite
the file and exits 1 until `--bump` is given. `--bump` archives the previous file as
`licensedata/history/dependencygraph/<id>-v<n>.ttl`, adds the change-log entry of version
*n+1* to `<id>-changelog.yaml`, with every added, removed and changed statement and a summary
that names the cause ("Follows core graph version 3.", "The difference file added a rule."),
and writes the new version; `--summary`, `--reason`, `--reviewer` and `--date` override what it
would write. A change of the comments or the layout alone is written without a new version.
`sync_repository_version` then moves a running deployment's rows of all eight graphs at its
next start, as below.

| IRI | What lives there |
|---|---|
| `DALICC_DEPENDENCY_GRAPH` (default `https://dalicc.net/dependencygraph/dg_default`) | the curated default graph: 46 axioms and one adopted default rule |
| `https://dalicc.net/dependencygraph/dg_eu`, `dg_us`, `dg_cn`, `dg_gb`, `dg_jp`, `dg_in`, `dg_br` | complete graphs built from the core graph and a difference file each: the core axioms and the adopted core rule, plus the default rules proposed for one market; none of them a default |
| `https://dalicc.net/dependencygraph/{id}` | any other published graph, core or user |
| `https://dalicc.net/users/{user_id}/dependencygraphs/{id}` | a graph somebody is working on; private, like a license draft |

The census of the shipped graphs, on 2026-09-24:

| Graph | Title | Version | Axioms | Default rules | Adopted |
|---|---|---|---|---|---|
| `dg_default` | DALICC deontic dependency graph | 3 | 46 | 1 | 1 |
| `dg_eu` | European Union default rules | 3 | 46 | 1 + 9 | 1 (the core's) |
| `dg_us` | United States default rules | 3 | 46 | 1 + 2 | 1 (the core's) |
| `dg_cn` | China default rules | 3 | 46 | 1 + 2 | 1 (the core's) |
| `dg_gb` | United Kingdom default rules | 3 | 46 | 1 + 5 | 1 (the core's) |
| `dg_jp` | Japan default rules | 3 | 46 | 1 + 3 | 1 (the core's) |
| `dg_in` | India default rules | 3 | 46 | 1 + 3 | 1 (the core's) |
| `dg_br` | Brazil default rules | 3 | 46 | 1 + 3 | 1 (the core's) |

Version 2 of the seven (2026-09-24) is complete, generated from version 2 of the core graph;
none of them removes an axiom or replaces a rule. Version 2 of the core graph is the one that
gives its rule the explanation. Version 3 of all eight (2026-09-24) is the review of the rules
against the statutes they cite: the core rule cites its basis and names who adopted it, and 22
of the 27 jurisdiction rules had their explanation, basis or label corrected, each keeping its
outcome and its status ([LICENSE_REVIEW.md](LICENSE_REVIEW.md#the-review-of-the-rules-against-their-statutes)).

A graph's title names the graph and nothing else. Version 1 of the seven jurisdiction
graphs ended every title in "(proposal)", which read as if the graph itself were
unpublished; version 2 (2026-09-24) names them plainly, and the status lives where it
belongs, on each rule as `dalicc:ruleStatus`. Every page that lists rules shows it beside
the rule, and a finding a rule supplied says "by default rule (proposed)" or "by default rule
(adopted)". `scripts/validate_data.py` refuses a shipped graph whose `dct:title` says
proposal.

[LICENSE_REVIEW.md](LICENSE_REVIEW.md#13-default-rules-and-jurisdictions) lists every rule
with the statute or principle it rests on.

`GET /dependencygraph/list` answers with the axioms and nothing else, exactly as it always
has; `GET /dependencygraph/rules` is the additive endpoint for the other kind of statement.

A graph is written as a whole: the named graph is cleared and re-inserted. Nothing else ever
shares one of these graphs, so there is no subject-scoped delete as there is for a license
document.

The RDF stays in Virtuoso; the account database holds only who owns what: `dependency_graphs`
(one row per graph: owner, creator, kind `core` or `user`, status, visibility, title,
description, version chain, named-graph IRI), `dependency_graph_members`,
`dependency_graph_revisions` (a snapshot per draft save) and `dependency_graph_versions` (a
snapshot plus a change-log entry per published version). See USERS.md.

The versions of a core graph live in two places and are shown as one sequence: in the
repository as `licensedata/history/dependencygraph/dg_default-v<n>.ttl` and `changelog.yaml`
for `dg_default`, and `<id>-v<n>.ttl` and `<id>-changelog.yaml` for the seven jurisdiction
graphs (each at version 2), exactly as section 4 describes, and in the
runtime store as one `dependency_graph_versions`
row per version an administrator published on the deployment. `make export-library` writes the
runtime half back:

```
licensedata/dependencygraph/<id>.ttl                     the graph as it is now, complete
licensedata/history/dependencygraph/<id>-v<n>.ttl        every superseded version
licensedata/history/dependencygraph/changelog.yaml       dg_default, files and runtime merged
licensedata/history/dependencygraph/<id>-changelog.yaml  any other core graph
```

The export compares bytes before writing, so it is idempotent. The workflow for changing the
curated graph on a deployment is therefore: edit it at
`/my/dependency-graphs/dg_default/edit` and publish version *n+1* with a summary and a reason;
run `make export-library` on that deployment; review the diff of `licensedata/` and commit it.
For a jurisdiction graph the export writes the complete graph, and
`python scripts/build_dependency_graphs.py --extract <id>` then folds it back into its
difference file, after which `--bump` regenerates it; see
ADMINISTRATION.md.

A graph a **user** published is never exported: it belongs to them, not to the curated data
set.

The version a deployment reports for a shipped graph is the one in its `dependency_graphs`
row, and that row is written once, at the first start, from the archived files present then. A
deployment that keeps its accounts database across an upgrade would therefore keep reporting
the old number after a commit ships a newer graph, so `app/main.py` moves every shipped row at
every start (`depgraph_history.sync_shipped_graphs`): each follows `current_version` in its
change log (`changelog.yaml` for `dg_default`, `<id>-changelog.yaml` for the others) as soon
as that file names a higher number. The number moves, and for a jurisdiction graph the title
and the description the repository ships move with it, which is how a deployment registered
on 2026-09-23 loses "(proposal)" from its selectors; the change-log entries are read from the
file anyway and become visible the moment the number does. A version published on this deployment and not
yet exported stops the move, since a file of the same number would otherwise hide what an
administrator published here; the row keeps its number, the log names both, and
`make export-library` is the way out.

A row can also be **above** the repository: a database written before the squash of section 4
holds `dg_default` at a number from 3 to 6 and a jurisdiction graph at 3, while the repository
ships 2 after the squash. The row follows the repository down, to the newest version it ships,
only when the version 2 entry of the change log carries the marker `squashed_from` and names
the row's number in it, when the server published no version
the marker does not name, and when what the server stores for the row's version (if it stores
anything) states the axioms and the rules the repository's graph states. The server's own
rows of the merged versions are then deleted, because the repository numbers those states no
longer. Otherwise the row stays and the log says why.

Curated license records have no such row and need no such step. What a record says about
itself is its own `dct:hasVersion`, read from the document the deployment loads out of
`licensedata/licenses/`, and `core_versions` holds only the versions published on this server,
from version 2 upwards, which `app/services/history.py` folds into the merged change log. A
record bumped in the repository is therefore reported at its new version as soon as the data
is loaded (section 5), with nothing to synchronise. The one asymmetry is the same rule as
above: while a record has a runtime version that has not been exported, that version is served
in place of the file, so the export is again what lets the repository take over.
