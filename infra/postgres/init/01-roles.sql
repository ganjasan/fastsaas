-- Postgres init script — runs once on cluster bootstrap (per docker-compose).
-- Creates the two roles required by ADR-007 multi-tenant isolation:
--   * app_user           — used by the FastAPI app and arq workers; NO BYPASSRLS.
--   * alembic_migrator   — used by Alembic and pg_dump; BYPASSRLS, but no SUPERUSER.
-- The default `fastsaas` superuser created by docker-compose is reserved for
-- emergency access only.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN PASSWORD 'dev';
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'alembic_migrator') THEN
    CREATE ROLE alembic_migrator LOGIN PASSWORD 'dev' BYPASSRLS;
  END IF;
END
$$;

-- alembic_migrator owns the schema so it can issue ALTER TABLE / DDL freely.
GRANT ALL ON SCHEMA public TO alembic_migrator;
GRANT CREATE ON DATABASE fastsaas TO alembic_migrator;
ALTER SCHEMA public OWNER TO alembic_migrator;

-- Extensions required by the schema. Installed here (as the bootstrap
-- superuser) because most extensions require SUPERUSER to install — even
-- though `citext` is trusted in PG 13+, the migration role's CREATE
-- privilege on the database is granted above as a belt-and-braces.
CREATE EXTENSION IF NOT EXISTS citext;
