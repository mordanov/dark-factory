-- Integration test database and user provisioning.
-- Executed by postgres docker-entrypoint-initdb.d on first boot.
-- This script runs as the postgres superuser.

-- user-input-manager
CREATE USER uim_test WITH PASSWORD 'uim_test_password';
CREATE DATABASE df_user_input_test OWNER uim_test;
GRANT ALL PRIVILEGES ON DATABASE df_user_input_test TO uim_test;

-- ticket-manager
CREATE USER tm_test WITH PASSWORD 'tm_test_password';
CREATE DATABASE df_ticket_manager_test OWNER tm_test;
GRANT ALL PRIVILEGES ON DATABASE df_ticket_manager_test TO tm_test;

-- orchestrator
CREATE USER orch_test WITH PASSWORD 'orch_test_password';
CREATE DATABASE df_orchestrator_test OWNER orch_test;
GRANT ALL PRIVILEGES ON DATABASE df_orchestrator_test TO orch_test;

-- context-distiller
CREATE USER distiller_test WITH PASSWORD 'distiller_test_password';
CREATE DATABASE df_distiller_test OWNER distiller_test;
GRANT ALL PRIVILEGES ON DATABASE df_distiller_test TO distiller_test;

-- service account for inter-service calls
CREATE USER service_test WITH PASSWORD 'service_password_test';
