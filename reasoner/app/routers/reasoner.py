# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""HTTP surface of the DALICC reasoner.

``POST /reasoner/compatibility``
    Deontic conflict detection for a set of licences.  Called by the public
    ``POST /compatibilitycheck/`` endpoint of the API service.
``GET /reasoner/dependency_graph``
    The transitive closure of the dependency-graph axioms, computed by
    ``getdepgraph.lp``.

Both accept an optional per-request dependency graph (``dependency_graph`` in the
compatibility body, ``?graph=`` on the closure endpoint).  It overrides
``DALICC_DEPENDENCY_GRAPH`` for that one solver run and has to be an absolute IRI in
one of the two DALICC graph spaces; the API service decides *who* may choose a graph,
this service decides *what* is a usable graph IRI at all.

Both endpoints validate their input, run ``hexlite`` in a per-request
temporary directory with a wall-clock timeout, and map solver problems onto
502 / 504 instead of an unhandled ``IndexError``.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..answersets import extract_answer_sets, parse_atoms
from ..conflicts import (
    build_conflict_response,
    build_dependency_graph_rows,
    empty_conflict_response,
)
from ..iri import IriValidationError, validate_dependency_graph_iri, validate_license_iri
from ..solver import SolverFailureError, SolverTimeoutError, run_compatibility, run_dependency_graph

__all__ = ["LicensesJSON", "router", "wants_normalized_shape"]

logger = logging.getLogger(__name__)

#: Opt-in header for the normalised (non-legacy) response shape.
COMPAT_HEADER = "X-DALICC-Compat"
COMPAT_NORMALISED = "2"

router = APIRouter(
    prefix="/reasoner",
    tags=["reasoner"],
    responses={404: {"description": "Not found"}},
)

CompatHeader = Annotated[str | None, Header(alias=COMPAT_HEADER)]


class LicensesJSON(BaseModel):
    """Request body of ``POST /reasoner/compatibility``."""

    model_config = ConfigDict(extra="ignore")

    licenses: list[Any] = Field(
        default_factory=list,
        description="Absolute http(s) licence IRIs, e.g. "
        "https://dalicc.net/licenselibrary/Apache-2.0",
    )
    normalize: bool | None = Field(
        default=None,
        description="Opt in to the normalised empty result "
        '{"conflicting_statements": {"direct": {}, "derived": {}}} '
        "instead of the legacy fall-through value.",
    )
    dependency_graph: str | None = Field(
        default=None,
        description="Named graph to reason with for this request, instead of "
        "DALICC_DEPENDENCY_GRAPH. Must be an absolute IRI under "
        "https://dalicc.net/dependencygraph/ or https://dalicc.net/users/.",
    )

    @field_validator("licenses")
    @classmethod
    def _validate_licenses(cls, value: list[Any]) -> list[str]:
        validated: list[str] = []
        for entry in value:
            try:
                validated.append(validate_license_iri(entry))
            except IriValidationError as exc:
                raise ValueError(str(exc)) from exc
        return validated

    @field_validator("dependency_graph")
    @classmethod
    def _validate_dependency_graph(cls, value: str | None) -> str | None:
        """Refuse a graph outside the two DALICC graph spaces with a 422.

        The value ends up in a SPARQL ``FROM`` clause inside the solver plugin, so it
        is validated here rather than trusted because the API service already checked
        it: this service is reachable on its own.
        """
        if value is None or not str(value).strip():
            return None
        try:
            return validate_dependency_graph_iri(str(value).strip())
        except IriValidationError as exc:
            raise ValueError(str(exc)) from exc


def wants_normalized_shape(body_flag: bool | None, compat_header: str | None) -> bool:
    """Return whether the caller opted in to the normalised response shape."""
    if body_flag:
        return True
    return bool(compat_header) and compat_header.strip() == COMPAT_NORMALISED


def _legacy_empty_response(normalized: bool) -> JSONResponse:
    """Reproduce the historical fall-through value for an empty solver result.

    The original implementation returned the raw (empty) stdout, which FastAPI
    serialised as the JSON string ``""``.  In practice this only happened when
    the solver failed -- which is now a 502 -- so this branch is reached only
    if ``hexlite`` succeeds while printing no answer set at all.
    """
    if normalized:
        return JSONResponse(empty_conflict_response())
    logger.warning("solver produced no answer set; returning the legacy empty value")
    return JSONResponse("")


def _solver_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SolverTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Reasoning timed out after {exc.timeout_seconds}s.",
        )
    if isinstance(exc, SolverFailureError):
        tail = exc.stderr_tail
        detail = f"Reasoner failed: {exc}."
        if tail:
            detail = f"{detail} Solver stderr: {tail}"
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    return HTTPException(  # pragma: no cover - defensive
        status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Reasoner failed: {exc}"
    )


@router.get(
    "/dependency_graph",
    summary="Transitive closure of the dependency graph",
    response_model=None,
)
def dependency_graph(
    normalize: bool = False,
    graph: str | None = None,
    x_dalicc_compat: CompatHeader = None,
) -> Response:
    """Return the dependency-graph triples after applying the closure rules.

    By default the historical string shape is preserved (terms keep their
    surrounding quotes).  ``?normalize=true`` or ``X-DALICC-Compat: 2`` returns
    clean, unquoted IRIs.  ``?graph=<IRI>`` computes the closure of another
    dependency graph, validated the same way as the request-body field.
    """
    normalized = wants_normalized_shape(normalize, x_dalicc_compat)
    chosen: str | None = None
    if graph and graph.strip():
        try:
            chosen = validate_dependency_graph_iri(graph.strip())
        except IriValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    try:
        result = run_dependency_graph(dependency_graph=chosen)
    except (SolverTimeoutError, SolverFailureError) as exc:
        raise _solver_http_error(exc) from exc

    if not extract_answer_sets(result.stdout):
        logger.warning("dependency graph solve produced no answer set")
        return JSONResponse([] if normalized else "")
    return JSONResponse(build_dependency_graph_rows(result.stdout, legacy=not normalized))


@router.post(
    "/compatibility",
    summary="Deontic conflict detection for a set of licences",
    response_model=None,
)
def compatibility(
    input_json: LicensesJSON,
    x_dalicc_compat: CompatHeader = None,
) -> Response:
    """Return the conflicting statements between the supplied licences.

    Request body: ``{"licenses": ["https://dalicc.net/licenselibrary/MIT", ...]}``,
    optionally with ``"dependency_graph": "<IRI>"`` to reason with a graph other
    than the configured one for this request.
    Response: ``{"conflicting_statements": {"direct": {...}, "derived": {...}}}``
    with stringified-integer keys.
    """
    normalized = wants_normalized_shape(input_json.normalize, x_dalicc_compat)
    licenses: list[str] = list(input_json.licenses)
    graph = input_json.dependency_graph
    logger.info(
        "compatibility check for %d licence(s)%s",
        len(licenses),
        f" with dependency graph {graph}" if graph else "",
    )

    try:
        result = run_compatibility(licenses, dependency_graph=graph)
    except (SolverTimeoutError, SolverFailureError) as exc:
        raise _solver_http_error(exc) from exc

    blocks = extract_answer_sets(result.stdout)
    if not blocks:
        return _legacy_empty_response(normalized)
    if len(blocks) > 1:
        logger.warning("solver returned %d answer sets; using the first", len(blocks))
    return JSONResponse(build_conflict_response(parse_atoms(blocks[0])))
