# DALICC reasoner

Part of the [documentation index](../README.md#documentation). The answer-set-programming
service that detects deontic conflicts between ODRL licences, for anyone working on the
compatibility check.

It is an internal service. The public `POST /compatibilitycheck/` on the API service is a
thin proxy: it forwards to `POST /reasoner/compatibility` here and hands the answer back
unchanged.

```
client -> dalicc-api  POST /compatibilitycheck/
             |
             +-> dalicc-reasoner  POST /reasoner/compatibility
                      |
                      +-> hexlite (clingo)  app/programs/query.lp
                               |
                               +-> app/plugins/plugins.py -> SPARQL (Virtuoso)
```

## What it computes

A DALICC licence is an `odrl:Set` whose rules carry an `odrl:action`. The reasoner reduces
each licence in the request to triples

```
license(<licence IRI>, <odrl:permission | prohibition | obligation | duty>, <action IRI>)
```

and to triples

```
licenseDuty(<licence IRI>, <the rule's predicate>, <the rule's action>, <the duty's action>)
```

for the duties a licence hangs on one of those rules rather than on itself, and looks for
statements that cannot all hold at once.

| Kind | Rule | Meaning |
|---|---|---|
| `direct` | `L1` permits `X` and `L2` prohibits `X` | the same action |
| `direct` | `L1` requires `X` as a duty and `L2` prohibits `X` | the duty can never be discharged |
| `direct` | `L` hangs a duty on a prohibition | the act the duty conditions never happens, so the duty never applies |
| `direct` | `L1` requires share alike of the whole work while `L2` permits `dalicc:ChangeLicense` without the `dalicc:compliantLicense` duty under it | the work could leave the licence that requires it to stay |
| `derived` | `L1` permits `Y`, `L2` prohibits `X`, and the dependency graph relates them | a conflict through `odrl:includedIn`, `odrl:implies` or `owl:sameAs` |
| `derived` | `L1` asserts `X`, `L2` asserts `Y`, and the graph says `X dalicc:contradicts Y` | two acts that cannot both hold of one asset, although neither licence forbids anything. Asserting is permitting or requiring |

## What a licence does not say

A dependency graph carries a second kind of statement beside its axioms: a
`dalicc:DefaultRule`, which names one action, what applies to it when the licence is
silent, the territory it holds in and the statute or principle it rests on. Nothing a
rule states is legal advice.

A licence is **silent** about an action when it neither permits it, prohibits it nor
requires it, and when no statement of the graph carries one of those to it. That is
`speaksAbout/2` in the program: permitting an act settles everything it entails and
every other name for it, prohibiting an act settles every special case of it and every
other name for it, and a duty settles the other names of what it requires. Those are the
two closures the derived conflicts use, so silence is read with the reasoning the rest
of the program is built on. `silent/2` is the stratified negation of it, and it is read
against `requiredByText/2` rather than `required/2`, so a derived duty can never make a
licence look as if it had spoken.

| Outcome | What the program adds |
|---|---|
| `dalicc:NotGrantedByDefault` | `defaultStatement(L, odrl:prohibition, A, R)` |
| `dalicc:GrantedByDefault` | `defaultStatement(L, odrl:permission, A, R)` |
| `dalicc:RequiredByDefault` | `defaultStatement(L, odrl:duty, A, R)` |
| `dalicc:NotWaivable` | nothing; `defaultFinding(L, A, R, P)` when the licence states the contrary |

"The contrary" is a prohibition where the same graph also says the action is granted by
default, and a permission everywhere else: the law either keeps an exception open that a
licence may not close, or keeps a protection in place that a licence may not give away.
`grantedBySomeRule/1` is that lookup.

`holds/3` is what holds of a licence, its own statements plus what a rule supplied, and
every conflict rule reads it, so a derived statement takes part exactly as a stated one
does. `#show` adds `defaultStatement/4` and `defaultFinding/4`, and `app/conflicts.py`
turns them into an additive `defaults` array and into `origin_1`, `origin_2`, `rule_1`
and `rule_2` on each conflict. Both are left out when no rule fired, so a deployment
whose graph carries no rule gets the answer it has always got.

`&getDependencyGraph` follows `dalicc:extendsGraph` one step, which is how a
jurisdiction graph holds its own rules and reads the core graph's axioms.
`app/programs/getdepgraph.lp` filters `t/3` to the four relations, because the closure
it publishes is about the relations and its shape is part of the contract.
`app/services/consistency.py` on the API side implements the same reading, and
`tests/unit/test_composer_reasoner.py` proves the two agree.

The last argument of `directConflict/7` says which of the four readings produced it, and
`app/conflicts.py` maps it onto the sentence the client reads. The permission-prohibition
case keeps the argument `"direct"` and the sentence it has always had.

A duty attached to a permission, a prohibition or another duty hangs off that rule's
node, not off the licence, so `&getLicense` -- whose subject is the licence -- cannot
see it. `&getLicenseDuties` fetches those, keeping the rule each one belongs to, which is
what stops "Distribute, with the duty Attribution" being flattened into "the licence
requires Attribution": the first is file-level reciprocity, the second covers the whole
work, and the share-alike rule turns on exactly that difference. The composer's expert
mode lets an author build every one of these shapes, so every one of them has a fact and
a reading here. [docs/SERVICES.md](../docs/SERVICES.md#what-the-reasoner-is-given-and-how-it-reads-it)
documents the encoding alongside the composer's own check, which draws the same
conclusions.

A contradiction is reported once per pair, whichever way round the two licences are
given, and `L1` may be `L2`: a licence that asserts both halves of a contradiction is in
conflict with itself, which is what the consistency check is there to find. Its reason
opens with "Derived conflict between two permissions." instead of the
permission-prohibition sentence; everything else about the answer is unchanged.

The dependency graph is a named graph in the triple store, by default
`https://dalicc.net/dependencygraph/dg_default`, holding 46 axioms over ODRL and DALICC
actions and one adopted default rule. `licensedata/dependencygraph/dg_default.ttl` is its source, and
[docs/DATA.md](../docs/DATA.md) describes the model.

`app/programs/query.lp` pulls the licence statements, the nested duties and the graph
through three external atoms, lifts the graph triples into `includedIn/3`, `implies/3`,
`sameAs/3` and `contradicts/3`, closes the first three transitively (a contradiction is
not transitive), collects what a licence requires into `required/2` and what it asserts
into `asserted/3`, and shows `directConflict/7` and `derivedConflict/10`. The SPARQL the
two licence atoms use is in `app/queries.py`, so a test can read it without starting a
solver.

A chain may cross from one relation into another, which is what `owl:sameAs` is for: a
second name for an act is that act, so a subsumption, an entailment or a contradiction
written about one name holds of every other name for the same thing. `includedIn/3`,
`implies/3` and `contradicts/3` each absorb a synonym on either side. One more rule,
`impliesIncluded/3`, carries an entailment into a subsumption: permitting an act that
entails a second act runs into a prohibition of anything that second act is a special
case of. It is kept out of `implies/3` because "permitting X collides with prohibiting
Z" is not "permitting X commits to Z", and feeding it back into the entailment closure
would carry it one step too far. These are the chains `app/services/composer.py` walks
inside its own two closures, so the form and the program draw the same conclusions from
one graph.

`app/programs/getdepgraph.lp` is the same machinery without licences: it loads the graph
and computes the transitive closure over `t/3`.

The `license/1` facts are the only caller-controlled part of the program, and they are
generated per request into a private temporary directory.

### External atoms

`app/plugins/plugins.py` runs inside the `hexlite` subprocess and registers four atoms.

| Atom | Input | Output | Query |
|---|---|---|---|
| `&getLicense[T]` | hex-encoded licence IRI | `(s, p, o)` | the deontic statements hanging on that licence and their `odrl:action` |
| `&getLicenseDuties[T]` | hex-encoded licence IRI | `(s, p, ra, da)` | the duties hanging on one of those statements: the rule's predicate and action, and the duty's action |
| `&getDependencyGraph[G]` | graph name (ignored: the configuration decides) | `(s, p, o)` | every triple of the configured dependency graph |
| `&concat[...]` | strings | string | a helper the shipped programs do not use |

## Routes

### `POST /reasoner/compatibility`

```json
{ "licenses": ["https://dalicc.net/licenselibrary/Apache-2.0",
               "https://dalicc.net/licenselibrary/GPL-3.0-only"] }
```

`licenses` must be absolute `http(s)` IRIs. Two optional fields:
`"normalize": true` (see [Response shape](#response-shape)) and
`"dependency_graph": "<IRI>"` (see [Choosing a dependency graph](#choosing-a-dependency-graph-per-request)).

A conflict answer (200):

```json
{
  "conflicting_statements": {
    "direct": {
      "0": {
        "statement_1": ["https://dalicc.net/licenselibrary/Apache-2.0",
                        "http://www.w3.org/ns/odrl/2/permission",
                        "https://dalicc.net/ns#ChangeLicense"],
        "statement_2": ["https://dalicc.net/licenselibrary/GPL-3.0-only",
                        "http://www.w3.org/ns/odrl/2/prohibition",
                        "https://dalicc.net/ns#ChangeLicense"],
        "reason": "Direct permission-prohibition conflict."
      }
    },
    "derived": {}
  }
}
```

A derived entry has the same shape with a longer reason, for example:

```
"reason": "Derived permission-prohibition conflict. (http://www.w3.org/ns/odrl/2/modify,http://www.w3.org/ns/odrl/2/includedIn,http://www.w3.org/ns/odrl/2/derive) is derived from the statements in the dependency graph."
```

The keys of `direct` and `derived` are stringified integers inside a JSON object, not an
array. That is part of the public contract; see
[docs/BACKWARD_COMPATIBILITY.md](../docs/BACKWARD_COMPATIBILITY.md).

No conflicts, also 200:

```json
{ "conflicting_statements": { "direct": {}, "derived": {} } }
```

Errors:

| Status | When |
|---|---|
| 422 | the body is not JSON, or `licenses` is not a list of valid absolute `http(s)` IRIs, or `dependency_graph` is outside the two allowed IRI spaces |
| 502 | `hexlite` exited non-zero, for instance because the triple store is unreachable; the detail carries the tail of the solver's stderr |
| 504 | the solve exceeded `REASONER_TIMEOUT_SECONDS` |
| 500 | anything unexpected, as JSON `{"detail": "Internal server error."}` |

### `GET /reasoner/dependency_graph`

The transitive closure of the dependency graph, as a list of triples. By default the terms
keep their surrounding quotes and the object of the last triple keeps a trailing `)`, which
is the shape clients have always received. `?normalize=true` or the header
`X-DALICC-Compat: 2` returns clean IRIs instead:

```json
[["http://www.w3.org/ns/odrl/2/modify",
  "http://www.w3.org/ns/odrl/2/includedIn",
  "http://www.w3.org/ns/odrl/2/derive"]]
```

`?graph=<IRI>` computes the closure of another graph, validated the same way as the request
body field.

The public dependency-graph endpoint is `GET /dependencygraph/list` on the API service,
which queries Virtuoso directly and is unaffected by this route.

### `GET /healthz`

```json
{"status": "ok",
 "service": "dalicc-reasoner",
 "hexlite": {"ok": true, "binary": "hexlite", "detail": "ok"},
 "sparql":  {"ok": true, "endpoint": "http://virtuoso-db:8890/sparql", "detail": "HTTP 200"}}
```

* `status` is `ok` when both probes pass, `degraded` otherwise.
* HTTP 200 as long as the solver works. An unreachable triple store is a soft dependency,
  so the container does not flap while Virtuoso starts.
* HTTP 503 only when `hexlite` is missing or broken. The container `HEALTHCHECK` uses this
  endpoint.

The solver probe runs `hexlite --help` once at startup and caches the result, so the route
stays cheap.

## Response shape

The no-conflict case returns `{"conflicting_statements": {"direct": {}, "derived": {}}}`
already, because `hexlite` prints an empty answer set rather than empty output. One branch
remains: the solver exits 0 and prints no answer set at all. By default that answers with
the JSON string `""`; `"normalize": true` in the body or `X-DALICC-Compat: 2` answers with
the empty object instead. The API service passes the reasoner's response through unchanged
either way.

## Configuration

Environment variables win over `reasoner.config`, an optional INI file with a `[DEFAULT]`
section that is read from the service directory (or from `DALICC_REASONER_CONFIG`). The
built-in defaults apply when neither supplies a value.

| Variable | Default | Meaning |
|---|---|---|
| `DALICC_SPARQL_ENDPOINT` | `http://virtuoso-db:8890/sparql` | the triple store the plugin queries |
| `DALICC_DEPENDENCY_GRAPH` | `https://dalicc.net/dependencygraph/dg_default` | the named graph of the axioms; a bare name such as `dg_default` is expanded with the `https://dalicc.net/dependencygraph/` prefix |
| `DALICC_REASONER_RESTRICT_GRAPHS` | `false` | restrict the licence lookup with `FROM` clauses. Off by default: the plugin queries the store's default-graph union, which is what makes composed licences visible. The API service sets the two graph variables below and the compose file shares one `.env` with this container, so the restriction must never follow from their presence alone |
| `DALICC_LICENSE_LIBRARY_GRAPH` | empty | first `FROM` graph, used only with the flag above |
| `DALICC_CUSTOM_LICENSES_GRAPH` | empty | second `FROM` graph, used only with the flag above |
| `REASONER_TIMEOUT_SECONDS` (alias `DALICC_REASONER_TIMEOUT_SECONDS`) | `60` | wall-clock budget for one solve; exceeding it is a 504 |
| `DALICC_SPARQL_TIMEOUT_SECONDS` | `30` | socket timeout of the plugin's SPARQL calls |
| `DALICC_HEALTH_TIMEOUT_SECONDS` | `3` | timeout of the `/healthz` SPARQL probe |
| `DALICC_LOG_LEVEL` | `INFO` | root log level |
| `DALICC_REASONER_CONFIG` | unset | explicit path to the INI fallback file |
| `REASONER_HEXLITE_BIN` | `hexlite` | the solver executable to invoke |
| `GUNICORN_WORKERS` | `2` | worker processes |
| `PORT` | `80` | bind port |

## Running

In the stack, this is the `reasoner` service of `docker-compose.yml`, container
`dalicc-reasoner`, published on `127.0.0.1:8190` and reached by the API service as
`http://dalicc-reasoner:80` (`DALICC_REASONER_URL`):

```bash
docker compose up -d reasoner
curl -s localhost:8190/healthz
```

On its own:

```bash
docker build -t dalicc-reasoner:dev reasoner/
docker run --rm -p 127.0.0.1:8190:80 \
  -e DALICC_SPARQL_ENDPOINT=http://virtuoso-db:8890/sparql \
  dalicc-reasoner:dev
```

The image is `python:3.12-slim`, runs as the non-root user `reasoner` (uid 10001) and serves
with `gunicorn` and `uvicorn_worker.UvicornWorker`. `docker-entrypoint.sh` derives the
gunicorn worker timeout from `REASONER_TIMEOUT_SECONDS + 30`, so a slow solve is answered
with the service's own 504 instead of being killed first.

Without a container, from `reasoner/`:

```bash
pip install -r requirements.txt
pip install --no-deps -r requirements-solver.txt
uvicorn app.main:app --port 8190
```

### The solver dependency

`hexlite` is installed separately, with `--no-deps`, because its own metadata pins
`clingo==5.5.0.post3` (no wheels for CPython 3.12 or linux/arm64) and `jpype1==1.2.1`, a
Java bridge this service never uses. It runs unmodified against the `clingo` and `ply`
versions pinned in `requirements.txt`:

* `requirements.txt`: FastAPI, gunicorn, SPARQLWrapper, `clingo==5.8.2`, `ply==3.11`;
* `requirements-solver.txt`: `hexlite==1.4.1`, installed with `pip install --no-deps`;
* `requirements-dev.txt`: the above plus pytest, httpx and ruff.

`clingo==5.8.2` ships `manylinux_2_28` wheels for x86_64 and aarch64 on CPython 3.12, which
Debian bookworm accepts. Do not relax the pin below 5.8: the 5.6 and 5.7 lines have no
CPython 3.12 wheel for arm64. The Dockerfile verifies the combination by importing `clingo`
and solving a one-line program at build time.

## Tests

The service has its own suite and its own `pytest.ini` (`pythonpath = .`,
`testpaths = tests`), so it runs from the service directory, not from the repository root:

```bash
pip install -r reasoner/requirements-dev.txt
cd reasoner && python -m pytest
```

Nine test modules cover the answer-set parser, the conflict response shape, IRI validation and
hex encoding, configuration precedence, solver invocation and error mapping, the
per-request dependency graph, the HTTP surface, and what the program concludes about each
shape a licence can state. `tests/test_integration_solver.py` runs the real solver against
an in-process stub SPARQL endpoint and skips itself when `hexlite` is not installed;
`tests/test_statement_structures.py` runs `query.lp` under plain `clingo` with the
external-atom rules dropped and the facts they produce given directly, and skips when
`clingo` is missing; everything else stubs the subprocess. It also covers the chains
that cross from one relation of the graph into another, one test per rule.

Lint: `ruff check reasoner/` uses `reasoner/ruff.toml`, because the repository root
configuration excludes this directory.

## Choosing a dependency graph per request

`DALICC_DEPENDENCY_GRAPH` says which named graph `&getDependencyGraph` dumps. A caller can
override it for one run:

* `POST /reasoner/compatibility` accepts `"dependency_graph": "<IRI>"` in the body;
* `GET /reasoner/dependency_graph?graph=<IRI>` computes the closure of another graph.

The IRI has to be absolute and start with `https://dalicc.net/dependencygraph/` or
`https://dalicc.net/users/` (`app.iri.DEPENDENCY_GRAPH_PREFIXES`). Anything else is a 422
and the solver is never started: the value ends up in a SPARQL `FROM` clause inside the
plugin, so an allow-list is the only safe shape. The API service decides who may choose a
graph; this service decides what counts as a usable graph IRI, because it is reachable on
its own.

The plugin runs in the `hexlite` subprocess and builds its own settings there, so
`solver.dependency_graph_override` simply sets `DALICC_DEPENDENCY_GRAPH` in the environment
of that one subprocess. Nothing in the service process is mutated and two concurrent
requests cannot see each other's choice. Omitting the field uses the configured graph.

## Security

Every licence identifier reaches this service from a public endpoint, is written into an
ASP source file and is interpolated into a SPARQL query. Both are textual languages, so
both are closed by construction:

* **ASP injection.** `app/iri.py` accepts only absolute `http(s)` IRIs of at most 512
  characters, with no quotes, whitespace, backslashes, parentheses, angle brackets, braces,
  pipes, carets, backticks or control characters, and no `.` followed by whitespace. The
  validated IRI is then hex encoded before it is written into `license("...").`, so the
  logic program only ever contains `[0-9a-f]`. The plugin decodes the token and validates
  it again.
* **SPARQL injection.** The decoded IRI is wrapped with `sparql_iri_ref()`, which
  percent-encodes every character SPARQL forbids inside an `IRIREF`. The endpoint and the
  named graphs come from configuration, never from the request.

Also: a private temporary directory per request, a wall-clock solver timeout, captured and
logged stderr, a non-root container user, and a JSON error handler so tracebacks never
reach clients.

## Known limitations

* Asset types are not read at all: the program knows nothing about `odrl:target`, and
  `app.services.mixer` computes asset conflicts itself.
* Only the first answer set is used. The program is stratified, so there is always
  exactly one; a warning is logged if that ever changes. The one negation in it,
  `not compliantRelicensing(L)` in the share-alike rule, is stratified: nothing below it
  derives `licenseDuty/4`.
* Every solve is a cold `hexlite` process start of about a second plus one SPARQL
  round trip per licence. There is no caching.
* The provenance sentence of a derived conflict is inverted: `R = "derived"` renders "is
  given in the dependency graph." and `R = "dependencygraph"` renders "is derived from the
  statements in the dependency graph.". Clients match on these strings, so the wording is
  kept as it is.
* The transitive-closure rules at the top of `query.lp` are commented out. Only the
  `includedIn`, `implies` and `sameAs` closures further down are active.
* A conflict found through `impliesIncluded/3` is reported as an `implies` one, because
  that is the relation the permission side of the chain starts from and the answer
  format names a single relation.
