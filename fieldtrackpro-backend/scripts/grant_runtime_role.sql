-- ============================================================================
-- FieldTrack Pro - runtime role grants (idempotent; safe to re-run after EVERY migration run).
--
-- WHY: no migration grants rights to the runtime role, so tables created by newer
-- migrations are invisible to `fieldtrack_app` until this file is applied.
--
-- HOW (run by hand as the schema OWNER / migrating role, never as the app role):
--   psql "$MIGRATION_DATABASE_URL_FOR_PSQL" -v owner_role=<migrating_owner_role> -f scripts/grant_runtime_role.sql
--   (`owner_role` = the role that runs `alembic upgrade head` and therefore owns future tables;
--    default below is the current user.)
--
-- This script is NOT executed by the application, by alembic, or by any test.
-- ============================================================================

\if :{?owner_role}
\else
  SELECT current_user AS owner_role \gset
\endif

BEGIN;

-- 0. Runtime role must exist (created once by the DBA; password is NOT managed here).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fieldtrack_app') THEN
    RAISE EXCEPTION 'role fieldtrack_app does not exist - create it first (CREATE ROLE fieldtrack_app LOGIN PASSWORD ...)';
  END IF;
END $$;

-- 1. Schema + data access for everything that exists today.
GRANT USAGE ON SCHEMA public TO fieldtrack_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fieldtrack_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO fieldtrack_app;

-- 2. Audit immutability (FT-032): geo verification logs are append-only for the app.
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE geo_verification_logs FROM fieldtrack_app;
GRANT SELECT, INSERT ON TABLE geo_verification_logs TO fieldtrack_app;

-- 2b. Security audit trail (admin password resets, role changes, super-admin bootstrap) is append-only
--     for the app too: a compromised API process must not be able to erase or rewrite its own audit trail.
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE security_audit_logs FROM fieldtrack_app;
GRANT SELECT, INSERT ON TABLE security_audit_logs TO fieldtrack_app;

-- 3. Tables / sequences created LATER by the migrating owner role get the same rights automatically.
--    (The geo_verification_logs / security_audit_logs REVOKEs above still have to be re-applied by re-running this file if a
--    future migration recreates that table.)
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fieldtrack_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO fieldtrack_app;

-- 4. The app role must never be able to change the schema or the migration bookkeeping.
REVOKE CREATE ON SCHEMA public FROM fieldtrack_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE alembic_version FROM fieldtrack_app;

COMMIT;
