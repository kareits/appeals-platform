#!/bin/bash
# Idempotent database/role provisioning for the shared PostgreSQL cluster (ADR-004).
#
# Unlike /docker-entrypoint-initdb.d (which runs ONLY on first cluster initialization), this script
# runs on every startup and safely brings an EXISTING cluster up to date: it creates any missing
# service role or database, and RECONCILES the password of an existing role, without touching or
# dropping existing data (CR-BFF-HIGH-003, CR-BFF-RR-MEDIUM-002). It is the supported upgrade path
# for a long-lived pgdata volume, including ordinary credential rotation. Re-running is a no-op.
#
# Runs as the cluster superuser against the maintenance database. Role name and password are passed
# as psql variables and injected via format(%I, %L), so a special character in a generated secret
# cannot break the statement or inject SQL. CREATE DATABASE (which cannot run inside a transaction)
# is guarded by a SELECT-then-create shell gate on a fixed internal database name.
set -euo pipefail

PGHOST="${PGHOST:-postgres}"
PGUSER="${POSTGRES_USER:-postgres}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"

ensure_role() {
	# Create the role if missing, otherwise reconcile its password. psql interpolates the role name
	# as a quoted identifier (:"role") and the password as a quoted literal (:'pw'), so a special
	# character in a generated secret cannot break the statement or inject SQL. A DO block is not
	# used because psql variables are not substituted inside dollar-quoted blocks.
	local role="$1" password="$2"
	psql -v ON_ERROR_STOP=1 -h "$PGHOST" -U "$PGUSER" -d postgres \
		-v role="$role" -v pw="$password" <<-'SQL'
		SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') AS role_exists \gset
		\if :role_exists
		ALTER ROLE :"role" WITH LOGIN PASSWORD :'pw';
		\else
		CREATE ROLE :"role" LOGIN PASSWORD :'pw';
		\endif
	SQL
}

ensure_database() {
	# Create a database owned by the given role if it does not already exist (idempotent).
	# The database name is a fixed internal constant (not a secret), so a shell gate is safe here.
	local database="$1" owner="$2"
	local exists
	exists="$(psql -tAX -h "$PGHOST" -U "$PGUSER" -d postgres \
		-c "SELECT 1 FROM pg_database WHERE datname = '${database}'")"
	if [ "$exists" != "1" ]; then
		psql -v ON_ERROR_STOP=1 -h "$PGHOST" -U "$PGUSER" -d postgres \
			-c "CREATE DATABASE ${database} OWNER ${owner}"
	fi
}

ensure_service() {
	# Ensure a service's role (with reconciled password) and database both exist.
	local role="$1" password="$2" database="$3"
	ensure_role "$role" "$password"
	ensure_database "$database" "$role"
}

ensure_service demo "${DEMO_DB_PASSWORD:-demo}" demo_service
ensure_service flowable "${FLOWABLE_DB_PASSWORD:-flowable}" flowable
ensure_service iam "${IAM_DB_PASSWORD:-iam}" iam_service
ensure_service ticket "${TICKET_DB_PASSWORD:-ticket}" ticket_service
ensure_service bff "${BFF_DB_PASSWORD:-bff}" bff_service
ensure_service document "${DOCUMENT_DB_PASSWORD:-document}" document_service

echo "database provisioning complete"
