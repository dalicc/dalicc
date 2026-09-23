# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The DALICC controlled vocabulary -- one source of truth for labels and prose.

Before this module the same data existed three times as the 23-entry
``propertyToTextDict`` literal in ``app/routers/web.py`` (lines 195, 343 and 643 of
the old file), once more as ``termsArray``/``termsDict`` in
``app/templates/wpcomposer.html``, and once more again as the ``title=`` tooltips in
``search.html``/``wpsearch.html``.  All five copies drifted:

* every copy of ``propertyToTextDict`` carried ``"https//dalicc.net/ns#WarrantyDisclaimer"``
  (no colon after ``https``), so the warranty disclaimer -- present on 324 of 342
  licenses -- never rendered on any license page;
* ``http://schema.org/endDate`` was missing from the map entirely, so a composed
  license with an expiry date never showed it;
* ``termsArray`` lacked ``dalicc:ModifiedWorks`` (used by 320 of 342 licenses),
  ``odrl:ensureExclusivity``, ``odrl:extract``, ``odrl:sell`` and ``odrl:copy``, so the
  composer could not express terms that 94% of the library uses.

The labels and definitions below come from two reviewed sources: the help tooltips of
the original DALICC license composer (``lost_site_content/tooltips_glossary.md``) and
``licensedata/vocabulary/dalicc-ns.ttl``.  Terms that appear only in the dependency
graph are included too -- the consistency check reasons over them -- but are flagged
``composable=False`` so they are not offered in the authoring UI.

Since 2026-09-15 the vocabulary file is the source of truth rather than a second copy:
every ``dalicc:`` term it defines is loaded at import with its label, its definition and
its classification (``dalicc:RuleAction``, ``dalicc:DutyAction``, ``dalicc:AssetType``,
a policy quality or a property), and the hand-written table below supplies only the ODRL
and Creative Commons terms, which the file does not define, and the plain-language
descriptions.  Defining a term in ``dalicc-ns.ttl`` is therefore all it takes to make the
composer, ``GET /licenselibrary/actions``, ``input_from_graph`` and the consistency check
accept it; nothing has to be added here as well.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import os
from pathlib import Path
import re

import rdflib
from rdflib.namespace import OWL, RDF, RDFS, SKOS

__all__ = [
    "ACTIONS",
    "ACTIONS_BY_CURIE",
    "ASSET_TYPES",
    "JURISDICTION_WORLDWIDE",
    "NAMESPACES",
    "POLICY_QUALITIES",
    "PROPERTY_LABELS",
    "VOCABULARY_FILE",
    "Term",
    "action_description",
    "action_label",
    "asset_type_label",
    "compact_iri",
    "composable_actions",
    "duty_actions",
    "expand_curie",
    "humanize_local_name",
    "humanize_value",
    "is_known_action",
    "policy_quality",
    "resolve_action",
    "term_payload",
]

#: Prefix -> namespace IRI.  Identical to the block at the head of every
#: ``licensedata/licenses/*.ttl``, plus the ``bpicountry`` spelling ``web.py`` used
#: (the data files spell the same namespace ``bpicounty``; both are accepted).
NAMESPACES: dict[str, str] = {
    "bpicountry": "http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#",
    "bpicounty": "http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#",
    "cc": "http://creativecommons.org/ns#",
    "dalicc": "https://dalicc.net/ns#",
    "dalicclib": "https://dalicc.net/licenselibrary/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    "osl": "http://opensource.org/licenses/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "scho": "http://schema.org/",
    "spdx": "http://spdx.org/rdf/terms#",
    "spdxlicense": "http://spdx.org/licenses/",
}

#: Longest namespace first, so ``compact_iri`` never picks a prefix of a prefix.
_NAMESPACE_ITEMS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((prefix, iri) for prefix, iri in NAMESPACES.items() if prefix != "bpicounty"),
        key=lambda item: len(item[1]),
        reverse=True,
    )
)

JURISDICTION_WORLDWIDE = "https://dalicc.net/ns#worldwide"


@dataclass(frozen=True, slots=True)
class Term:
    """One vocabulary term: an ODRL/CC/DALICC action usable in a license."""

    iri: str
    curie: str
    label: str
    description: str
    #: May be the action of an ``odrl:Permission`` or ``odrl:Prohibition``.
    is_rule_action: bool = True
    #: May be the action of an ``odrl:Duty`` (attached to a permission or license-wide).
    is_duty_action: bool = False
    #: Offered in the composer / search UIs.  Dependency-graph-only terms are not.
    composable: bool = True
    #: Grouping hint for UIs: "action" | "duty" | "quality" | "reasoning".
    group: str = "action"
    #: Published in the 2022 vocabulary documentation but used by no license of the
    #: current library.  Such a term is never offered for authoring (``composable`` is
    #: False), but it is resolved for display in case it turns up in imported data.
    documented_only: bool = False
    #: Superseded IRI kept so that data written against the old documentation still
    #: resolves.  ``replaced_by`` names the term to use instead.
    deprecated: bool = False
    replaced_by: str = ""


def _term(
    curie: str,
    label: str,
    description: str,
    *,
    rule: bool = True,
    duty: bool = False,
    composable: bool = True,
    group: str = "action",
    documented_only: bool = False,
    deprecated: bool = False,
    replaced_by: str = "",
) -> Term:
    prefix, _, local = curie.partition(":")
    return Term(
        iri=NAMESPACES[prefix] + local,
        curie=curie,
        label=label,
        description=description,
        is_rule_action=rule,
        is_duty_action=duty,
        composable=composable,
        group=group,
        documented_only=documented_only,
        deprecated=deprecated,
        replaced_by=replaced_by,
    )


_BUILTIN_TERMS: tuple[Term, ...] = (
    # --- actions that are granted or forbidden -----------------------------
    _term(
        "odrl:reproduce",
        "Reproduce",
        "Reproduce means to make duplicate copies of the work in any form.",
    ),
    _term(
        "odrl:distribute",
        "Distribute",
        "Distribute means providing the work to the public or making it accessible to "
        "anyone else. This may also include to present, to display or to perform the work.",
    ),
    _term(
        "odrl:display",
        "Display",
        "Display means to create a static and transient rendition of the work.",
    ),
    _term(
        "odrl:present",
        "Present",
        "Present means to publicly perform the work.",
    ),
    _term(
        "odrl:modify",
        "Modify",
        "To modify a work means that it is slightly altered (such as updated) from time to "
        "time without substantially changing it and thus creating a new work. If modifying "
        "the work results in a new work the action 'derive' should be chosen.",
    ),
    _term(
        "odrl:derive",
        "Derive",
        "To make a derivative means to create a new work from an existing work. This "
        "includes but is not limited to any translation, adaptation, arrangement, "
        "modification, or any other substantial alteration of the work or of a part of it.",
    ),
    _term(
        "dalicc:ModifiedWorks",
        "Modified works",
        "Distributing a modified version of the work and making it available to the public. "
        "The counterpart of Derivative works for alterations that do not amount to a new, "
        "derivative work.",
    ),
    _term(
        "cc:DerivativeWorks",
        "Derivative works",
        "Derivative works means to distribute the derivative and making it available to the "
        "public.",
    ),
    _term(
        "cc:CommercialUse",
        "Commercial use",
        "Commercial use is equivalent to income-generating use of any kind, whether direct "
        "or indirect. This spans from generating revenue by selling the work (i.e. charging "
        "a license fee) to using it for advertising purposes.",
    ),
    _term(
        "dalicc:promote",
        "Promote",
        "Promote means that the licensee can use the licensor's trademark for advertising "
        "and promotion purposes.",
    ),
    _term(
        "dalicc:chargeDistributionFee",
        "Charge distribution fee",
        "The licensee is allowed to charge a distribution fee.",
    ),
    _term(
        "dalicc:chargeLicenseFee",
        "Charge license fee",
        "The licensee is allowed to charge a fee for granting a license to the work, that "
        "is, to generate revenue from sub-licensing rather than from distribution alone.",
    ),
    _term(
        "dalicc:ChangeLicense",
        "Change license",
        "The licensee may change, extend or modify the license terms and replace the "
        "original license with a new one. Where the license carries a share-alike duty "
        "for the whole work, this permission must carry the duty to use a compliant "
        "license.",
    ),
    _term(
        "odrl:grantUse",
        "Grant use",
        "Grant use means to create policies for the use of the asset for third parties.",
    ),
    _term(
        "dalicc:addLimitation",
        "Add limitation",
        "Adding further limitations or restrictions to the license terms when "
        "redistributing the work. Where this action is prohibited the license may not be "
        "made more restrictive downstream.",
    ),
    _term(
        "dalicc:addStatement",
        "Add statement",
        "Attaching additional terms, notices or statements to the work when redistributing "
        "it. Where this action is prohibited the licensee must pass the license on "
        "unchanged.",
    ),
    _term(
        "dalicc:noWarrantyNotice",
        "No-warranty notice",
        "The licensee may attach a notice stating that the work is provided without "
        "warranty of any kind.",
        duty=True,
    ),
    # --- duty actions ------------------------------------------------------
    _term(
        "cc:Attribution",
        "Attribution",
        "Attributing means to give credit to the copyright holder(s) and/or author(s) of "
        "the work. The licensor might request a specific attribution notice.",
        duty=True,
        group="duty",
    ),
    _term(
        "cc:Notice",
        "Notice",
        "Noticing means to attach or clearly refer to the license when distributing the "
        "work.",
        duty=True,
        group="duty",
    ),
    _term(
        "cc:SourceCode",
        "Source code",
        "Including the source code means to provide access to the source code when "
        "distributing the work.",
        duty=True,
        group="duty",
    ),
    _term(
        "dct:source",
        "Source",
        "Including the source means to provide access to the source material when "
        "distributing the work.",
        rule=False,
        duty=True,
        # No record of the current library names it as an odrl:action: only the pre-2023
        # files under licensedata/deprecated do, and the GFDL defect that put it here is
        # closed, so it is no longer offered for authoring.  The term stays defined, so
        # GET /licenselibrary/actions?include_reasoning_terms=true still lists it and an
        # imported policy that uses it still renders with a label.
        composable=False,
        group="duty",
    ),
    _term(
        "cc:ShareAlike",
        "Share alike",
        "The licensee must license the entire work or modifications / derivatives thereof, "
        "as a whole, under the original license to anyone who comes into possession of a "
        "copy. Where it applies to the whole work, a permission to change the license "
        "must carry the duty to use a compliant license.",
        duty=True,
        group="duty",
    ),
    _term(
        "dalicc:rename",
        "Rename",
        "Rename means to change the title of the modified or derived work so that it can be "
        "clearly distinguished from the original work.",
        duty=True,
        group="duty",
    ),
    _term(
        "dalicc:modificationNotice",
        "Modification notice",
        "Providing a modification note means to document any changes done to the work and "
        "clearly document how it differs from the original work.",
        duty=True,
        group="duty",
    ),
    _term(
        "dalicc:compliantLicense",
        "Use a compliant license",
        "The replacement license chosen by the licensee must remain compliant with the "
        "terms of the original license.",
        duty=True,
        group="duty",
    ),
    # --- dependency-graph vocabulary (reasoning only) ----------------------
    _term(
        "odrl:use",
        "Use",
        "The umbrella action every other usage action is included in.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:copy",
        "Copy",
        "Make a copy of the asset. A synonym of Reproduce in the dependency graph.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:extract",
        "Extract",
        "Extract part of the asset. Included in Reproduce and implies Source code.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:sell",
        "Sell",
        "Trade the asset for consideration. Included in Commercialize and Transfer.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:commercialize",
        "Commercialize",
        "Use the asset in a business environment. The reasoning counterpart of "
        "Commercial use.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:transfer",
        "Transfer",
        "Transfer ownership of the asset to a third party.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:attribute",
        "Attribute",
        "The ODRL synonym of Attribution.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:AttachPolicy",
        "Attach policy",
        "The ODRL synonym of Notice.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:attachSource",
        "Attach source",
        "The ODRL synonym of Source code.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:shareAlike",
        "Share alike (ODRL)",
        "The ODRL synonym of Share alike.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:ensureExclusivity",
        "Ensure exclusivity",
        "Guarantee that the asset is not licensed to anyone else. Contradicts "
        "Commercialize.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:execute",
        "Execute",
        "Run the asset (typically software).",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:print",
        "Print",
        "Produce a hard copy of the asset.",
        composable=False,
        group="reasoning",
    ),
    _term(
        "odrl:play",
        "Play",
        "Render the asset in an audio or video form.",
        composable=False,
        group="reasoning",
    ),
    # --- published in 2022, used by no license of the current library -------
    # Definitions verbatim from https://dalicc.github.io/ (see
    # licensedata/vocabulary/dalicc-ns.ttl).  They are resolved so that an imported or
    # hand-written policy that uses them still renders with a proper label, but they are
    # not offered for authoring: composable=False keeps them out of composable_actions()
    # and duty_actions().
    _term(
        "dalicc:attachoffer",
        "Attach offer",
        "The Assignee may add a written offer for permissions according to the license.",
        composable=False,
        documented_only=True,
    ),
    _term(
        "dalicc:chargeOffer",
        "Charge offer",
        "The Assignee may charge a fee for the physical act of transferring a copy, and "
        "you may at your option offer warranty protection in exchange for a fee.",
        composable=False,
        documented_only=True,
    ),
    _term(
        "dalicc:publish",
        "Publish",
        "The Assigner permits the Assignee to prepare and issue (a book, journal) for "
        "public sale to make it generally known, to make available online.",
        composable=False,
        documented_only=True,
    ),
    _term(
        "dalicc:redistribute",
        "Redistribute",
        "The Assigner permits/prohibits the Assignees to redistribute the Asset.",
        composable=False,
        documented_only=True,
    ),
    _term(
        "dalicc:sellCopy",
        "Sell copy",
        "The Assignee may sell the copies of the License Material.",
        composable=False,
        documented_only=True,
    ),
    _term(
        "dalicc:sublicense",
        "Sublicense",
        "The license granted by a licensee to a third party, under the authority of the "
        "license originally granted by a licensor to the licensee.",
        composable=False,
        documented_only=True,
    ),
    # Notices: duty actions, not permissions.
    _term(
        "dalicc:attributionNotice",
        "Attribution notice",
        "Notify the attributes of License Material.",
        rule=False,
        duty=True,
        composable=False,
        group="duty",
        documented_only=True,
    ),
    _term(
        "dalicc:patentNotice",
        "Patent notice",
        "Notifies that Licensed Material is patented or includes patented parts.",
        rule=False,
        duty=True,
        composable=False,
        group="duty",
        documented_only=True,
    ),
    _term(
        "dalicc:permissionNotice",
        "Permission notice",
        "The permission notices which are in the License shall be included.",
        rule=False,
        duty=True,
        composable=False,
        group="duty",
        documented_only=True,
    ),
    _term(
        "dalicc:trademarkNotice",
        "Trademark notice",
        "Informs that Licensed Material is a trademark or includes trademark. The license "
        "does not grant permission to use the trade names, trademarks, service marks, or "
        "product names of the Licensor, except as required for reasonable and customary "
        "use in describing the origin of the Work and reproducing the content of the "
        "notice file.",
        rule=False,
        duty=True,
        composable=False,
        group="duty",
        documented_only=True,
    ),
)

#: Policy-level qualities: values that describe the licence as a whole rather than an act
#: it permits or forbids.  They are the object of ``dalicc:validityType``,
#: ``cc:jurisdiction`` or an equivalent property, never of ``odrl:action``, so they are
#: deliberately *not* part of :data:`ACTIONS`.
_BUILTIN_QUALITIES: tuple[Term, ...] = (
    _term(
        "dalicc:perpetual",
        "Perpetual",
        "A perpetual license allows to use the licensed work indefinitely.",
        rule=False,
        composable=False,
        group="quality",
    ),
    _term(
        "dalicc:specifyDate",
        "Specify date",
        "The license is valid between an explicit start date and end date.",
        rule=False,
        composable=False,
        group="quality",
    ),
    _term(
        "dalicc:specifyPeriod",
        "Specify period",
        "The license is valid for a duration counted from the moment it is granted.",
        rule=False,
        composable=False,
        group="quality",
    ),
    _term(
        "dalicc:worldwide",
        "Worldwide",
        "The license terms are valid throughout the world.",
        rule=False,
        composable=False,
        group="quality",
    ),
    _term(
        "dalicc:irrevocable",
        "Irrevocable",
        "The license cannot be terminated for any reason or only that the license cannot "
        "be terminated for convenience, but still may be terminated for breach.",
        rule=False,
        composable=False,
        group="quality",
        documented_only=True,
    ),
    _term(
        "dalicc:patentFree",
        "Patent free",
        "The license applies only to those patent claims licensable by such Contributor "
        "that are necessarily infringed by their Contribution(s) alone or by combination "
        "of their Contribution(s) with the Licensed Material to which such Contribution(s) "
        "was submitted.",
        rule=False,
        composable=False,
        group="quality",
        documented_only=True,
    ),
    _term(
        "dalicc:royaltyFree",
        "Royalty free",
        "Refers to the right to use copyright material or intellectual property without "
        "the need to pay royalties or license fees for each use, per each copy or volume "
        "sold or some time period of use or sales.",
        rule=False,
        composable=False,
        group="quality",
        documented_only=True,
    ),
    _term(
        "dalicc:royalityFree",
        "Royalty free (deprecated spelling)",
        "Refers to the right to use copyright material or intellectual property without "
        "the need to pay royalties or license fees for each use, per each copy or volume "
        "sold or some time period of use or sales.",
        rule=False,
        composable=False,
        group="quality",
        documented_only=True,
        deprecated=True,
        replaced_by="https://dalicc.net/ns#royaltyFree",
    ),
)

# ---------------------------------------------------------------------------
# the vocabulary file is the source of truth
# ---------------------------------------------------------------------------
#
# The tables above are the *hand-written* half: the ODRL and Creative Commons terms,
# which ``dalicc-ns.ttl`` does not define, and the plain-language descriptions the
# original composer's help texts gave the terms it did cover.  Everything else -- which
# ``dalicc:`` terms exist, what they are called, what they mean, whether they may be the
# action of a permission, of a prohibition or of a duty, and whether they qualify the
# policy as a whole -- is read from ``licensedata/vocabulary/dalicc-ns.ttl`` at import,
# so that defining a term in the vocabulary is all it takes to make the composer, the
# API, ``input_from_graph`` and the consistency check accept it.
#
# ``dalicc:RuleAction`` and ``dalicc:DutyAction`` carry the classification; an action
# typed neither is treated as a rule action, which is what every action was before the
# classification existed.  A term whose ``skos:note`` says that no license uses it is not
# offered for authoring, exactly as ``documented_only`` used to say by hand; those notes
# are regenerated from the data by ``scripts/review/refresh_vocab_notes.py``.

LOG = logging.getLogger(__name__)

_NS_IRI = rdflib.URIRef("https://dalicc.net/ns#")
_DALICC = rdflib.Namespace("https://dalicc.net/ns#")
_ODRL_NS = rdflib.Namespace("http://www.w3.org/ns/odrl/2/")
_DCT = rdflib.Namespace("http://purl.org/dc/terms/")

#: Phrases a ``skos:note`` uses to say that the term is published but unused.  A term
#: carrying one is resolved for display and kept out of the authoring drop-downs.
_UNUSED_NOTES = (
    "not used by any license in the current library",
    "the review applied it to no license record",
)

_PROPERTY_TYPES = (OWL.DatatypeProperty, OWL.ObjectProperty, OWL.AnnotationProperty)


def _vocabulary_file() -> Path | None:
    """Locate ``licensedata/vocabulary/dalicc-ns.ttl``.

    ``DALICC_LICENSEDATA_DIR`` wins, then the checkout this module lives in, then the
    working directory -- the same order ``scripts/`` and the contract-snapshot tooling
    use.  ``None`` means the file is not there, in which case the hand-written tables
    are the whole vocabulary and nothing breaks.
    """
    candidates: list[Path] = []
    from_env = os.environ.get("DALICC_LICENSEDATA_DIR")
    if from_env:
        candidates.append(Path(from_env))
    candidates.append(Path(__file__).resolve().parents[2] / "licensedata")
    candidates.append(Path("licensedata"))
    for base in candidates:
        path = base / "vocabulary" / "dalicc-ns.ttl"
        if path.is_file():
            return path
    return None


#: The file the term table was read from, or ``None``.  Shown by ``/ns``.
VOCABULARY_FILE: Path | None = _vocabulary_file()


def _english(graph: rdflib.Graph, subject: rdflib.term.Node, predicate) -> str:
    """The English literal of ``predicate``, preferring the ``@en`` one."""
    values = list(graph.objects(subject, predicate))
    for value in values:
        if isinstance(value, rdflib.Literal) and value.language == "en":
            return str(value).replace("\n", " ").strip()
    return str(values[0]).replace("\n", " ").strip() if values else ""


def _collapse(text: str) -> str:
    """Collapse the line breaks of a Turtle long string into single spaces."""
    return " ".join(text.split())


def _load_vocabulary(path: Path) -> tuple[list[Term], list[Term], dict[str, str], dict[str, str]]:
    """Read the vocabulary file and return its actions, qualities, assets and properties."""
    graph = rdflib.Graph()
    graph.parse(path.as_posix(), format="turtle")

    actions: list[Term] = []
    qualities: list[Term] = []
    asset_types: dict[str, str] = {}
    property_labels: dict[str, str] = {}

    for subject in sorted(graph.subjects(RDFS.isDefinedBy, _NS_IRI), key=str):
        if not isinstance(subject, rdflib.URIRef) or not str(subject).startswith(str(_DALICC)):
            continue
        iri = str(subject)
        curie = "dalicc:" + iri[len(str(_DALICC)) :]
        types = set(graph.objects(subject, RDF.type))
        label = _collapse(_english(graph, subject, RDFS.label)) or humanize_local_name(iri)
        comment = _collapse(_english(graph, subject, RDFS.comment))
        definition = _collapse(_english(graph, subject, SKOS.definition))
        description = definition or comment
        notes = " ".join(str(value) for value in graph.objects(subject, SKOS.note)).lower()
        unused = any(phrase in notes for phrase in _UNUSED_NOTES)
        deprecated = rdflib.Literal(True) in set(graph.objects(subject, OWL.deprecated))
        replaced_by = next(
            (str(value) for value in graph.objects(subject, _DCT.isReplacedBy)), ""
        )

        if _ODRL_NS.Action in types:
            is_duty = _DALICC.DutyAction in types
            is_rule = _DALICC.RuleAction in types or not is_duty
            actions.append(
                Term(
                    iri=iri,
                    curie=curie,
                    label=label,
                    description=description,
                    is_rule_action=is_rule,
                    is_duty_action=is_duty,
                    composable=not unused and not deprecated,
                    group="duty" if is_duty and not is_rule else "action",
                    documented_only=unused,
                    deprecated=deprecated,
                    replaced_by=replaced_by,
                )
            )
            continue

        if _DALICC.AssetType in types:
            asset_types[iri] = label
            continue

        if types & set(_PROPERTY_TYPES):
            property_labels[iri] = label
            continue

        if SKOS.Concept in types:
            qualities.append(
                Term(
                    iri=iri,
                    curie=curie,
                    label=label,
                    description=description,
                    is_rule_action=False,
                    is_duty_action=False,
                    composable=False,
                    group="quality",
                    documented_only=unused,
                    deprecated=deprecated,
                    replaced_by=replaced_by,
                )
            )
    return actions, qualities, asset_types, property_labels


def _merge(builtin: tuple[Term, ...], loaded: list[Term]) -> tuple[Term, ...]:
    """Overlay ``loaded`` on ``builtin``, keeping the hand-written description.

    The vocabulary file owns the label, the classification and the existence of a term;
    the table above owns the plain-language description wherever it has one, because
    those are the lawyer-reviewed help texts of the original composer and they read
    better in a drop-down than the legal definition does.
    """
    merged: dict[str, Term] = {term.iri: term for term in builtin}
    for term in loaded:
        existing = merged.get(term.iri)
        if existing is None:
            merged[term.iri] = term
            continue
        merged[term.iri] = replace(
            term,
            description=existing.description or term.description,
            composable=term.composable and existing.group != "reasoning",
            group=existing.group if existing.group == "reasoning" else term.group,
        )
    return tuple(merged.values())


_LOADED_ACTIONS: list[Term] = []
_LOADED_QUALITIES: list[Term] = []
_LOADED_ASSETS: dict[str, str] = {}
_LOADED_PROPERTIES: dict[str, str] = {}
if VOCABULARY_FILE is not None:
    try:
        (
            _LOADED_ACTIONS,
            _LOADED_QUALITIES,
            _LOADED_ASSETS,
            _LOADED_PROPERTIES,
        ) = _load_vocabulary(VOCABULARY_FILE)
    except Exception:  # pragma: no cover - a broken file must not break the app
        LOG.exception("cannot read the DALICC vocabulary from %s", VOCABULARY_FILE)

#: Every action term: the hand-written ODRL and Creative Commons half, overlaid with
#: every ``dalicc:`` term the vocabulary file defines.
_TERMS: tuple[Term, ...] = _merge(_BUILTIN_TERMS, _LOADED_ACTIONS)
#: Every policy-level quality, the same way.
_QUALITIES: tuple[Term, ...] = _merge(_BUILTIN_QUALITIES, _LOADED_QUALITIES)

#: IRI -> :class:`Term`.
ACTIONS: dict[str, Term] = {term.iri: term for term in _TERMS}
#: CURIE -> :class:`Term` (``cc:Attribution`` and friends, as the legacy form posts them).
ACTIONS_BY_CURIE: dict[str, Term] = {term.curie: term for term in _TERMS}
#: IRI -> :class:`Term` for the policy-level qualities (validity, jurisdiction,
#: revocability, cost).  Keyed by IRI *and* CURIE, like the action maps.
POLICY_QUALITIES: dict[str, Term] = {term.iri: term for term in _QUALITIES}

#: Asset-type IRI -> label, as ``odrl:target``/``dct:type`` carries them.  The two
#: Dublin Core types are fixed; the DALICC ones come from ``dalicc:AssetType`` in the
#: vocabulary file, with the long label of the creative work kept as an override.
ASSET_TYPES: dict[str, str] = {
    "https://dalicc.net/ns#CreativeWork": "Creative work (i.e. text, picture, sound, movie)",
    "http://purl.org/dc/dcmitype/Dataset": "Dataset",
    "http://purl.org/dc/dcmitype/Software": "Software",
    **{iri: label for iri, label in _LOADED_ASSETS.items()
       if iri != "https://dalicc.net/ns#CreativeWork"},
}

#: Property IRI -> display label.  The successor of the three copies of
#: ``propertyToTextDict``; ``dalicc:WarrantyDisclaimer`` now has its colon and
#: ``schema:endDate`` is present.
PROPERTY_LABELS: dict[str, str] = {
    **dict(_LOADED_PROPERTIES),
    "http://purl.org/dc/terms/title": "Title",
    "http://purl.org/dc/terms/alternative": "Alternative names",
    "http://purl.org/dc/terms/publisher": "License owner",
    "http://purl.org/dc/terms/creator": "License creator",
    "http://purl.org/dc/terms/source": "Source",
    "http://purl.org/dc/terms/type": "Type",
    "http://purl.org/dc/terms/hasVersion": "Version",
    # The language of the legal code, on the records whose text is not English.
    "http://purl.org/dc/terms/language": "Language of the legal code",
    "http://creativecommons.org/ns#attributionName": "Attribution name",
    "http://creativecommons.org/ns#jurisdiction": "Region",
    "http://creativecommons.org/ns#legalcode": "Legal code",
    "http://creativecommons.org/ns#license": "Licensed under",
    # The one live occurrence of the capitalised spelling (SampleLicenseSl.ttl) is a
    # modelling error in the data, but it is public data, so it keeps rendering.
    "http://creativecommons.org/ns#License": "Licensed under",
    "http://www.w3.org/ns/odrl/2/permission": "Permissions",
    "http://www.w3.org/ns/odrl/2/prohibition": "Prohibitions",
    "http://www.w3.org/ns/odrl/2/duty": "Duties",
    "http://www.w3.org/ns/odrl/2/target": "Target",
    "http://www.w3.org/ns/odrl/2/assignee": "Licensee",
    "https://dalicc.net/ns#additionalClauses": "Additional clauses",
    "https://dalicc.net/ns#licenseOwner": "Licensor",
    # Added with version 5 of the vocabulary: the licence text a composed license
    # carries with it.
    "https://dalicc.net/ns#licenseText": "License text",
    "https://dalicc.net/ns#LiabilityLimitation": "Limitation of liability",
    "https://dalicc.net/ns#PromotionSpecification": "Promotion specification",
    "https://dalicc.net/ns#validityType": "Validity period",
    # Fixed: every historical copy of this map spelled the key "https//dalicc.net/..."
    "https://dalicc.net/ns#WarrantyDisclaimer": "Warranty disclaimer",
    "https://dalicc.net/ns#WarrantyOrLiabilityAcceptance": "Warranty or liability acceptance",
    "http://schema.org/startDate": "Start date",
    # Added: composed licenses carry an end date and it was never displayed.
    "http://schema.org/endDate": "End date",
    "http://schema.org/validFor": "Valid for",
    "http://spdx.org/rdf/terms#licenseId": "SPDX ID",
    "http://xmlns.com/foaf/0.1/logo": "Logo",
    "http://xmlns.com/foaf/0.1/img": "Image",
}

#: Acronyms that must survive the CamelCase-to-words transformation intact.
_ACRONYMS = ("ODbL", "LaTeX", "SPDX", "GNU", "BSD", "MIT", "CC", "EU", "UK", "US")

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")


def expand_curie(value: str) -> str | None:
    """Expand ``prefix:local`` to an absolute IRI, or return ``None``.

    Absolute ``http(s)`` IRIs are returned unchanged, so callers can accept either
    spelling from a form field.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith(("http://", "https://")):
        return candidate
    prefix, sep, local = candidate.partition(":")
    if not sep or not local:
        return None
    namespace = NAMESPACES.get(prefix)
    if namespace is None:
        return None
    return namespace + local


def compact_iri(iri: str) -> str:
    """Return ``prefix:local`` for a known namespace, else ``iri`` unchanged."""
    for prefix, namespace in _NAMESPACE_ITEMS:
        if iri.startswith(namespace):
            return f"{prefix}:{iri[len(namespace):]}"
    return iri


def local_name(iri: str) -> str:
    """The fragment or last path segment of ``iri``."""
    return iri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def humanize_local_name(iri: str) -> str:
    """Turn ``https://dalicc.net/ns#chargeLicenseFee`` into ``Charge license fee``.

    Reproduces the display transformation the legacy license page applied to any
    action it did not recognise, so unknown terms still render readably.
    """
    name = local_name(iri).replace("_", " ")
    spaced = _CAMEL_RE.sub(r" \1", name).strip()
    return spaced[:1].upper() + spaced[1:].lower() if spaced else iri


def policy_quality(value: str) -> Term | None:
    """Look a policy-level quality up by IRI or CURIE (``dalicc:perpetual``)."""
    iri = expand_curie(value)
    if iri is None:
        return None
    return POLICY_QUALITIES.get(iri)


def humanize_value(value: str) -> str:
    """Humanise a scalar RDF value (a jurisdiction or validity type) for display.

    A value that names a known policy quality gets its reviewed label; everything else
    (the BPI country IRIs, above all) is humanised from its local name.  Known acronyms
    are kept intact -- the legacy code carried a hardcoded ``["ODbL", "LaTeX"]``
    avoid-list for exactly this reason.
    """
    quality = POLICY_QUALITIES.get(value)
    if quality is not None:
        return quality.label
    name = local_name(value).replace("_", " ")
    placeholders: dict[str, str] = {}
    for index, acronym in enumerate(_ACRONYMS, start=1):
        if acronym in name:
            token = f"\x00{index}\x00"
            placeholders[token] = acronym
            name = name.replace(acronym, token)
    name = _CAMEL_RE.sub(r" \1", name).strip()
    for token, acronym in placeholders.items():
        name = name.replace(token, acronym)
    return name[:1].upper() + name[1:] if name else value


def resolve_action(value: str) -> Term | None:
    """Look an action up by IRI or by CURIE."""
    iri = expand_curie(value)
    if iri is None:
        return None
    return ACTIONS.get(iri)


def is_known_action(value: str) -> bool:
    """Whether ``value`` (IRI or CURIE) names a term of the DALICC vocabulary."""
    return resolve_action(value) is not None


def action_label(iri: str) -> str:
    """Display label for an action IRI, falling back to a humanised local name."""
    term = ACTIONS.get(iri)
    return term.label if term else humanize_local_name(iri)


def action_description(iri: str) -> str:
    """One-sentence definition for an action IRI (empty when unknown)."""
    term = ACTIONS.get(iri)
    return term.description if term else ""


def asset_type_label(iri: str) -> str:
    """Display label for an ``odrl:AssetCollection`` ``dct:type`` value."""
    return ASSET_TYPES.get(iri) or humanize_value(iri)


def composable_actions() -> list[Term]:
    """Terms the composer and the search questionnaire may offer, label-sorted."""
    return sorted((t for t in _TERMS if t.composable), key=lambda t: t.label)


def duty_actions() -> list[Term]:
    """Terms that make sense as an ``odrl:Duty`` action, label-sorted."""
    return sorted((t for t in _TERMS if t.composable and t.is_duty_action), key=lambda t: t.label)


def term_payload(term: Term) -> dict[str, object]:
    """JSON shape of one term, as ``GET /licenselibrary/actions`` publishes it."""
    return {
        "iri": term.iri,
        "curie": term.curie,
        "label": term.label,
        "description": term.description,
        "rule_action": term.is_rule_action,
        "duty_action": term.is_duty_action,
        "group": term.group,
    }
