#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Run this with: source ./bootstrap.sh"
  exit 1
fi

set -euo pipefail

env_name="${1:-.venv}"

if command -v pythos >/dev/null 2>&1; then
  pythos "$env_name"
else
  if [[ ! -d "$env_name" ]]; then
    python3 -m venv "$env_name"
  fi
  # shellcheck disable=SC1090
  source "$env_name/bin/activate"
fi

python3 -m pip install --upgrade pip
python3 -m pip install -e .

echo "Environment ready: $VIRTUAL_ENV"
