#const odrl_includedIn = "http://www.w3.org/ns/odrl/2/includedIn".
#const owl_sameAs = "http://www.w3.org/2002/07/owl#sameAs".
#const odrl_implies = "http://www.w3.org/ns/odrl/2/implies".
#const dalicc_contradicts = "http://dalicc.net/ns#contradicts".
#const odrl_permission = "http://www.w3.org/ns/odrl/2/permission". 
#const odrl_prohibition = "http://www.w3.org/ns/odrl/2/prohibition".
#const odrl_obligation = "http://www.w3.org/ns/odrl/2/obligation".
#const odrl_duty = "http://www.w3.org/ns/odrl/2/duty". 

%% core compatibility relations
%t(X, odrl_includedIn, Z) :-  t(X, odrl_includedIn, Y), t(Y, odrl_includedIn, Z).
%t(X, odrl_implies, Z) :-  t(X, odrl_implies, Y), t(Y, odrl_implies, Z).
%t(X, owl_sameAs, Z) :- t(X, owl_sameAs, Y), t(Y, owl_sameAs, Z).
%t(X, owl_sameAs, Z) :- t(Z, owl_sameAs, X).

%% get permisions, prohibitions, and obligations of the input licenses
license(S,P,O) :- &getLicense[L](S,P,O), license(L).

%% get dependency graph
dg(S,P,O) :- &getDependencyGraph["dg_default"](S,P,O).

%% Dependency Graph Logic

includedIn(X,Z,"derived") :- includedIn(X,Y,_), includedIn(Y,Z,_) .

implies(X,Z,"derived") :- implies(X,Y,_), implies(Y,Z,_) .

sameAs(X,Z,"derived") :- sameAs(X,Y,_), sameAs(Y,Z,_) .
sameAs(X,Z,"dependencygraph") :- sameAs(Z,X,"dependencygraph") .
sameAs(X,X,"dependencygraph") :- action(X) .

sameAs(X,Y,"dependencygraph") :- dg(X,"http://www.w3.org/2002/07/owl#sameAs",Y).
implies(X,Y,"dependencygraph") :- dg(X,"http://www.w3.org/ns/odrl/2/implies",Y).
includedIn(X,Y,"dependencygraph") :- dg(X,"http://www.w3.org/ns/odrl/2/includedIn",Y).

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


#show directConflict/7.
#show derivedConflict/10.