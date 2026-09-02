#!/usr/bin/env bash
# Yerel geliştirme sunucusu. Google/Stripe/OpenRouter anahtarı olmadan çalışır;
# .env varsa okunur. Veri dizini varsayılan olarak .dev-data/ altındadır.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:8000}"
export MEVZUAT_DATA_DIR="${MEVZUAT_DATA_DIR:-$PWD/.dev-data}"
export AUTH_SESSION_SECRET="${AUTH_SESSION_SECRET:-local-dev-session-secret-change-me-0123456789abcdef}"
mkdir -p "$MEVZUAT_DATA_DIR"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" -m uvicorn app:app --host 127.0.0.1 --port "${PORT:-8000}" "$@"
