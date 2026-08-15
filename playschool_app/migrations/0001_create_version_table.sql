-- Initial migration: create schema_migrations table (runner also creates it if missing)
-- This file intentionally left minimal; use subsequent migrations to change schema.

CREATE TABLE IF NOT EXISTS example_migration_marker (
    id INT AUTO_INCREMENT PRIMARY KEY,
    note VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;