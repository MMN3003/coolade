#!/bin/bash
# Creates the two databases Coolade needs (TECH.md section 2.2): `coolade` (our
# authoritative schema) and `litellm` (owned/managed entirely by the litellm
# proxy — we never touch its schema). Runs once, only against a fresh
# postgres_data volume (docker-entrypoint-initdb.d convention).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER coolade WITH PASSWORD '${POSTGRES_PASSWORD}';
    CREATE DATABASE coolade OWNER coolade;

    CREATE USER litellm WITH PASSWORD '${POSTGRES_PASSWORD}';
    CREATE DATABASE litellm OWNER litellm;
EOSQL
