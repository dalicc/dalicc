#!/usr/bin/env bash
# DEPRECATED: superseded by scripts/load_data.sh (see docs/DATA.md).
# Kept so that older documentation and shell history keep working.
set -euo pipefail
printf '%s\n' "licensedata/copy_ttls.sh is deprecated -- calling scripts/load_data.sh instead." >&2
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/load_data.sh" "$@"
