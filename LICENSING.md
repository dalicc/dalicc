# Licensing of this repository

Part of the [documentation index](README.md#documentation).

This file says who owns what in this repository and under which terms you may use it. It
is a description of the project's licensing, not legal advice. Questions that need a
binding answer go to the association's legal counsel.

Contact for anything on this page: <tassilo.pellegrini@ustp.at> or
<giray.havur@ustp.at>.

| Part of the repository | Terms |
|---|---|
| `licensedata/**`, the license library, the dependency graph and the vocabulary | CC-BY-4.0 |
| `reasoner/`, `scripts/`, `docs/` and everything else here | AGPL-3.0-only, or a commercial licence from the association |
| The code this repository held until 2024, at the tag `release-2023` | MIT, as it was published |

## 1. Source code: AGPL-3.0-only

All first-party source code in this repository is licensed under the GNU Affero General
Public License, version 3 only (SPDX: `AGPL-3.0-only`). The full text is in
[LICENSE](LICENSE). "Only" means that the "or (at your option) any later version" clause
is deliberately not granted.

Copyright notice:

> Copyright (C) 2021-2026 DALICC - Verein zur Förderung der Rechtssicherheit in der
> Datenbewirtschaftung (ZVR 1249185710) and contributors. Principal author: Giray Havur.

The association:

* Name: DALICC - Verein zur Förderung der Rechtssicherheit in der Datenbewirtschaftung
* Register: ZVR 1249185710, Austria
* Seat: Vienna
* Delivery address: Campus-Platz 1, 3100 St. Pölten, Austria
* E-mail: <tassilo.pellegrini@ustp.at> or <giray.havur@ustp.at>

The AGPL matters here because DALICC is normally run as a network service. Section 13 of
the AGPL requires that users who interact with a modified version over a network can
obtain the source of that modified version. Running a modified DALICC as a public or
internal web service therefore triggers the source offer.

### Commercial licence

The same code is also available under a commercial licence from the association, for
organisations that cannot or do not wish to comply with the AGPL, for example because
they want to keep modifications private while operating a network service. See
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

## 2. Data: `licensedata/**` is CC-BY-4.0

The license library (`licensedata/licenses/*.ttl` and the generated
`licensedata/licenselibrary/licenselibrary.ttl`), the dependency graph
(`licensedata/dependencygraph/dg_default.ttl`) and the DALICC vocabulary
(`licensedata/vocabulary/dalicc-ns.ttl`) are published under the Creative Commons
Attribution 4.0 International licence (SPDX: `CC-BY-4.0`). The legal code is in
[licensedata/LICENSE](licensedata/LICENSE).

Attribution line to use when you redistribute or build on the data:

```
DALICC License Library, DALICC association, https://dalicc.net, CC BY 4.0
```

This is not a new decision. The licence is already declared inside the data itself:

* every license record carries `cc:license dalicclib:CC-BY-4.0`;
* the vocabulary declares `dct:license <http://creativecommons.org/licenses/by/4.0/>` on
  the `https://dalicc.net/ns#` ontology resource, and repeats it in the file header.

`licensedata/LICENSE` records the same thing at the file-system level. The RDF statements
and the file are two views of one licence, and they must stay in agreement: if the data
licence is ever changed, all three places change together.

Note that the *content* of a license record describes a third-party licence (MIT,
Apache-2.0 and so on). CC-BY-4.0 covers the DALICC description of that licence, not the
licence it describes, and it grants no rights in the third-party licence text itself.

## 3. The 2023 release stays MIT

Until 2024 this repository held the first open-source release of DALICC under the MIT
licence. That code is still there, at the tag `release-2023`, under the MIT licence it
was published with. Nothing about it is withdrawn or relicensed: the new terms apply to
the new generation of the code, which is what `main` carries now.

## 4. What is not in this repository

The API service and the website are developed privately for the moment and are not part
of this repository. What is here is the data, the reasoner and the tooling that keeps
both checkable. The Python client for the API is in
[dalicc/python-sdk](https://github.com/dalicc/python-sdk), under Apache-2.0, because a
client that only talks to a public API has no reason to carry the service's terms with
it.

No trademark or branding rights in the DALICC name or the DALICC logo are granted by any
licence in this repository.

## 5. Third-party components

The reasoner builds on the hexlite solver, clingo, FastAPI and the other packages pinned
in `reasoner/requirements.txt` and `reasoner/requirements-solver.txt`; the tooling builds
on rdflib and PyYAML, pinned in `requirements.txt`. Each of them keeps its own licence.
[NOTICE](NOTICE) is the short form that travels with a distribution.

## 6. SPDX headers in source files

Every first-party source file carries two tags, an `SPDX-License-Identifier` and an
`SPDX-FileCopyrightText`, at the top of the file in the comment syntax of its language,
so that the licence of a file travels with the file. Data files carry their licence
inside the RDF instead, and `licensedata/LICENSE` records it at the file-system level.

## 7. Contributing

The association has to hold the exploitation rights in every contribution in order to
offer both the AGPL and the commercial licence, so every contributor signs a contributor
licence agreement before their first change is merged. Contributors keep their moral
rights, including the right to be named. Write to <giray.havur@ustp.at> before you start
on anything substantial, and you get the agreement and an answer on whether the change
fits.
