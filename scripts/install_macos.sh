#!/usr/bin/env bash
set -euo pipefail

source_app="${1:-}"
if [[ -z "${source_app}" || ! -d "${source_app}" ]]; then
  echo "Не найдена сборка .app. Сначала выполните make build." >&2
  exit 1
fi

python_bin="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.venv/bin/python"
install_dir="$(${python_bin} -c 'from pathlib import Path; print(Path.home() / "Applications")')"
target_app="${install_dir}/OIF-Foundations.app"

if pgrep -f "${target_app}/Contents/MacOS/OIF-Foundations" >/dev/null 2>&1; then
  echo "Закройте OIF-Foundations и повторите make install." >&2
  exit 1
fi

mkdir -p "${install_dir}"
ditto "${source_app}" "${target_app}"
touch "${target_app}"

echo "Установлено: ${target_app}"
echo "Запуск: make open или через Finder → Applications."
