#!/usr/bin/env bash
# Where the Aktogay stand can be reached (printed by `make up` after the platform addresses).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
set -a; . "$ROOT/deploy/compose/.env"; set +a
H="${OPENEGIZ_PUBLIC_HOST:-localhost}"
cat <<TXT
Aktogay stand is up (free run x60 from 08:00, seed 42).

  Interface      http://$H:${AKT_WEB_PORT:-8000}         no login; menu: План, Линия 1/2, Очередь, Руда, Калибровка, Дерево, Текст
  Thing Models   http://$H:${AKT_MODELS_PORT:-8092}/tm/

Check the stand with: make akt-check   Calibration table: make akt-calib
TXT
