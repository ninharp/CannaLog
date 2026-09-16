#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

# Data lives in /share so it survives reinstalls and stays reachable via Samba.
SHARE_DIR=/share/cannalog
mkdir -p "${SHARE_DIR}/database" "${SHARE_DIR}/uploads"

export CANNALOG_DATA_DIR=/data
export DATABASE_URL="sqlite:///${SHARE_DIR}/database/cannalog.db"
export UPLOAD_FOLDER="${SHARE_DIR}/uploads"
export CANNALOG_VERSION="$(bashio::addon.version)"

if bashio::config.has_value 'secret_key'; then
    SECRET_KEY="$(bashio::config 'secret_key')"
    export SECRET_KEY
fi
export ALLOW_REGISTRATION="$(bashio::config 'allow_registration')"
export SECURE_COOKIES="$(bashio::config 'secure_cookies')"
export MAX_UPLOAD_MB="$(bashio::config 'max_upload_mb')"

LOG_LEVEL=info
if bashio::config.true 'debug'; then
    LOG_LEVEL=debug
fi

cd /app
bashio::log.info "Checking database schema..."
python3 init_db.py

bashio::log.info "Starting CannaLog ${CANNALOG_VERSION}..."
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --log-level "${LOG_LEVEL}" \
    --access-logfile - \
    --error-logfile - \
    app:app
