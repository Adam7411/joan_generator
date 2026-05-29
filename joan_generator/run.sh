#!/bin/bash
# Production Version (Gunicorn)
# init:false — CMD uruchamiany przez legacy-services (nie jako PID 1).

echo " "
echo "🚀 STARTING JOAN 6 DASHBOARD GENERATOR (PRODUCTION)..."
echo "---------------------------------------------------"

# Token Supervisora: pliki s6 (baza HA) lub zmienne już w środowisku
load_s6_token() {
  local name="$1"
  local file="/run/s6/container_environment/${name}"
  if [ -n "${!name}" ]; then
    return 0
  fi
  if [ -f "$file" ]; then
    # shellcheck disable=SC2086
    export "${name}=$(tr -d '\0\n\r' < "$file")"
    echo "🔑 Loaded ${name} from ${file}"
    return 0
  fi
  return 1
}

load_s6_token SUPERVISOR_TOKEN || load_s6_token HASSIO_TOKEN || true

if [ -z "$SUPERVISOR_TOKEN" ] && [ -n "$HASSIO_TOKEN" ]; then
  export SUPERVISOR_TOKEN="$HASSIO_TOKEN"
fi

if [ -z "$SUPERVISOR_TOKEN" ]; then
  echo "⚠️ SUPERVISOR_TOKEN not found — wyczyść manual_token w konfiguracji addona i zrestartuj."
else
  echo "✅ SUPERVISOR_TOKEN available for Home Assistant API"
fi

echo "🔧 Fixing file formatting..."
dos2unix /app/run.py 2>/dev/null || true

echo "🦄 Starting Gunicorn WSGI Server..."
echo "---------------------------------------------------"
exec gunicorn -w 2 -b 0.0.0.0:5000 --chdir /app --access-logfile - --error-logfile - run:app
