#!/bin/bash
# Creates the two databases EcoCode needs (TECH.md section 2.2): `ecocode` (our
# authoritative schema) and `litellm` (owned/managed entirely by the litellm
# proxy — we never touch its schema). Runs once, only against a fresh
# postgres_data volume (docker-entrypoint-initdb.d convention).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER ecocode WITH PASSWORD '${POSTGRES_PASSWORD}';
    CREATE DATABASE ecocode OWNER ecocode;

    CREATE USER litellm WITH PASSWORD '${POSTGRES_PASSWORD}';
    CREATE DATABASE litellm OWNER litellm;
EOSQL
