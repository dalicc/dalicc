# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The data checks of the public DALICC repository, and the modules they need.

This package is published at ``scripts/dalicc_check/`` in https://github.com/dalicc/dalicc
by ``scripts/publish_data.sh``.  In the service repository only this file and
``__main__.py`` live here; the three modules beside them in the public checkout are
copies of service modules, made when the data is published:

``vocab.py``
    the controlled vocabulary: the labels, the definitions and the classification of
    every term, read at import from ``licensedata/vocabulary/dalicc-ns.ttl``.  A copy
    of ``app/services/vocab.py``.
``consistency.py``
    the rule set behind ``POST /licenselibrary/consistencycheck`` on the API: a license
    that permits and prohibits the same action, a duty that can never be discharged, a
    share-alike condition beside a permission to relicense, and the same three closed
    under the dependency graph.  A copy of ``app/services/consistency.py``;
    ``scripts/review/consistency_sweep.py`` runs it over every record.
``c14n.py``
    the canonical form ``dalicc-c14n-1`` and the content hash, the first half of
    ``app/services/content_hash.py``.

They are copies on purpose: a second implementation of the rule set or of the hash
would answer differently from the API sooner or later, and then neither answer would
mean anything.  They depend on nothing but the standard library, rdflib and the data in
``licensedata/``, which is why they can live there at all.  The only edit made when
they are copied is the import line that names the service's package; the script that
copies them checks that no ``from app.`` import survives, and the data workflow runs the
checks on every push, so a copy that went wrong fails at once.

``python -m dalicc_check <record.ttl>`` (``__main__.py``) checks one record offline with
all of them together.
"""
