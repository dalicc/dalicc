# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
"""FastAPI application for the DALICC reasoner service.

The reasoner is an internal service: the public API (``POST
/compatibilitycheck/``) proxies to ``POST /reasoner/compatibility`` here.  It
owns the ``hexlite`` answer-set solver, the ASP programs in ``app/programs``
and the SPARQL plugin in ``app/plugins``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings
from .health import check_health, probe_hexlite
from .routers import reasoner

__all__ = ["LegacyJsonBodyMiddleware", "app", "create_app"]

logger = logging.getLogger("dalicc.reasoner")


def configure_logging(level: str) -> None:
    """Configure root logging once, honouring ``DALICC_LOG_LEVEL``."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


JSON_CONTENT_TYPE = b"application/json"
#: Content types that are rewritten to JSON -- see :class:`LegacyJsonBodyMiddleware`.
UNTYPED_CONTENT_TYPES = {None, "application/x-www-form-urlencoded"}
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class LegacyJsonBodyMiddleware:
    """Accept a JSON request body that arrives without a JSON ``Content-Type``.

    The API service calls this reasoner with
    ``requests.post(url, data=model.model_dump_json())``.  ``requests`` sets no
    ``Content-Type`` at all for a string body (and
    ``application/x-www-form-urlencoded`` for a dict).  FastAPI 0.103 -- the
    version this service used to run -- parsed such a body as JSON anyway;
    newer versions reject it with 422.  This middleware restores the old
    tolerance instead of forcing a lock-step upgrade of the API service.

    The reasoner exposes no form endpoints, so rewriting form content types is
    safe: a body that is not JSON still fails validation with 422.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the downstream ASGI *app*."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Rewrite an absent or form-encoded request content type to JSON."""
        if scope["type"] == "http" and scope.get("method") in BODY_METHODS:
            headers: list[tuple[bytes, bytes]] = list(scope.get("headers") or [])
            content_type: str | None = None
            for key, value in headers:
                if key.lower() == b"content-type":
                    content_type = value.decode("latin-1").split(";")[0].strip().lower()
                    break
            if content_type in UNTYPED_CONTENT_TYPES:
                rewritten = [(k, v) for k, v in headers if k.lower() != b"content-type"]
                rewritten.append((b"content-type", JSON_CONTENT_TYPE))
                scope = dict(scope, headers=rewritten)
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warm the solver probe so ``/healthz`` stays cheap."""
    settings = get_settings()
    configure_logging(settings.log_level)
    probe = probe_hexlite(refresh=True)
    logger.info(
        "reasoner starting: solver=%s sparql=%s dependency_graph=%s timeout=%ss",
        "ok" if probe["ok"] else f"BROKEN ({probe['detail']})",
        settings.sparql_endpoint,
        settings.dependency_graph,
        settings.timeout_seconds,
    )
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    application = FastAPI(
        title="DALICC Reasoner",
        version="2.0",
        description=(
            "Answer-set-programming reasoner for deontic conflict detection "
            "between ODRL licences."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(LegacyJsonBodyMiddleware)
    application.include_router(reasoner.router)

    @application.get("/healthz", tags=["ops"], summary="Health probe")
    def healthz() -> JSONResponse:
        """Report solver availability and SPARQL reachability."""
        payload, status_code = check_health()
        return JSONResponse(payload, status_code=status_code)

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a JSON body instead of a bare ``Internal Server Error``."""
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error."}, status_code=500)

    return application


app = create_app()


def openapi_schema() -> dict[str, Any]:  # pragma: no cover - convenience helper
    """Return the generated OpenAPI document."""
    return app.openapi()
