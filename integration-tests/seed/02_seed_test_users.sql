-- Test user grants for cross-service access.
-- Service-specific users (admin, regular) are created by each service's
-- startup seed script using DEFAULT_*_EMAIL / INITIAL_ADMIN_EMAIL env vars.
-- This script only ensures the service accounts can connect to their DBs.

-- Allow service_test to connect to ticket-manager DB for inter-service calls
GRANT CONNECT ON DATABASE df_ticket_manager_test TO service_test;
