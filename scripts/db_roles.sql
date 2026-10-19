-- Разграничение прав сервисных учётных записей MagicTech (выполнять под postgres):
--   psql -U postgres -d MagicTech -f scripts/db_roles.sql
-- Пароли замените перед применением в рабочем контуре.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'magictech_app') THEN
    CREATE ROLE magictech_app LOGIN PASSWORD 'change-me-app' CONNECTION LIMIT 50;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'magictech_readonly') THEN
    CREATE ROLE magictech_readonly LOGIN PASSWORD 'change-me-ro' CONNECTION LIMIT 10;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'magictech_backup') THEN
    CREATE ROLE magictech_backup LOGIN PASSWORD 'change-me-backup' REPLICATION CONNECTION LIMIT 3;
  END IF;
END $$;

REVOKE ALL ON DATABASE "MagicTech" FROM PUBLIC;
GRANT CONNECT ON DATABASE "MagicTech" TO magictech_app, magictech_readonly, magictech_backup;
GRANT USAGE ON SCHEMA public TO magictech_app, magictech_readonly;

-- приложение: только DML, без DDL (миграции выполняет владелец схемы)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO magictech_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO magictech_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO magictech_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO magictech_app;
-- журнал аудита — только дополнение, без правки и удаления
REVOKE UPDATE, DELETE ON audit_log FROM magictech_app;

-- аналитика/отчёты: только чтение, без персональных данных и хешей паролей
GRANT SELECT ON ALL TABLES IN SCHEMA public TO magictech_readonly;
REVOKE SELECT ON auth_credentials, user_profiles, api_tokens, payment_logs FROM magictech_readonly;

-- резервное копирование
GRANT pg_read_all_data TO magictech_backup;
