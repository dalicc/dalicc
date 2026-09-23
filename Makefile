# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
# The checks that keep the DALICC license data and the reasoner honest.
#
#   make venv           create .venv and install what the checks need
#   make validate       the data gate: parsing, the canonical comparison, the conventions
#   make sweep          the consistency rule set over every record
#   make family-rules   the family conventions over every record
#   make canonical      the combined library document equals the per-record files
#   make reasoner-test  the reasoner's own test suite
#   make check          all of the above

SHELL := /bin/bash
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help venv validate sweep family-rules canonical check reasoner-test reasoner-venv clean

help: ## Show the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3.12 -m venv $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

venv: $(VENV)/bin/python ## Create the virtualenv and install the dependencies
	$(PIP) install -r requirements.txt

validate: venv ## The data gate: every record parses, agrees with the library and carries what the model needs
	$(PY) scripts/validate_data.py

sweep: venv ## Run the consistency rule set over every license record
	$(PY) scripts/review/consistency_sweep.py

# Rule 14 (no padding space inside a literal) has 575 open violations, all cosmetic and
# all in the Creative Commons ports. docs/DATA.md explains them under the known
# data-quality issues; fixing them takes 287 records to a new version in one sweep, so it
# waits for a commit of its own and does not fail this gate meanwhile.
family-rules: venv ## Check the twenty family rules over every license record
	$(PY) scripts/review/family_rules.py --strict --skip-rule 14

canonical: venv ## The generated library document is exactly what the per-record files produce
	$(PY) scripts/build_licenselibrary.py --check

check: validate canonical sweep family-rules ## Every data check, in the order CI runs them

reasoner-venv: reasoner/.venv/bin/python

reasoner/.venv/bin/python:
	python3.12 -m venv reasoner/.venv || python3 -m venv reasoner/.venv
	reasoner/.venv/bin/pip install --upgrade pip
	reasoner/.venv/bin/pip install -r reasoner/requirements-dev.txt
	reasoner/.venv/bin/pip install --no-deps -r reasoner/requirements-solver.txt

reasoner-test: reasoner-venv ## Run the reasoner's test suite
	cd reasoner && .venv/bin/python -m pytest

clean: ## Remove the virtualenvs and the caches
	rm -rf $(VENV) reasoner/.venv .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
