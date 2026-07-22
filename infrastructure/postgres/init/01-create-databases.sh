#!/bin/bash
# Create a separate database and user per service in the shared PostgreSQL cluster (ADR-004).
# Runs once, on first cluster initialization, via the postgres image init hook.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE USER demo WITH PASSWORD '${DEMO_DB_PASSWORD}';
	CREATE DATABASE demo_service OWNER demo;

	CREATE USER flowable WITH PASSWORD '${FLOWABLE_DB_PASSWORD}';
	CREATE DATABASE flowable OWNER flowable;

	CREATE USER iam WITH PASSWORD '${IAM_DB_PASSWORD}';
	CREATE DATABASE iam_service OWNER iam;
EOSQL
