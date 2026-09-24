# Difference files of the jurisdiction graphs

Every dependency graph DALICC publishes is complete: `licensedata/dependencygraph/dg_eu.ttl`
holds every axiom and every default rule a check under the European Union graph reads, and
the reasoner follows no link to another graph. The seven jurisdiction graphs are
nevertheless written down here, as what each one does *differently* from the core graph
`dg_default`, because that is what a legal reviewer reads and what changes when a law
changes. This directory is the source of truth; the complete files next to it are
generated from it and must not be edited by hand.

| File | Graph | Adds | Removes | Replaces |
|---|---|---|---|---|
| `dg_eu.ttl` | European Union default rules | 9 rules | nothing | nothing |
| `dg_us.ttl` | United States default rules | 2 rules | nothing | nothing |
| `dg_cn.ttl` | China default rules | 2 rules | nothing | nothing |
| `dg_gb.ttl` | United Kingdom default rules | 5 rules | nothing | nothing |
| `dg_jp.ttl` | Japan default rules | 3 rules | nothing | nothing |
| `dg_in.ttl` | India default rules | 3 rules | nothing | nothing |
| `dg_br.ttl` | Brazil default rules | 3 rules | nothing | nothing |

Nothing in these files is legal advice. Every rule is `dalicc:Proposed` until the
association's legal reviewer adopts it.

## What a difference file holds

1. **The graph's metadata**, on the graph's own address: `dct:title`, `dct:description`,
   the jurisdiction concept as `dct:coverage` (`dalicc:EU`, `dalicc:US`, ...) and
   `dalicc:basedOnGraph <https://dalicc.net/dependencygraph/dg_default>`.
2. **The default rules it adds.** A `dalicc:DefaultRule` with `dalicc:appliesTo`,
   `dalicc:defaultOutcome`, `dalicc:inJurisdiction`, `dalicc:ruleBasis` (the citation),
   `dalicc:ruleExplanation` (two or three plain sentences: what the rule does to a
   licence that is silent, why the law leads there, and what a person combining licences
   will notice), `dct:date` and `dalicc:ruleStatus`.
3. **The core axioms it removes**, each as a `dalicc:AxiomRemoval` that names the axiom in
   the reified form and says why it does not hold there.
4. **The core default rules it replaces**, each as a rule of its own that names the core
   rule with `dalicc:replacesRule` and carries its own outcome, basis and explanation.

Every rule and every removal needs both texts, the basis and the explanation; the build
and `scripts/validate_data.py` refuse one without them.

An example, the European exhaustion rule as `dg_eu.ttl` writes it:

```turtle
<https://dalicc.net/dependencygraph/dg_eu> dct:title "European Union default rules"@en ;
    dct:description """The DALICC deontic dependency graph with default rules ..."""@en ;
    dct:coverage dalicc:EU ;
    dalicc:basedOnGraph <https://dalicc.net/dependencygraph/dg_default> .

<https://dalicc.net/dependencygraph/rules/eu-exhaustion> a dalicc:DefaultRule ;
    rdfs:label "A copy that was sold may be sold on"@en ;
    dalicc:appliesTo dalicc:sellCopy ;
    dalicc:defaultOutcome dalicc:GrantedByDefault ;
    dalicc:inJurisdiction dalicc:EU ;
    dalicc:ruleBasis "Directive 2001/29/EC article 4(2): ..." ;
    dalicc:ruleExplanation "A licence that says nothing about reselling a copy is read as ..."@en ;
    dct:date "2026-09-23"^^xsd:date ;
    dalicc:ruleStatus dalicc:Proposed .
```

## Removals and replacements: none shipped, and why

No shipped graph removes an axiom or replaces a rule. The 46 axioms of the core graph say
how actions relate to each other (selling a copy is a way of selling, copying is the same
act as reproducing), which is not something the law of one country changes, and the one
core rule, that a copyright licence silent about endorsement grants none, rests on trademark
law and the protection of names in every jurisdiction the reviewer knows of. Inventing an
example would put a claim about the law into the data that no source supports, so the
syntax is shown here instead.

A removal (the axiom, why it does not hold, and the status):

```turtle
<https://dalicc.net/dependencygraph/removals/xx-sellcopy-sell> a dalicc:AxiomRemoval ;
    rdfs:label "Selling a copy is not treated as selling the work"@en ;
    rdf:subject dalicc:sellCopy ;
    rdf:predicate odrl:includedIn ;
    rdf:object odrl:sell ;
    dalicc:ruleBasis "the statute and article that make the difference" ;
    dalicc:ruleExplanation "Why the axiom does not hold under this law, in plain words."@en ;
    dct:date "2026-09-24"^^xsd:date ;
    dalicc:ruleStatus dalicc:Proposed .
```

A replacement (a rule about the same action that takes the place of a core rule):

```turtle
<https://dalicc.net/dependencygraph/rules/xx-endorsement> a dalicc:DefaultRule ;
    rdfs:label "Endorsement follows the local rule"@en ;
    dalicc:replacesRule <https://dalicc.net/dependencygraph/rules/endorsement-worldwide> ;
    dalicc:appliesTo dalicc:promote ;
    dalicc:defaultOutcome dalicc:GrantedByDefault ;
    dalicc:inJurisdiction dalicc:XX ;
    dalicc:ruleBasis "the statute and article that make the difference" ;
    dalicc:ruleExplanation "What changes against the core rule, and why."@en ;
    dct:date "2026-09-24"^^xsd:date ;
    dalicc:ruleStatus dalicc:Proposed .
```

The generated graph then holds neither the removed axiom nor the replaced rule, and it
never holds two default rules of one kind for one action in one territory (a
`dalicc:NotWaivable` rule beside a rule that supplies a statement is how a graph says an
exception cannot be contracted away, and is allowed).

## The build

```
python scripts/build_dependency_graphs.py            # write; refuse a graph whose statements change
python scripts/build_dependency_graphs.py --bump     # version every graph whose statements change
python scripts/build_dependency_graphs.py --check    # exit 1 when a generated file is stale
python scripts/build_dependency_graphs.py --extract dg_eu   # complete graph -> this file
```

The build writes `licensedata/dependencygraph/<id>.ttl` deterministically: the core
graph's prefix block, a header that names the version, the core version and this file,
the metadata with `dalicc:basedOnVersion`, the axioms in canonical order, the rules, and
the removal records. When a core change or a change here alters what a generated graph
states, the build refuses to overwrite it until `--bump` is given; `--bump` archives the
previous file as `licensedata/history/dependencygraph/<id>-v<n>.ttl` and adds the change-log
entry of the next version, whose summary names the cause ("Follows core graph version 3.",
"The difference file added a rule."). `scripts/validate_data.py` runs `--check`.

A jurisdiction graph an administrator edits on the server is exported to
`licensedata/dependencygraph/<id>.ttl` by `make export-library`, like a core edit, and folded
back into this directory with `--extract <id>`, which keeps the comment block of the file
that is here. docs/ADMINISTRATION.md describes the round trip.
