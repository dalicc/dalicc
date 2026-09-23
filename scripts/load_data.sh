#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2021-2026 DALICC - Verein zur Foerderung der Rechtssicherheit in der Datenbewirtschaftung (ZVR 1249185710)
#
# load_data.sh -- load the DALICC RDF data into the Virtuoso container.
#
# Loads four named graphs from this repository:
#
#   licensedata/licenselibrary/licenselibrary.ttl -> https://dalicc.net/licenselibrary/
#   licensedata/dependencygraph/dg_default.ttl    -> https://dalicc.net/dependencygraph/dg_default
#   licensedata/vocabulary/dalicc-ns.ttl          -> https://dalicc.net/ns
#   (optional) a custom-licenses N-Triples file   -> https://dalicc.net/customlicenses/
#
# The target graph of every file is read from its sibling `<file>.graph`, which is the
# convention Virtuoso's bulk loader (`ld_dir`) uses. Never edit a .ttl without checking
# its .graph file.
#
# The script is idempotent: it clears the loader work list before every run, so calling
# it twice does not double-load. It does NOT clear the target graphs unless you pass
# --clear -- Virtuoso's bulk loader APPENDS, which is how stale pre-2023 license
# identifiers survived in production for years (see docs/DATA.md).
#
# --clear empties only the graphs this repository ships: the library, the vocabulary, the
# core dependency graph and the seven jurisdiction dependency graphs. It never empties
# <https://dalicc.net/customlicenses/>. That graph holds the licenses people compose on
# the running instance, it exists nowhere in this repository, and clearing it destroys
# user data that only a backup can bring back. Emptying it takes the separate
# --clear-custom, which is refused unless --custom-licenses names the file that refills
# it.
#
# Before anything is cleared the script prints the graphs it is about to clear and the
# current triple count of the custom-licenses graph, and it refuses to run if that graph
# would be cleared without --clear-custom.
#
# Usage:
#   scripts/load_data.sh [options]
#
# Options:
#   --container NAME        Virtuoso container name           (default: virtuoso-db)
#   --password PW           Virtuoso dba password             (default: $VIRTUOSO_DBA_PASSWORD, else "dba")
#   --custom-licenses PATH  extra .nt/.ttl file of user-composed licenses to load
#                           (produce it with scripts/restore_custom_licenses.py)
#   --data-dir PATH         Virtuoso's data directory inside the container (default: /data)
#   --dump-dir NAME         staging directory under --data-dir               (default: ttl_dump)
#   --ld-dir PATH           the staging directory as ld_dir() must name it
#                           (default: ./<dump-dir>, relative to the server's cwd)
#   --clear                 SPARQL CLEAR GRAPH, before loading, each graph this
#                           repository ships: the library, the vocabulary, the core
#                           dependency graph and the jurisdiction dependency graphs.
#                           Never the custom-licenses graph.
#   --clear-custom          also SPARQL CLEAR GRAPH <https://dalicc.net/customlicenses/>,
#                           the composed licenses of the running instance. Only together
#                           with --custom-licenses, and only when that file is meant to
#                           replace them.
#   --skip-index            do not (re)build the full-text index
#   --dry-run               print what would happen, touch nothing (needs no docker)
#   -h, --help              this text
#
# Environment:
#   VIRTUOSO_DBA_PASSWORD   dba password; the same variable docker-compose.yml uses.
#
# Examples:
#   VIRTUOSO_DBA_PASSWORD=s3cret scripts/load_data.sh --clear
#   scripts/load_data.sh --custom-licenses build/customlicenses.nt
#   scripts/load_data.sh --clear --custom-licenses dump.nt --clear-custom   # full restore
#
# Requirements: docker, and a running Virtuoso container (docker compose up -d db);
# --dry-run needs neither.
# In the tenforce/virtuoso image /data is a SYMLINK to the server's working directory
# (/usr/local/virtuoso-opensource/var/lib/virtuoso/db), and virtuoso.ini sets
# DirsAllowed = "." plus the vad share. Virtuoso matches DirsAllowed against the path as
# written, without resolving symlinks, so ld_dir('/data/ttl_dump', ...) is REFUSED with
# "FA003: Access ... is denied due to access control in ini file" while ld_dir('./ttl_dump',
# ...) is accepted. Files are therefore copied to <data-dir>/<dump-dir> but handed to
# ld_dir() under --ld-dir (default ./<dump-dir>).

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly DATA_DIR_HOST="${REPO_ROOT}/licensedata"

CONTAINER="virtuoso-db"
PASSWORD=""
CUSTOM_LICENSES=""
CONTAINER_DATA_DIR="/data"
DUMP_DIR="ttl_dump"
LD_DIR=""
CLEAR=0
CLEAR_CUSTOM=0
SKIP_INDEX=0
DRY_RUN=0

readonly GRAPH_LIBRARY="https://dalicc.net/licenselibrary/"
readonly GRAPH_DEPENDENCY="https://dalicc.net/dependencygraph/dg_default"
readonly GRAPH_VOCABULARY="https://dalicc.net/ns"
readonly GRAPH_CUSTOM="https://dalicc.net/customlicenses/"

log()  { printf '[load_data] %s\n' "$*" >&2; }
warn() { printf '[load_data] WARNING: %s\n' "$*" >&2; }
die()  { printf '[load_data] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    # Print the leading comment block (everything between the shebang and the first
    # non-comment line) as the help text.
    awk 'NR==1 { next } /^#/ { sub(/^#[ ]?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)       CONTAINER="${2:?--container needs a value}"; shift 2 ;;
        --password)        PASSWORD="${2:?--password needs a value}"; shift 2 ;;
        --custom-licenses) CUSTOM_LICENSES="${2:?--custom-licenses needs a value}"; shift 2 ;;
        --data-dir)        CONTAINER_DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
        --dump-dir)        DUMP_DIR="${2:?--dump-dir needs a value}"; shift 2 ;;
        --ld-dir)          LD_DIR="${2:?--ld-dir needs a value}"; shift 2 ;;
        --clear)           CLEAR=1; shift ;;
        --clear-custom)    CLEAR_CUSTOM=1; shift ;;
        --skip-index)      SKIP_INDEX=1; shift ;;
        --dry-run)         DRY_RUN=1; shift ;;
        -h|--help)         usage; exit 0 ;;
        *)                 die "unknown option '$1' (try --help)" ;;
    esac
done

# --- password ---------------------------------------------------------------------
# Never hardcode dba/dba. The password is passed to the container through the
# environment (docker exec -e) so that it does not appear in the host's process list
# or shell history. It is still visible in the container's own process list for the
# lifetime of the isql call, which is unavoidable with isql-v.
if [[ -z "${PASSWORD}" ]]; then
    PASSWORD="${VIRTUOSO_DBA_PASSWORD:-}"
fi
if [[ -z "${PASSWORD}" ]]; then
    PASSWORD="dba"
    warn "no --password and no VIRTUOSO_DBA_PASSWORD; falling back to the image default 'dba'."
    warn "Set VIRTUOSO_DBA_PASSWORD in your .env and rebuild before exposing this instance."
fi

# --- inputs -----------------------------------------------------------------------
declare -a FILES=()        # host paths of the payload files
declare -a GRAPHS=()       # every target graph IRI, for the triple counts at the end
declare -a REPO_GRAPHS=()  # of those, the ones this repository ships -- what --clear clears

add_pair() {
    # add_pair <host .ttl/.nt path> <expected graph IRI>
    local path="$1" expected="$2" graph_file="$1.graph" actual
    [[ -f "${path}" ]] || die "missing data file: ${path}"
    [[ -f "${graph_file}" ]] || die "missing graph file: ${graph_file}"
    actual="$(tr -d '[:space:]' < "${graph_file}")"
    [[ "${actual}" == "${expected}" ]] \
        || die "${graph_file} names <${actual}> but <${expected}> was expected"
    FILES+=("${path}" "${graph_file}")
    GRAPHS+=("${expected}")
    REPO_GRAPHS+=("${expected}")
}

add_pair "${DATA_DIR_HOST}/licenselibrary/licenselibrary.ttl"  "${GRAPH_LIBRARY}"
add_pair "${DATA_DIR_HOST}/dependencygraph/dg_default.ttl"     "${GRAPH_DEPENDENCY}"
add_pair "${DATA_DIR_HOST}/vocabulary/dalicc-ns.ttl"           "${GRAPH_VOCABULARY}"

# The jurisdiction graphs. Each holds the default rules proposed for one market and is
# read together with the core graph, which it names with dalicc:extendsGraph. None of
# them is the default for any check: a reader chooses one deliberately.
for jurisdiction in eu us cn gb jp in br; do
    add_pair "${DATA_DIR_HOST}/dependencygraph/dg_${jurisdiction}.ttl" \
             "https://dalicc.net/dependencygraph/dg_${jurisdiction}"
done

CUSTOM_GRAPH_FILE=""
CUSTOM_TARGET=""
if [[ -n "${CUSTOM_LICENSES}" ]]; then
    [[ -f "${CUSTOM_LICENSES}" ]] || die "missing custom-licenses file: ${CUSTOM_LICENSES}"
    CUSTOM_GRAPH_FILE="${CUSTOM_LICENSES}.graph"
    if [[ ! -f "${CUSTOM_GRAPH_FILE}" ]]; then
        # scripts/restore_custom_licenses.py writes the .graph file for you; if the caller
        # supplied a bare dump, stage a temporary .graph next to it instead of guessing later.
        CUSTOM_GRAPH_FILE="$(mktemp -t dalicc-customlicenses.XXXXXX).graph"
        printf '%s\n' "${GRAPH_CUSTOM}" > "${CUSTOM_GRAPH_FILE}"
        warn "${CUSTOM_LICENSES}.graph not found; loading into <${GRAPH_CUSTOM}>"
    else
        actual="$(tr -d '[:space:]' < "${CUSTOM_GRAPH_FILE}")"
        [[ "${actual}" == "${GRAPH_CUSTOM}" ]] \
            || warn "${CUSTOM_GRAPH_FILE} names <${actual}>, not the usual <${GRAPH_CUSTOM}>"
    fi
    CUSTOM_TARGET="$(tr -d '[:space:]' < "${CUSTOM_GRAPH_FILE}")"
    FILES+=("${CUSTOM_LICENSES}")
    # Deliberately not added to REPO_GRAPHS: --clear must not reach this graph.
    GRAPHS+=("${CUSTOM_TARGET}")
fi

if [[ "${CLEAR_CUSTOM}" -eq 1 && -z "${CUSTOM_LICENSES}" ]]; then
    die "--clear-custom without --custom-licenses would empty <${GRAPH_CUSTOM}> and load nothing back into it. Name the file that refills it, or drop --clear-custom."
fi

# --- container --------------------------------------------------------------------
if [[ "${DRY_RUN}" -eq 0 ]]; then
    command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
    docker inspect --format '{{.State.Running}}' "${CONTAINER}" 2>/dev/null | grep -q true \
        || die "container '${CONTAINER}' is not running (try: docker compose up -d db)"
fi

readonly STAGE="${CONTAINER_DATA_DIR}/${DUMP_DIR}"
# The path ld_dir() gets: relative by default, because DirsAllowed = "." and Virtuoso does
# not follow the /data symlink when it checks the access control list (see the header).
readonly LD_STAGE="${LD_DIR:-./${DUMP_DIR}}"

isql() {
    # Run one isql-v batch in the container. isql-v reports SQL errors on stdout and still
    # exits 0, so every caller has to inspect the output (see check_isql_output).
    docker exec -i -e DALICC_VPW="${PASSWORD}" "${CONTAINER}" \
        sh -c 'exec isql-v 1111 dba "$DALICC_VPW"'
}

check_isql_output() {
    # isql-v exits 0 even after "*** Error 42000: ... FA003: Access to ... is denied",
    # which is how a completely failed load used to report success.
    grep -q '^\*\*\* Error' "$1" && die "isql reported an error (see the output above)"
    return 0
}

graph_triples() {
    # The triple count of one graph, or the empty string when the store cannot be asked.
    # No `exit` in awk: closing the pipe early would SIGPIPE `docker exec` and, with
    # `set -o pipefail`, abort the script.
    printf 'SPARQL SELECT (COUNT(*) AS ?t) FROM <%s> WHERE { ?s ?p ?o };\n' "$1" \
        | isql | awk '/^[0-9]+$/ && !seen { print; seen = 1 }'
}

# --- what gets cleared ------------------------------------------------------------
# Built from REPO_GRAPHS, never from GRAPHS. GRAPHS carries the custom-licenses graph
# whenever --custom-licenses is given, and clearing every entry of GRAPHS is how
# `--clear --custom-licenses <dump>` emptied the composed licenses of a running instance
# before loading the dump back over them: anything composed since that dump was taken was
# gone, and nothing in this repository could restore it.
declare -a CLEAR_GRAPHS=()
if [[ "${CLEAR}" -eq 1 ]]; then
    CLEAR_GRAPHS+=("${REPO_GRAPHS[@]}")
fi
if [[ "${CLEAR_CUSTOM}" -eq 1 ]]; then
    CLEAR_GRAPHS+=("${CUSTOM_TARGET:-${GRAPH_CUSTOM}}")
fi

# Belt and braces: whatever a .graph sidecar said, that graph is only ever in the list on
# an explicit --clear-custom.
for graph in ${CLEAR_GRAPHS[@]+"${CLEAR_GRAPHS[@]}"}; do
    [[ "${graph}" == "${GRAPH_CUSTOM}" && "${CLEAR_CUSTOM}" -ne 1 ]] && die \
        "refusing to clear <${GRAPH_CUSTOM}>: it holds the licenses composed on this instance, it is in no file of this repository, and only a backup can bring it back. Pass --clear-custom together with --custom-licenses if that file really is meant to replace them."
done

# Say it before doing it. A reader who sees the custom graph in this list, or sees a
# triple count it did not expect, still has time to press Ctrl-C.
if [[ "${#CLEAR_GRAPHS[@]}" -eq 0 ]]; then
    log "no graph will be cleared: the loader appends into the existing graphs"
else
    log "graphs that will be CLEARED before loading (${#CLEAR_GRAPHS[@]}):"
    printf '[load_data]     <%s>\n' "${CLEAR_GRAPHS[@]}" >&2
fi
if [[ "${DRY_RUN}" -eq 1 ]]; then
    CUSTOM_COUNT="not read (dry run)"
else
    CUSTOM_COUNT="$(graph_triples "${GRAPH_CUSTOM}")"
    CUSTOM_COUNT="${CUSTOM_COUNT:-0} triple(s)"
fi
if [[ "${CLEAR_CUSTOM}" -eq 1 ]]; then
    log "custom licenses <${GRAPH_CUSTOM}>: ${CUSTOM_COUNT}, CLEARED and replaced by ${CUSTOM_LICENSES}"
else
    log "custom licenses <${GRAPH_CUSTOM}>: ${CUSTOM_COUNT}, kept"
fi

# --- build the isql script --------------------------------------------------------
SQL_FILE="$(mktemp -t dalicc-load-sql.XXXXXX)"
trap 'rm -f "${SQL_FILE}"' EXIT

{
    echo "-- generated by scripts/load_data.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    for graph in ${CLEAR_GRAPHS[@]+"${CLEAR_GRAPHS[@]}"}; do
        echo "SPARQL CLEAR GRAPH <${graph}>;"
    done
    # Make ld_dir idempotent: without this, files already in the work list are skipped
    # on a second run and a --clear would leave the graphs empty.
    echo "DELETE FROM DB.DBA.load_list WHERE ll_file LIKE '%${DUMP_DIR}%';"
    echo "ld_dir('${LD_STAGE}', '*.ttl', NULL);"
    echo "ld_dir('${LD_STAGE}', '*.nt', NULL);"
    echo "rdf_loader_run();"
    echo "checkpoint;"
    # Surface loader failures instead of exiting 0 on a silently skipped file.
    echo "SELECT ll_file, ll_state, ll_error FROM DB.DBA.load_list WHERE ll_error IS NOT NULL;"
    echo "SELECT COUNT(*) AS loaded_files FROM DB.DBA.load_list WHERE ll_state = 2;"
    if [[ "${SKIP_INDEX}" -eq 0 ]]; then
        # Full-text index over the license library, as documented in the README. The
        # /licenselibrary/list and /web/search endpoints use bif:contains, which needs it.
        echo "DB.DBA.RDF_OBJ_FT_RULE_ADD('${GRAPH_LIBRARY}', null, 'licenses');"
        echo "DB.DBA.VT_INC_INDEX_DB_DBA_RDF_OBJ();"
        echo "checkpoint;"
    fi
} > "${SQL_FILE}"

# --- go ---------------------------------------------------------------------------
if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "dry run -- files that would be staged in ${CONTAINER}:${STAGE}"
    printf '  %s\n' "${FILES[@]}" >&2
    log "dry run -- isql script:"
    sed 's/^/  /' "${SQL_FILE}" >&2
    exit 0
fi

log "staging $(( ${#FILES[@]} )) file(s) in ${CONTAINER}:${STAGE}"
docker exec "${CONTAINER}" mkdir -p "${STAGE}"
# Remove anything a previous run left behind so a renamed file cannot be loaded twice.
docker exec "${CONTAINER}" sh -c "rm -f '${STAGE}'/*.ttl '${STAGE}'/*.nt '${STAGE}'/*.graph" || true

for path in "${FILES[@]}"; do
    docker cp "${path}" "${CONTAINER}:${STAGE}/$(basename "${path}")"
done
if [[ -n "${CUSTOM_LICENSES}" ]]; then
    docker cp "${CUSTOM_GRAPH_FILE}" \
        "${CONTAINER}:${STAGE}/$(basename "${CUSTOM_LICENSES}").graph"
fi

log "running isql-v in ${CONTAINER}"
ISQL_OUT="$(mktemp -t dalicc-load-out.XXXXXX)"
trap 'rm -f "${SQL_FILE}" "${ISQL_OUT}"' EXIT
isql < "${SQL_FILE}" | tee "${ISQL_OUT}"
check_isql_output "${ISQL_OUT}"

# --- verify -----------------------------------------------------------------------
# One labelled COUNT per graph, so the caller sees the numbers instead of an unlabelled
# column of integers, and an empty graph fails the run instead of passing silently.
log "triple counts:"
failed=0
for graph in "${GRAPHS[@]}"; do
    count="$(graph_triples "${graph}")"
    count="${count:-0}"
    log "  <${graph}>  ${count}"
    [[ "${count}" -gt 0 ]] || { warn "  ^ empty: nothing was loaded into this graph"; failed=1; }
done
[[ "${failed}" -eq 0 ]] || die "at least one target graph is empty after the load"

log "done."
