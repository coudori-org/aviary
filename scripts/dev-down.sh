#!/usr/bin/env bash
# Usage: ./scripts/dev-down.sh [-v|--volumes]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

DOWN_ARGS=()
for arg in "$@"; do
  case "$arg" in
    -v|--volumes) DOWN_ARGS+=("-v") ;;
  esac
done

services_compose down "${DOWN_ARGS[@]}"
local_infra_compose --profile k3s down --remove-orphans "${DOWN_ARGS[@]}"
