# DALICC license library content review

The record of how every license in `licensedata/licenses/` was checked against its legal
text, what that changed, and what is still undecided. For anyone correcting a record,
deciding one of the open questions, or judging how far the data can be trusted.

Part of the [documentation index](../README.md#documentation).

Contents: 1. method; 2. results; 3. the family map; 4. the seventeen consolidation
decisions; 5. the modelling rules the standard licenses settled; 6. **open issues**;
7. vocabulary gaps; 8. two readings that were reversed; 9. the family rules; 10. the scripts;
11. the licences GitHub projects use; 12. the dependency graph review.

Reviewer: Giray Havur. Review date: 2026-09-15, with the addition of
[section 11](#11-licences-github-projects-use) on 2026-09-22 and
[section 12](#12-the-dependency-graph-review) on 2026-09-23. Companion to
[DATA.md](DATA.md), which documents the model this report refers to. **Nothing in this
document is legal advice.**

The per-record audit trail is `licensedata/reviews/<id>.yaml`, one file per license, and it
is the authority for anything this summary compresses. Its schema is documented in
[`licensedata/reviews/README.md`](../licensedata/reviews/README.md).

---

## 1. Method

Each record is checked on ten points and every point is recorded as a finding. The rubric,
the four severities (`major`, `minor`, `gap`, `info`), the three actions (`applied`,
`proposed`, `none`), the five verdicts and the corrections policy are defined in
[`licensedata/reviews/README.md`](../licensedata/reviews/README.md), and this review follows
them without exception.

The reading worked from the record itself; the legal text, fetched from the record's own
`cc:legalcode` wherever it resolved and otherwise from the SPDX license list text or an
archive snapshot of the same URL; the DALICC vocabulary,
`licensedata/vocabulary/dalicc-ns.ttl`; the modelling conventions in [DATA.md](DATA.md); and
`app.services.composer.consistency_check`, run with
`licensedata/dependencygraph/dg_default.ttl`.

A change is applied directly only where the license text supports it without interpretation.
Everything interpretive is recorded as a proposal with the exact triples to add or remove,
and left to the owner. **No record is ever deleted and no identifier or IRI is ever
changed**, because every identifier is a published IRI.

---

## 2. Results

Over the 581 records and their 581 review files, the 2026-09-15 review and the addition of
[section 11](#11-licences-github-projects-use) together:

| | Count |
|---|---|
| Records | 581 |
| Legal texts retrieved | 580 |
| Findings recorded | 8,410 |
| of them `major` | 1,461 |
| of them `minor` | 1,494 |
| of them `gap` | 1,474 |
| of them `info` | 3,981 |
| Findings **applied** | 2,513 |
| Findings **proposed** and left to the owner | 825 |

| Verdict | Records | Meaning |
|---|---|---|
| `corrected` | 342 | one or more text-supported changes were applied |
| `created` | 237 | the record did not exist and was written from the legal text |
| `correct` | 1 | the record matched its text and the conventions; nothing changed |
| `text-unavailable` | 1 | `SampleLicenseSl`, the composer fixture: there is no text to check it against |

A record's own state is in the data: 343 records carry `dalicc:reviewStatus dalicc:Reviewed`
and 238 carry `dalicc:Created`, namely the 237 `created` records, which no second reader has
checked, and the fixture. `dalicc:Approved` and `dalicc:Audited` are defined and nothing sets
them; see [open issue 12](#6-open-issues).

The results are pinned by executable checks, not by this document:

```
python scripts/validate_data.py             0 errors, 3 warnings over 581 records
python scripts/review/consistency_sweep.py  581 records, 2 conflicts (both expected)
python scripts/review/family_rules.py       18 rules; 17 clean, rule 14 knowingly open
python scripts/review/ttl_record.py         581 files, 0 differ
pytest tests/unit/test_data_review.py       the decisions below, as assertions
```

The two conflicts the sweep reports are `DataExplorationLicence` and `DeveloperLicense`, the
two Ordnance Survey evaluation licences. They are a faithful rendering of those licences, not
a modelling error; see [open issue 2](#6-open-issues).

### Observable behaviour changes

The data the API serves is the corrected data. Paths, parameter names, defaults and JSON
shapes are untouched; the content is not. The differences a client can observe:

* `GET /licenselibrary/license/{id}` returns the corrected document for every record, in all
  three serialisations.
* `GET /licenselibrary/list` returns 579 rows; after the 2026-09-15 review it returned 460.
* `GET /dependencygraph/list` returns 46 statements, and no longer asserts that a share-alike
  condition contradicts a permission to sublicense.
* `POST /compatibilitycheck/` reports the `dalicc:sublicense` prohibition wherever a Creative
  Commons license is involved, and reports no conflict between `Apache-2.0` and `MIT`.
* `POST /licenselibrary/facetedsearch` matches `CC-BY-NC-SA-4.0` on an asset-type facet,
  which it could not while that record's `odrl:target` was empty.

Every difference is listed with its justification in
BACKWARD_COMPATIBILITY.md.

---

## 3. The family map

The 581 records are 291 distinct licenses and 290 jurisdiction ports and editions of nine
parents. The site and the API count 290 and 289: the two test-fixture records are left
out of every listing, and one of the two is itself a port. 33 of the 291 are a **variant**
of another record, which is a different relation from a port and does not group the listing;
see [section 11](#11-licences-github-projects-use).

| Parent | Ports | What they are |
|---|---|---|
| `CC-BY-4.0` | 48 | Creative Commons 2.0 and 3.0 jurisdiction ports |
| `CC-BY-SA-4.0` | 48 | the same |
| `CC-BY-ND-4.0` | 48 | the same |
| `CC-BY-NC-4.0` | 48 | the same |
| `CC-BY-NC-ND-4.0` | 48 | the same |
| `CC-BY-NC-SA-4.0` | 47 | the same |
| `UkOpenGovernmentLicenseForPublicSectorInformation` | 1 | `OpenSupremeCourtLicence` |
| `OpenGovernmentLicenceCanada` | 1 | `OpenDataLicenceAgreement` |
| `DataExplorationLicence` | 1 | `DeveloperLicense` |
| **total** | **290** | under **9** parents |

319 records carry a Creative Commons legal code: the six 4.0 International licenses, the CC0
dedication, the 24 unported and generic legal codes of versions 1.0 to 3.0, the Public Domain
Dedication and Certification and 287 ports, 77 of version 2.0 and 210 of version 3.0. 92
records name a variant kind without naming a parent, because the library does not hold the
text they vary from. `NCGL-UK-2.0` is an edition of the UK Open Government Licence and says
so with `dct:isVersionOf`, not with `dalicc:jurisdictionPortOf`; see
[open issue 13](#6-open-issues).

The review records group the library into 85 families, 48 of them one Creative Commons
jurisdiction each. The `family` key of a review record is the grouping.

### The Creative Commons ports are deontically identical to their parents

Every Creative Commons jurisdiction port carries exactly the permissions, the duties attached
to them, the prohibitions and the license-wide duties of the 4.0 International record of the
same element set, statement for statement. The compatibility checker cannot tell a port from
its parent, and cannot tell two ports of the same element set apart.

The one place where ports differ from each other is `odrl:target`: a port whose text licenses
or waives a database right carries `dcmitype:Dataset` next to `dalicc:CreativeWork`, and a
port whose text is silent about databases carries `dalicc:CreativeWork` alone. That
distinction is evidence-based and deliberate; 167 of the 290 ports are on the silent side.

What the ports really differ in is not expressible in the current vocabulary: the law they
are drafted against, the language, the moral-rights regime (five different treatments, two of
them binding the licensor rather than the licensee), the collecting-society and royalty
arrangements, the database-right clause, and the wording of the attribution duty, which in
several ports reaches performers, phonogram producers, broadcasters and database makers as
well as the author. All of it is recorded as `info` and `gap` findings in the individual
review records.

**That is a consequence for presentation, not for the data.** Nothing may be deleted: every
record has a published IRI. The grouping belongs in the site listing, the search results and
the autocomplete, which is what `dalicc:jurisdictionPortOf` makes possible.

### Per-family notes

| Family | What to know |
|---|---|
| GNU (GPL, LGPL, AGPL, FDL) | one model across GPL-3.0-only, LGPL-3.0-only and AGPL-3.0, which is right for the clauses the vocabulary can express. Every copyleft record in the family permits charging for distribution, as GPL 2 section 1 and GPL 3 section 4 say. The difference that still cannot be shown is weak against strong copyleft: LGPL-3.0-only prohibits `dalicc:ChangeLicense` exactly as GPL-3.0-only does |
| BSD | the four differ by exactly one step each: no duty, then notice and attribution, then the endorsement prohibition, then the advertising acknowledgement. `BSD-4-Clause` is the generic four-clause text, not the Berkeley variant |
| Short permissive (MIT, ISC, Zlib, Boost, UPL, WTFPL) | none of the six carries a share-alike statement of any kind. WTFPL keeps zero prohibitions and zero duties, which its text supports |
| Apache | both records are faithful within the vocabulary. The substantive difference between them, that 1.1 has no patent grant and no patent retaliation and 2.0 has both, is now expressible and modelled |
| Other OSI approved | the widest variety and the most errors. One composer template had stamped a `cc:ShareAlike` prohibition on eight reciprocal licenses, which asserts the opposite of what a reciprocal license requires |
| Creative Commons 4.0 International | the reference model for the 287 ports, checked clause by clause; the six differ from `CC-BY-4.0` exactly where the element set differs. Three clauses of the 4.0 text are still unmodelled in all six: sui generis database rights, the no-downstream-restrictions and no-technological-measures rule, and termination with a 30 day cure period |
| Creative Commons 2.0 and 3.0 ports | the 3.0 ports support the `dalicc:promote` prohibition better than the 2.0 ports, because the no-endorsement rule sits in the licence body rather than in the notice around it. Five ports carry an affirmative warranty or an unusual liability rule where the family has a disclaimer (Georgia, Azerbaijan, Armenia, Guatemala, Romania). New Zealand is a rewrite rather than a translation |
| Dedications (CC0, PDDL) | one deontic signature, correctly: both dedicate and both fall back to a permissive licence, which each record carries as clause text. Neither the vocabulary nor the model can say that a record is a dedication rather than a licence |
| UK and Canadian government | four National Archives documents share one drafting pattern and now model it alike. The Canadian pair carries the same text under two institutions and models it the same way |
| Open Data Commons | the three differ in the model where they differ in the text. ODbL models the commercial use its section 3.1 grants; ODC-By quotes its own warranty clause rather than the publisher's website disclaimer |
| Weak copyleft (Mozilla, CDDL, Eclipse, Apple) | reciprocity attaches to `odrl:modify`, `odrl:derive` and, where the text says so, `odrl:distribute`, and relicensing is permitted. A legacy record and the record modelled from the same text now show no deontic difference at all; see [section 8](#8-two-readings-that-were-reversed) |
| Ordnance Survey | evaluation licences, not open licences: time limited, revocable, no distribution, no products. They are the library's only two consistency conflicts |

---

## 4. The seventeen consolidation decisions, as applied

These are the library-wide decisions. `scripts/review/apply_decisions.py` applies them, is
idempotent and prints a triple-level difference per decision; `licensedata/history/` records
each resulting change with `source: consolidation-decision <n>`; and
`tests/unit/test_data_review.py` asserts the ones that describe a rule rather than a one-off.

| # | Decision | Records |
|---|---|---|
| 1 | A `dalicc:sublicense` prohibition on every Creative Commons record, plus ODbL and ODC-By. Every CC 2.0 and 3.0 legal code says it in as many words, the 4.0 licenses grant no sublicense, and the two data licenses forbid it in their section 4. CC0 is excluded: a dedication has nothing to sublicense | 295 |
| 2 | The `odrl:modify` and `dalicc:ModifiedWorks` permissions removed from every NoDerivatives record, with the duties that hung on them. A NoDerivatives text grants no right to adapt beyond the technically necessary; the `odrl:derive` prohibition stays | 98 |
| 3 | `dcmitype:Dataset` on a port only where the port text itself licenses or waives a database right. The silent ports keep `dalicc:CreativeWork` alone | per port |
| 4 | `dalicc:chargeDistributionFee` kept under NonCommercial, and recorded as an open question; see [open issue 1](#6-open-issues) | 0 |
| 5 | The axiom `cc:ShareAlike dalicc:contradicts odrl:grantUse`, and its inverse, removed from `dg_default.ttl`. Passing the same terms on is the normal way to satisfy a share-alike condition, not a contradiction of it | 1 file |
| 6 | `dalicc:orLaterVersionOption` defined and set to `false` on the GNU records, none of which models an "or any later version" text. Four records at the time; the family holds ten `-only` records now and all ten carry it | 4 |
| 7 | The Azerbaijani 3.0 port keeps no `dalicc:WarrantyDisclaimer`: its section 5 gives an affirmative warranty, so the text belongs in `dalicc:additionalClauses` | 1 |
| 8 | MIT: the `dalicc:modificationNotice` duty removed from `odrl:modify` and `odrl:derive`. The license has exactly one condition and it is not a change log | 1 |
| 9 | ODC-By: the license-wide `cc:ShareAlike` duty removed. SPDX and the Open Definition both treat it as attribution only | 1 |
| 10 | CDDL-1.0: reciprocity aligned with MPL-2.0. A `cc:ShareAlike` duty hangs on `odrl:modify` and `odrl:distribute`, which is where sections 3.1 and 3.2 put it; the `dalicc:ChangeLicense` permission was replaced by a prohibition | 1 |
| 11 | BSD-4-Clause is the generic four-clause text, not the Berkeley variant: the advertising clause and the warranty disclaimer are the generic wording | 1 |
| 12 | The two Ordnance Survey conflicts are kept. They are faithful to the licences, which allow building a prototype and forbid supplying anything made with the data | 0 |
| 13 | `dalicc:recordStatus dalicc:testFixture` on `SampleLicenseSl` and `DeveloperLicense`. The IRIs stay resolvable; presentation layers leave them out of listings, search and counts | 2 |
| 14 | The Georgian 3.0 ports: section 5 moved from `dalicc:WarrantyDisclaimer` to `dalicc:additionalClauses`. It is an affirmative warranty and an indemnity, so the field said the opposite of the licence | 6 |
| 15 | The United States 3.0 ports: `dct:title` shortened from "3.0 United States of America" to "3.0 United States", the name Creative Commons and SPDX both use. The identifiers and IRIs are unchanged | 6 |
| 16 | The trailing ISO country code in `dct:alternative` upper-cased, so the ShareAlike ports agree with every other record | 46 records, 184 literals |
| 17 | `CreativeCommonsAttributionNoncommercialNoderivs30Norway` created: the library held five of the six Norwegian 3.0 element sets. Modelled on the five siblings and on the legal code at `https://creativecommons.org/licenses/by-nc-nd/3.0/no/legalcode` | 1 new record |

Two sweeps follow from the decisions without being numbered:

| Sweep | What it writes |
|---|---|
| Ports | `dalicc:jurisdictionPortOf`, `dalicc:variantKind` and, on every Creative Commons port, `dalicc:licenseVersion`, so that the version of the port's own licence text stays readable next to a parent of a different version |
| Review state | `dalicc:reviewStatus` and `dalicc:reviewedOn "2026-09-15"^^xsd:date` on every record |

---

## 5. The modelling rules the standard licenses settled

Modelling every license the owner calls **standard** took the library to 460 records and
forced ten questions that the seventeen decisions above do not answer. "Standard" means the
union of three lists: every OSI-approved entry of the SPDX license list, every license on
choosealicense.com, and the open data and content licenses the improvement plan names, which
resolve to 165 distinct targets. 116 of them had no record; 26 were already present and 23
present under a legacy identifier, which they keep, because an identifier is a published IRI
and a second record for the same text would split every compatibility answer.

Out of scope, and not counted as missing: the **or-later** identifiers, which the library
models with `dalicc:orLaterVersionOption` on the `-only` record; **license-with-exception**
identifiers, which SPDX expresses as a `WITH` expression over its exceptions list; and
**deprecated identifiers that have a successor**.

1. **The validator accepts `created`.** A record written from a legal text rather than checked
   against an existing model gets the verdict `created`, `dct:hasVersion "1"`,
   `dalicc:reviewStatus dalicc:Created` and no archived version.
2. **The vocabulary file is the single source of truth.** Defining a `dalicc:` term in
   `licensedata/vocabulary/dalicc-ns.ttl` is all it takes for the composer, the API and the
   consistency check to accept it; see [DATA.md](DATA.md#the-dalicc-vocabulary).
3. **The consistency check is narrower.** The hard-coded rule "share-alike required and
   `odrl:grantUse` permitted is a conflict" is gone, matching decision 5. The rule for
   `dalicc:ChangeLicense` fires only when the share-alike duty is **license-wide** and the
   relicensing permission carries **no** `dalicc:compliantLicense` duty, so a compatibility
   clause is modellable and so is file-level reciprocity beside a permission to relicense the
   object code.
4. **One reciprocity shape per kind.** Whole-work copyleft is a license-wide `cc:ShareAlike`
   duty. File-level or weak copyleft attaches the duty to `odrl:modify`, `odrl:derive` and,
   where the text says so, `odrl:distribute`, and permits `dalicc:ChangeLicense` with no duty.
   A compatibility clause permits `dalicc:ChangeLicense` with the `dalicc:compliantLicense`
   duty and quotes the list of compatible licenses in `dalicc:additionalClauses`. Where the
   two rules meet, as for `CECILL-C` and `LiLiQ-R-1.1`, the attachment follows the scope the
   text gives the reciprocity and the relicensing permission follows the compatibility clause.
5. **Sublicensing.** `dalicc:sublicense` and `odrl:grantUse` name the same act and are related
   in the dependency graph by `owl:sameAs` in both spellings, so a bundle of a Creative
   Commons license and an MIT-style license reports the conflict it always had.
6. **Fees follow the text.** A record whose text forbids or caps a distribution fee keeps the
   prohibition or omits the permission. Decision 4 still stands for the non-commercial
   Creative Commons family.
7. **`dalicc:orLaterVersionOption` outside the GNU family.** 16 new records and `PhpLicense30`
   state it as true, each on a clause that lets the licensee move to a later version of the
   same license. The property is on 58 records in all.
8. **26 new vocabulary terms**, defined and then applied to exactly the records whose own
   review record names them; see [section 7](#7-vocabulary-gaps).
9. **38 existing records were corrected against their new siblings** and versioned from 2 to
   3, each with a changelog entry quoting the sentence of the license text behind the change.
   `scripts/review/apply_existing_fixes.py` holds the edit and the summary for each and drives
   `bump_version.py`. The commonest faults were a merged warranty and liability paragraph, a
   placeholder publisher, a padding space inside a clause literal, and a missing patent
   statement on a text that states one.
10. **A family-rule checker.** `scripts/review/family_rules.py` runs the rules over every
    record; there are eighteen of them now, see [section 9](#9-the-family-rules).

---

## 6. Open issues

**This is the list a successor picks up.** Every item changes a compatibility answer, a count
or a published IRI, which is why none of them was decided by the review. Each names what is
in the data now, what the alternative is, and roughly how big the change is. Items 1 to 9 come
from reading the existing library, 10 to 18 from modelling the standard licenses.

1. **A distribution fee under NonCommercial** (158 records). Every NonCommercial record
   permits `dalicc:chargeDistributionFee` while prohibiting `cc:CommercialUse`. Most Creative
   Commons texts test whether the use is "primarily intended for or directed toward commercial
   advantage or private monetary compensation", under which a pure cost-recovery fee is
   arguable; the Japanese 2.0 port and the New Zealand 3.0 port have no such test, and the
   Guatemalan 3.0 port is narrower still. The present modelling is kept. A ruling either way
   is one sweep over the family.
2. **The two Ordnance Survey conflicts.** `DataExplorationLicence` and `DeveloperLicense`
   permit `odrl:derive` and prohibit `cc:DerivativeWorks`, which the dependency graph reports
   as a conflict because deriving implies a derivative work. Both licences really do allow
   building a prototype and forbid supplying anything made with the data. Either the
   `odrl:derive` permission goes, or the axiom "derive implies derivative works" is weakened,
   or the conflict is accepted as a faithful rendering. They are the only two conflicts in the
   library.
3. **Asset types of the silent ports** (167 of the 290 ports). Where a port text says nothing
   about databases, `dcmitype:Dataset` was not added, so ports of the same element set differ
   in their asset types. The counter-argument is that Creative Commons licences are media
   neutral and the grant runs to all media and formats "now known or later devised", which
   would make the type right everywhere. The present state is evidence-based; uniformity would
   be easier to explain.
4. **NonCommercial-NoDerivatives edge cases.** Decision 2 removed the adaptation permission
   from all 98 NoDerivatives records. A 4.0 NoDerivatives text does allow producing adapted
   material and forbids only sharing it, which the model can no longer distinguish from a 3.0
   port that forbids producing it at all; and the `dalicc:modificationNotice` duty that used
   to hang on the removed permission is gone from those records, which is right on the text
   but removes a statement users may have relied on.
5. **`cc:ShareAlike` where the text only requires conveying under the same terms.** Decision 9
   removed it from ODC-By. The same sentence pattern appears elsewhere, for example in the UK
   government licences, and was left alone.
6. **`dalicc:ChangeLicense` and `dalicc:promote` where the text is silent.** `dalicc:promote`
   is prohibited on 519 of the 581 records, and in the Creative Commons 2.0 ports the only
   support for it sits in the notice printed around the licence rather than in the licence
   body. Both are family-wide decisions and stay proposals.
7. **The Georgian and Armenian affirmative warranties.** Decision 14 moved the Georgian clause
   to `dalicc:additionalClauses`, where the compatibility checker cannot see it. A
   `dalicc:LicensorWarranty` property would keep the fact that a licensor warrants; it needs a
   decision about what the checker should do with it.
8. **Records that describe a superseded document.** `DataExplorationLicence` models the 2018
   edition while the published terms are v9.5 of December 2025;
   `W3cSoftwareAndDocumentNoticeAndLicense` pins the 2015 edition, in force only until
   31 December 2022; `InspireEndUserLicence` has no live text at all. Each needs either a
   refresh or a label saying it is historical.
9. **825 proposed corrections.** Each one names the exact triples to add or remove, in the
   record's review YAML, and each was left because it is interpretive. They are the bulk of
   the outstanding work and they need a queue rather than a reading: the correction-request
   mechanism exists (see USERS.md) and importing the proposals into it is the
   missing piece.
10. **A covenant not to sue is not a patent grant.** The two CeCILL records model Article 5
    ("the Licensor undertakes not to enforce the rights granted by these patents") as
    `dalicc:patentGrant`, while the two use of data agreements carry `dalicc:covenantNotToSue`
    for a promise that is wider than patents. One of the two readings should win.
11. **Litigation retaliation that is wider than patents.** `CDLA-Permissive-1.0`,
    `CDLA-Sharing-1.0` and `OCLC-2.0` end the grant on any claim about the work.
    `dalicc:patentRetaliationTermination` is the closest term and its comment says so; a
    `dalicc:litigationRetaliationTermination` would be more honest.
12. **`dalicc:Approved` and `dalicc:Audited` have no workflow.** Both values are defined and
    nothing sets either, so the review ladder stops at `Reviewed`. The obvious shape is a
    second decision on the existing review queue, taken by somebody other than the person who
    wrote the record.
13. **`NCGL-UK-2.0` is not grouped under its parent.** It is an edition, not a jurisdiction
    port, so the wrong relation was removed and it carries `dct:isVersionOf`, which
    `app/services/ports.py` does not group on. Either define `dalicc:editionOf` as a second
    sub-property of `dct:isVersionOf` and write it, or teach the ports service the
    super-property.
14. **`CERN-OHL-P-2.0` has a variant-scoped or-later option** (section 7.3: any version of the
    CERN-OHL *with that variant*), which a plain boolean cannot express, so the record carries
    no `dalicc:orLaterVersionOption` at all. `dalicc:shareAlikeVersionQualifier` would fit and
    is applied nowhere.
15. **The warranty clause of CeCILL 2.1 is quoted in French.** The retrieved legal code is the
    French original and no English text was available, so Article 9.3 is verbatim French in a
    record whose other clause is English.
16. **`OGTSL` clause 4** requires a binary distribution to ship the Standard Version alongside
    the modified one. The record models it as `cc:SourceCode`; `dalicc:originalVersionOffer`
    is the more honest term, and the record's own review record does not yet name it.
17. **Three records for one OFL text.** `OFL-1.1`, `OFL-1.1-RFN` and `OFL-1.1-no-RFN` have
    identical legal texts and differ in one duty, and the two editions are linked to the
    parent only by `dalicc:variantKind "edition"`.
18. **`dalicc:chargeLicenseFee` in the Academic Free and Open Software family** is written on
    eleven records on the strength of a patent grant that says "sell and offer for sale". A
    reciprocal license that requires every copy to be royalty-free arguably should not carry
    it.

One defect is open as well, and is engineering rather than interpretation. It is described in
[DATA.md](DATA.md#8-known-data-quality-issues) with the rest of the known data-quality
issues: 575 clause literals, on 287 Creative Commons ports and on `SampleLicenseSl`, carry a
padding space inside their quotation marks (family rule 14).

---

## 7. Vocabulary gaps

1,474 findings say that a licence really carries a clause the model cannot express. Terms were
defined for the ones that recur, and applied only where the record's own review record names
the clause: defining a term is not the same as using it.

`licensedata/vocabulary/dalicc-ns.ttl` now defines 104 terms. The gap terms among them, with
the number of records each reaches today:

| Group | Terms | Applied to |
|---|---|---|
| Termination | `dalicc:terminatesOnBreach`, `dalicc:curePeriod`, `dalicc:patentRetaliationTermination` | 145, 43 and 77 records |
| Patents | `dalicc:patentGrant`, `dalicc:patentFreedomCondition`, `dalicc:covenantNotToSue` | 91, 6 and 2 records |
| Network use and reciprocity scope | `dalicc:networkUseTrigger`, `dalicc:compatibleLicenseTest`, `dalicc:sublicenseSurvival`, `dalicc:alternativeConditionSet`, `dalicc:reciprocityScope` | 30, 23, 17, 6 and 47 records |
| Database rights | `dalicc:suiGenerisDatabaseRights` | 8 records |
| Notices and duties the texts impose | `dalicc:includeNoticeFile`, `dalicc:recipientAssent`, `dalicc:exportControlNotice`, `dalicc:advertisingAcknowledgement`, `dalicc:contributionGrantBack`, `dalicc:provideUserData`, `dalicc:originalVersionOffer`, `dalicc:standardsConformance`, `dalicc:recipientRegistrationRequest` | 12 records and fewer |
| Restrictions the texts state | `dalicc:applyTechnicalProtectionMeasures`, `dalicc:exemptedMaterial`, `dalicc:useForModelTraining`, `dalicc:sellCopy`, `dalicc:publicationNonObstruction`, `dalicc:computationalUseOnly`, `dalicc:fieldOfUseRestriction`, `dalicc:conditionalAddLimitation`, `dalicc:governmentRightsLimitation` | 30 records and fewer |
| Moral rights | `dalicc:moralRightsNonAssertion`, `dalicc:moralRightsRestriction` | 4 and 6 records |
| Qualifiers and structure | `dalicc:orLaterVersionOption`, `dalicc:shareAlikeVersionQualifier`, `dalicc:governingLaw`, `dalicc:sourcePublicationPeriod`, `dalicc:composedOf`, `dalicc:jurisdictionPortOf`, `dalicc:translationOf`, `dalicc:variantKind` | 58, 8, 20, 7, 1, 290, 0 and 415 records |
| Record and review state | `dalicc:recordStatus` with `dalicc:testFixture`; `dalicc:reviewStatus` with `dalicc:Created`, `dalicc:Reviewed`, `dalicc:Approved`, `dalicc:Audited`; `dalicc:reviewedOn` | 2 and 581 records |

Two asset types (`dalicc:CreativeWork`, `dalicc:Hardware`) and `dct:language`, which records
the language of a legal code that is not English (7 records), came out of the same reading.

Five terms are defined and applied nowhere, each because no text read so far states the
clause unambiguously: `dalicc:databaseRightWaiver`, `dalicc:derivativeDatabaseAccess`,
`dalicc:downstreamOffer`, `dalicc:terminationOnBreach` and `dalicc:translationOf`. Nine terms
published by the 2022 vocabulary documentation are likewise unused and kept because their
IRIs must keep dereferencing. `scripts/review/refresh_vocab_notes.py` keeps every one of
those `skos:note` claims honest, from the generated usage counts.

The largest gaps are still open, and no term has been proposed for them: the moral-rights
regimes of the Creative Commons ports (five different treatments), their collecting-society
and royalty arrangements, and the no-downstream-restrictions rule of the 4.0 texts. They are
described in [section 3](#3-the-family-map).

---

## 8. Two readings that were reversed

Both were applied library-wide, both were wrong, both are corrected, and both are now pinned
by a test in `tests/unit/test_data_review.py`. They are recorded here because a reader of an
archived version will meet the old shape.

### A permissive license permits relicensing

The notice clause of the MIT, ISC and BSD family was read as a prohibition on putting a copy
under other terms, and a `dalicc:ChangeLicense` prohibition was written into every permissive
record on that reading. The reading is wrong. The notice clause is a **duty** attached to the
acts it governs: the copyright notice and the permission notice must be kept with the copy. It
says nothing about the terms the copy travels under, which is why permissive code is
relicensed every day, into GNU projects and into proprietary products, and why `Apache-2.0`
has permitted the act in this library from the start.

**Family rule 15** states the corrected rule: a record that makes no share-alike statement
anywhere, requires no source code and forbids none of the core acts (reproduce, distribute,
modify, derive, derivative works, modified works, commercial use) carries
`dalicc:ChangeLicense` as a **permission** and never as a prohibition. Creative Commons
licenses are excluded whatever their elements say, because their no-downstream-restrictions
clause is exactly the bar rule 15 denies. `Cc010Universal` is in, as a dedication, and so are
`Vim`, `Artistic-2.0` and `CECILL-B`, whose texts name the licenses a licensee may move the
work to although they ask for source. The rule checks 115 records and they all pass.

The permission carries the `dalicc:compliantLicense` duty wherever the license keeps a
condition, which is the shape `Apache-2.0` already had: the notice has to survive the
relicensing. On a dedication it carries no duty. Nothing moved onto it that belongs elsewhere:
the attribution and notice duties stay on `odrl:distribute`, `odrl:modify` and `odrl:derive`,
where the texts put them. 63 records were corrected, 18 of them published records that were
versioned and 45 of them records at version 1 that were corrected in place, with the
correction as a rubric 3 finding in their review record. The finding that asserted the
opposite is marked as corrected rather than deleted, because a review record is a history of
what was thought.

`Apache-2.0` with `MIT`, the pair every user bundles first, reports no conflict.

### The weak-copyleft family says one thing

Four records of that family were modelled years before the licenses that share their text, and
each was silent about clauses its sibling quotes. Each was corrected against a named sentence
and versioned:

| Record | What it was missing |
|---|---|
| `MozillaPublicLicenseVersion20` | the derivative-works permission of section 2.1, the distribution fee of section 3.2(a) and the sublicensing permission of section 3.2(b) ("or sublicense it under different terms") |
| `CommonDevelopmentAndDistributionLicense10` | the sublicensing permission and the promotion prohibition of section 2.1(a), the patent retaliation of section 6.2 and the attribution duty of section 3.3 |
| `EPL-2.0` | the sublicensing permission of section 2(a), which it stated with the older spelling `odrl:grantUse`, and the license fee its three siblings read out of section 3.2 |
| `EclipsePublicLicense10` | the modified-works and sublicensing permissions, the attribution, notice and source duties on `odrl:modify` and `odrl:derive` (they sat on the derivative-works permission), and three statements its text does not support |
| `APSL-2.0` | the source duty on `odrl:modify` and `odrl:derive` that sections 2.1 and 2.2 state and that `APSL-1.0`, `APSL-1.1` and `APSL-1.2` carry |

`CPL-1.0` and `IPL-1.0` carried the source duty on distribution alone and were brought onto
the same shape. The comparator now shows **no deontic difference at all** between a legacy
record and its text-modelled sibling: `MozillaPublicLicenseVersion20` against
`MPL-2.0-no-copyleft-exception`, `CommonDevelopmentAndDistributionLicense10` against
`CDDL-1.1`, and `EclipsePublicLicense10` against `CPL-1.0` and against `EPL-2.0` differ in
their title and in nothing else.

Across the three families, `MPL-2.0` against `CDDL-1.0` against `EPL-2.0` is down to three
rows, and every one of them is a difference between the texts:

| Row | Difference |
|---|---|
| Charge license fee | the Eclipse family lets a distributor distribute under its own license agreement (section 3.2); the Mozilla and CDDL texts do not |
| Promote | Mozilla and CDDL grant their rights "other than patent or trademark"; the Eclipse texts have no trademark clause |
| Modification notice on `odrl:derive` and `odrl:modify` | CDDL 1.0 section 3.3 and EPL section 3 require the change to be identified; MPL 2.0 dropped that requirement, which MPL 1.1 still had |

---

## 9. The family rules

`scripts/review/family_rules.py` is the runnable form of the rules the review works from:
eighteen checks over every record, with the offending identifiers named. `--json` and
`--markdown` render the same result for a report, `--strict` fails on any violation, and
`make family-rules` runs it.

| # | Rule | Checked | Violations |
|---|---|---|---|
| 1 | GNU copyleft records carry source code and share alike | 31 | 0 |
| 2 | NonCommercial records prohibit commercial use | 158 | 0 |
| 3 | NoDerivatives records prohibit derivatives and permit no adaptation | 106 | 0 |
| 4 | ShareAlike records carry the share-alike duty | 105 | 0 |
| 5 | Permissive records make no share-alike statement | 58 | 0 |
| 6 | Every record carries an attribution or a notice duty | 566 | 0 |
| 7 | A record with neither a prohibition nor a duty is suspicious | 581 | 0 |
| 8 | Software licenses target `dcmitype:Software` | 115 | 0 |
| 9 | A patent retaliation clause travels with a patent grant | 68 | 0 |
| 10 | Warranty and liability are quoted into their own predicates | 557 | 0 |
| 11 | No record repeats a statement | 581 | 0 |
| 12 | A jurisdiction port names its country | 287 | 0 |
| 13 | Reciprocity has one shape per kind | 60 | 0 |
| 14 | No padding space and no placeholder in a literal | 581 | **575** |
| 15 | Permissive records permit relicensing | 115 | 0 |
| 16 | An or-later record says what its base says | 14 | 0 |
| 17 | An exception or a rider record keeps everything its base says | 19 | 0 |
| 18 | Creative Commons records of one version agree | 24 | 0 |

Rule 14 is the one open sweep: 575 literals, on 287 Creative Commons ports and on
`SampleLicenseSl`, begin or end with a space inside their quotation marks. It changes no
compatibility answer, and fixing it takes 287 records to a new version in one edit, so it
wants its own commit.

Rules 16 to 18 came with the licences GitHub projects use; decisions 2, 3 and 6 of
[section 11](#11-licences-github-projects-use) say what each of them tests and why.

The exceptions are recorded in the script rather than fixed, each against the text.
`BSD-ask-to-endorse`, `SSH-OpenSSH`, `Intel-Research-Use-License` and
`PolyForm-Strict-1.0.0` really have no attribution or notice condition (rule 6).
`CDLA-Permissive-1.0`, `CDLA-Sharing-1.0`, `OCLC-2.0` and the six `Llama-*-Community-License` records
use `dalicc:patentRetaliationTermination` for a clause that ends the license on **any**
litigation and not only on a patent claim, so there is no patent grant for it to travel with
(rule 9). `Cube` and `OpenSSL` are permissive texts that bar relicensing in as many words, so
the prohibition in the record is the text and not a misread notice clause (rule 15). And
`CC-PDDC` is a dedication, so it asks for nothing (rules 6 and 7).

---

## 10. The scripts

Every one of them is idempotent and has a `--dry-run` or `--check` mode.

| Script | What it is |
|---|---|
| `scripts/review/ttl_record.py` | a format-preserving reader and writer for one license record, so the hand-curated Turtle layout survives an edit. Run with no arguments it re-renders all 581 files and reports any that differ |
| `scripts/review/apply_decisions.py` | the seventeen consolidation decisions plus the port and review-state sweeps, with a triple-level difference per decision |
| `scripts/review/apply_standard_additions.py` | the 116 records written from their legal texts, and the vocabulary terms applied to the records whose review record names them |
| `scripts/review/apply_existing_fixes.py` | the 38 existing records corrected against their new siblings; drives `bump_version.py` |
| `scripts/review/apply_verification_fixes.py` | the two reversed readings of [section 8](#8-two-readings-that-were-reversed) |
| `scripts/review/family_rules.py` | the eighteen family rules over every record |
| `scripts/review/consistency_sweep.py` | the composer consistency check over every record, with the expected conflict set as the exit condition |
| `scripts/review/build_spdx_mapping.py` | generates `licensedata/spdx-mapping.json`, 276 of 581 records mapped, plus the alias table for the deprecated SPDX identifiers |
| `scripts/review/refresh_vocab_notes.py` | rewrites the `skos:note` usage claims from the generated usage counts |
| `scripts/review/refresh_contract_snapshots.py` | re-records only the contract snapshots the corrected data invalidated, through the application's own serialisation path |
| `scripts/review/build_history.py` | archives a record's previous version and derives its change log from the triple-level difference, annotated with the finding or the decision behind each change |
| `scripts/review/bump_version.py` | versions the next hand edit of a record, so the history cannot fall behind the data |

After any of them, rebuild and re-prove. The commands, the layout of the history, the
annotation rules and the workflow for the next edit are in
[DATA.md](DATA.md#4-model-history-and-versioning).

---

## 11. Licences GitHub projects use

The library held 460 records and none of them was an or-later identifier, an SPDX exception
combination or a model licence, although those are what a great many public repositories
declare. The gap was measured on 2026-09-22, and 121 records were written from their legal
texts, which takes the library to 581. Nothing here is legal advice.

### The evidence

Every number was retrieved on 2026-09-22 and every raw response was kept. Nothing below is
an estimate, and where a source could not be used the table says so.

| Source | What it measures | Outcome | Size |
|---|---|---|---|
| GitHub, licence keys | public repositories whose licence file the licensee library recognises as that key | worked | 47 keys, 20,858,490 repositories on the largest |
| GitHub, exact phrase | public repositories whose name, description or readme contains the phrase | worked, weak signal | 165 phrases |
| ecosyste.ms | packages and repositories by licence | did not work | neither service has an endpoint that aggregates by licence, and the `license` filter of the repositories endpoint returns rows whose own `license` field is `null` |
| libraries.io | packages by licence | rejected | the `licenses` filter returns rows that do not carry the filtered licence. `licenses=BUSL-1.1` returned 19,049 and not one of the first five rows carried it, so no number from it is used anywhere |
| Hugging Face | public models carrying a licence tag | worked, by a different route | 73 tags, 546,083 models on the largest |
| Public reports | audited codebases, package registries, developers, pageviews | worked, 7 of 12 sources | Black Duck OSSRA 2026, the Black Duck top 20 for 2024, the Open Source Initiative pageview rankings for 2025 and 2024, the OSI and ClearlyDefined per-ecosystem shares for 2023, the GitHub Innovation Graph licences CSV and an MSR 2024 study over 33.7M package versions |
| SPDX license list 3.29.0 | membership and the canonical identifier | worked | 740 licences, of which 32 deprecated, and 86 exceptions |
| ScanCode LicenseDB | membership, category and the licence text | worked | 2,733 entries, and the text source of last resort for the licences SPDX does not list |
| Blue Oak Council list, version 16 | a quality rating, not a usage count | worked | 225 licences in 5 tiers |

Five sources were tried and dropped: Mend.io serves no figures in the blog and no recoverable
text in the whitepaper, Sonatype publishes no ranked licence list in the 2024 or 2026 report,
GitHub Octoverse publishes no licence data at all (the Innovation Graph is GitHub's licence
dataset instead), the RedMonk 2026 rankings are chart images, and the 2025 OSSRA PDF is no
longer served and an archive lookup answered 429.

261 candidates were examined against the library, by SPDX identifier first, then by
normalised title and alternative name, then by legal-code URL. 64 were already present, 197
were missing, and none turned out to be present under a different SPDX identifier: the
2026-09-15 review had assigned every identifier the SPDX list supports.

### What the set GitHub recognises covers

All 47 keys of the licensee set that choosealicense.com is built from resolve to a record,
so there is no gap there. Twelve of them resolve through a legacy identifier rather than the
SPDX one, which is how the library has always held them: `agpl-3.0` to `AGPL-3.0`, `cc0-1.0`
to `Cc010Universal`, `mpl-2.0` to `MozillaPublicLicenseVersion20`, `isc` to `IscLicense`,
`epl-1.0` to `EclipsePublicLicense10`, `zlib` to `TheZlibLibpngLicense`, `upl-1.0`,
`ms-pl`, `lppl-1.3c`, `gfdl-1.3`, `odbl-1.0` and `cecill-2.1` likewise.

The recognised set looks complete and is not. GitHub reports the deprecated identifiers
`GPL-2.0`, `GPL-3.0`, `LGPL-2.1`, `LGPL-3.0`, `AGPL-3.0` and `GFDL-1.3` for the GNU
licences, and one key covers both the `-only` and the `-or-later` form of each. Half of what
those six keys count is an identifier the library did not hold. That is the single clearest
finding of this pass, and the public reports say the same thing from a different population:
Black Duck writes "GNU LGPL v2.1 or later" and "GNU General Public License v2.0 or Later" as
rows of their own, because that is what the audited codebases declare.

### How the ranking works, and its top

Every candidate carries the sources that put it on the list, and the score adds one term per
source. Logarithms are used because the counts span seven orders of magnitude: a licence with
twenty million repositories is not a thousand times more worth having than one with twenty
thousand. A declaration counts for more than a mention, and a mention of a licence named
after its own software counts least of all, because the query cannot tell the licence from
the program. Above about 20 points the order is driven by real counts; below that it is
driven by list membership and by judgement, and the cut between the last selected record and
the first queued one is arbitrary to within a few places.

| # | Score | Identifier | Kind | Evidence |
|---|---|---|---|---|
| 1 | 103.7 | `LGPL-2.1-or-later` | version option | OSSRA 2026 position 8, 49 percent of 947 audited codebases; Black Duck 2024 position 7; GitHub base key `lgpl-2.1`: 79,242 |
| 2 | 70.6 | `GPL-3.0-or-later` | version option | GitHub base key `gpl-3.0`: 3,635,200; Hugging Face: 3,909; 28,654 mentions |
| 3 | 66.5 | `GPL-2.0-or-later` | version option | Black Duck 2024 position 18; GitHub base key `gpl-2.0`: 652,262 |
| 4 | 65.5 | `AGPL-3.0-or-later` | version option | GitHub base key `agpl-3.0`: 497,344; Hugging Face: 2,820 |
| 5 | 62.0 | `LGPL-3.0-or-later` | version option | Black Duck 2024 position 17; GitHub base key `lgpl-3.0`: 124,520 |
| 6 | 60.0 | `Apache-2.0-with-LLVM-exception` | exception | 1,537 mentions of the exception identifier; LLVM and a large part of the Rust crate ecosystem |
| 7 | 54.9 | `PSF-2.0` | permissive variant | OSSRA 2026 position 9, 48 percent; Black Duck 2024 position 14 |
| 8 | 50.9 | `GPL-3.0-only-with-GPL-3.0-linking-exception` | exception | 118 mentions; several OCaml and Ada libraries |
| 9 | 49.8 | `GPL-2.0-only-with-Classpath-exception-2.0` | exception | 206 mentions; OpenJDK |
| 10 | 49.8 | `GPL-2.0-or-later-with-Classpath-exception-2.0` | exception | 206 mentions; the GNU Java world |
| 11 | 48.7 | `GPL-2.0-only-with-Linux-syscall-note` | exception | 152 mentions; the Linux kernel user space API headers |
| 21 | 38.5 | `CreativeML-OpenRAIL-M` | model licence | Hugging Face: 33,070 models |
| 22 | 37.1 | `Gemma-Terms-of-Use` | model licence | Hugging Face: 15,729 models |
| 26 | 36.1 | `CC-BY-3.0` | content | Black Duck 2024 position 16; Hugging Face: 325 |
| 33 | 30.1 | `PolyForm-Noncommercial-1.0.0` | source available | 18,970 mentions |
| 35 | 28.4 | `BUSL-1.1` | source available | 7,041 mentions; HashiCorp Terraform, Vault and Consul, MariaDB MaxScale, Couchbase |

One record is in for a reason that is not its score. `CC-PDDC`, the Creative Commons Public
Domain Dedication and Certification, scores 10.52 against a cut at 10.75, and it goes in with
the 24 unported Creative Commons records because leaving it out would make that family look
complete when it is not. That is the only record selected against the ranking, and it is why
the cap of about 120 came out at 121.

### The ten decisions

| # | Decision |
|---|---|
| 1 | The vocabulary goes to version 6. `dalicc:variantOf` names the record a variant varies, and `dalicc:exceptedCombination` is the action of an SPDX exception. The 18 exception records carried `dalicc:exemptedMaterial` as a permission, which says the opposite of what that term means on `OGL-UK-1.0`, `OGL-UK-2.0` and `NLOD-2.0`, where it is prohibited and means material the grant never reached. They now carry `dalicc:exceptedCombination`, and `dalicc:exemptedMaterial` keeps its one meaning |
| 2 | `variantKind "version-option"` is the kind of the SPDX version-option identifiers, and the flag follows the identifier: an `-or-later` identifier carries `dalicc:orLaterVersionOption true`, an `-only` identifier false, the GFDL invariants `-only` identifiers included. Family rule 16 checks that an or-later record says exactly what its base says |
| 3 | An exception record is a superset of its base: every statement of the base plus the `dalicc:exceptedCombination` permission, the `dalicc:reciprocityScope` annotation and the exception text in `dalicc:additionalClauses`. Its `spdx:licenseId` holds the SPDX expression with the space and `WITH`. The rider record works the same way, without an SPDX identifier. Family rule 17 checks it |
| 4 | The SPDX mapping gains an `aliases` table: the 35 identifiers the SPDX list has deprecated and the `+` forms, mapped onto what replaced them, so that a lookup for `GPL-2.0` or `GPL-2.0+` reaches a record. A row whose current identifier no record carries stays in the table and answers 404 |
| 5 | The licence page lists the variants of a record under a heading of their own. The `ports` parameter of the listing keeps its meaning, which is jurisdiction ports: a variant is an ordinary row |
| 6 | The 24 Creative Commons records of versions 1.0 to 3.0 agree with each other and with the 3.0 ports the library already held. `dcmitype:Dataset` on all six 3.0 records and on none of the others, `dalicc:moralRightsRestriction` on all six 3.0 records, `dalicc:royaltyCollectionReserved` on every NonCommercial record of 2.0, 2.5 and 3.0 and on none of 1.0, `dalicc:terminatesOnBreach true` with no cure period on all 24, and the same passages quoted by the records of one version. Family rule 18 checks the first three |
| 7 | The lists in the tooling were extended rather than the records bent: `CC-PDDC` is a dedication, `SSH-OpenSSH`, `Intel-Research-Use-License` and `PolyForm-Strict-1.0.0` ask for no notice, the six `Llama-*-Community-License` records end the grant on any claim and not only on a patent claim, and `Cube` and `OpenSSL` bar relicensing in as many words |
| 8 | Seven published records were corrected against their own texts and versioned; see below |
| 9 | A licence's own title is data. The naming guard of `tests/unit/test_ownership_guards.py` bans the provider and model names of an assistant, not the names of licences, and it trips on no record of the library: every licence identifier and title the documentation names is safe. It does trip on one queued candidate whose identifier carries a banned token, so the queue below names that licence in prose instead. If such an identifier ever becomes a record, the guard's allow list is to be built from the identifiers in `licensedata/licenses/`, read from the files rather than typed by hand |
| 10 | Text-to-License compares a reading with the nearest curated record. Where two records score the same, the one that is not a variant wins, and then the SPDX-canonical one, so a reading of an MIT text is still compared with `MIT` |

### The new records, by kind

| Kind | Records | What they are |
|---|---|---|
| Version options | 14 | the `-or-later` identifiers of the GNU family, plus `GFDL-1.3-invariants-or-later`, `GFDL-1.3-no-invariants-or-later` and the two `-only` invariants identifiers. Each copies its base record statement for statement and changes the identifier, the title, the alternatives, the SPDX identifier, the flag and the relation |
| Records for a text the library did not hold | 3 | `GPL-1.0-only`, `GFDL-1.1-only` and `GFDL-1.2-only`, modelled from their own texts so that their or-later siblings have a base |
| Exception combinations | 18 | a GNU licence or Apache 2.0 read together with one SPDX exception: Classpath, the Linux syscall note, GCC 2.0 and 3.1, Autoconf 2.0 and 3.0, Bison 2.2, Font 2.0, the OpenJDK assembly exception, the Universal FOSS exception, the two Qt exceptions, the LGPL 3.0 and GPL 3.0 linking exceptions and the LLVM exception |
| Rider | 1 | `Apache-2.0-with-Commons-Clause`, which adds a `dalicc:sellCopy` prohibition and quotes the rider's definition of selling |
| Permissive variants | 22 | `X11`, `JSON`, `MIT-CMU`, `MIT-Wu`, `Bitstream-Vera`, `Apache-1.0`, `BSD-2-Clause-Views`, `BSD-3-Clause-Attribution`, `OpenSSL`, `bzip2-1.0.6`, `Info-ZIP`, `Cube`, `Libpng`, `libpng-2.0`, `zlib-acknowledgement`, `ImageMagick`, `Beerware`, `DOC`, `MulanPSL-1.0`, `PSF-2.0`, `Ruby` and `SSH-OpenSSH` |
| Source-available licences | 16 | `BUSL-1.1`, `SSPL-1.0`, `Elastic-2.0`, `RSALv2`, `Confluent-Community-1.0`, `Timescale-License`, `Sustainable-Use-License`, the two Functional Source License texts, the four PolyForm texts, the two Parity texts and `Hippocratic-2.1` |
| Model licences | 17 | the five responsible-use texts (`CreativeML-OpenRAIL-M`, `CreativeML-OpenRAIL-Mpp`, `BigScience-OpenRAIL-M`, `BigScience-BLOOM-RAIL-1.0`, `BigCode-OpenRAIL-M`), the six `Llama-*-Community-License` texts, `Gemma-Terms-of-Use`, `NVIDIA-Open-Model-License`, `DeepFloyd-IF-License`, `Apple-Sample-Code-License`, `Apple-ML-Research-Model-License` and `Intel-Research-Use-License`. None has an SPDX identifier, and all but one target `dcmitype:Dataset` and `dcmitype:Software` together, because a released model is weights and code in one package |
| Creative Commons 1.0 to 3.0 | 24 | the unported and generic legal codes the library's 287 jurisdiction ports were adapted from, six element sets across four versions |
| Creative Commons public domain | 1 | `CC-PDDC`, a dedication: everything permitted, nothing required, no prohibition at all |
| LaTeX Project Public License | 4 | versions 1.0, 1.1, 1.2 and 1.3a, beside the 1.3c record the library has carried for years |
| Open Font License | 1 | `OFL-1.0`, which repeats `OFL-1.1` statement for statement and differs only where the two texts differ |

Every one of the 121 is version 1 with the verdict `created` and
`dalicc:reviewStatus dalicc:Created`: each was written from a legal text and no second reader
has checked it. Together they carry 1,539 findings, of which 496 are `major`, 243 `minor`,
184 `gap` and 616 `info`.

### The variant relation, and the kinds

`dalicc:jurisdictionPortOf` says that a record adapts a licence to another legal system.
None of the three new kinds does that, so they carry `dalicc:variantOf` instead, and
`dalicc:variantKind` gained `version-option`, `exception` and `rider` beside the four the
review of 2026-09-15 defined. Unlike the port relation the variant relation may be two steps
long, because an exception on an or-later identifier names the or-later record, which names
the `-only` one. [DATA.md](DATA.md#ports-and-variants) has the shape.

The 18 exception records are the first in the library whose `spdx:licenseId` holds an SPDX
expression rather than a single identifier, and each carries a `dalicc:reciprocityScope`
literal in the exception's own words. The nine literals of the GNU set are not
interchangeable: the Classpath exception reaches "the covered files, not an independent
module that links to them", the font exception "the font, not a document that embeds it",
the Linux syscall note "the kernel, not a user program that uses kernel services by normal
system calls", and the OpenJDK assembly exception names the combination itself, because
there the executable does not leave the licence at all.

### The published records that changed

Each was edited against a sentence of its own text and versioned with
`scripts/review/bump_version.py`, so the change log holds the triple-level difference.

| Record | New version | What changed |
|---|---|---|
| `AGPL-3.0` | 4 | a `dalicc:networkUseTrigger` permission carrying a `cc:SourceCode` duty for section 13, which the record already quoted; `dalicc:terminatesOnBreach true`, `dalicc:curePeriod "30 days"` and a `dalicc:patentGrant` permission from sections 8 and 11 of the GNU General Public License version 3, which this licence incorporates |
| `GPL-2.0-only` | 4 | `dalicc:terminatesOnBreach true`. Section 4: "Any attempt otherwise to copy, modify, sublicense or distribute the Program is void, and will automatically terminate your rights under this License." `LGPL-2.1-only` already carried the flag on the same sentence of its own section 8 |
| `GPL-3.0-only` | 4 | `dalicc:terminatesOnBreach true`, `dalicc:curePeriod "30 days"` from section 8, and a `dalicc:patentGrant` permission from section 11: "Each contributor grants you a non-exclusive, worldwide, royalty-free patent license under the contributor's essential patent claims" |
| `LGPL-3.0-only` | 4 | the same three, because the licence incorporates the terms of version 3 of the General Public License |
| `GnuFreeDocumentationLicense` | 3 | the three duty nodes whose `odrl:action` was `dct:source` are gone. `dct:source` is a Dublin Core property and not an action, so the dependency graph could not see the duty; `cc:SourceCode` sat beside each of the three already and carries the rule of section 3. This closes the defect the known-issues list in [DATA.md](DATA.md#8-known-data-quality-issues) had carried since 2026-09-15 |
| `LatexProjectPublicLicenseVersion13c` | 4 | the `cc:ShareAlike` prohibition removed, which no sentence of the licence supports and which clause 10(a) contradicts; a `dalicc:originalVersionOffer` duty on modify and derive for clause 6(d); `dalicc:CreativeWork` added to the target, because the licence governs "Any work being distributed under this License"; the padding space stripped from `dalicc:WarrantyOrLiabilityAcceptance`; `dct:title` tagged `@en` |
| `TheZlibLibpngLicense` | 5 | `dct:alternative "Libpng"` dropped. The SPDX list gives that identifier to the libpng notice, which is now a record of its own, so the name reached the wrong licence |

Two more changes were made without a version bump, because no triple moved. The review
record of `CAL-1.0` proposed `dalicc:networkUseTrigger` and `dalicc:terminatesOnBreach` as
terms to create; the vocabulary defines both and the record carries both, so the two findings
are `applied` rather than `none`. And `LPPL-1.0` and `LPPL-1.2`, which were written in this
pass, lost the same unsupported `cc:ShareAlike` prohibition as their 1.3c sibling.

`MIT` was looked at and left alone. A sublicensing permission was proposed for it, for
"including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense", and the record already carries `odrl:grantUse`, which the dependency graph makes
the same action as `dalicc:sublicense`. `Apache-2.0` states it the same way.

### What is still open

Everything below is recorded in the review records with the sentence behind it, and nothing
of it was applied. Each line says how many records depend on the answer.

1. **`dalicc:promote` where no text supports it.** The prohibition is on 519 of the 581
   records. The GNU texts have no trademark or endorsement clause and their records carry
   it as a library-wide convention, and so do the ten Creative Commons records of versions
   1.0 to 2.5, where the nearest sentence is the trademark notice printed around the
   licence rather than in it. The 2026-09-15 review already listed this as open issue 6;
   100 of the 121 new records carry the prohibition, so more of the library depends on the
   answer than before.
2. **The Creative Commons 4.0 records and the 287 ports have no termination flag** (293
   records). Section 6(a) of every 4.0 legal code says the licence "terminate[s]
   automatically" on a failure to comply and 6(b)(1) reinstates it "within 30 days of Your
   discovery of the violation". The 24 new records of versions 1.0 to 3.0 carry
   `dalicc:terminatesOnBreach true` because their own texts say it, so the family now reads
   unevenly until the 4.0 records and the ports are given what their texts say.
3. **Three clauses of the Creative Commons family are quoted and not modelled** (319
   records carry a Creative Commons legal code): the technological measures bar, which
   `dalicc:applyTechnicalProtectionMeasures` would carry, the bar on offering or imposing
   further terms, which `dalicc:addLimitation` would carry, and the licence every recipient
   receives directly from the licensor, which `dalicc:downstreamOffer` describes exactly.
   Writing them into 24 records out of 319 would split the compatibility behaviour of one
   family, so they were quoted instead.
4. **`Apache-2.0` has no `dalicc:includeNoticeFile` duty** (1 record, and its two variants).
   Clause 4(d) states the condition: "If the Work includes a 'NOTICE' text file as part of
   its distribution, then any Derivative Works that You distribute must include a readable
   copy of the attribution notices contained within such NOTICE file". A termination flag for
   the same record is the weakest of the proposals, because section 4 is silent on
   termination and only the patent retaliation of section 3 ends anything.
5. **`Apache-1.1` needs its own text fetched** (1 record). Its record carries the
   acknowledgement wording in `dalicc:PromotionSpecification` with no duty saying where it
   has to appear, carries `dalicc:modificationNotice` although the 1.0 text has no
   change-record clause, and quotes neither a warranty disclaimer nor a liability limitation
   although every other member of the family does.
6. **`Python-2.0.1` carries an alternative that belongs to another licence** (1 record). It
   holds `dct:alternative "Python Software Foundation License Version 2"`, and the SPDX list
   gives that name to `PSF-2.0`, which is now a record of its own. The two documents are not
   the same: `PSF-2.0` is the agreement standing alone and `Python-2.0.1` is the composite
   CPython ships.
7. **The Ruby and Artistic readings disagree** (4 records). `Artistic-1.0` turns two of the
   four alternatives of its clauses 3 and 4 into duties and also carries
   `dalicc:alternativeConditionSet`; the new `Ruby` record carries the annotation and no
   duty. The clauses are all but identical, so one of the two readings should win.
8. **The GNU Free Documentation records target `dcmitype:Software`** (10 records). Section 1
   applies the licence to "any manual or other work, in any medium", so `dcmitype:Text` fits
   better. Changing an asset type changes faceted search results.
9. **The six records for version 1.3 of the Free Documentation License cannot be told
   apart** (6 records). SPDX splits that version into six identifiers so that a document
   with Invariant Sections can be told from one without, and the legal text behind all six
   is one file with one checksum: whether a document carries Invariant Sections is stated in
   that document's licence notice and not in the licence. The six records therefore hold the
   same model and differ only in identifier, title and alternative names. A term such as
   `dalicc:invariantSections` is what the library would need to separate them.
10. **The 3.0 ports point at a 4.0 record** (287 records). Every Creative Commons port names
    the 4.0 International record of its element set as its parent, because the library held
    no unported 2.0 or 3.0 record. It now holds the 3.0 ones. Re-pointing the 210 version 3.0
    ports at them would make the relation say what it means, and it would bump 287 records
    and change what the licence page of every 4.0 record lists, so it is the owner's call.
11. **About 40 vocabulary terms were proposed and none was created** beyond the two of
    decision 1. The ones with the widest support are `dalicc:competingServiceRestriction`
    (four source-available records), `dalicc:permittedPurpose` (two),
    `dalicc:scaleThresholdCondition` (the six `Llama-*-Community-License` records, for the 700 million
    monthly active user threshold), `dalicc:incorporatedUsePolicy` and
    `dalicc:prohibitedUsePolicy` (seven and eight model records),
    `dalicc:passThroughUseRestrictions` (five), `dalicc:changeDate` and
    `dalicc:changeLicense` (three), `dalicc:researchUseOnly` (two) and
    `dalicc:creditRemovalOnRequest` (the Creative Commons family). Each is quoted in the
    review record that proposes it.

### The queue beyond the cap

76 candidates pass the test for a record and fall outside the cap of about 120. They keep
their numbers and are the starting point for the next pass. The first six are within half a
point of the cut, so the line between the last selected record and the first queued one is
not a judgement about their merits.

| Score | Identifiers |
|---|---|
| 10.6 to 10.0 | `TCL`, `MITNFA`, `CockroachDB-Community-License`, `BSD-Source-Code`, `Plexus`, `Linux-OpenIB` |
| 9.9 to 9.0 | `MIT-feh`, `BSD-3-Clause-Modification`, `Xerox`, `Mup`, `NetCDF`, `Spencer-99`, `Stability-AI-Community-License`, `DeepSeek-Model-License`, `Xfig`, `Adobe-Glyph`, `Prosperity-3.0.0`, `SGI-B-2.0`, `MIT-advertising`, `BSD-4-Clause-UC`, `SWL`, `Zed`, `Sendmail` |
| 8.9 to 8.0 | `BSD-3-Clause-No-Nuclear-Warranty`, `OML`, `SSH-short`, `BSD-3-Clause-No-Nuclear-License-2014`, `HTMLTIDY`, `MIT-open-group`, `MIT-enna`, `SMLNJ`, `IJG`, `ANTLR-PD`, `AMPAS`, `Saxpath`, `ClArtistic`, `OGC-1.0`, `FSFAP` |
| 7.9 to 7.0 | `Caldera`, `NLPL`, `blessing`, `BSD-3-Clause-No-Military-License`, `FSFUL`, `Adobe-2006`, `BSD-Protection`, `Giftware`, `HPND-sell-variant`, `Latex2e`, `MulanPubL-2.0`, `Unicode-TOU` |
| 6.9 to 6.0 | `BSD-3-Clause-No-Nuclear-License`, `FCL-1.0-ALv2`, `FCL-1.0-MIT`, `FSFULLR`, `Spencer-94`, `BSD-4.3TAHOE`, `Wsuipa`, `Zend-2.0`, `Condor-1.1`, `NAIST-2003`, `Noweb`, `Boehm-GC`, `TU-Berlin-2.0`, `X11-distribute-modifications-variant`, `BSD-4.3RENO` |
| below 6.0 | the Falcon model licence, `Qwen-License-Agreement`, `AGPL-1.0-only`, `AGPL-1.0-or-later`, `CC-SA-1.0`, `OFL-1.0-RFN`, `OFL-1.0-no-RFN`, `Mistral-AI-Research-License`, `PolyForm-Free-Trial-1.0.0`, `PolyForm-Internal-Use-1.0.0`, `PolyForm-Perimeter-1.0.0` |

Two groups are out of scope as a category rather than by score. The nine Creative Commons
jurisdiction ports the library does not hold (`CC-BY-2.5-AU`, `CC-BY-3.0-IGO` and seven
more) belong to a ports pass, and no source publishes a usage number for any of them. And the
deprecated identifiers with a successor are the alias table, not records.

### What a reader should distrust

1. The GitHub phrase counts are mention counts, not declaration counts. `"JSON License"`
   returns 33,779 repositories, which is a count of repositories that talk about JSON. Where
   a candidate rests on a phrase count alone its score is small and its row says so.
2. The Hugging Face counts are the hub's own figure for a tag, read from the listing page,
   because the API no longer returns a total. A tag that returns 0 may not exist rather than
   be unused.
3. The public reports measure different populations and they disagree structurally below the
   top five. `GPL-3.0` is third by developer count on GitHub and absent from the Black Duck
   audit top 10.
4. No source publishes a ranked list longer than about 25 licences, so nothing here is
   evidence that the long tail of permissive variants is or is not used. Their selection
   rests on list membership and on judgement.

---

## 12. The dependency graph review

The library had been read against its legal texts twice; the graph the checker reasons with
had not been read against the vocabulary at all. It was read on 2026-09-23, and every
decision below names the definition it rests on. Nothing here is legal advice.

### What was there

The action vocabulary holds **77 terms**: the 49 that `dalicc-ns.ttl` defines and 28 from
ODRL and Creative Commons. 49 of the 77 may be used only in a permission or a prohibition,
21 only as a duty, and 7 as either. The graph mentioned **29 of them in 41 axioms**, so
**48 terms had no axiom at all**. That is not in itself wrong, because most of those terms
name a notice, a condition or a trigger that no other term subsumes; it becomes wrong when a
term the data leans on is missing, and one was.

`cc:CommercialUse` is the most used action in the library after the four that every record
states: **579 `odrl:action` triples** name it, 410 records permit it and 169 prohibit it. It
was in no axiom. Three axioms spoke about `odrl:commercialize` instead, and **no record
names `odrl:commercialize`**, so "charging a licence fee entails commercializing", "selling
is commercializing" and "keeping a work exclusive contradicts commercializing it" concluded
nothing about any licence in the library, and nothing about any licence a visitor could
compose, because `odrl:commercialize` is not offered for authoring either.

### The sweep, before and after

`scripts/review/consistency_sweep.py` over all **581** records:

| | Records checked | Records with a conflict | Which |
|---|---|---|---|
| Before (41 axioms) | 581 | 2 | `DataExplorationLicence`, `DeveloperLicense` |
| After (46 axioms) | 581 | 2 | `DataExplorationLicence`, `DeveloperLicense` |

The two are the Ordnance Survey evaluation licences of [open issue 2](#6-open-issues), and
they stay. No record changed:
**no candidate axiom produced a conflict that a licence text supports**, so this review
proposes no correction. Every axiom that would have produced one was rejected, and each
rejection below names the text that rules it out.

`DataExplorationLicence` now reports its conflict twice, once against its
`cc:DerivativeWorks` prohibition and once against its `odrl:distribute` prohibition, because
a derivative work is now a kind of distribution. Both readings are true of that record, and
the check was changed to report both rather than only the longer chain.

Beyond the library, the change is measurable on bundles: over every pair of the graph's own
actions, **five conflicts are reported that were not, and one is no longer reported**. They
are listed as change 51 in BACKWARD_COMPATIBILITY.md.

### What was added

**`cc:CommercialUse owl:sameAs odrl:commercialize`**, and its inverse. `cc:CommercialUse` is
"income-generating use of any kind, whether direct or indirect. This spans from generating
revenue by selling the work (i.e. charging a license fee) to using it for advertising
purposes"; `odrl:commercialize` is "use the asset in a business environment", and the DALICC
term table already called it "the reasoning counterpart of Commercial use". They are one act
under two names, which is what `owl:sameAs` is for. This is the axiom that makes the other
three about commercial exploitation reach the data.

**`dalicc:sellCopy odrl:includedIn odrl:sell`**. `dalicc:sellCopy` is "the Assignee may sell
the copies of the License Material" and `odrl:sell` is "trade the asset for consideration",
so selling copies is one way of selling. Through `odrl:sell odrl:includedIn
odrl:commercialize` a prohibition of commercial use now reaches it. The subsumption runs one
way only, which is what the seven records that permit commercial use and forbid selling
copies need: Commons Clause, Bitstream Vera, the four OFL records and the Timescale licence
all allow a business to use the work and forbid selling the work itself.

**`cc:DerivativeWorks odrl:includedIn odrl:distribute`** and **`dalicc:ModifiedWorks
odrl:includedIn odrl:distribute`**. The first is "derivative works means to distribute the
derivative and making it available to the public"; the second is "distributing a modified
version of the work and making it available to the public". Both definitions begin by
distributing, and `odrl:distribute` is "providing the work to the public or making it
accessible to anyone else", so both are kinds of it. `odrl:modify` is untouched, because
altering a work is not publishing it.

**Three inverse `owl:sameAs` spellings**: `odrl:AttachPolicy owl:sameAs cc:Notice`,
`odrl:attachSource owl:sameAs cc:SourceCode` and `odrl:shareAlike owl:sameAs cc:ShareAlike`.
The change log of version 3 says the graph states every `owl:sameAs` pair in both
directions; three pairs did not, and a reader of the viewer saw some synonyms listed twice
and others once. A test now keeps the convention true.

### What was removed

**`odrl:extract owl:sameAs odrl:copy`**. `odrl:extract` is "extract part of the asset", and
its own entry places it "included in Reproduce", which the graph also says. Calling it the
same act as `odrl:copy`, which is the same act as `odrl:reproduce`, put extract, copy and
reproduce in one equivalence class, so permitting the extraction of a part permitted copying
the whole and a prohibition of extraction reached reproduction. The subsumption carries
everything that does follow.

**`odrl:reproduce odrl:includedIn odrl:copy`**. `odrl:copy owl:sameAs odrl:reproduce` is in
the graph, both ways. A subsumption between two names for one act states nothing, and it put
the same pair in two rows of the viewer under two different readings.

**`odrl:display odrl:includedIn odrl:play`**. `odrl:display` is "create a static and
transient rendition of the work" and `odrl:play` is "render the asset in an audio or video
form". A static rendition is not an audio or video one. ODRL makes the two siblings, both
under `odrl:present`, and the graph keeps `odrl:display odrl:includedIn odrl:present`.

### What was weighed and rejected

Each of these was tested over all 581 records. An axiom is rejected when a real licence text
can permit one side and prohibit the other without contradicting itself.

**Charging a distribution fee and commercial use.** `dalicc:chargeDistributionFee` is "a fee
covering the act of providing the work to a third party". An `odrl:implies
odrl:commercialize` on it makes **158 records** conflict, every NonCommercial record among
them: CC BY-NC 4.0 permits recovering the cost of handing a copy over and prohibits use
"primarily intended for or directed toward commercial advantage or private monetary
compensation". This is [open issue 1](#6-open-issues) and the present modelling is kept.

**Using for model training and deriving.** `dalicc:useForModelTraining` is "using the
licensed material to train, validate or tune an automated system that learns from data";
`odrl:derive` is "to create a new work from an existing work ... any translation, adaptation,
arrangement, modification, or any other substantial alteration". A trained model is not an
alteration of the training material, and the Llama 2 and Llama 3 community licences permit
deriving and prohibit training on the outputs in the same document. Rejected.

**Computational use only and commercial use.** `dalicc:computationalUseOnly` is "using the
work only as the input of a computation ... as against publishing or performing the work
itself". It says nothing about income. `C-UDA-1.0` requires it and permits
`cc:CommercialUse`, which is the whole point of a computational use of data agreement.
Rejected.

**The network-use trigger and the source-code duties.** `dalicc:networkUseTrigger` is
"making the work available over a network, deploying it or providing a service with it ...
that act triggers the duties the license would otherwise attach to distribution, so the
duties hang off this action rather than off `odrl:distribute`". Which duties is the
licence's business, not the graph's: `AGPL-3.0` hangs `cc:SourceCode` on it, and
`BigCode-OpenRAIL-M` hangs attribution, a notice and a duty to pass the use restrictions on.
Nor is network use a kind of distribution: the AGPL exists because it is not. Rejected both
ways.

**The excepted combination and share-alike.** `dalicc:exceptedCombination` is "combining or
linking the covered work with the material the exception names and conveying the result
without the condition the exception lifts". A `dalicc:contradicts cc:ShareAlike` on it makes
**17 records** conflict, every GPL-with-exception record among them: the exception exists
inside a reciprocal licence, so `GPL-2.0-only-with-Classpath-exception-2.0` states both on
purpose. Rejected.

**Exempted material.** `dalicc:exemptedMaterial` is "using material that the license
expressly carves out of its grant". Thirteen records prohibit it and none permits it, and no
other action subsumes it, entails it or excludes it. No axiom.

**The patent grant, the patent freedom condition and patent retaliation.**
`dalicc:patentGrant` is "an express license to the patent claims a contributor holds that the
contribution necessarily infringes"; `dalicc:patentRetaliationTermination` is "bringing a
patent claim over the licensed work"; `dalicc:patentFreedomCondition` is "the condition that
a patent reading on the work must be licensed for free and unrestricted use by everyone".
**Sixty-eight records** permit the grant and prohibit the retaliation, which is the
Apache-2.0 shape and the opposite of a contradiction, and the freedom condition is about a
patent licence rather than about a fee for the copyright licence. No axiom.

**Technical protection measures and the anti-circumvention terms.**
`dalicc:applyTechnicalProtectionMeasures` is "applying technological measures that control
access to the work or its use". Seven records prohibit it. The relation to the rights the
licence grants is that the measure must not defeat them, which none of the four relations
can say: it is not subsumption, entailment, synonymy or mutual exclusion. No axiom, and a
term for it would be a vocabulary question rather than a graph one.

**Promote, endorsement and trademark use.** `dalicc:promote` is "the licensee can use the
licensor's trademark for advertising and promotion purposes" and `dalicc:trademarkNotice`
carries the sentence that the licence "does not grant permission to use the trade names,
trademarks, service marks, or product names of the Licensor". Permission to use somebody
else's mark is not income from the work, and a licence can require the standard notice and
separately permit a named promotional use, which is Apache-2.0 section 6 beside a trademark
policy. No axiom.

**The modification notice, renaming and modifying.** `dalicc:modificationNotice` is
"providing a modification note means to document any changes done to the work"; it is
already `odrl:includedIn odrl:AttachPolicy`, which is `owl:sameAs cc:Notice`, so a
prohibition of notices reaches it. `dalicc:rename` is "change the title of the modified or
derived work so that it can be clearly distinguished from the original work", which is a duty
about naming the result, not a way of altering the work. No axiom.

**The change-licence permission, the compliant-licence duty and share-alike.** This is rule 3
of `consistency_check`: share alike required of the whole work, `dalicc:ChangeLicense`
permitted, and no `dalicc:compliantLicense` duty under that permission. It stays in code, and
the code now says why. The four relations of a graph hold between **two actions**; nothing in
them can say that a permission lacks a duty, which is exactly what the rule tests. Everything
else `consistency_check` concludes is a statement of the graph or a chain of them, so a
deployment that edits the graph edits the check.

**Reproduce, distribute, display, present and their ODRL parents.** `odrl:print` is "produce
a hard copy of the asset" and ODRL places it, like `odrl:display`, under `odrl:present`; both
stay. `odrl:display odrl:includedIn odrl:present` also matches the library, where the two
records that prohibit presenting prohibit displaying as well.

**Derive against modify against `cc:DerivativeWorks`.** Three candidates, all rejected.
`odrl:modify odrl:includedIn odrl:derive` conflicts with the terms' own instruction, "if
modifying the work results in a new work the action derive should be chosen", and it makes
`InspireEndUserLicence` contradict itself. `dalicc:ModifiedWorks odrl:includedIn
cc:DerivativeWorks` is refused by the definition of the first, "the counterpart of
cc:DerivativeWorks for alterations that do not amount to a new, derivative work".
`odrl:modify odrl:implies dalicc:ModifiedWorks` would repeat the flaw of `odrl:derive
odrl:implies cc:DerivativeWorks` that open issue 2 is about, and `DeveloperLicense` permits
altering the data and forbids supplying the result.

**Sublicensing and the grant of use** are related by `owl:sameAs` since version 3, and the
Creative Commons sublicensing prohibition meets an MIT-style grant through it. **Attribution
and notice** are related by `cc:Attribution odrl:implies cc:Notice`. Both already hold.

**Sui generis database rights and the dataset targets.** `dalicc:suiGenerisDatabaseRights` is
"exercising the database right that protects a substantial investment in obtaining, verifying
or presenting the contents of a database". Eight records permit it, none prohibits it, and
whether a licence fits a dataset is the asset-type check the License Mixer runs beside the
conflicts, not a statement about actions. No axiom.

**Adding a limitation and adding a statement.** `dalicc:addLimitation` is "adding further
limitations or restrictions to the license terms when redistributing the work";
`dalicc:addStatement` is "attaching additional terms, notices or statements to the work when
redistributing it". An `odrl:includedIn` between them makes
`CommonPublicAttributionLicenseVersion10` contradict itself, and that record follows the
Mozilla 1.1 shape, which forbids altering the terms of the source it received and allows
extra obligations on the executable it distributes. Rejected. `dalicc:conditionalAddLimitation`
is "the qualified form of dalicc:addLimitation", and the qualified form exists precisely to
name what a licence allows although it forbids the general act, so it is not a special case
of it for the checker's purposes either. No record states both, so the sweep decides nothing
here and the graph stays silent.

**The umbrella.** `odrl:use` subsumes the fourteen usage actions the graph relates, and the
remaining DALICC actions are notices, conditions and triggers rather than uses. Adding them
would draw no conclusion the check can use: no record prohibits `odrl:use`, and it is not
offered for authoring.

### What the two checks now agree on

`app/services/composer.py` and `reasoner/app/programs/query.lp` are two implementations of
one reading, and a chain that crosses from one relation of the graph into another was where
they parted. Over every ordered pair of the graph's own actions, **eighteen pairs got
different answers** from the form and from the program: the program stopped at a synonym, and
at the step from an entailment into a subsumption, while the form walked both. The program
now composes `owl:sameAs` with the other three relations and carries an entailment on into a
subsumption, and the disagreement is **nil** over all 1,395 comparisons. The test is
`tests/unit/test_composer_reasoner.py`, and it runs where `clingo` is installed.

### What this section does not settle

Open issue 2 is untouched and is now slightly wider: because a derivative work is a kind of
distribution, a licence that permits deriving also meets a licence that prohibits
distributing. That follows from `odrl:derive odrl:implies cc:DerivativeWorks`, which the
content review decided to keep and which conflates making a derivative with publishing one.
Weakening it is still the open question, and it now affects one more pair of statements.
