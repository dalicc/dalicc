% Constants representing various RDF and ODRL properties
#const odrl_includedIn = "http://www.w3.org/ns/odrl/2/includedIn".
#const owl_sameAs = "http://www.w3.org/2002/07/owl#sameAs".
#const odrl_implies = "http://www.w3.org/ns/odrl/2/implies".
#const dalicc_contradicts = "https://dalicc.net/ns#contradicts".
#const odrl_permission = "http://www.w3.org/ns/odrl/2/permission". 
#const odrl_prohibition = "http://www.w3.org/ns/odrl/2/prohibition".
#const odrl_obligation = "http://www.w3.org/ns/odrl/2/obligation".
#const odrl_duty = "http://www.w3.org/ns/odrl/2/duty". 

% Core compatibility relations (currently commented out)
% t(X, odrl_includedIn, Z) :-  t(X, odrl_includedIn, Y), t(Y, odrl_includedIn, Z).
% t(X, odrl_implies, Z) :-  t(X, odrl_implies, Y), t(Y, odrl_implies, Z).
% t(X, owl_sameAs, Z) :- t(X, owl_sameAs, Y), t(Y, owl_sameAs, Z).
% t(X, owl_sameAs, Z) :- t(Z, owl_sameAs, X).

% Get permissions, prohibitions, and obligations of the input licenses
license(S,P,O) :- &getLicense[L](S,P,O), license(L).

% Get dependency graph
dg(S,P,O) :- &getDependencyGraph["dg_default"](S,P,O).

% Dependency Graph Logic

% Recursive relation for 'includedIn' with derived label
includedIn(X,Z,"derived") :- includedIn(X,Y,_), includedIn(Y,Z,_) .

% Recursive relation for 'implies' with derived label
implies(X,Z,"derived") :- implies(X,Y,_), implies(Y,Z,_) .

% Recursive relation for 'sameAs' with derived label and dependency graph logic
sameAs(X,Z,"derived") :- sameAs(X,Y,_), sameAs(Y,Z,_) .
sameAs(X,Z,"dependencygraph") :- sameAs(Z,X,"dependencygraph") .
sameAs(X,X,"dependencygraph") :- action(X) .

% Dependency graph relations
sameAs(X,Y,"dependencygraph") :- dg(X,owl_sameAs,Y).
implies(X,Y,"dependencygraph") :- dg(X,odrl_implies,Y).
includedIn(X,Y,"dependencygraph") :- dg(X,odrl_includedIn,Y).

% Logic to identify direct conflicts between permissions and prohibitions
directConflict(L1, odrl_permission, X, L2, odrl_prohibition, X, "direct") :- 
    license(L1, odrl_permission, X), 
    license(L2, odrl_prohibition, X).

% Logic to identify derived conflicts through 'includedIn' relation
derivedConflict(L1, odrl_permission, Y, L2, odrl_prohibition, X, "includedIn", Y, X, R) :- 
    license(L1, odrl_permission, Y), 
    license(L2, odrl_prohibition, X), 
    includedIn(Y, X, R).

% Logic to identify derived conflicts through 'sameAs' relation
derivedConflict(L1, odrl_permission, Y, L2, odrl_prohibition, X, "sameAs", Y, X, R) :- 
    license(L1, odrl_permission, Y), 
    license(L2, odrl_prohibition, X), 
    sameAs(Y, X, R).

% Logic to identify derived conflicts through 'implies' relation
derivedConflict(L1, odrl_permission, X, L2, odrl_prohibition, Y, "implies", X, Y, R) :- 
    license(L1, odrl_permission, X), 
    license(L2, odrl_prohibition, Y), 
    implies(X, Y, R).

% Directives to show specific conflicts
#show directConflict/7.
#show derivedConflict/10.