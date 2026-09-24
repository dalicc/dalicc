# Review records

Part of the [documentation index](../../README.md#documentation). One YAML file per license
record, holding the result of checking it against the legal text it models, for anyone
reviewing or correcting the library.

`licensedata/reviews/<id>.yaml` is the sidecar of `licensedata/licenses/<id>.ttl`. There
are 581 of each, and `scripts/validate_data.py` fails if a record has no review file or a
review file no record.

A review record says what was looked at, what was found, what was changed and what was only
proposed. It is data about the data: it is never loaded into the triple store and never
appears in `licenselibrary.ttl`. The record itself carries the outcome as
`dalicc:reviewStatus` and `dalicc:reviewedOn`. The reviewer of the current library is Giray
Havur; the review date is 2026-09-15 for the 460 records the content review covered and
2026-09-22 for the 121 records added with the licences GitHub projects use. The
consolidated report is [docs/LICENSE_REVIEW.md](../../docs/LICENSE_REVIEW.md).

Nothing in this folder is legal advice.

## What a reviewer works from

* the record itself, `licensedata/licenses/<id>.ttl`;
* the legal text of the license, from the SPDX license list, from `cc:legalcode` or from
  `dct:source`;
* the DALICC vocabulary, `licensedata/vocabulary/dalicc-ns.ttl`, which is the only source of
  valid `dalicc:` terms;
* the modelling conventions and the known-issues list in [docs/DATA.md](../../docs/DATA.md);
* the consistency check, `app.services.composer.consistency_check`, run with the dependency
  graph from `licensedata/dependencygraph/dg_default.ttl`.

## The record

```yaml
id: Apache-2.0
title: Apache License, Version 2.0
reviewed_on: 2026-09-15          # YYYY-MM-DD
reviewer: Giray Havur
text_source: http://www.apache.org/licenses/LICENSE-2.0   # or the word unavailable
text_retrieved: true             # true or false
verdict: correct                 # see the table below
summary: >-
  Two or three sentences. What the record models, whether it matches the text,
  what the reader should know before trusting it.
findings:
  - rubric: 5                    # 1 to 10, the rubric point below
    severity: major              # major, minor, gap or info
    field: odrl:duty
    description: What is wrong or missing, and what in the license text says so.
    action: proposed             # applied, proposed, none or superseded
    change: |                    # optional: the exact triples to add or remove
      odrl:permission [ a odrl:Permission ;
              odrl:action odrl:distribute ;
              odrl:duty [ a odrl:Duty ; odrl:action cc:SourceCode ] ] ;
family: Apache Software Foundation
port_of: null                    # the parent record, for a jurisdiction port
variant_kind: null               # see the table below
variant_of: null                 # the base record, for a version-option, exception or rider
notes: Anything that did not fit a finding.
```

The keys are required and come in that order: `id`, `title`, `reviewed_on`, `reviewer`,
`text_source`, `text_retrieved`, `verdict`, `summary`, `findings`, `family`, `port_of`,
`variant_kind`, `notes`. `scripts/validate_data.py` fails on a missing one. `variant_of` is
a later key and is optional: the 121 records added on 2026-09-22 carry it and the 460 older
ones do not. Every finding carries `rubric`, `severity`, `field`, `description`, `action`
and, where it proposes or records a change, `change`.

`port_of`, `variant_kind` and `variant_of` are all `null` on a record that stands on its
own. They are what `dalicc:jurisdictionPortOf`, `dalicc:variantKind` and `dalicc:variantOf`
in the `.ttl` are derived from, and the first of them is what groups the listings.

| `variant_kind` | What the record is | Names a base in |
|---|---|---|
| `jurisdiction-port` | the same licence adapted to another legal system | `port_of` |
| `translation` | the same licence in another language | `port_of` |
| `version` | an earlier or later version of the same licence text | `port_of`, when the library holds the other version |
| `edition` | the same text reissued by another body | `port_of` |
| `version-option` | the or-later identifier of a licence whose `-only` identifier is the base | `variant_of` |
| `exception` | the base licence read together with one SPDX exception | `variant_of` |
| `rider` | the base licence with a rider such as the Commons Clause | `variant_of` |

The last three are variants rather than ports: they model the base record's own legal text
with one thing changed, so they are licences of their own and are listed like any other.
`scripts/validate_data.py` checks that each of them names an existing base record.

Write ASCII punctuation. No long dashes anywhere, in this folder or in the data: use commas,
colons, periods, parentheses or plain hyphens.

The ASCII rule covers punctuation, not the letters of a quoted text. A quotation of a legal
text keeps the text's own letters, "Sie dürfen den Schutzgegenstand nicht unterlizenzieren",
not a transliteration such as "duerfen": a quotation that is not verbatim is not a
quotation. `scripts/review/restore_quoted_letters.py` gave 2,230 words their letters back
in 106 review records and 47 change logs, by looking each quotation up in the legal text of
its record.

## Verdicts

| verdict | meaning |
|---|---|
| `correct` | the record matches the legal text and the conventions; nothing was changed |
| `corrected` | one or more clear-cut, text-supported changes were applied to the `.ttl` |
| `created` | the record did not exist and was written from the legal text |
| `issues-proposed` | findings exist but every one of them is interpretive, so nothing was changed |
| `text-unavailable` | the legal text could not be retrieved, so the record could not be checked against it |

A record can be both corrected and carry proposals. Use `corrected` when anything was
applied, and list the proposals as findings with `action: proposed`.

A proposal that a later version of the record applied is no longer open. Its finding reads
`action: superseded` and carries one more key, `superseded_by`, the number of the version
whose change list applied it:

```yaml
    action: superseded
    superseded_by: 2
```

The record page folds such findings under "Settled in version N", so the review box and the
History below it agree. `scripts/review/mark_superseded.py` finds them: it reads the
`change` block of every proposed finding as Turtle, checks that the current record says
what the block asks for, and checks that a version's change list records that very change,
matched by predicate, deontic kind and `odrl:action`. A proposal that offers alternatives,
abbreviates a literal with `...`, is only partly applied, or is true without a change that
says so stays `proposed`. Run it after a version applies a proposal; it is idempotent.

`created` belongs to a record written from scratch rather than checked. Such a record starts
at `dct:hasVersion "1"` with `dalicc:reviewStatus dalicc:Created`, archives nothing, and
every statement in it is a finding with `action: applied`, because the record is the finding.

## The rubric

1. Identification: title, `dct:alternative`, `spdx:licenseId` present and correct;
   `cc:legalcode` and `dct:source` valid and pointing at the right version.
2. Targets: the asset types are plausible for the license (software, dataset, creative work,
   hardware).
3. Permissions: each modelled permission is supported by the text, and the ones the text
   clearly grants are present (reproduce, distribute, modify, derive, display, present,
   commercial use, sublicense or grant use, charge a fee).
4. Prohibitions: each is supported, and the ones the text clearly states are present
   (commercial use, derivatives, trademark or endorsement use, sublicensing, technical
   protection measures where the vocabulary has a term, otherwise a vocabulary gap).
5. Duties: the ones present are supported and the missing ones are named (attribution,
   notice or license copy, source code, share-alike, modification notice, rename, compliant
   license). Check the attachment level too: a duty tied to the right permission (distribute,
   modify, derive) rather than license-wide, and no duplicates.
6. Clause texts: `dalicc:WarrantyDisclaimer`, `dalicc:LiabilityLimitation` and
   `dalicc:additionalClauses` are present when the text has them, quoted accurately and not
   paraphrased.
7. Jurisdiction and validity: worldwide and perpetual unless the text says otherwise; a
   ported Creative Commons 3.0 license carries the country of its legal code.
8. Vocabulary gaps: patent grant, patent retaliation, termination, no-trademark, anti-DRM,
   the network-use trigger of AGPL and anything else the vocabulary cannot express. Record
   these as `severity: gap` with a proposed term. Never bend an existing term to cover them.
9. Internal consistency: run the consistency check and record the conflicts.
10. Family consistency: variants of one family model their shared clauses identically, ports
    and translations match their parent, and duplicates or near-duplicates are named together
    with a judgement on whether separate records are justified.

Severity: `major` when a permission, prohibition or duty is wrong or missing in a way that
changes the compatibility outcome; `minor` for metadata, clause text and placement issues
that do not; `gap` when the vocabulary cannot express the term; `info` for observations.

## Corrections policy

Apply directly, and record as `action: applied`, only changes the license text supports
without interpretation:

* add a missing `spdx:licenseId` taken from the SPDX license list;
* add or fix `cc:legalcode` and `dct:source` URLs;
* add a permission, prohibition or duty the text states unambiguously and the vocabulary
  already expresses;
* remove a duplicated or contradictory statement;
* fix a misplaced duty attachment where the text is explicit about the trigger;
* add a missing clause text, quoted from the license.

Everything interpretive stays `action: proposed`, with the exact triples to add or remove,
and is left open for the decision of the association.

Never delete a license record. Never change a license id or IRI. Never edit
`licensedata/licenselibrary/licenselibrary.ttl` by hand: it is generated.

## After an edit

```bash
python scripts/build_licenselibrary.py      # rebuild licenselibrary.ttl from licenses/*.ttl
python scripts/validate_data.py             # the gate: parses, compares, checks conventions
python scripts/review/family_rules.py --strict   # the family rules; rule 14 is left out of the exit status
```

Run all three before you hand a change on. `--strict` exits non-zero on a violation of any
rule but rule 14 (a padding space inside a clause literal), which is known not to be clean
and is left out by default; `--count-every-rule` counts it as well.
[The license data and its terms](../README.md) has the rest of the data workflow, including
how to reload a running stack.
