# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
# DALICC reasoner: FastAPI + the hexlite answer-set solver.
#
# Python 3.12 (the previous image was tiangolo/uvicorn-gunicorn:python3.7,
# EOL since 2023-06-27).  hexlite 1.4.1 runs unmodified on clingo 5.8.x, which
# is the first clingo line with wheels for cp312 on both amd64 and arm64.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# curl is only used by the container HEALTHCHECK below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-solver.txt ./
RUN pip install -r requirements.txt \
 && pip install --no-deps -r requirements-solver.txt \
 && python -c "import clingo; print('clingo', clingo.__version__)" \
 && printf 'smoke.\n' > /tmp/smoke.lp && hexlite /tmp/smoke.lp && rm /tmp/smoke.lp

COPY reasoner.config ./reasoner.config
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY app ./app

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin reasoner \
 && chown -R reasoner:reasoner /app
USER reasoner

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:80/healthz > /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
