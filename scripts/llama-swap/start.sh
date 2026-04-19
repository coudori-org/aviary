#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$script_dir/../.." && pwd)"
config="$script_dir/config.yaml"

if [ -f "$project_dir/.env" ]; then
  set -a
  source "$project_dir/.env"
  set +a
fi

export HOME=$(cd ~ && pwd)
exec llama-swap -config "$config" -listen ":9292"
