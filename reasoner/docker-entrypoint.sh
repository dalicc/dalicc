#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
# Start gunicorn with uvicorn workers.
#
# The gunicorn worker timeout is derived from the solver budget so that a slow
# hexlite run is answered with the service's own 504 instead of being killed by
# gunicorn first.
set -eu

TIMEOUT="${REASONER_TIMEOUT_SECONDS:-${DALICC_REASONER_TIMEOUT_SECONDS:-60}}"
WORKERS="${GUNICORN_WORKERS:-2}"
PORT="${PORT:-80}"
GUNICORN_TIMEOUT=$((TIMEOUT + 30))

# No --access-logfile: that line carries the caller's address and the full request
# target, which nothing here needs and nothing rotates. The error log stays.
exec gunicorn app.main:app \
    --worker-class uvicorn_worker.UvicornWorker \
    --workers "${WORKERS}" \
    --bind "0.0.0.0:${PORT}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --graceful-timeout 30 \
    --error-logfile - \
    --forwarded-allow-ips '*'
