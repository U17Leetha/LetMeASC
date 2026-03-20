#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="${repo_dir}/.venv"
bin_dir="${HOME}/.local/bin"
launcher_path="${bin_dir}/letmeasc"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_venv() {
  if [[ -d "${venv_dir}" ]]; then
    return
  fi

  echo "Creating virtual environment at ${venv_dir}"
  python3 -m venv "${venv_dir}"
}

install_python_package() {
  echo "Installing LetMeASC and Python dependencies"
  "${venv_dir}/bin/python" -m pip install --upgrade pip
  "${venv_dir}/bin/python" -m pip install -e "${repo_dir}"
}

install_launcher() {
  mkdir -p "${bin_dir}"
  cat > "${launcher_path}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${venv_dir}/bin/python" -m letmeasc.cli "\$@"
EOF
  chmod +x "${launcher_path}"
}

check_path() {
  case ":${PATH}:" in
    *":${bin_dir}:"*)
      ;;
    *)
      echo ""
      echo "Add ${bin_dir} to your PATH to run 'letmeasc' directly."
      echo 'For zsh: echo '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> ~/.zshrc'
      echo 'Then reload: source ~/.zshrc'
      ;;
  esac
}

require_command python3
ensure_venv
install_python_package
install_launcher

echo ""
echo "Installed launcher: ${launcher_path}"
echo "Repo environment: ${venv_dir}"
echo "Try: letmeasc --help"

check_path
