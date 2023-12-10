% Define constants representing various RDF and ODRL properties
#const odrl_includedIn = "http://www.w3.org/ns/odrl/2/includedIn".
#const owl_sameAs = "http://www.w3.org/2002/07/owl#sameAs".
#const odrl_implies = "http://www.w3.org/ns/odrl/2/implies".
#const dalicc_contradicts = "http://dalicc.net/ns#contradicts".
#const odrl_permission = "http://www.w3.org/ns/odrl/2/permission". 
#const odrl_prohibition = "http://www.w3.org/ns/odrl/2/prohibition".
#const odrl_obligation = "http://www.w3.org/ns/odrl/2/obligation".
#const odrl_duty = "http://www.w3.org/ns/odrl/2/duty". 

% Recursive rule for the 'odrl:includedIn' relation
t(X, odrl_includedIn, Z) :-  t(X, odrl_includedIn, Y), t(Y, odrl_includedIn, Z), X != Z.

% Recursive rule for the 'odrl:implies' relation
t(X, odrl_implies, Z) :-  t(X, odrl_implies, Y), t(Y, odrl_implies, Z), X != Z.

% Recursive rule for the 'owl:sameAs' relation
t(X, owl_sameAs, Z) :- t(X, owl_sameAs, Y), t(Y, owl_sameAs, Z), X != Z.
% Symmetric property rule for 'owl:sameAs' (if X is sameAs Y, then Y is sameAs X)
t(X, owl_sameAs, Z) :- t(Z, owl_sameAs, X).

% Rule to get the dependency graph using an external function 'getDependencyGraph'
% 'dg_default' might refer to a default setting or specific configuration for the dependency graph
t(S, P, O) :- &getDependencyGraph["dg_default"](S, P, O).