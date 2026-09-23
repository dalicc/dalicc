# DALICC data layer

The reference for `licensedata/`: what each directory and file holds, how a licence record
is modelled, and how to add or change one. For anyone editing the data or the scripts that
build, validate, load and export it.

Part of the [documentation index](../README.md#documentation).

This document is shared with the DALICC service repository, where the data is edited and
where the service that serves it is developed. It therefore names things that are not in
this repository: paths beginning with `app/` are modules of that service, and a handful
of the scripts it names are the ones that export a running deployment's corrections back
into the data, apply the decisions of the 2026 content review, or refresh the contract
snapshots of the API. They are named so that you can see where the data comes from and
where it is read. What is here is the data itself, the reasoner, and the checks that
prove the data is sound, which `README.md` lists and `make check` runs.

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
│   ├── dg_default.ttl                                46 reasoning axioms + 1 default rule (version 5)
│   ├── dg_default.ttl.graph      → https://dalicc.net/dependencygraph/dg_default
│   ├── dg_eu|us|cn|gb|jp|in|br.ttl                   the default rules proposed for one market each
│   └── dg_<id>.ttl.graph         → https://dalicc.net/dependencygraph/dg_<id>
├── vocabulary/
│   ├── dalicc-ns.ttl                                 the DALICC vocabulary, 132 terms (version 7)
│   ├── dalicc-ns.ttl.graph       → https://dalicc.net/ns
│   └── usage-counts.json                             how often each term is used (GENERATED)
├── history/                                          the model history; never loaded into the store
│   ├── licenses/<id>/v<n>.ttl                        each superseded version of a record
│   ├── licenses/<id>/changelog.yaml                  what every version changed, and why
│   ├── dependencygraph/dg_default-v<n>.ttl + changelog.yaml
│   └── vocabulary/dalicc-ns-v<n>.ttl       + changelog.yaml
├── reviews/                       581 × <id>.yaml    the review record of one license
├── spdx-mapping.json              DALICC id ↔ SPDX id, both directions (GENERATED)
├── deprecated/                    pre-2023-04-24 identifiers and Drupal-era exports, never loaded
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
| `https://dalicc.net/customlicenses/` | **runtime only**, written when a licence is published | `/licenselibrary/license/{id}` fallback for composed licenses |
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
the whole licence in words. A record of the library points at the authoritative text with
`cc:legalcode` and quotes single clauses in the clause properties below; a license
composed with the License Composer may carry the text written for it, and its license
page renders that text after the clauses. It is a plain `xsd:string`, one per record, and
a license without one reads exactly as it always did.

`cc:license` on a record is the license of the **record**, not the license the record
models: every record carries `cc:license dalicclib:CC-BY-4.0`, which is what
`licensedata/LICENSE` says in prose.

The composer writes the same predicate. Its question "Under which license do you provide
your license?" asks for the license of the document the author is about to publish, which
is the very thing `cc:license` states, so a composed license carries the author's choice
there and a curated record carries CC-BY-4.0. A record that has the predicate twice was
composed from a record that already had one: the only one in the library is the fixture
`SampleLicenseSl`, and it is listed under [modelling errors](#modelling-errors) below.
Read `cc:license` as "the terms this document is published under" and never as "the
terms this document grants".

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
    dalicc:licenseVersion     "3.0" ;                 # of the licence text, not of the model
    cc:jurisdiction           bpicounty:Norway .
```

| Predicate | Records | Meaning |
|---|---|---|
| `dalicc:jurisdictionPortOf` | 290 | the record this one was adapted from. A sub-property of `dct:isVersionOf`, because the library holds no unported 2.0 or 3.0 record: the parent of every Creative Commons port is the **4.0 International** record of the same element set, so the relation carries a version difference as well as a jurisdiction difference |
| `dalicc:licenseVersion` | 351 | the version of the *licence text* the record models, so that the version difference above stays readable (`"2.0"` on 96 records and `"3.0"` on 224; on the 287 ports alone, 77 and 210). `dct:hasVersion` carries the version of the DALICC **model**, and the two meanings do not share a term |
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

**The Creative Commons ports are deontically identical to their parents.** Every one of them
carries exactly the permissions, duties, prohibitions and license-wide duties of its parent,
statement for statement, so the compatibility checker cannot tell them apart. The one field
where ports still differ is `odrl:target`: a port whose text licenses or waives a database
right carries `dcmitype:Dataset`, a port whose text is silent about databases does not.
Grouping them belongs in the presentation layer; see `app/services/ports.py` and the
`ports=include|exclude|only` parameter in API.md.

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
license text to check it against at all.

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
| | | | `dalicc:terminatesOnBreach` | 145 | 145 |
| | | | `cc:attributionName` | 95 | 95 |
| | | | `dalicc:WarrantyOrLiabilityAcceptance` | 62 | 62 |
| | | | `dalicc:orLaterVersionOption` | 58 | 58 |
| | | | `dalicc:reciprocityScope` | 47 | 47 |
| | | | `dalicc:curePeriod` | 43 | 43 |
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
| 1,448 | `cc:Notice` | attach or clearly refer to the license when distributing the work |
| 1,388 | `cc:Attribution` | give credit to the copyright holder(s) and author(s) |
| 735 | `dalicc:modificationNotice` | document every change and how the result differs from the original |
| 581 | `odrl:derive` | create a new work from the existing one (translation, adaptation, ...) |
| 581 | `odrl:distribute` | provide the work to the public or make it accessible to anyone else |
| 581 | `odrl:reproduce` | make duplicate copies of the work in any form |
| 579 | `cc:CommercialUse` | income-generating use of any kind, direct or indirect |
| 567 | `dalicc:ChangeLicense` | change, extend or replace the license terms |
| 565 | `odrl:display` | create a static, transient rendition of the work |
| 564 | `odrl:present` | publicly perform the work |
| 541 | `dalicc:chargeDistributionFee` | charge a fee for distributing the work |
| 363 | `dalicc:promote` | use the licensor's trademark for advertising and promotion |
| 475 | `odrl:modify` | alter the work without substantially changing it (otherwise: `odrl:derive`) |
| 475 | `cc:DerivativeWorks` | distribute the derivative and make it available to the public |
| 458 | `dalicc:ModifiedWorks` | distribute the modified version of the work |
| 401 | `dalicc:sublicense` | grant a third party a license of one's own, under the license received |
| 318 | `cc:SourceCode` | provide access to the source code when distributing |
| 312 | `cc:ShareAlike` | relicense the work, or the part the license names, under the original license |
| 119 | `dalicc:addStatement` | attach additional terms or notices when redistributing |
| 119 | `dalicc:compliantLicense` | the replacement license must stay compliant with the original |
| 98 | `dalicc:suiGenerisDatabaseRights` | exercise the database right in the contents of a licensed database |
| 91 | `dalicc:patentGrant` | the express patent license a contributor grants |
| 77 | `dalicc:patentRetaliationTermination` | a patent claim over the work ends the grant |
| 70 | `dalicc:rename` | give the modified work a name of its own |
| 49 | `dalicc:chargeLicenseFee` | charge a fee for granting a license |
| 42 | `odrl:grantUse` | pass the license on to a third party (the same act as `dalicc:sublicense`) |
| 36 | `dalicc:noWarrantyNotice` | attach, or pass on, a notice that the work carries no warranty |
| 30 | `dalicc:networkUseTrigger` | running the work over a network fires the duties the licence attaches |
| 25 | `dalicc:includeNoticeFile` | carry a named NOTICE file forward |
| 22 | `dalicc:addLimitation` | add a restriction downstream |
| 18 | `dalicc:exceptedCombination` | combine the work as an SPDX exception allows, outside the condition it lifts |
| 17 | `dalicc:useForModelTraining` | use the material to train an automated system |
| 13 | `dalicc:exemptedMaterial` | use material the licence carves out of its grant |
| 20 more, each with fewer than 13 triples | | `dalicc:originalVersionOffer`, `dalicc:exportControlNotice`, `dalicc:royaltyCollectionReserved`, `dalicc:sellCopy`, `dalicc:applyTechnicalProtectionMeasures`, `dalicc:recipientAssent`, `dalicc:contributionGrantBack`, `dalicc:moralRightsRestriction`, `dalicc:patentFreedomCondition`, `dalicc:advertisingAcknowledgement`, `dalicc:provideUserData`, `dalicc:moralRightsNonAssertion`, `dalicc:standardsConformance`, `dalicc:covenantNotToSue`, `dalicc:computationalUseOnly`, `dalicc:publicationNonObstruction`, `dalicc:patentNotice`, `dalicc:trademarkNotice`, `dalicc:recipientRegistrationRequest`, `dalicc:conditionalAddLimitation` |

Every one of the 53 is defined in the DALICC vocabulary or comes from ODRL or Creative
Commons. `odrl:action dct:source`, which the GNU Free Documentation records carried and
`validate_data.py` warned about, is gone: the three duty nodes were removed on 2026-09-23
and `cc:SourceCode`, which sat beside each of them, carries the rule.

### The dependency graph

`licensedata/dependencygraph/dg_default.ttl` holds the axioms the compatibility checker
reasons with: 46 triples over four relations, hand-maintained, no blank nodes and no
literals. Since version 5 it also holds one default rule, which is a different kind of
statement and is described in [section 9](#9-dependency-graphs-as-data). It is at version 5;
versions 1 to 4 and the change log are in `licensedata/history/dependencygraph/`.

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

### The DALICC vocabulary

`licensedata/vocabulary/dalicc-ns.ttl` defines **132 terms** in 1217 triples. Each carries
`rdf:type`, `rdfs:label@en`, `rdfs:comment@en`, `rdfs:isDefinedBy <https://dalicc.net/ns#>`
and, where an ODRL or CC counterpart exists, `rdfs:seeAlso`.

| Kind | Count | How it is typed |
|---|---|---|
| Actions | 49 | `odrl:Action` and `skos:Concept`, plus `dalicc:RuleAction` (29) when the term may be the action of a permission or a prohibition and `dalicc:DutyAction` (23) when it may be the action of a duty. Three are both; an action typed neither is read as a rule action |
| Classes | 14 | `owl:Class`: the asset types `dalicc:CreativeWork` and `dalicc:Hardware`, the classifiers `dalicc:AssetType`, `dalicc:Jurisdiction`, `dalicc:ValidityType`, `dalicc:DependencyRelation`, `dalicc:RecordStatus`, `dalicc:ReviewStatus`, `dalicc:RuleAction`, `dalicc:DutyAction`, and the four of the default-rule layer: `dalicc:DefaultRule`, `dalicc:DefaultOutcome`, `dalicc:RuleStatus`, `dalicc:StatementOrigin` |
| Datatype properties | 13 | the clause properties (`dalicc:WarrantyDisclaimer`, `dalicc:LiabilityLimitation`, `dalicc:WarrantyOrLiabilityAcceptance`, `dalicc:additionalClauses`, `dalicc:PromotionSpecification`, `dalicc:licenseOwner`), `dalicc:licenseText` and the boolean and literal qualifiers, all with `rdfs:domain odrl:Set` |
| Object properties | 9 | `dalicc:validityType`, `dalicc:jurisdictionPortOf`, `dalicc:translationOf`, `dalicc:variantOf`, `dalicc:recordStatus`, `dalicc:reviewStatus`, `dalicc:versionHistory`, `dalicc:composedOf` and `dalicc:contradicts`, which is also `owl:SymmetricProperty` |
| Annotation properties | 9 | the per-record annotations such as `dalicc:curePeriod`, `dalicc:governingLaw` and `dalicc:compatibleLicenseTest` |
| Policy qualities and controlled values | 14 | `skos:Concept` only: `dalicc:perpetual`, `dalicc:worldwide`, `dalicc:irrevocable`, `dalicc:patentFree`, `dalicc:royaltyFree`, `dalicc:specifyDate`, `dalicc:specifyPeriod`, `dalicc:terminationOnBreach`, the deprecated `dalicc:royalityFree`, the four `dalicc:ReviewStatus` values and `dalicc:testFixture` |

Version 5 added one term, `dalicc:licenseText`. It holds the full text of a licence as its
licensor publishes it, on the record itself. A curated record does not carry it: it points
at the authoritative text with `cc:legalcode` and quotes single clauses in the clause
properties. A licence composed with the License Composer may carry it, because the composer
writes the licence text into the form and keeps it with the licence.

Version 6 adds two, for the records of the licences GitHub projects use.
`dalicc:variantOf` is the object property that names the record a version option, an
exception combination or a rider varies, and the comment of `dalicc:variantKind` gained the
three values that go with it. `dalicc:exceptedCombination` is the rule action of an SPDX
exception: combining or linking the covered work with the material the exception names and
conveying the result without the condition the exception lifts. It is the counterpart of
`dalicc:exemptedMaterial`, which keeps its one meaning, material the grant does not reach at
all, and which the exception records used to carry in the opposite position.

Version 7 adds the terms for what a licence does **not** say. `dalicc:DefaultRule` is a rule
about an action a licence is silent on; it names the action with `dalicc:appliesTo`, the
conclusion with `dalicc:defaultOutcome` (`dalicc:NotGrantedByDefault`,
`dalicc:GrantedByDefault`, `dalicc:RequiredByDefault` or `dalicc:NotWaivable`), the territory
with `dalicc:inJurisdiction`, the statute or principle with `dalicc:ruleBasis` and its state
with `dalicc:ruleStatus` (`dalicc:Adopted` or `dalicc:Proposed`). `dalicc:statementOrigin`
says of a statement in a result whether it is `dalicc:FromText` or `dalicc:FromDefaultRule`;
it is never written into a curated record. `dalicc:extendsGraph` relates one dependency graph
to another it is read together with. Seven region jurisdictions, `dalicc:EU`, `dalicc:US`,
`dalicc:CN`, `dalicc:GB`, `dalicc:JP`, `dalicc:IN` and `dalicc:BR`, name their members with
`skos:member` and the BPI country IRIs the records use. Two actions came with them because
the jurisdiction proposals had nothing to name: `dalicc:textAndDataMining`, the automated
analysis the European and British mining exceptions describe, and
`dalicc:reverseEngineerForInteroperability`, decompiling only so far as interoperability
needs. Neither is used by a record, so neither is offered for authoring.

Every superseded version is archived next to its change log, as
`licensedata/history/vocabulary/dalicc-ns-v<n>.ttl`, and the change log says why each term
was added.

**The file is the source of truth, not a second copy of one.** `app/services/vocab.py` reads
every `dalicc:` term from it at import: the label, the definition and the classification.
Defining a term here is all it takes for the composer, `GET /licenselibrary/actions`,
`input_from_graph` and the consistency check to accept it. The module supplies only the ODRL
and Creative Commons terms, which the file does not define, and the plain-language
descriptions that read better in a drop-down than a legal definition does.

#### Where the definitions come from

| Source | Carried as | Covers |
|---|---|---|
| The DALICC vocabulary documentation published at <https://dalicc.github.io/> (`index.md`, last updated 2022-03-15, served as `docs.dalicc.net`) | `rdfs:comment@en`, **verbatim**, with `dct:source <https://dalicc.github.io/>` | 23 `dalicc:` terms, lawyer-written |
| The help texts of the original DALICC license composer | `skos:definition@en` where a documentation definition already occupies `rdfs:comment`, otherwise `rdfs:comment@en` | the terms the documentation never covered, and a plain-language gloss for the ones it did |

Where both exist the lawyer-written text wins. One verbatim oddity is preserved on purpose:
`dalicc:promote` ends in a double full stop, exactly as published.

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

#### The one deprecated term

The 2022 documentation misspells "royalty". Both IRIs are defined:

* `dalicc:royaltyFree` is canonical: the same verbatim definition, with `dct:replaces` and
  `skos:exactMatch` pointing at the alias;
* `dalicc:royalityFree` is kept with `owl:deprecated true`,
  `dct:isReplacedBy dalicc:royaltyFree`, `skos:exactMatch` and an explanatory `skos:note`.
  Deleting it would break any data written against the published documentation, so it stays
  and `GET /ns/royalityFree` keeps resolving.

`validate_data.py` enforces the pattern: every `owl:deprecated` term must name a defined
replacement with `dct:isReplacedBy`, and a deprecated term that turns up in the data raises
a warning.

#### The usage notes are generated, not asserted

Two kinds of `skos:note` make a claim about the library, and both go stale the moment a
record starts using the term:

* "Defined in the 2022 documentation; not used by any license in the current library." is on
  9 terms: `attachoffer`, `attributionNotice`, `chargeOffer`, `irrevocable`, `patentFree`,
  `permissionNotice`, `publish`, `redistribute`, `royaltyFree`. They are part of the
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

Two kinds of identifier were added with the records of the licences GitHub projects use.
The 18 records that model a licence with an SPDX exception declare an **expression** rather
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
6. The dependency graph parses, uses only `https://dalicc.net/ns#` (never `http://`) and only
   the four known relations.
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
└── vocabulary/dalicc-ns-v<n>.ttl       + changelog.yaml
```

343 records are past version 1 and 412 archived version files exist. An archived version is
the **committed file, byte for byte**, never an rdflib re-serialisation: the hand-curated
Turtle layout is part of what was published, and a reader comparing two versions should see
the change and not thousands of renamed blank nodes.

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

The 412 entries hold 3,167 changes. Every one of the 2,951 changes recorded at version 2
names a finding or a decision; only the 216 later hand edits carry `manual`.
`scripts/review/build_history.py` prints anything it cannot attribute, and a unit test
asserts that list is empty.

### What a record says about itself

```turtle
dalicclib:Apache-2.0
    dct:hasVersion      "2" ;                     # of the DALICC model
    dct:modified        "2026-09-15"^^xsd:date ;
    dalicc:versionHistory <https://dalicc.net/licenselibrary/Apache-2.0/versions> .
```

`dct:hasVersion` is the version of the **model**, exactly as it already was on a license
composed with the License Composer. It is always one more than the number of archived
versions, which is what makes the two representations impossible to drift apart. 238 records
are at version 1 and archive nothing, 299 are at version 2, 20 at version 3, 23 at version 4
and one at version 5.

The version of the **licence text** is a different fact and has its own term,
`dalicc:licenseVersion` (`"3.0"` on a Creative Commons 3.0 port).

A jurisdiction port is a record like any other: its own history, its own `dct:hasVersion`,
its own change log. A port is never versioned *through* its parent, because the two are
separate published URIs and may be corrected at different times. The dependency graph carries
a comment naming its version, and the vocabulary says so in its ontology header:

```turtle
<https://dalicc.net/ns#> a owl:Ontology ;
    dct:hasVersion  "6" ;
    owl:versionInfo "6.0" ;
    owl:priorVersion <https://dalicc.net/ns/versions/1> ,
        <https://dalicc.net/ns/versions/2> ,
        <https://dalicc.net/ns/versions/3> ,
        <https://dalicc.net/ns/versions/4> ,
        <https://dalicc.net/ns/versions/5> ,
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
python scripts/review/family_rules.py --strict   # the eighteen family rules
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
`--dry-run` reports without writing, `--reviewer` sets the name (it defaults to "Giray
Havur"), and `--base-file <path>` overrides what the new version supersedes, for the one case
`HEAD` gets wrong: a pass that corrects a record a second time before the first correction is
committed.

### The gate

`validate_data.py` proves that for every record `dct:hasVersion` equals one plus the number
of archived versions, that the archived versions are numbered `1..n` and all parse, that
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
| No `spdx:licenseId` | **305 of 581** | no interoperability with SPDX-based tooling. Most of the 305 are jurisdiction ports that the SPDX license list does not define, and the 17 model licences have no SPDX identifier at all, which is why the absence is deliberate rather than a gap to close |
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
| 575 clause literals carry a padding space inside their quotation marks | 287 Creative Commons ports plus `SampleLicenseSl` | cosmetic, changes no compatibility answer, and it is the one family rule that is not clean (rule 14). Fixing it takes 287 records to a new version in one sweep, so it wants its own commit. The one on `LatexProjectPublicLicenseVersion13c` was stripped on 2026-09-23 |

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

A redirect table from old to new identifiers would turn 33 dead links into 301s. It does not
exist yet.

---

## 9. Dependency graphs as data

`licensedata/dependencygraph/dg_default.ttl` is the **core** graph, the one every caller
reasons with unless it chooses otherwise, and it is no longer the only one: seven further
graphs ship with the service, and anybody with an account can keep a graph of their own.

A graph holds two kinds of statement.

An **axiom** relates two actions: triples of three IRIs, a subject action, one of the four
relations, an object action, with no blank nodes and no literals. That is the whole of the
model this section described until version 5 of the core graph.

A **default rule** says what applies to an action a license is silent about. It is a node of
type `dalicc:DefaultRule` carrying five statements, and it exists because a record states what
its text states while most texts are silent about most acts:

```turtle
<https://dalicc.net/dependencygraph/rules/endorsement-worldwide> a dalicc:DefaultRule ;
    rdfs:label "Endorsement is not granted by default"@en ;
    dalicc:appliesTo dalicc:promote ;
    dalicc:defaultOutcome dalicc:NotGrantedByDefault ;
    dalicc:inJurisdiction dalicc:worldwide ;
    dalicc:ruleBasis "trademark law and the protection of names: a copyright licence that is silent grants no right to endorsement" ;
    dct:date "2026-09-23"^^xsd:date ;
    dalicc:ruleStatus dalicc:Adopted .
```

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

`dalicc:extendsGraph` relates a graph to one it is read together with, one step. A
jurisdiction graph holds its own rules and takes the 46 curated axioms and the adopted
endorsement rule from the core graph, so the axioms stay written in one place and the next
graph review edits one file rather than eight.

| IRI | What lives there |
|---|---|
| `DALICC_DEPENDENCY_GRAPH` (default `https://dalicc.net/dependencygraph/dg_default`) | the curated default graph: 46 axioms and one adopted default rule |
| `https://dalicc.net/dependencygraph/dg_eu`, `dg_us`, `dg_cn`, `dg_gb`, `dg_jp`, `dg_in`, `dg_br` | the default rules proposed for one market each, read together with the core graph; every one of them a proposal and none of them a default |
| `https://dalicc.net/dependencygraph/{id}` | any other published graph, core or user |
| `https://dalicc.net/users/{user_id}/dependencygraphs/{id}` | a graph somebody is working on; private, like a license draft |

The census of the shipped graphs, on 2026-09-23:

| Graph | Axioms | Default rules | Adopted |
|---|---|---|---|
| `dg_default` | 46 | 1 | 1 |
| `dg_eu` | from the core graph | 9 | 0 |
| `dg_us` | from the core graph | 2 | 0 |
| `dg_cn` | from the core graph | 2 | 0 |
| `dg_gb` | from the core graph | 5 | 0 |
| `dg_jp` | from the core graph | 3 | 0 |
| `dg_in` | from the core graph | 3 | 0 |
| `dg_br` | from the core graph | 3 | 0 |

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

The versions of `dg_default` live in two places and are shown as one sequence: in the
repository as `licensedata/history/dependencygraph/dg_default-v<n>.ttl` and `changelog.yaml`,
exactly as section 4 describes, and in the runtime store as one `dependency_graph_versions`
row per version an administrator published on the deployment. `make export-library` writes the
runtime half back:

```
licensedata/dependencygraph/<id>.ttl                     the axioms the graph has now
licensedata/history/dependencygraph/<id>-v<n>.ttl        every superseded version
licensedata/history/dependencygraph/changelog.yaml       dg_default, files and runtime merged
licensedata/history/dependencygraph/<id>-changelog.yaml  any other core graph
```

The export compares bytes before writing, so it is idempotent. The workflow for changing the
curated graph on a deployment is therefore: edit it at
`/my/dependency-graphs/dg_default/edit` and publish version *n+1* with a summary and a reason;
run `make export-library` on that deployment; review the diff of `licensedata/` and commit it.

A graph a **user** published is never exported: it belongs to them, not to the curated data
set.

The version a deployment reports for `dg_default` is the one in its `dependency_graphs` row,
and that row is written once, at the first start, from the archived files present then. A
deployment that keeps its accounts database across an upgrade would therefore keep reporting
the old number after a commit ships a newer graph, so `app/main.py` moves the row at every
start: it follows `current_version` in
`licensedata/history/dependencygraph/changelog.yaml` as soon as that file names a higher
number. Only the number moves, because the change-log entries are read from the file anyway
and become visible the moment the number does. A version published on this deployment and not
yet exported stops the move, since a file of the same number would otherwise hide what an
administrator published here; the row keeps its number, the log names both, and
`make export-library` is the way out.

Curated license records have no such row and need no such step. What a record says about
itself is its own `dct:hasVersion`, read from the document the deployment loads out of
`licensedata/licenses/`, and `core_versions` holds only the versions published on this server,
from version 2 upwards, which `app/services/history.py` folds into the merged change log. A
record bumped in the repository is therefore reported at its new version as soon as the data
is loaded (section 5), with nothing to synchronise. The one asymmetry is the same rule as
above: while a record has a runtime version that has not been exported, that version is served
in place of the file, so the export is again what lets the repository take over.
