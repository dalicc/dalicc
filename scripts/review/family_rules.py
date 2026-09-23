#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""Check that licenses of one family are modelled the same way.

A reader compares two records and expects the difference between them to be a difference
between the two licenses, not a difference between two reviewers.  The 2026-09-15 content
review produced a hand-written baseline of family rules; the standard-license addition
turned it into this script, extended it with the rules decision 10 names, and made it
runnable so that a data change can be checked against the same expectations.

Every rule states what the convention requires, how many records it applies to and which
ids break it.  A violation is a starting point, not a verdict: the legal text decides.

Rules
-----
1   GNU-style copyleft records carry both cc:SourceCode and cc:ShareAlike.
2   Creative Commons NonCommercial records prohibit cc:CommercialUse.
3   Creative Commons NoDerivatives records prohibit derivative works.
4   Creative Commons ShareAlike records carry a cc:ShareAlike duty.
5   Permissive records make no share-alike statement at all, in any position.
6   Every record carries an attribution or a notice duty, except the dedications.
7   A record with neither a prohibition nor a duty is probably incomplete.
8   Asset targets match the kind of work the license governs.
9   A patent-granting record uses dalicc:patentGrant, and a patent-retaliation clause
    uses dalicc:patentRetaliationTermination; the two travel together where the text has
    both.
10  A record that quotes a warranty clause also quotes the liability clause, when the
    license has one, instead of keeping both inside dalicc:WarrantyDisclaimer.
11  No record repeats a permission or a prohibition for the same action.
12  A jurisdiction port names the country of its legal code in cc:jurisdiction.
13  Reciprocity has one shape per kind: whole-work copyleft is a license-wide
    cc:ShareAlike duty, file-level copyleft hangs it off the acts, and a record that
    permits dalicc:ChangeLicense beside a license-wide share-alike carries the
    dalicc:compliantLicense duty (consolidation decision 4 of 2026-09-15).
14  A clause literal has no padding space and no placeholder value.
15  A permissive record permits dalicc:ChangeLicense and never prohibits it: the notice
    clause of a permissive license is a duty that travels with the copy, not a bar on
    putting the copy under other terms, except where the text bars it in as many words.
16  An or-later record says what its base record says: the same permissions with the same
    duties, the same prohibitions, the same license-wide duties, the same asset types and
    the same clause texts.
17  An exception record and a rider record keep everything their base record says and add
    what the exception or the rider changes.
18  Creative Commons records of one version of the unported text agree on the asset types,
    on the termination terms and on the moral-rights statement.
19  A record prohibits dalicc:promote only where a sentence of its text says so. What a
    licence that is silent about endorsement grants is a legal default, and the default
    lives in the dependency graph as an adopted dalicc:DefaultRule, not in the records.
20  A Creative Commons record permits dalicc:suiGenerisDatabaseRights exactly where its own
    text settles the database right, and the duties on that permission are the ones that
    text attaches: the conditions of Section 3(a) on the six 4.0 records, none on the 3.0
    ports, whose own carve-out takes the restrictions off the database layer.

Usage
-----
    python scripts/review/family_rules.py
    python scripts/review/family_rules.py --json
    python scripts/review/family_rules.py --markdown > report.md
    python scripts/review/family_rules.py --strict      # exit 1 on any violation
    python scripts/review/family_rules.py --strict --skip-rule 14
    python scripts/review/family_rules.py --strict --skip-rule 14,16

``--skip-rule`` names the rules whose violations do not count towards the exit status.
It is repeatable and accepts a comma-separated list.  The rules still run and still
print their counts; the report names what was skipped and how many violations the exit
status left out, so the printed total and the counted total can be told apart.  Rule 14
is the one the gate skips today: its 575 padding-space violations are a known cosmetic
issue that takes 287 records to a new version to fix, which docs/DATA.md explains and
which wants a commit of its own.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import sys

import rdflib
from rdflib.namespace import RDF, Namespace

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSES_DIR = REPO_ROOT / "licensedata" / "licenses"

CC = Namespace("http://creativecommons.org/ns#")
DALICC = Namespace("https://dalicc.net/ns#")
DCT = Namespace("http://purl.org/dc/terms/")
DCMITYPE = Namespace("http://purl.org/dc/dcmitype/")
ODRL = Namespace("http://www.w3.org/ns/odrl/2/")
DALICCLIB = Namespace("https://dalicc.net/licenselibrary/")

LOG = logging.getLogger("family_rules")

#: The records whose own text bars the use of the licensor's name or mark, and which
#: therefore state the dalicc:promote prohibition.  Every other record is silent about
#: endorsement and gets the answer from the adopted default rule of the core dependency
#: graph instead, which is what rule 19 checks.  The set was read off the texts and the
#: review records one record at a time on 2026-09-23; docs/LICENSE_REVIEW.md section 13
#: says how each side was decided.
TEXT_SUPPORTED_PROMOTE: frozenset[str] = frozenset({
    "AAL", "AFL-1.1", "AFL-1.2", "AFL-2.0", "AFL-2.1", "AFL-3.0", "APSL-1.0", "APSL-1.1",
    "APSL-1.2", "APSL-2.0", "Apache-1.0", "Apache-1.1", "Apache-2.0",
    "Apache-2.0-with-Commons-Clause", "Apache-2.0-with-LLVM-exception",
    "Apple-ML-Research-Model-License", "Artistic-1.0", "Artistic-1.0-Perl", "Artistic-1.0-cl8",
    "Artistic-2.0", "AttributionNoncommercial20Brazil", "AttributionNoncommercial20Croatia",
    "AttributionNoncommercial20Italy", "AttributionNoncommercial30Armenia",
    "AttributionNoncommercial30Azerbaijan", "AttributionNoncommercial30Brazil",
    "AttributionNoncommercial30Chile", "AttributionNoncommercial30China",
    "AttributionNoncommercial30CostaRica", "AttributionNoncommercial30Croatia",
    "AttributionNoncommercial30Czechia", "AttributionNoncommercial30Ecuador",
    "AttributionNoncommercial30Egypt", "AttributionNoncommercial30Estonia",
    "AttributionNoncommercial30France", "AttributionNoncommercial30Germany",
    "AttributionNoncommercial30Guatemala", "AttributionNoncommercial30Ireland",
    "AttributionNoncommercial30Italy", "AttributionNoncommercial30Luxembourg",
    "AttributionNoncommercial30Netherlands", "AttributionNoncommercial30NewZealand",
    "AttributionNoncommercial30Norway", "AttributionNoncommercial30Philippines",
    "AttributionNoncommercial30Poland", "AttributionNoncommercial30Portugal",
    "AttributionNoncommercial30Romania", "AttributionNoncommercial30Singapore",
    "AttributionNoncommercial30SouthAfrica", "AttributionNoncommercial30Thailand",
    "AttributionNoncommercial30Uganda", "AttributionNoncommercial30Venezuela", "BSD-3-Clause",
    "BSD-3-Clause-Attribution", "BSD-3-Clause-Clear", "BSD-3-Clause-LBNL",
    "BSD-3-Clause-Open-MPI", "BSD-4-Clause", "BSD-ask-to-endorse", "BUSL-1.1",
    "BigCode-OpenRAIL-M", "BigScience-BLOOM-RAIL-1.0", "BigScience-OpenRAIL-M",
    "Bitstream-Vera", "CAL-1.0", "CAL-1.0-Combined-Work-Exception", "CATOSL-1.1", "CC-BY-3.0",
    "CC-BY-4.0", "CC-BY-NC-3.0", "CC-BY-NC-4.0", "CC-BY-NC-ND-3.0", "CC-BY-NC-ND-4.0",
    "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-4.0", "CC-BY-ND-3.0", "CC-BY-ND-4.0", "CC-BY-SA-3.0",
    "CC-BY-SA-4.0", "CDDL-1.1", "CERN-OHL-P-2.0", "CERN-OHL-S-2.0", "CERN-OHL-W-2.0",
    "CNRI-Python", "CNRI-Python-GPL-Compatible", "CUA-OPL-1.0", "Cc010Universal",
    "CommonDevelopmentAndDistributionLicense10", "CommonPublicAttributionLicenseVersion10",
    "Confluent-Community-1.0", "CreativeCommonsAttribution20Brazil",
    "CreativeCommonsAttribution20Croatia", "CreativeCommonsAttribution20Italy",
    "CreativeCommonsAttribution30Armenia", "CreativeCommonsAttribution30Azerbaijan",
    "CreativeCommonsAttribution30Brazil", "CreativeCommonsAttribution30Chile",
    "CreativeCommonsAttribution30China", "CreativeCommonsAttribution30CostaRica",
    "CreativeCommonsAttribution30Croatia", "CreativeCommonsAttribution30Czechia",
    "CreativeCommonsAttribution30Ecuador", "CreativeCommonsAttribution30Egypt",
    "CreativeCommonsAttribution30Estonia", "CreativeCommonsAttribution30France",
    "CreativeCommonsAttribution30Germany", "CreativeCommonsAttribution30Guatemala",
    "CreativeCommonsAttribution30Ireland", "CreativeCommonsAttribution30Italy",
    "CreativeCommonsAttribution30Luxembourg", "CreativeCommonsAttribution30Netherlands",
    "CreativeCommonsAttribution30NewZealand", "CreativeCommonsAttribution30Norway",
    "CreativeCommonsAttribution30Philippines", "CreativeCommonsAttribution30Poland",
    "CreativeCommonsAttribution30Portugal", "CreativeCommonsAttribution30Romania",
    "CreativeCommonsAttribution30Singapore", "CreativeCommonsAttribution30SouthAfrica",
    "CreativeCommonsAttribution30Thailand", "CreativeCommonsAttribution30Uganda",
    "CreativeCommonsAttribution30Venezuela", "CreativeCommonsAttributionNoderivs20Brazil",
    "CreativeCommonsAttributionNoderivs20Croatia", "CreativeCommonsAttributionNoderivs20Italy",
    "CreativeCommonsAttributionNoderivs30Armenia",
    "CreativeCommonsAttributionNoderivs30Azerbaijan",
    "CreativeCommonsAttributionNoderivs30Brazil", "CreativeCommonsAttributionNoderivs30Chile",
    "CreativeCommonsAttributionNoderivs30China",
    "CreativeCommonsAttributionNoderivs30CostaRica",
    "CreativeCommonsAttributionNoderivs30Croatia",
    "CreativeCommonsAttributionNoderivs30Czechia",
    "CreativeCommonsAttributionNoderivs30Ecuador", "CreativeCommonsAttributionNoderivs30Egypt",
    "CreativeCommonsAttributionNoderivs30Estonia", "CreativeCommonsAttributionNoderivs30France",
    "CreativeCommonsAttributionNoderivs30Germany",
    "CreativeCommonsAttributionNoderivs30Guatemala",
    "CreativeCommonsAttributionNoderivs30Ireland", "CreativeCommonsAttributionNoderivs30Italy",
    "CreativeCommonsAttributionNoderivs30Luxembourg",
    "CreativeCommonsAttributionNoderivs30Netherlands",
    "CreativeCommonsAttributionNoderivs30NewZealand",
    "CreativeCommonsAttributionNoderivs30Norway",
    "CreativeCommonsAttributionNoderivs30Philippines",
    "CreativeCommonsAttributionNoderivs30Poland",
    "CreativeCommonsAttributionNoderivs30Portugal",
    "CreativeCommonsAttributionNoderivs30Romania",
    "CreativeCommonsAttributionNoderivs30Singapore",
    "CreativeCommonsAttributionNoderivs30SouthAfrica",
    "CreativeCommonsAttributionNoderivs30Thailand",
    "CreativeCommonsAttributionNoderivs30Uganda",
    "CreativeCommonsAttributionNoderivs30Venezuela",
    "CreativeCommonsAttributionNoncommercialNoderivs20Brazil",
    "CreativeCommonsAttributionNoncommercialNoderivs20Croatia",
    "CreativeCommonsAttributionNoncommercialNoderivs20Italy",
    "CreativeCommonsAttributionNoncommercialNoderivs30Armenia",
    "CreativeCommonsAttributionNoncommercialNoderivs30Azerbaijan",
    "CreativeCommonsAttributionNoncommercialNoderivs30Brazil",
    "CreativeCommonsAttributionNoncommercialNoderivs30Chile",
    "CreativeCommonsAttributionNoncommercialNoderivs30China",
    "CreativeCommonsAttributionNoncommercialNoderivs30CostaRica",
    "CreativeCommonsAttributionNoncommercialNoderivs30Croatia",
    "CreativeCommonsAttributionNoncommercialNoderivs30Czechia",
    "CreativeCommonsAttributionNoncommercialNoderivs30Ecuador",
    "CreativeCommonsAttributionNoncommercialNoderivs30Egypt",
    "CreativeCommonsAttributionNoncommercialNoderivs30Estonia",
    "CreativeCommonsAttributionNoncommercialNoderivs30France",
    "CreativeCommonsAttributionNoncommercialNoderivs30Germany",
    "CreativeCommonsAttributionNoncommercialNoderivs30Guatemala",
    "CreativeCommonsAttributionNoncommercialNoderivs30Ireland",
    "CreativeCommonsAttributionNoncommercialNoderivs30Italy",
    "CreativeCommonsAttributionNoncommercialNoderivs30Luxembourg",
    "CreativeCommonsAttributionNoncommercialNoderivs30Netherlands",
    "CreativeCommonsAttributionNoncommercialNoderivs30NewZealand",
    "CreativeCommonsAttributionNoncommercialNoderivs30Norway",
    "CreativeCommonsAttributionNoncommercialNoderivs30Philippines",
    "CreativeCommonsAttributionNoncommercialNoderivs30Poland",
    "CreativeCommonsAttributionNoncommercialNoderivs30Portugal",
    "CreativeCommonsAttributionNoncommercialNoderivs30Romania",
    "CreativeCommonsAttributionNoncommercialNoderivs30Singapore",
    "CreativeCommonsAttributionNoncommercialNoderivs30SouthAfrica",
    "CreativeCommonsAttributionNoncommercialNoderivs30Thailand",
    "CreativeCommonsAttributionNoncommercialNoderivs30Uganda",
    "CreativeCommonsAttributionNoncommercialNoderivs30Venezuela",
    "CreativeCommonsAttributionNoncommercialSharealike20Brazil",
    "CreativeCommonsAttributionNoncommercialSharealike20Croatia",
    "CreativeCommonsAttributionNoncommercialSharealike30Armenia",
    "CreativeCommonsAttributionNoncommercialSharealike30Azerbaijan",
    "CreativeCommonsAttributionNoncommercialSharealike30Brazil",
    "CreativeCommonsAttributionNoncommercialSharealike30Chile",
    "CreativeCommonsAttributionNoncommercialSharealike30China",
    "CreativeCommonsAttributionNoncommercialSharealike30CostaRica",
    "CreativeCommonsAttributionNoncommercialSharealike30Croatia",
    "CreativeCommonsAttributionNoncommercialSharealike30Czechia",
    "CreativeCommonsAttributionNoncommercialSharealike30Ecuador",
    "CreativeCommonsAttributionNoncommercialSharealike30Egypt",
    "CreativeCommonsAttributionNoncommercialSharealike30Estonia",
    "CreativeCommonsAttributionNoncommercialSharealike30France",
    "CreativeCommonsAttributionNoncommercialSharealike30Germany",
    "CreativeCommonsAttributionNoncommercialSharealike30Guatemala",
    "CreativeCommonsAttributionNoncommercialSharealike30Ireland",
    "CreativeCommonsAttributionNoncommercialSharealike30Italy",
    "CreativeCommonsAttributionNoncommercialSharealike30Luxembourg",
    "CreativeCommonsAttributionNoncommercialSharealike30Netherlands",
    "CreativeCommonsAttributionNoncommercialSharealike30NewZealand",
    "CreativeCommonsAttributionNoncommercialSharealike30Norway",
    "CreativeCommonsAttributionNoncommercialSharealike30Philippines",
    "CreativeCommonsAttributionNoncommercialSharealike30Poland",
    "CreativeCommonsAttributionNoncommercialSharealike30Portugal",
    "CreativeCommonsAttributionNoncommercialSharealike30Romania",
    "CreativeCommonsAttributionNoncommercialSharealike30Singapore",
    "CreativeCommonsAttributionNoncommercialSharealike30SouthAfrica",
    "CreativeCommonsAttributionNoncommercialSharealike30Thailand",
    "CreativeCommonsAttributionNoncommercialSharealike30Uganda",
    "CreativeCommonsAttributionNoncommercialSharealike30Venezuela",
    "CreativeCommonsAttributionSharealike20Brazil",
    "CreativeCommonsAttributionSharealike20Croatia",
    "CreativeCommonsAttributionSharealike20Italy",
    "CreativeCommonsAttributionSharealike30Armenia",
    "CreativeCommonsAttributionSharealike30Azerbaijan",
    "CreativeCommonsAttributionSharealike30Brazil",
    "CreativeCommonsAttributionSharealike30Chile",
    "CreativeCommonsAttributionSharealike30China",
    "CreativeCommonsAttributionSharealike30CostaRica",
    "CreativeCommonsAttributionSharealike30Croatia",
    "CreativeCommonsAttributionSharealike30Czechia",
    "CreativeCommonsAttributionSharealike30Ecuador",
    "CreativeCommonsAttributionSharealike30Egypt",
    "CreativeCommonsAttributionSharealike30Estonia",
    "CreativeCommonsAttributionSharealike30France",
    "CreativeCommonsAttributionSharealike30Germany",
    "CreativeCommonsAttributionSharealike30Guatemala",
    "CreativeCommonsAttributionSharealike30Ireland",
    "CreativeCommonsAttributionSharealike30Italy",
    "CreativeCommonsAttributionSharealike30Luxembourg",
    "CreativeCommonsAttributionSharealike30Netherlands",
    "CreativeCommonsAttributionSharealike30NewZealand",
    "CreativeCommonsAttributionSharealike30Norway",
    "CreativeCommonsAttributionSharealike30Philippines",
    "CreativeCommonsAttributionSharealike30Poland",
    "CreativeCommonsAttributionSharealike30Portugal",
    "CreativeCommonsAttributionSharealike30Romania",
    "CreativeCommonsAttributionSharealike30Singapore",
    "CreativeCommonsAttributionSharealike30SouthAfrica",
    "CreativeCommonsAttributionSharealike30Thailand",
    "CreativeCommonsAttributionSharealike30Uganda",
    "CreativeCommonsAttributionSharealike30Venezuela", "CreativeML-OpenRAIL-M",
    "CreativeML-OpenRAIL-Mpp", "DOC", "DataExplorationLicence", "DeepFloyd-IF-License",
    "DeveloperLicense", "ECL-1.0", "ECL-2.0", "EUDatagrid", "EUPL-1.1", "EUPL-1.2",
    "Elastic-2.0", "Entessa", "FSL-1.1-ALv2", "FSL-1.1-MIT", "GFDL-1.1-only",
    "GFDL-1.1-or-later", "GFDL-1.2-only", "GFDL-1.2-or-later", "GFDL-1.3-invariants-only",
    "GFDL-1.3-invariants-or-later", "GFDL-1.3-no-invariants-only",
    "GFDL-1.3-no-invariants-or-later", "GFDL-1.3-or-later", "Gemma-Terms-of-Use",
    "GnuFreeDocumentationLicense", "HPND", "ICU", "IPA", "ImageMagick", "Info-ZIP", "Intel",
    "LiLiQ-P-1.1", "LiLiQ-R-1.1", "LiLiQ-Rplus-1.1", "Llama-2-Community-License",
    "Llama-3-Community-License", "Llama-3.1-Community-License", "Llama-3.2-Community-License",
    "Llama-3.3-Community-License", "Llama-4-Community-License", "MIT-CMU", "MPL-1.1",
    "MPL-2.0-no-copyleft-exception", "MS-RL", "MicrosoftPublicLicense", "Motosoto",
    "MozillaPublicLicenseVersion20", "MulanPSL-1.0", "MulanPSL-2.0", "Multics", "NASA-1.3",
    "NCGL-UK-2.0", "NCSA", "NLOD-2.0", "NPOSL-3.0", "NTP", "NVIDIA-Open-Model-License",
    "Naumen", "Nokia", "OCLC-2.0", "OFL-1.0", "OFL-1.1", "OFL-1.1-RFN", "OFL-1.1-no-RFN",
    "OGL-UK-1.0", "OGL-UK-2.0", "OGTSL", "OLDAP-2.8", "OLFL-1.3", "OSET-PL-2.1", "OSL-1.0",
    "OSL-2.0", "OSL-2.1", "OSL-3.0", "OdcOpenDatabaseLicense",
    "OdcPublicDomainDedicationAndLicence", "OpenDataCommonsAttributionLicenseV10",
    "OpenDataLicenceAgreement", "OpenGovernmentLicenceCanada", "OpenSSL",
    "OpenSupremeCourtLicence", "PHP-3.01", "PSF-2.0", "PhpLicense30", "Python-2.0.1",
    "PythonLicense20", "RPL-1.1", "RPL-1.5", "RPSL-1.0", "RSALv2", "RSCPL", "SISSL",
    "SimPL-2.0", "Sleepycat", "StatisticsCanadaOpenLicenceAgreement",
    "SunPublicLicenseVersion10", "Sustainable-Use-License", "UCL-1.0",
    "UkOpenGovernmentLicenseForPublicSectorInformation", "Unicode-3.0", "Unicode-DFS-2016",
    "VSL-1.0", "W3C", "W3cSoftwareAndDocumentNoticeAndLicense", "Watcom-1.0", "WordNet", "X11",
    "ZPL-2.0", "ZPL-2.1", "bzip2-1.0.6", "curl", "etalab-2.0",
})

#: The six Creative Commons 4.0 records.  Section 4 of that text grants the sui generis
#: database right and Section 4(c) carries the conditions of Section 3(a) over to it, so
#: their dalicc:suiGenerisDatabaseRights permission carries the attribution and notice
#: duties of the copyright grant.
CC_40_RECORDS: frozenset[str] = frozenset({
    "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-ND-4.0",
    "CC-BY-NC-ND-4.0",
})

#: The 3.0 jurisdiction ports whose own legal code settles the database right: fourteen
#: states of the Union whose text either grants the extraction and re-use of a substantial
#: part outright or waives the licensor's own database right, and in either case carves the
#: restrictions out of the material that qualifies only under that right.  Their permission
#: therefore carries no duty.  Read off the review records one port at a time on 2026-09-23;
#: the ports left out, and why, are in docs/LICENSE_REVIEW.md section 11.
DATABASE_RIGHT_PORT_COUNTRIES: tuple[str, ...] = (
    "Austria", "Croatia", "Czechia", "Estonia", "France", "Germany", "Greece", "Ireland",
    "Italy", "Luxembourg", "Netherlands", "Poland", "Portugal", "Romania",
)

#: The identifier of each element set of one 3.0 port.
CC_30_ELEMENT_SETS: tuple[str, ...] = (
    "CreativeCommonsAttribution30",
    "CreativeCommonsAttributionSharealike30",
    "AttributionNoncommercial30",
    "CreativeCommonsAttributionNoncommercialSharealike30",
    "CreativeCommonsAttributionNoderivs30",
    "CreativeCommonsAttributionNoncommercialNoderivs30",
)

#: Every Creative Commons record whose own text settles the sui generis database right,
#: which is what rule 20 checks.  A record that is silent about it gets the answer from the
#: proposed default rule eu-sui-generis-db of the EU dependency graph instead.
DATABASE_RIGHT_BY_TEXT: frozenset[str] = frozenset(
    set(CC_40_RECORDS)
    | {prefix + country
       for prefix in CC_30_ELEMENT_SETS
       for country in DATABASE_RIGHT_PORT_COUNTRIES}
)

#: Dedications: no attribution duty is expected, and a bare permission set is correct.
#: CC-PDDC is one of them: "Dedicator intends this dedication to be an overt act of
#: relinquishment in perpetuity of all present and future rights under copyright law".
DEDICATIONS = {
    "Cc010Universal", "OdcPublicDomainDedicationAndLicence", "WTFPL", "Unlicense",
    "MIT-0", "DL-DE-ZERO-2.0", "0BSD", "CC-PDDC",
}
#: Composer and test fixtures rather than published licenses.
FIXTURES = {"SampleLicenseSl", "DeveloperLicense"}
#: Placeholder values that mean "we did not know".
PLACEHOLDERS = {"n.n.", "- not specified -", "tbd", "unknown"}
#: Licenses whose only condition is not an attribution or a notice, confirmed against
#: the text: BSD-ask-to-endorse asks only that the copyright holder be asked before an
#: endorsement is claimed, and requires no notice to travel with a copy.  SSH-OpenSSH
#: asks nowhere that the copyright notice travel with a copy; its one condition is that
#: "any derived versions of this software must be clearly marked as such".
#: Intel-Research-Use-License asks for no notice, no attribution and no copy of the
#: agreement.  PolyForm-Strict-1.0.0 grants no right to distribute at all, so there is
#: nobody to pass a notice to.
NO_ATTRIBUTION = {
    "BSD-ask-to-endorse", "InspireEndUserLicence", "SSH-OpenSSH",
    "Intel-Research-Use-License", "PolyForm-Strict-1.0.0",
}
#: Records of rule 8 that govern data or content rather than software.
DATA_AND_CONTENT = {
    "C-UDA-1.0", "CDLA-Sharing-1.0", "OdcOpenDatabaseLicense",
    "OdcPublicDomainDedicationAndLicence", "DL-DE-ZERO-2.0",
}
#: Records where dalicc:patentRetaliationTermination carries a clause that is wider than
#: a patent claim, so there is no patent grant to travel with it.  Each is recorded as an
#: open interpretive issue in docs/LICENSE_REVIEW.md.  The six community model licenses
#: end the grant on a claim "alleging that the Llama Materials or ... outputs or results
#: ... constitutes an infringement of intellectual property or other rights owned or
#: licensable by you", which reaches every kind of right and is paired with no patent
#: license.
WIDER_THAN_PATENTS = {
    "CDLA-Permissive-1.0", "CDLA-Sharing-1.0", "OCLC-2.0",
    "Llama-2-Community-License", "Llama-3-Community-License",
    "Llama-3.1-Community-License", "Llama-3.2-Community-License",
    "Llama-3.3-Community-License", "Llama-4-Community-License",
}
#: Permissive by rule 15 although they ask for the source of a modified version: each
#: text names the licenses a licensee may move the work to (Vim clause 4, the Artistic
#: License 4(c)(ii), CeCILL-B Article 5.3.4), and CC0 waives every right there is.
RELICENSING_PERMITTED = {"Vim", "Artistic-2.0", "CECILL-B", "Cc010Universal"}
#: The mirror image of the set above: a permissive text that bars relicensing in as many
#: words, so the prohibition in the record is the text and not a misreading of a notice
#: clause.  Cube, clause 4, which the text itself heads "additional clause specific to
#: Cube": "Source versions may not be 'relicensed' under a different license without my
#: explicitly written permission."  The SSLeay half of the OpenSSL document: "The licence
#: and distribution terms for any publically available version or derivative of this code
#: cannot be changed. i.e. this code cannot simply be copied and put under another
#: distribution licence [including the GNU Public Licence.]"
RELICENSING_PROHIBITED_BY_TEXT = {"Cube", "OpenSSL"}
#: The acts a permissive license grants.  A record that forbids one of them is something
#: else, whatever its duties say, so rule 15 leaves it alone.
CORE_ACTS = frozenset({
    str(ODRL.derive), str(ODRL.modify), str(ODRL.distribute), str(ODRL.reproduce),
    str(CC.CommercialUse), str(CC.DerivativeWorks), str(DALICC.ModifiedWorks),
})


@dataclass
class Record:
    """One record, flattened into the shapes the rules ask about."""

    identifier: str
    title: str
    permitted: set[str] = field(default_factory=set)
    prohibited: set[str] = field(default_factory=set)
    license_wide_duties: set[str] = field(default_factory=set)
    duties_by_act: dict[str, set[str]] = field(default_factory=dict)
    targets: set[str] = field(default_factory=set)
    literals: dict[str, list[str]] = field(default_factory=dict)
    legalcode: str = ""
    jurisdiction: str = ""
    port_of: str = ""
    variant_kind: str = ""
    variant_of: str = ""
    license_version: str = ""
    repeated: int = 0

    @property
    def required(self) -> set[str]:
        out = set(self.license_wide_duties)
        for duties in self.duties_by_act.values():
            out |= duties
        return out

    @property
    def is_creative_commons(self) -> bool:
        return "creativecommons.org" in self.legalcode

    @property
    def clause_texts(self) -> frozenset[str]:
        """Every quoted clause of the record, whichever predicate holds it."""
        return frozenset(
            value
            for name in ("WarrantyDisclaimer", "LiabilityLimitation",
                         "WarrantyOrLiabilityAcceptance", "additionalClauses")
            for value in self.literals.get(name, [])
        )

    def statements_by_act(self, position: str) -> frozenset[tuple[str, tuple[str, ...]]]:
        """The permissions with the duties that hang off each of them."""
        del position  # only ``permitted`` has duties; the signature keeps the call sites alike
        return frozenset(
            (action, tuple(sorted(self.duties_by_act.get(action, set()))))
            for action in self.permitted
        )


def local(node) -> str:
    return str(node).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def load(path: Path) -> Record:
    graph = rdflib.Graph()
    graph.parse(path.as_posix(), format="turtle")
    subject = next(iter(graph.subjects(RDF.type, ODRL.Set)))
    record = Record(
        identifier=path.stem,
        title=next((str(v) for v in graph.objects(subject, DCT.title)), ""),
        legalcode=next((str(v) for v in graph.objects(subject, CC.legalcode)), ""),
        jurisdiction=next((str(v) for v in graph.objects(subject, CC.jurisdiction)), ""),
        port_of=next(
            (local(v) for v in graph.objects(subject, DALICC.jurisdictionPortOf)), ""),
        variant_kind=next((str(v) for v in graph.objects(subject, DALICC.variantKind)), ""),
        variant_of=next((local(v) for v in graph.objects(subject, DALICC.variantOf)), ""),
        license_version=next(
            (str(v) for v in graph.objects(subject, DALICC.licenseVersion)), ""),
    )
    seen: Counter[str] = Counter()
    for node in graph.objects(subject, ODRL.permission):
        for action in graph.objects(node, ODRL.action):
            record.permitted.add(str(action))
            seen[f"permission {action}"] += 1
            bucket = record.duties_by_act.setdefault(str(action), set())
            for duty in graph.objects(node, ODRL.duty):
                for duty_action in graph.objects(duty, ODRL.action):
                    bucket.add(str(duty_action))
    for node in graph.objects(subject, ODRL.prohibition):
        for action in graph.objects(node, ODRL.action):
            record.prohibited.add(str(action))
            seen[f"prohibition {action}"] += 1
    for node in graph.objects(subject, ODRL.duty):
        for action in graph.objects(node, ODRL.action):
            record.license_wide_duties.add(str(action))
    for asset in graph.objects(subject, ODRL.target):
        for asset_type in graph.objects(asset, DCT.type):
            record.targets.add(str(asset_type))
    for predicate in (
        DALICC.WarrantyDisclaimer, DALICC.LiabilityLimitation, DALICC.additionalClauses,
        DALICC.WarrantyOrLiabilityAcceptance, DCT.publisher, CC.attributionName,
        DALICC.terminatesOnBreach, DALICC.curePeriod,
    ):
        values = [str(v) for v in graph.objects(subject, predicate)]
        if values:
            record.literals[local(predicate)] = values
    record.repeated = sum(count - 1 for count in seen.values() if count > 1)
    return record


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------

GNU_PREFIXES = ("GPL-", "LGPL-", "AGPL-")
PERMISSIVE = {
    "MIT", "MIT-0", "MIT-Modern-Variant", "IscLicense", "BSD-1-Clause", "BSD-2-Clause",
    "BSD-3-Clause", "BSD-4-Clause", "TheZlibLibpngLicense", "Apache-2.0", "Apache-1.1",
    "BSL-1.0", "TheUniversalPermissiveLicenseUplVersion10", "0BSD", "NTP", "HPND",
    "curl", "PostgreSQL", "NCSA", "Xnet", "ICU", "Intel", "MirOS", "Unlicense",
    "BlueOak-1.0.0", "MulanPSL-2.0", "AFL-1.1", "AFL-1.2", "AFL-2.0", "AFL-2.1",
    "AFL-3.0", "ECL-1.0", "ECL-2.0", "W3C", "W3cSoftwareAndDocumentNoticeAndLicense",
    "ZPL-2.0", "ZPL-2.1", "Unicode-3.0", "Unicode-DFS-2016", "PythonLicense20",
    "Python-2.0.1", "CNRI-Python", "CNRI-Python-GPL-Compatible", "Fair", "Jam",
    "EFL-1.0", "EFL-2.0", "OLDAP-2.8", "CERN-OHL-P-2.0", "Multics", "OSC-1.0",
    "OLFL-1.3", "LiLiQ-P-1.1", "CECILL-B", "Naumen", "Entessa", "LPL-1.0", "LPL-1.02",
}
#: Whole-work copyleft: the share-alike duty belongs on the odrl:Set.
WHOLE_WORK = {
    "GPL-2.0-only", "GPL-3.0-only", "LGPL-2.0-only", "LGPL-2.1-only", "LGPL-3.0-only",
    "AGPL-3.0", "OSL-1.0", "OSL-2.0", "OSL-2.1", "OSL-3.0", "NPOSL-3.0", "UCL-1.0",
    "EUPL-1.1", "EUPL-1.2", "CAL-1.0", "RPL-1.1", "RPL-1.5", "RPSL-1.0", "NASA-1.3",
    "SimPL-2.0", "NGPL", "CERN-OHL-S-2.0", "LiLiQ-Rplus-1.1", "Frameworx-1.0",
    "OCLC-2.0", "GnuFreeDocumentationLicense", "OdcOpenDatabaseLicense",
    "SunPublicLicenseVersion10",
}
#: File-level or weak copyleft: the share-alike duty belongs on the acts.
FILE_LEVEL = {
    "MozillaPublicLicenseVersion20", "MPL-1.0", "MPL-1.1",
    "MPL-2.0-no-copyleft-exception", "CommonDevelopmentAndDistributionLicense10",
    "CDDL-1.1", "Nokia", "SISSL", "RSCPL", "OSET-PL-2.1", "CUA-OPL-1.0", "Motosoto",
    "APSL-1.0", "APSL-1.1", "APSL-1.2", "APSL-2.0", "EclipsePublicLicense10", "EPL-2.0",
    "CPL-1.0", "IPL-1.0", "CECILL-C", "LiLiQ-R-1.1", "MS-RL", "CERN-OHL-W-2.0",
    "Watcom-1.0", "CAL-1.0-Combined-Work-Exception", "CDLA-Sharing-1.0", "C-UDA-1.0",
    "OFL-1.1", "OFL-1.1-RFN", "OFL-1.1-no-RFN", "IPA",
}


def is_permissive(record: Record) -> bool:
    """Whether ``record`` is permissive in the sense of rule 15.

    A permissive license grants the core acts, asks for no reciprocity and asks for no
    source code: what it asks for is that the notice travels with the copy.  Creative
    Commons licenses are not permissive in this sense whatever their elements say,
    because their "no downstream restrictions" clause forbids exactly what rule 15 asks
    about; the public-domain dedication of that family is listed in
    :data:`RELICENSING_PERMITTED` instead.
    """
    if record.identifier in FIXTURES:
        return False
    if record.identifier in RELICENSING_PERMITTED:
        return True
    if record.is_creative_commons:
        return False
    if str(CC.ShareAlike) in (record.required | record.permitted | record.prohibited):
        return False
    if str(CC.SourceCode) in record.required:
        return False
    return not (CORE_ACTS & record.prohibited)


def rules(records: list[Record]) -> list[dict]:
    """Run every rule and return one result dictionary per rule."""
    by_id = {r.identifier: r for r in records}
    out: list[dict] = []

    def result(number: str, title: str, expectation: str, checked: int,
               offenders: list[str]) -> None:
        out.append({
            "rule": number, "title": title, "expectation": expectation,
            "checked": checked, "violations": len(offenders), "offenders": offenders,
        })

    # 1 --------------------------------------------------------------------
    gnu = [r for r in records if r.identifier.startswith(GNU_PREFIXES)]
    offenders = [
        r.identifier for r in gnu
        if str(CC.ShareAlike) not in r.required or str(CC.SourceCode) not in r.required
    ]
    result("1", "GNU copyleft records carry source code and share alike",
           "every GNU record states both duties", len(gnu), offenders)

    # 2 --------------------------------------------------------------------
    nc = [r for r in records
          if r.is_creative_commons and ("/by-nc" in r.legalcode
                                        or "noncommercial" in r.identifier.lower())]
    offenders = [r.identifier for r in nc if str(CC.CommercialUse) not in r.prohibited]
    result("2", "NonCommercial records prohibit commercial use",
           "an NC element means a cc:CommercialUse prohibition", len(nc), offenders)

    # 3 --------------------------------------------------------------------
    nd = [r for r in records
          if "noderiv" in r.identifier.lower() or "noderiv" in r.title.lower()]
    offenders = [
        r.identifier for r in nd
        if not ({str(ODRL.derive), str(CC.DerivativeWorks)} & r.prohibited)
        or ({str(ODRL.modify), str(DALICC.ModifiedWorks)} & r.permitted)
    ]
    result("3", "NoDerivatives records prohibit derivatives and permit no adaptation",
           "review decision 2 of 2026-09-15", len(nd), offenders)

    # 4 --------------------------------------------------------------------
    sa = [r for r in records
          if r.is_creative_commons and ("sa" in r.identifier.lower().split("-")
                                        or "sharealike" in r.identifier.lower())]
    offenders = [r.identifier for r in sa if str(CC.ShareAlike) not in r.required]
    result("4", "ShareAlike records carry the share-alike duty",
           "an SA element means a cc:ShareAlike duty", len(sa), offenders)

    # 5 --------------------------------------------------------------------
    permissive = [r for r in records if r.identifier in PERMISSIVE]
    offenders = [
        r.identifier for r in permissive
        if str(CC.ShareAlike) in (r.required | r.permitted | r.prohibited)
    ]
    result("5", "Permissive records make no share-alike statement",
           "a permissive license says nothing about share alike, in any position",
           len(permissive), offenders)

    # 6 --------------------------------------------------------------------
    checked = [r for r in records
               if r.identifier not in DEDICATIONS and r.identifier not in FIXTURES
               and r.identifier not in NO_ATTRIBUTION]
    offenders = [
        r.identifier for r in checked
        if not ({str(CC.Attribution), str(CC.Notice)} & r.required)
    ]
    result("6", "Every record carries an attribution or a notice duty",
           "except the public-domain dedications and the licenses whose only condition "
           "is something else", len(checked), offenders)

    # 7 --------------------------------------------------------------------
    offenders = [
        r.identifier for r in records
        if not r.prohibited and not r.required and r.identifier not in DEDICATIONS
        and r.identifier not in FIXTURES
    ]
    result("7", "A record with neither a prohibition nor a duty is suspicious",
           "only a dedication grants permissions and asks nothing", len(records),
           offenders)

    # 8 --------------------------------------------------------------------
    software_families = (PERMISSIVE | WHOLE_WORK | FILE_LEVEL) - DATA_AND_CONTENT
    checked = [r for r in records if r.identifier in software_families]
    offenders = [
        r.identifier for r in checked if str(DCMITYPE.Software) not in r.targets
    ]
    result("8", "Software licenses target dcmitype:Software",
           "a record whose text governs software lists the software asset type",
           len(checked), offenders)

    # 9 --------------------------------------------------------------------
    checked = [r for r in records
               if str(DALICC.patentRetaliationTermination) in r.prohibited
               and r.identifier not in WIDER_THAN_PATENTS]
    offenders = [
        r.identifier for r in checked if str(DALICC.patentGrant) not in r.permitted
    ]
    result("9", "A patent retaliation clause travels with a patent grant",
           "a license that ends a patent license on litigation granted one first",
           len(checked), offenders)

    # 10 -------------------------------------------------------------------
    checked = [r for r in records if "WarrantyDisclaimer" in r.literals]
    offenders = [
        r.identifier for r in checked
        if "LiabilityLimitation" not in r.literals
        and any("IN NO EVENT" in value.upper() for value in r.literals["WarrantyDisclaimer"])
    ]
    result("10", "Warranty and liability are quoted into their own predicates",
           "a disclaimer that also holds the liability sentence is split",
           len(checked), offenders)

    # 11 -------------------------------------------------------------------
    offenders = [f"{r.identifier} ({r.repeated})" for r in records if r.repeated]
    result("11", "No record repeats a statement",
           "the same action appears once per position", len(records), offenders)

    # 12 -------------------------------------------------------------------
    ports = [r for r in records if r.port_of and r.is_creative_commons]
    offenders = [
        r.identifier for r in ports
        if r.jurisdiction == str(DALICC.worldwide)
        and not r.identifier.endswith(("40", "4.0"))
    ]
    result("12", "A jurisdiction port names its country",
           "only the unported and international versions are worldwide", len(ports),
           offenders)

    # 13 -------------------------------------------------------------------
    checked = [r for r in records
               if r.identifier in WHOLE_WORK or r.identifier in FILE_LEVEL]
    offenders = []
    for r in checked:
        share_alike = str(CC.ShareAlike)
        license_wide = share_alike in r.license_wide_duties
        per_act = any(share_alike in duties for duties in r.duties_by_act.values())
        if r.identifier in WHOLE_WORK and not license_wide:
            offenders.append(f"{r.identifier} (whole-work, not license-wide)")
        if r.identifier in FILE_LEVEL and not per_act:
            offenders.append(f"{r.identifier} (file-level, not on the acts)")
        if r.identifier in FILE_LEVEL and license_wide:
            offenders.append(f"{r.identifier} (file-level, but also license-wide)")
        if (
            license_wide
            and str(DALICC.ChangeLicense) in r.permitted
            and str(DALICC.compliantLicense) not in r.duties_by_act.get(
                str(DALICC.ChangeLicense), set())
        ):
            offenders.append(f"{r.identifier} (relicensing without compliantLicense)")
    result("13", "Reciprocity has one shape per kind",
           "consolidation decision 4 of 2026-09-15", len(checked), offenders)

    # 14 -------------------------------------------------------------------
    offenders = []
    for r in records:
        for name, values in r.literals.items():
            for value in values:
                if value != value.strip():
                    offenders.append(f"{r.identifier} ({name}: padding space)")
                elif value.strip().lower().rstrip("-").strip() in PLACEHOLDERS:
                    offenders.append(f"{r.identifier} ({name}: placeholder)")
    result("14", "No padding space and no placeholder in a literal",
           "a value the reviewer did not know is left out, not filled with a word",
           len(records), offenders)

    # 15 -------------------------------------------------------------------
    checked = [r for r in records
               if is_permissive(r) and r.identifier not in RELICENSING_PROHIBITED_BY_TEXT]
    offenders = [
        r.identifier for r in checked
        if str(DALICC.ChangeLicense) not in r.permitted
        or str(DALICC.ChangeLicense) in r.prohibited
    ]
    result("15", "Permissive records permit relicensing",
           "the notice clause of a permissive license is a duty, not a bar on putting "
           "the work under other terms, except where the text bars it in as many words",
           len(checked), offenders)

    # 16 -------------------------------------------------------------------
    checked = [r for r in records if r.variant_kind == "version-option" and r.variant_of]
    offenders = []
    for r in checked:
        base = by_id.get(r.variant_of)
        if base is None:
            offenders.append(f"{r.identifier} (no record for {r.variant_of})")
            continue
        for label, mine, theirs in (
            ("permissions", r.statements_by_act("permitted"), base.statements_by_act("permitted")),
            ("prohibitions", r.prohibited, base.prohibited),
            ("license-wide duties", r.license_wide_duties, base.license_wide_duties),
            ("targets", r.targets, base.targets),
            ("clause texts", r.clause_texts, base.clause_texts),
        ):
            if mine != theirs:
                offenders.append(f"{r.identifier} ({label} differ from {r.variant_of})")
    result("16", "An or-later record says what its base says",
           "a version option differs from its base in the identifier, the title, the "
           "alternatives, the SPDX id, the version flag and the relation, and in nothing "
           "else", len(checked), offenders)

    # 17 -------------------------------------------------------------------
    checked = [r for r in records
               if r.variant_kind in ("exception", "rider") and r.variant_of]
    offenders = []
    for r in checked:
        base = by_id.get(r.variant_of)
        if base is None:
            offenders.append(f"{r.identifier} (no record for {r.variant_of})")
            continue
        for label, mine, theirs in (
            ("permissions", r.statements_by_act("permitted"), base.statements_by_act("permitted")),
            ("prohibitions", r.prohibited, base.prohibited),
            ("license-wide duties", r.license_wide_duties, base.license_wide_duties),
            ("targets", r.targets, base.targets),
            ("clause texts", r.clause_texts, base.clause_texts),
        ):
            missing = theirs - mine
            if missing:
                offenders.append(f"{r.identifier} ({label} of {r.variant_of} dropped)")
    result("17", "An exception or a rider record keeps everything its base says",
           "an exception lifts a condition for named material and a rider adds one; "
           "neither takes a statement away", len(checked), offenders)

    # 18 -------------------------------------------------------------------
    by_version: dict[str, list[Record]] = {}
    for r in records:
        if r.is_creative_commons and not r.port_of and r.license_version:
            by_version.setdefault(r.license_version, []).append(r)
    checked_records = [r for group in by_version.values() for r in group]
    offenders = []
    for version, group in sorted(by_version.items()):
        for name, reader in (
            ("the asset types", lambda r: r.targets),
            ("the termination terms", lambda r: (
                r.literals.get("terminatesOnBreach", []), r.literals.get("curePeriod", []))),
            ("the moral rights statement", lambda r: str(DALICC.moralRightsRestriction)
                in r.prohibited),
        ):
            values = {repr(reader(r)) for r in group}
            if len(values) > 1:
                offenders.append(
                    f"version {version}: {name} differ "
                    f"({', '.join(sorted(r.identifier for r in group))})")
    result("18", "Creative Commons records of one version agree",
           "two records of one version of the unported text differ where their element "
           "sets differ and nowhere else", len(checked_records), offenders)

    # 19 --------------------------------------------------------------------
    # The endorsement prohibition was a house convention on 519 of 581 records until
    # 2026-09-23. What a licence that says nothing about endorsement grants is a legal
    # default, and a default belongs in the rule layer of the dependency graph, where it
    # reaches every silent licence at once and says which jurisdiction it holds in. A
    # record states the prohibition only where a sentence of its own text does, and the
    # list below is that set, read off the texts and the review records one at a time.
    promote = str(DALICC.promote)
    offenders = []
    for r in records:
        states = promote in r.prohibited
        listed = r.identifier in TEXT_SUPPORTED_PROMOTE
        if states and not listed:
            offenders.append(
                f"{r.identifier} (prohibits dalicc:promote and is not in the "
                f"text-supported list)"
            )
        elif listed and not states:
            offenders.append(
                f"{r.identifier} (the list says its text bars endorsement, and the "
                f"record does not prohibit dalicc:promote)"
            )
    result("19", "Endorsement is prohibited only where the text says so",
           "a record carries the dalicc:promote prohibition exactly when a sentence of "
           "its own text bars the use of the licensor's name or mark", len(records),
           offenders)

    # 20 --------------------------------------------------------------------
    # The sui generis database right is a right of its own, separate from copyright, and a
    # licence that says nothing about it leaves it untouched: that is the proposed default
    # rule eu-sui-generis-db of dg_eu.ttl. A record therefore states the permission only
    # where its own text settles the right, and the duties follow the text that grants it.
    # The 4.0 text sends the reader to the conditions of Section 3(a) (Section 4(c)); the
    # 3.0 ports take their restrictions off the material that qualifies only under the
    # database right, so their permission carries no duty at all.
    database = str(DALICC.suiGenerisDatabaseRights)
    checked = [r for r in records if r.is_creative_commons]
    offenders = []
    for r in checked:
        states = database in r.permitted
        listed = r.identifier in DATABASE_RIGHT_BY_TEXT
        if states and not listed:
            offenders.append(
                f"{r.identifier} (permits dalicc:suiGenerisDatabaseRights and is not in "
                f"the text-supported list)"
            )
            continue
        if listed and not states:
            offenders.append(
                f"{r.identifier} (the list says its text settles the database right, and "
                f"the record does not permit dalicc:suiGenerisDatabaseRights)"
            )
            continue
        if not states:
            continue
        expected = (
            {str(CC.Attribution), str(CC.Notice)}
            if r.identifier in CC_40_RECORDS
            else set()
        )
        duties = r.duties_by_act.get(database, set())
        if duties != expected:
            offenders.append(
                f"{r.identifier} (the duties on dalicc:suiGenerisDatabaseRights are "
                f"{sorted(local(d) for d in duties)}, expected "
                f"{sorted(local(d) for d in expected)})"
            )
    result("20", "The database right is stated only where the text settles it",
           "a Creative Commons record permits dalicc:suiGenerisDatabaseRights exactly "
           "where its own legal code disposes of that right, with the duties that text "
           "attaches to it", len(checked), offenders)

    return out


def _skip_note(skipped: list[str], by_number: dict, total: int, counted: int) -> str:
    """Say which rules the exit status left out and what that did to the total."""
    lines = []
    for number in skipped:
        entry = by_number.get(number)
        if entry is None:
            lines.append(f"skipped for the exit status: rule {number}, which is no rule")
            continue
        lines.append(
            f"skipped for the exit status: rule {number} ({entry['title']}), "
            f"{entry['violations']} violations left out"
        )
    lines.append(
        f"violations counted for the exit status: {counted} of the {total} printed"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit 1 on any violation")
    parser.add_argument(
        "--skip-rule",
        action="append",
        default=[],
        metavar="N",
        help="rule numbers whose violations do not count towards the exit status; "
             "repeatable, or one comma-separated list. The rules still run and still "
             "report their counts",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    skipped: list[str] = []
    for value in args.skip_rule:
        for part in value.split(","):
            number = part.strip()
            if number and number not in skipped:
                skipped.append(number)

    records = [load(path) for path in sorted(LICENSES_DIR.glob("*.ttl"))]
    results = rules(records)
    by_number = {entry["rule"]: entry for entry in results}
    # The printed total is every violation the rules found; the counted total is the
    # one the exit status uses, which leaves out the rules named by --skip-rule.
    total = sum(r["violations"] for r in results)
    counted = sum(r["violations"] for r in results if r["rule"] not in skipped)
    for number in skipped:
        if number not in by_number:
            LOG.warning("--skip-rule %s names no rule", number)

    if args.json:
        payload: dict = {"records": len(records), "rules": results}
        if skipped:
            payload["skipped_rules"] = skipped
            payload["violations_total"] = total
            payload["violations_counted"] = counted
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    elif args.markdown:
        lines = [
            f"# Family rules over {len(records)} records",
            "",
            "| # | Rule | Checked | Violations | Ids |",
            "|---|---|---|---|---|",
        ]
        for entry in results:
            ids = ", ".join(f"`{name}`" for name in entry["offenders"]) or "none"
            lines.append(
                f"| {entry['rule']} | {entry['title']} | {entry['checked']} | "
                f"{entry['violations']} | {ids} |"
            )
        if skipped:
            lines += ["", _skip_note(skipped, by_number, total, counted)]
        sys.stdout.write("\n".join(lines) + "\n")
    else:
        LOG.info("records: %d", len(records))
        for entry in results:
            LOG.info("rule %-3s %-58s checked %4d  violations %d",
                     entry["rule"], entry["title"], entry["checked"], entry["violations"])
            for name in entry["offenders"]:
                LOG.info("          %s", name)
        LOG.info("total violations: %d", total)
        if skipped:
            for line in _skip_note(skipped, by_number, total, counted).splitlines():
                LOG.info("%s", line)
    return 1 if args.strict and counted else 0


if __name__ == "__main__":
    sys.exit(main())
