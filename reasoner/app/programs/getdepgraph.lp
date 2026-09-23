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

t(X, odrl_includedIn, Z) :-  t(X, odrl_includedIn, Y), t(Y, odrl_includedIn, Z), X!=Z.

t(X, odrl_implies, Z) :-  t(X, odrl_implies, Y), t(Y, odrl_implies, Z), X!=Z.

t(X, owl_sameAs, Z) :- t(X, owl_sameAs, Y), t(Y, owl_sameAs, Z), X!=Z.
t(X, owl_sameAs, Z) :- t(Z, owl_sameAs, X).

% get dependency graph
%
% Only the four relations become t/3. A graph also carries dalicc:DefaultRule nodes,
% which say what applies to an action a licence is silent about rather than relating
% two actions; the closure below is about the relations, and the published shape of
% GET /reasoner/dependency_graph is the closure of the axioms and nothing else. The
% rules are served by GET /dependencygraph/rules on the API service.
relation(odrl_includedIn). relation(odrl_implies).
relation(owl_sameAs). relation(dalicc_contradicts).

t(S,P,O) :- &getDependencyGraph["dg_default"](S,P,O), relation(P).