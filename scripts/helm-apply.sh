#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Helm template + kubectl apply — the one-liner we kept typing by hand.
#
# Usage:
#   ./scripts/helm-apply.sh <release> [values-file]
#
#   release    : one of the known shorthand releases below, or a bare
#                <release-name> <chart-dir> pair (pass 3 args).
#   values-file: relative to the chart dir (default: values-dev.yaml).
#
# Shorthand releases:
#   platform  → aviary-platform / values-dev.yaml
#   default   → aviary-env-default / charts/aviary-environment / values-dev.yaml
#   custom    → aviary-env-custom  / charts/aviary-environment / values-custom.yaml
#
# Raw form:
#   ./scripts/helm-apply.sh aviary-env-foo aviary-environment values-foo.yaml
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
cd "$PROJECT_DIR"

HELM_IMAGE="alpine/helm:3.14.4"

if [ $# -lt 1 ]; then
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

case "$1" in
  platform)  RELEASE="aviary-platform";    CHART="aviary-platform";    VALUES="${2:-values-dev.yaml}" ;;
  default)   RELEASE="aviary-env-default"; CHART="aviary-environment"; VALUES="${2:-values-dev.yaml}" ;;
  custom)    RELEASE="aviary-env-custom";  CHART="aviary-environment"; VALUES="${2:-values-custom.yaml}" ;;
  *)
    if [ $# -lt 2 ]; then
      echo "Unknown shorthand '$1'. Either use platform|default|custom, or pass <release> <chart> [values]."
      exit 1
    fi
    RELEASE="$1"
    CHART="$2"
    VALUES="${3:-values-dev.yaml}"
    ;;
esac

K8S_GATEWAY_IP="$(k8s_gateway_ip)"
echo "Rendering $RELEASE (chart=$CHART values=$VALUES gateway=$K8S_GATEWAY_IP)..."

docker run --rm -v "$PROJECT_DIR/charts:/charts:ro" "$HELM_IMAGE" template \
  "$RELEASE" "/charts/$CHART" -f "/charts/$CHART/$VALUES" \
  --set hostGatewayIP="$K8S_GATEWAY_IP" \
  | docker compose exec -T k8s kubectl apply -f -

echo "✓ $RELEASE applied."
