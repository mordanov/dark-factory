#!/bin/bash
# T013: Creates all four Dark Factory databases and their dedicated users.
# Runs once on first postgres container boot via /docker-entrypoint-initdb.d/.
# POSTGRES_USER / POSTGRES_PASSWORD come from Docker Compose environment.

set -euo pipefail

create_db_and_user() {
    local db="$1"
    local user="$2"
    local password="$3"

    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
        DO \$\$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$user') THEN
                CREATE ROLE "$user" WITH LOGIN PASSWORD '$password';
            END IF;
        END
        \$\$;

        SELECT 'CREATE DATABASE $db OWNER "$user"'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')
        \gexec

        GRANT ALL PRIVILEGES ON DATABASE "$db" TO "$user";
SQL
}

# user-input-manager
create_db_and_user "df_user_input" "${UIM_DB_USER}" "${UIM_DB_PASSWORD}"

# ticket-manager
create_db_and_user "df_ticket_manager" "${TM_DB_USER}" "${TM_DB_PASSWORD}"

# orchestrator
create_db_and_user "df_orchestrator" "${ORCH_DB_USER}" "${ORCH_DB_PASSWORD}"

# context-distiller
create_db_and_user "df_distiller" "${DISTILLER_DB_USER}" "${DISTILLER_DB_PASSWORD}"
