-- FieldTrack Pro - one-time PostgreSQL bootstrap for a FRESH production database on the VPS.
--
-- Run as the postgres superuser, passing the two passwords as psql variables so they never appear in this file
-- or in shell history files you keep:
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 \
--        -v owner_pw="$(cat /root/.fieldtrack/owner_db_pw)" -v app_pw="$(cat /root/.fieldtrack/app_db_pw)" \
--        -f 01_roles_and_database.sql
--
-- Passwords must be alphanumeric (openssl rand -hex 24): they go into DATABASE_URL, where # @ / ? : % would break parsing.
--
-- Creates:  fieldtrack_owner  (owns the schema; used by alembic + bootstrap scripts)
--           fieldtrack_app    (runtime role; granted rights AFTER migrations by scripts/grant_runtime_role.sql)
--           fieldtrackpro_prod (database, UTF8) with the PostGIS extension (needs superuser, hence done here).
-- Refuses to run twice (so it can never reset a live database's passwords).

\set ON_ERROR_STOP on

SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'fieldtrackpro_prod') AS db_exists \gset
\if :db_exists
  \echo 'fieldtrackpro_prod already exists - refusing to continue (this script is for a FRESH install only).'
  DO $$ BEGIN RAISE EXCEPTION 'refusing: database fieldtrackpro_prod already exists'; END $$;
\endif

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fieldtrack_owner') AS owner_exists \gset
\if :owner_exists
  \echo 'role fieldtrack_owner already exists - refusing to continue.'
  DO $$ BEGIN RAISE EXCEPTION 'refusing: role fieldtrack_owner already exists'; END $$;
\endif
SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fieldtrack_app') AS app_exists \gset
\if :app_exists
  \echo 'role fieldtrack_app already exists - refusing to continue.'
  DO $$ BEGIN RAISE EXCEPTION 'refusing: role fieldtrack_app already exists'; END $$;
\endif

CREATE ROLE fieldtrack_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_pw';
CREATE ROLE fieldtrack_app   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';

CREATE DATABASE fieldtrackpro_prod OWNER fieldtrack_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE fieldtrackpro_prod FROM PUBLIC;
GRANT CONNECT ON DATABASE fieldtrackpro_prod TO fieldtrack_app;

\connect fieldtrackpro_prod
CREATE EXTENSION IF NOT EXISTS postgis;
-- keep the schema private to the owner until grant_runtime_role.sql opens exactly what the app needs
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT  ALL    ON SCHEMA public TO fieldtrack_owner;

\echo 'OK: roles and database created. Next: run alembic as fieldtrack_owner, then scripts/grant_runtime_role.sql.'
