#!/bin/bash
# 01-set-passwords.sh — sets the authenticator role password from the environment.
# Runs in docker-entrypoint-initdb.d/ AFTER 00_dev_init.sql.
# Works for both local dev (.env) and Doppler-injected secrets.
# In K8s (CloudNativePG), this file is NOT used — the operator sets
# the password via its own bootstrap/initDB mechanism using a Secret.

set -e

if [ -z "${POSTGREST_PASSWORD}" ]; then
    echo "WARNING: POSTGREST_PASSWORD not set — using fallback 'postgrest_pass'" >&2
    POSTGREST_PASSWORD="postgrest_pass"
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
ALTER ROLE authenticator PASSWORD '${POSTGREST_PASSWORD}';
SQL

echo "authenticator password set from POSTGREST_PASSWORD env var."
