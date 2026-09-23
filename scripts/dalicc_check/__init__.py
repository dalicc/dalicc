# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The two modules the data checks need out of the DALICC service.

``vocab.py`` is the controlled vocabulary: the labels, the definitions and the
classification of every term, read at import from
``licensedata/vocabulary/dalicc-ns.ttl``.  ``consistency.py`` is the rule set behind
``POST /licenselibrary/consistencycheck`` on the API: a license that permits and
prohibits the same action, a duty that can never be discharged, a share-alike condition
beside a permission to relicense, and the same three closed under the dependency graph.
``scripts/review/consistency_sweep.py`` runs it over every record.

Both files are copies of ``app/services/vocab.py`` and ``app/services/consistency.py``
in the service repository, and they are copies on purpose: a second implementation of
the rule set would answer differently from the API sooner or later, and then neither
answer would mean anything.  They depend on nothing but the standard library, rdflib and
the data in ``licensedata/``, which is why they can live here at all.

The only edit made when they are copied is the import line that names the service's
package.  The script that copies them checks that no ``from app.`` import survives, and
the data workflow runs the sweep on every push, so a copy that went wrong fails at once.
"""
