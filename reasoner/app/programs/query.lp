% SPDX-License-Identifier: AGPL-3.0-only
% SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
#const odrl_includedIn = "http://www.w3.org/ns/odrl/2/includedIn".
#const owl_sameAs = "http://www.w3.org/2002/07/owl#sameAs".
#const odrl_implies = "http://www.w3.org/ns/odrl/2/implies".
#const dalicc_contradicts = "https://dalicc.net/ns#contradicts".
#const odrl_permission = "http://www.w3.org/ns/odrl/2/permission". 
#const odrl_prohibition = "http://www.w3.org/ns/odrl/2/prohibition".
#const odrl_obligation = "http://www.w3.org/ns/odrl/2/obligation".
#const odrl_duty = "http://www.w3.org/ns/odrl/2/duty".
#const cc_ShareAlike = "http://creativecommons.org/ns#ShareAlike".
#const rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type".
#const dalicc_DefaultRule = "https://dalicc.net/ns#DefaultRule".
#const dalicc_appliesTo = "https://dalicc.net/ns#appliesTo".
#const dalicc_defaultOutcome = "https://dalicc.net/ns#defaultOutcome".
#const dalicc_NotGrantedByDefault = "https://dalicc.net/ns#NotGrantedByDefault".
#const dalicc_GrantedByDefault = "https://dalicc.net/ns#GrantedByDefault".
#const dalicc_RequiredByDefault = "https://dalicc.net/ns#RequiredByDefault".
#const dalicc_NotWaivable = "https://dalicc.net/ns#NotWaivable".
#const dalicc_ChangeLicense = "https://dalicc.net/ns#ChangeLicense".
#const dalicc_compliantLicense = "https://dalicc.net/ns#compliantLicense".
#const odrl_derive = "http://www.w3.org/ns/odrl/2/derive".
#const dalicc_compatibleWith = "https://dalicc.net/ns#compatibleWith".

%% core compatibility relations
%t(X, odrl_includedIn, Z) :-  t(X, odrl_includedIn, Y), t(Y, odrl_includedIn, Z).
%t(X, odrl_implies, Z) :-  t(X, odrl_implies, Y), t(Y, odrl_implies, Z).
%t(X, owl_sameAs, Z) :- t(X, owl_sameAs, Y), t(Y, owl_sameAs, Z).
%t(X, owl_sameAs, Z) :- t(Z, owl_sameAs, X).

%% get permisions, prohibitions, and obligations of the input licenses
license(S,P,O) :- &getLicense[L](S,P,O), license(L).

%% Reading: the duties a licence hangs on one of its rules rather than on itself.
%% The subject of such a duty is the rule node, so the atom above -- whose subject is
%% the licence -- cannot see it. licenseDuty(Licence, RulePredicate, RuleAction,
%% DutyAction) keeps the rule the duty belongs to, so "Distribute, with the duty
%% Attribution" is not flattened into "the licence requires Attribution" and a duty
%% under a prohibition or under another duty does not vanish. The composer's expert
%% view builds exactly these trees, and the questionnaire builds the permission case.
licenseDuty(S,P,RA,DA) :- &getLicenseDuties[L](S,P,RA,DA), license(L).

%% Reading: the licences of the request, by their IRI. license/1 holds the token the
%% request was written with, and every statement above names the licence by its IRI,
%% so a rule that ranges over the licences themselves reads this atom.
bundleLicense(S) :- &getLicenseIri[L](S), license(L).

%% Reading: which licence a record is a version of: its family, its version as a key
%% that sorts like the number, and whether it offers "this version or any later
%% version". app/profiles.py reads them from the record; a record it cannot place has
%% no profile.
licenseProfile(S,F,V,O) :- &getLicenseProfile[L](S,F,V,O), license(L).

%% Reading: the licences a record names with dalicc:compatibleWith, each with the
%% profile of the named record ("unplaced" three times when app/profiles.py cannot
%% place it). L compatibleWith X says a work under L may be released under X, and
%% nothing about the other way round.
namedCompatibility(S,X,F,V,O) :- &getLicenseCompatibility[L](S,X,F,V,O), license(L).

%% get dependency graph
dg(S,P,O) :- &getDependencyGraph["dg_default"](S,P,O).

%% Dependency Graph Logic

includedIn(X,Z,"derived") :- includedIn(X,Y,_), includedIn(Y,Z,_) .

implies(X,Z,"derived") :- implies(X,Y,_), implies(Y,Z,_) .

sameAs(X,Z,"derived") :- sameAs(X,Y,_), sameAs(Y,Z,_) .
sameAs(X,Z,"dependencygraph") :- sameAs(Z,X,"dependencygraph") .

sameAs(X,Y,"dependencygraph") :- dg(X,owl_sameAs,Y).
implies(X,Y,"dependencygraph") :- dg(X,odrl_implies,Y).
includedIn(X,Y,"dependencygraph") :- dg(X,odrl_includedIn,Y).
contradicts(X,Y,"dependencygraph") :- dg(X,dalicc_contradicts,Y).

%% Reading: a second name for an act is that act, so a subsumption, an entailment or a
%% contradiction written about one name holds of every other name for the same thing.
%% The graph says that commercial use and commercialize are one act and that charging
%% a licence fee entails commercializing, so a licence that permits the fee runs into
%% one that prohibits commercial use. Without these rules the synonym would stop the
%% chain, and app/services/composer.py, which walks owl:sameAs inside both of its
%% closures, would report a conflict the program does not.
includedIn(X,Z,"derived") :- includedIn(X,Y,_), sameAs(Y,Z,_).
includedIn(X,Z,"derived") :- sameAs(X,Y,_), includedIn(Y,Z,_).
implies(X,Z,"derived") :- implies(X,Y,_), sameAs(Y,Z,_).
implies(X,Z,"derived") :- sameAs(X,Y,_), implies(Y,Z,_).
contradicts(X,Z,"derived") :- contradicts(X,Y,_), sameAs(Y,Z,_).
contradicts(Z,Y,"derived") :- contradicts(X,Y,_), sameAs(X,Z,_).

%% Reading: permitting an act that entails a second act runs into a prohibition of
%% anything that second act is a special case of. Deriving entails a derivative work,
%% and a derivative work is one kind of distribution, so a permission to derive meets a
%% prohibition of distributing. The conclusion is kept in an atom of its own rather
%% than added to implies/3: "permitting X collides with prohibiting Z" is not
%% "permitting X commits to Z", and feeding it back into the entailment closure would
%% carry it one step too far.
impliesIncluded(X,Z,"derived") :- implies(X,Y,_), includedIn(Y,Z,_).

directConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"direct") :- holds(L1,"http://www.w3.org/ns/odrl/2/permission",X), 
                                                                                                                   holds(L2,"http://www.w3.org/ns/odrl/2/prohibition",X).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",Y,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"includedIn",Y,X,R) :- holds(L1,"http://www.w3.org/ns/odrl/2/permission",Y), 
                                                                                                                       holds(L2,"http://www.w3.org/ns/odrl/2/prohibition",X), 
                                                                                                                       includedIn(Y,X,R).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",Y,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"sameAs",Y,X,R) :- holds(L1,"http://www.w3.org/ns/odrl/2/permission",Y), 
                                                                                                                       holds(L2,"http://www.w3.org/ns/odrl/2/prohibition",X), 
                                                                                                                       sameAs(Y,X,R).


derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",Y,"implies",X,Y,R) :- holds(L1,"http://www.w3.org/ns/odrl/2/permission",X),
                                                                                                                       holds(L2,"http://www.w3.org/ns/odrl/2/prohibition",Y),
                                                                                                                       implies(X,Y,R).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",Y,"implies",X,Y,R) :- holds(L1,"http://www.w3.org/ns/odrl/2/permission",X),
                                                                                                                       holds(L2,"http://www.w3.org/ns/odrl/2/prohibition",Y),
                                                                                                                       impliesIncluded(X,Y,R).


%% Reading: what the licence requires, wherever the duty that requires it hangs.
%% A licence-wide duty, an obligation, a duty under a permission, one under a
%% prohibition and one under another duty all say the same thing about the action:
%% the licensee has to do it. The rule each one belongs to is kept in licenseDuty/4
%% for the rules that need it. requiredByText/2 is what the licence itself says, and
%% required/2 adds what a default rule supplies; the first is what silence is read
%% against, so that a derived duty can never make a licence look as if it had spoken.
requiredByText(L,A) :- license(L,odrl_duty,A).
requiredByText(L,A) :- license(L,odrl_obligation,A).
requiredByText(L,A) :- licenseDuty(L,_,_,A).
required(L,A) :- requiredByText(L,A).
required(L,A) :- defaultStatement(L,odrl_duty,A,_).


%% ------------------------------------------------------------------------------
%% Default rules: what applies to an action the licence does not mention.
%%
%% A dependency graph carries a second kind of statement beside its axioms. A
%% dalicc:DefaultRule names one action, one outcome, one jurisdiction and the legal
%% source it rests on. Nothing it states is legal advice: it is a reading of a legal
%% default, and what a licence means is decided by its text.
%% app/services/consistency.py implements the same reading for the composer's form,
%% and tests/unit/test_composer_reasoner.py proves the two agree.
%% ------------------------------------------------------------------------------

ruleAction(R,A) :- dg(R,dalicc_appliesTo,A).
ruleOutcome(R,O) :- dg(R,dalicc_defaultOutcome,O).

%% Reading: every rule the chosen graph carries takes part. The core graph holds only
%% the rules the library has adopted; a jurisdiction graph holds proposals and is
%% never the default, so loading one is the reader's request to see what they would
%% do. The predicate is written out rather than folded into the rules below so that
%% the reading has a name, and a place to be narrowed later.
ruleApplies(R) :- ruleAction(R,_), ruleOutcome(R,_).

%% Reading: a licence settles an action when it permits it, prohibits it or requires
%% it, and also when the graph carries one of those statements to it. Permitting an
%% act permits everything it entails and every other name for it; prohibiting an act
%% prohibits every special case of it and every other name for it; a duty carries to
%% the other names of the act it requires. Those are the two closures the derived
%% conflicts already use, so silence is read with the reasoning the rest of the
%% program is built on, and everything else is silence.
speaksAbout(L,A) :- license(L,odrl_permission,A).
speaksAbout(L,A) :- license(L,odrl_prohibition,A).
speaksAbout(L,A) :- requiredByText(L,A).
speaksAbout(L,A) :- license(L,odrl_permission,X), implies(X,A,_).
speaksAbout(L,A) :- license(L,odrl_permission,X), sameAs(X,A,_).
speaksAbout(L,A) :- license(L,odrl_prohibition,X), includedIn(A,X,_).
speaksAbout(L,A) :- license(L,odrl_prohibition,X), sameAs(A,X,_).
speaksAbout(L,A) :- requiredByText(L,X), sameAs(X,A,_).

%% The negation is stratified: nothing below speaksAbout/2 derives it, so the program
%% still has exactly one answer set.
silent(L,A) :- bundleLicense(L), ruleAction(R,A), ruleApplies(R), not speaksAbout(L,A).

defaultStatement(L,odrl_prohibition,A,R) :- silent(L,A), ruleAction(R,A), ruleApplies(R),
                                            ruleOutcome(R,dalicc_NotGrantedByDefault).
defaultStatement(L,odrl_permission,A,R) :- silent(L,A), ruleAction(R,A), ruleApplies(R),
                                           ruleOutcome(R,dalicc_GrantedByDefault).
defaultStatement(L,odrl_duty,A,R) :- silent(L,A), ruleAction(R,A), ruleApplies(R),
                                     ruleOutcome(R,dalicc_RequiredByDefault).

%% Reading: dalicc:NotWaivable adds nothing and reports that the licence says
%% something the law of that jurisdiction does not let it say. Which statement is the
%% contrary one depends on which way the law leans, and the graph says which: where it
%% also carries a GrantedByDefault rule for the same action the law keeps an exception
%% open, so a prohibition is the contrary statement; everywhere else the law keeps a
%% protection in place, so a permission is. The companion is looked up by action
%% inside the graph the check runs under.
grantedBySomeRule(A) :- ruleAction(R,A), ruleApplies(R), ruleOutcome(R,dalicc_GrantedByDefault).

defaultFinding(L,A,R,odrl_prohibition) :- ruleOutcome(R,dalicc_NotWaivable), ruleAction(R,A),
                                          ruleApplies(R), grantedBySomeRule(A),
                                          license(L,odrl_prohibition,A).
defaultFinding(L,A,R,odrl_permission) :- ruleOutcome(R,dalicc_NotWaivable), ruleAction(R,A),
                                         ruleApplies(R), not grantedBySomeRule(A),
                                         license(L,odrl_permission,A).

%% Reading: what holds of a licence is what its text says plus what a default rule
%% supplies for an action the text is silent about. Every conflict rule below reads
%% holds/3, so a derived statement takes part exactly as a stated one does; it is only
%% the reporting that keeps the two apart, through defaultStatement/4.
holds(L,P,A) :- license(L,P,A).
holds(L,P,A) :- defaultStatement(L,P,A,_).

%% Reading: an action that one licence requires as a duty and another forbids can
%% never be done, so the duty can never be discharged. This is the conclusion
%% app/services/composer.py draws for the same pair inside one licence, and it holds
%% across a bundle for the same reason. L1 = L2 is allowed: a licence that requires
%% what it forbids contradicts itself.
directConflict(L1,odrl_duty,X,L2,odrl_prohibition,X,"duty-prohibited") :- required(L1,X),
                                                                          holds(L2,odrl_prohibition,X).

%% Reading: a duty hanging on a prohibition conditions an act that is forbidden, so
%% it can never apply. Both statements are in the same licence, which is why one
%% licence variable stands in both places.
directConflict(L,odrl_prohibition,RA,L,odrl_duty,DA,"duty-on-prohibition") :- licenseDuty(L,odrl_prohibition,RA,DA).

%% Reading: a compatibility clause. A ChangeLicense permission that carries the
%% compliantLicense duty lets the work move to another license only on terms that
%% comply with this one, which is what the EUPL, CeCILL and LiLiQ records state. This
%% is the one place the duty *under* a permission changes a verdict rather than adding
%% one, so the nested fact is what makes the reading possible at all.
compliantRelicensing(L) :- licenseDuty(L,odrl_permission,dalicc_ChangeLicense,dalicc_compliantLicense).

%% Reading: share alike is required for the whole work while changing the license is
%% permitted without that compatibility clause, so the work could leave the license
%% that requires it to stay. The duty has to hang on the licence itself: the same duty
%% on Modify or Distribute is file-level reciprocity and leaves the rest free, which
%% is why licenseDuty/4 is not read here. The negation is stratified -- nothing below
%% derives licenseDuty/4 -- so the program still has exactly one answer set.
directConflict(L1,odrl_duty,cc_ShareAlike,L2,odrl_permission,dalicc_ChangeLicense,"share-alike-escape") :- license(L1,odrl_duty,cc_ShareAlike),
                                                                                                          holds(L2,odrl_permission,dalicc_ChangeLicense),
                                                                                                          not compliantRelicensing(L2).

%% Reading: a licence binds the whole of a work it takes part in to itself when it
%% requires share alike of the whole work (the reading share-alike-escape uses), and
%% also when it requires share alike of every derivative work and forbids changing the
%% license: then no derivative of it can carry another licence either. A share-alike
%% duty on Modify or Distribute alone is file-level reciprocity and binds nothing else.
bindsWholeWork(L) :- license(L,odrl_duty,cc_ShareAlike).
bindsWholeWork(L) :- licenseDuty(L,odrl_permission,odrl_derive,cc_ShareAlike),
                     license(L,odrl_prohibition,dalicc_ChangeLicense).

%% Reading: a path from one such licence to another. The same licence text is one (the
%% same family and version, as an exception or a jurisdiction port of it is); an
%% "or later" option that reaches the other's version is another; a compatibility
%% clause (compliantRelicensing) lets the work move to a licence that complies with
%% it. A licence named with dalicc:compatibleWith is handled below, because it leads
%% one way only and the combined work then has to go that way.
reciprocityPath(L1,L2) :- licenseProfile(L1,F,V,_), licenseProfile(L2,F,V,_), L1 != L2.
reciprocityPath(L1,L2) :- licenseProfile(L1,F,V1,"or-later"), licenseProfile(L2,F,V2,_),
                          V1 <= V2, L1 != L2.
reciprocityPath(L1,L2) :- compliantRelicensing(L1), bindsWholeWork(L2), L1 != L2.
reciprocityPath(L1,L2) :- reciprocityPath(L2,L1).

%% Reading: two licences that each bind the whole work to themselves, with no path
%% above between them, in the order of their IRIs.
reciprocityGap(L1,L2) :- bindsWholeWork(L1), bindsWholeWork(L2), L1 < L2,
                         not reciprocityPath(L1,L2).

%% Reading: L1 grants by name that a work under it may be released under L2. The name
%% is L2 itself, or one hop from it: a record of the same licence text as L2, or one
%% whose "or later" option reaches L2's version (LGPL-2.1 names GPL-2.0-or-later, which
%% reaches GPL-3.0). A named licence the reasoner cannot place only matches by its IRI.
compatibleByName(L1,L2) :- namedCompatibility(L1,L2,_,_,_), bindsWholeWork(L2), L1 != L2.
compatibleByName(L1,L2) :- namedCompatibility(L1,X,F,V,_), licenseProfile(L2,F,V,_),
                           F != "unplaced", bindsWholeWork(L2), L1 != L2.
compatibleByName(L1,L2) :- namedCompatibility(L1,X,F,V1,"or-later"), licenseProfile(L2,F,V2,_),
                           F != "unplaced", V1 <= V2, bindsWholeWork(L2), L1 != L2.
namedPath(L1,L2) :- compatibleByName(L1,L2).
namedPath(L1,L2) :- compatibleByName(L2,L1).

%% Reading: two licences that each bind the whole work to themselves cannot both be
%% satisfied by one combined work unless a path leads from one to the other. The pair
%% is reported once, in the order of the IRIs, whichever order the request names them.
%% The negations are stratified: nothing reciprocityPath/2 or namedPath/2 depends on is
%% derived from a conflict, so the program still has exactly one answer set.
directConflict(L1,odrl_duty,cc_ShareAlike,L2,odrl_duty,cc_ShareAlike,"share-alike-reciprocity") :-
    reciprocityGap(L1,L2), not namedPath(L1,L2).

%% Reading: a named compatibility clears the pair in the direction it states, and that
%% direction is a restriction on the combined work: it has to be released under L2.
%% One entry per direction the records state, so a pair that names each other (AGPL-3.0
%% and GPL-3.0) gets two. The first statement reads L1 compatibleWith L2, with L2 the
%% licence of the request the name reaches (the named record itself, or the one a hop
%% leads to); a client that checks against a target licence compares the target with
%% its object.
directConflict(L1,dalicc_compatibleWith,L2,L2,odrl_duty,cc_ShareAlike,"share-alike-direction") :-
    reciprocityGap(L1,L2), compatibleByName(L1,L2).
directConflict(L2,dalicc_compatibleWith,L1,L1,odrl_duty,cc_ShareAlike,"share-alike-direction") :-
    reciprocityGap(L1,L2), compatibleByName(L2,L1).

%% Reading: what a licence asserts about an action is that it is permitted, or that
%% it is required. A duty to do X commits the licensee to X as surely as a permission
%% allows it, so both count when the graph says two acts cannot both hold of one
%% asset.
asserted(L,odrl_permission,X) :- holds(L,odrl_permission,X).
asserted(L,odrl_duty,X) :- required(L,X).

%% Two acts that cannot both be allowed of the same asset: asserting both is a
%% conflict although neither license forbids anything.  The axiom is directed in the
%% graph and needs no symmetric copy here, because L1 and L2 range over every license
%% of the bundle, so either order of the two licenses matches it.  L1 = L2 is allowed
%% on purpose: one license that asserts both contradicts itself, which is what the
%% consistency check has to see.  Two permissions produce exactly the atom the
%% earlier permission-only rule produced, so that answer is unchanged.
derivedConflict(L1,P1,X,L2,P2,Y,"contradicts",X,Y,R) :- asserted(L1,P1,X),
                                                        asserted(L2,P2,Y),
                                                        contradicts(X,Y,R).


%% The two conflict atoms keep the arity and the shape the client contract fixes.
%% defaultStatement/4 and defaultFinding/4 are shown beside them so that the service
%% can say, of every finding, which side came from the text and which from a rule, and
%% can publish the derived statements in their own right.
#show directConflict/7.
#show derivedConflict/10.
#show defaultStatement/4.
#show defaultFinding/4.