# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""The content hash of a licence record, a dependency graph or the vocabulary.

A version of a model is served as Turtle, JSON-LD, RDF/XML and N-Triples, and none of
those byte streams is stable: JSON-LD names its blank nodes at random, and a Turtle
writer is free to order and abbreviate as it likes.  What is stable is the set of
triples, so the hash is taken over a canonical N-Triples form of that set, called
``dalicc-c14n-1``:

1. every term is written in one fixed way (IRIs with the N-Triples escapes, literals
   with their lexical form as parsed, ``xsd:string`` dropped, language tags in lower
   case);
2. a blank node is named after the hash of its own subtree, which is possible because
   every blank node in the curated data is the object of exactly one triple and no
   chain of blank nodes loops back on itself; a graph where that is not so is refused
   (:class:`NotTreeShaped`) rather than hashed wrongly;
3. the lines are deduplicated, sorted by their UTF-8 bytes and each ends with LF.

``content_hash`` is ``"sha256:"`` plus the SHA-256 of that text.  A client that
downloads ``format=nt`` from the version 2 API receives exactly the canonical text, so
it can verify a version with nothing but SHA-256.

The first half of this module (up to the marker line) uses the standard library and
rdflib only, so ``scripts/publish_data.sh`` can copy it verbatim into the public data
checks.  The second half resolves "version ``n`` of X" to the RDF the service serves
and caches the hashes; every version 2 route and the release manifest read through it,
so they cannot disagree.
"""

from __future__ import annotations

import hashlib

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD

__all__ = [
    "ALGORITHM",
    "NotTreeShaped",
    "canonical_ntriples",
    "content_hash",
    "hash_text",
    "hash_turtle",
    "record_closure",
]

#: The name of the canonical form, carried beside every hash.
ALGORITHM = "dalicc-c14n-1"

#: Characters an IRI writes as ``\uXXXX``: the controls, the space and the seven the
#: N-Triples grammar does not allow inside ``<...>``.
_IRI_ESCAPE = frozenset('<>"{}|^`\\') | frozenset(chr(code) for code in range(0x21))


class NotTreeShaped(ValueError):
    """The graph has a blank node that is shared or part of a cycle."""

    def __init__(self, detail: str = "") -> None:
        """Say why, in the fixed wording the other implementations use."""
        message = "dalicc-c14n-1 needs tree-shaped blank nodes"
        super().__init__(f"{message}: {detail}" if detail else message)


def _iri(value: str) -> str:
    """One IRI in canonical form."""
    return "<" + "".join(
        f"\\u{ord(ch):04X}" if ch in _IRI_ESCAPE else ch for ch in value
    ) + ">"


def _literal(literal: Literal) -> str:
    """One literal in canonical form: lexical form as parsed, four escapes."""
    lexical = (
        str(literal)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    if literal.language:
        return '"' + lexical + '"@' + literal.language.lower()
    if literal.datatype is None or literal.datatype == XSD.string:
        return '"' + lexical + '"'
    return '"' + lexical + '"^^' + _iri(str(literal.datatype))


def _term(term, labels: dict) -> str:
    """Any term in canonical form; a blank node by its computed label."""
    if isinstance(term, BNode):
        return "_:" + labels[term]
    if isinstance(term, URIRef):
        return _iri(str(term))
    return _literal(term)


def _labels(graph: Graph) -> dict:
    """The label of every blank node, computed bottom-up from its subtree."""
    children: dict = {}
    referenced: dict = {}
    for subject, predicate, obj in graph:
        children.setdefault(subject, []).append((predicate, obj))
        if isinstance(obj, BNode):
            referenced[obj] = referenced.get(obj, 0) + 1
    shared = [node for node, count in referenced.items() if count > 1]
    if shared:
        raise NotTreeShaped(f"{len(shared)} blank node(s) are the object of several triples")

    labels: dict = {}

    def label(node, path: frozenset) -> str:
        if node in labels:
            return labels[node]
        if node in path:
            raise NotTreeShaped("a chain of blank nodes loops back on itself")
        inner = path | {node}
        lines = set()
        for predicate, obj in children.get(node, ()):
            if isinstance(obj, BNode):
                label(obj, inner)
            lines.add(_term(predicate, labels) + " " + _term(obj, labels))
        text = "".join(line + "\n" for line in sorted(lines, key=lambda x: x.encode("utf-8")))
        labels[node] = "b" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        return labels[node]

    for subject, _predicate, obj in graph:
        for node in (subject, obj):
            if isinstance(node, BNode):
                label(node, frozenset())
    return labels


def canonical_ntriples(graph: Graph) -> str:
    """The canonical N-Triples of ``graph`` (``dalicc-c14n-1``), as text."""
    labels = _labels(graph)
    lines = {
        f"{_term(s, labels)} {_term(p, labels)} {_term(o, labels)} ." for s, p, o in graph
    }
    return "".join(line + "\n" for line in sorted(lines, key=lambda x: x.encode("utf-8")))


def hash_text(canonical: str) -> str:
    """``"sha256:<hex>"`` of a canonical text that is already computed."""
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def content_hash(graph: Graph) -> str:
    """``"sha256:<64 hex>"`` of the canonical N-Triples of ``graph``."""
    return hash_text(canonical_ntriples(graph))


def hash_turtle(text: str) -> str:
    """Parse ``text`` as Turtle, then hash it."""
    graph = Graph()
    graph.parse(data=text, format="turtle")
    return content_hash(graph)


def record_closure(graph: Graph, subject: URIRef) -> Graph:
    """The concise bounded description of ``subject``.

    Every triple whose subject is ``subject``, plus, recursively, every triple whose
    subject is a blank node reached from it.  That is what a licence record is, in a
    file of its own and inside the shared named graph of the store alike.
    """
    out = Graph()
    for prefix, namespace in graph.namespaces():
        out.bind(prefix, namespace, override=True, replace=True)
    seen: set = set()
    pending = [subject]
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for predicate, obj in graph.predicate_objects(node):
            out.add((node, predicate, obj))
            if isinstance(obj, BNode) and obj not in seen:
                pending.append(obj)
    return out


