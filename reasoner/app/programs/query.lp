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
#const dalicc_ChangeLicense = "https://dalicc.net/ns#ChangeLicense".
#const dalicc_compliantLicense = "https://dalicc.net/ns#compliantLicense".

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

directConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"direct") :- license(L1,"http://www.w3.org/ns/odrl/2/permission",X), 
                                                                                                                   license(L2,"http://www.w3.org/ns/odrl/2/prohibition",X).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",Y,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"includedIn",Y,X,R) :- license(L1,"http://www.w3.org/ns/odrl/2/permission",Y), 
                                                                                                                       license(L2,"http://www.w3.org/ns/odrl/2/prohibition",X), 
                                                                                                                       includedIn(Y,X,R).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",Y,L2,"http://www.w3.org/ns/odrl/2/prohibition",X,"sameAs",Y,X,R) :- license(L1,"http://www.w3.org/ns/odrl/2/permission",Y), 
                                                                                                                       license(L2,"http://www.w3.org/ns/odrl/2/prohibition",X), 
                                                                                                                       sameAs(Y,X,R).


derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",Y,"implies",X,Y,R) :- license(L1,"http://www.w3.org/ns/odrl/2/permission",X),
                                                                                                                       license(L2,"http://www.w3.org/ns/odrl/2/prohibition",Y),
                                                                                                                       implies(X,Y,R).

derivedConflict(L1,"http://www.w3.org/ns/odrl/2/permission",X,L2,"http://www.w3.org/ns/odrl/2/prohibition",Y,"implies",X,Y,R) :- license(L1,"http://www.w3.org/ns/odrl/2/permission",X),
                                                                                                                       license(L2,"http://www.w3.org/ns/odrl/2/prohibition",Y),
                                                                                                                       impliesIncluded(X,Y,R).


%% Reading: what the licence requires, wherever the duty that requires it hangs.
%% A licence-wide duty, an obligation, a duty under a permission, one under a
%% prohibition and one under another duty all say the same thing about the action:
%% the licensee has to do it. The rule each one belongs to is kept in licenseDuty/4
%% for the rules that need it.
required(L,A) :- license(L,odrl_duty,A).
required(L,A) :- license(L,odrl_obligation,A).
required(L,A) :- licenseDuty(L,_,_,A).

%% Reading: an action that one licence requires as a duty and another forbids can
%% never be done, so the duty can never be discharged. This is the conclusion
%% app/services/composer.py draws for the same pair inside one licence, and it holds
%% across a bundle for the same reason. L1 = L2 is allowed: a licence that requires
%% what it forbids contradicts itself.
directConflict(L1,odrl_duty,X,L2,odrl_prohibition,X,"duty-prohibited") :- required(L1,X),
                                                                          license(L2,odrl_prohibition,X).

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
                                                                                                          license(L2,odrl_permission,dalicc_ChangeLicense),
                                                                                                          not compliantRelicensing(L2).

%% Reading: what a licence asserts about an action is that it is permitted, or that
%% it is required. A duty to do X commits the licensee to X as surely as a permission
%% allows it, so both count when the graph says two acts cannot both hold of one
%% asset.
asserted(L,odrl_permission,X) :- license(L,odrl_permission,X).
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


#show directConflict/7.
#show derivedConflict/10.