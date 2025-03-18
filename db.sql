-- Login as Super DBA
-- CREATE ROLE mphoto_user WITH LOGIN PASSWORD 'your_secure_password';
-- CREATE DATABASE mphoto_db OWNER mphoto_user;

-- Connect to mphoto_db database
\connect mphoto_db

ALTER DATABASE mphoto_db SET search_path TO mphoto;

-- Grant用户权限
GRANT ALL PRIVILEGES ON DATABASE mphoto_db TO mphoto_user;

-- Create schema
CREATE SCHEMA IF NOT EXISTS mphoto AUTHORIZATION mphoto_user;

-- 设置默认 schema
SET search_path TO mphoto, public;

-- Install vector extension
CREATE EXTENSION IF NOT EXISTS vector
ALTER EXTENSION vector SET SCHEMA mphoto;

-- Create event table
CREATE TABLE IF NOT EXISTS mphoto.event
(
    id SERIAL PRIMARY KEY,
    name character varying(100) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    expiry TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT uniq_name UNIQUE (name)
)
ALTER TABLE IF EXISTS mphoto.event OWNER to mphoto_user;

-- Create bib table
CREATE TABLE IF NOT EXISTS mphoto.bib (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    bib_number character varying(10)  NOT NULL,
    enabled BOOLEAN DEFAULT TRUE NOT NULL,
    expiry TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    name character varying(100) NOT NULL,
    code character varying(20) NOT NULL,
    CONSTRAINT unique_bib_number UNIQUE (event_id, bib_number),
    CONSTRAINT unique_code UNIQUE(code)
);
ALTER TABLE IF EXISTS mphoto.bib OWNER to mphoto_user;

-- Create download_history table
CREATE TABLE IF NOT EXISTS mphoto.download_history (
    id SERIAL PRIMARY KEY,
    bib_id INTEGER NOT NULL REFERENCES mphoto.bib(id) ON DELETE CASCADE,
    total_size INTEGER NOT NULL,
    download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS mphoto.download_history OWNER to mphoto_user;

-- Create photo table
CREATE TABLE IF NOT EXISTS mphoto.photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    photo_path TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT unique_photo_path UNIQUE (event_id, photo_path)
);
ALTER TABLE IF EXISTS mphoto.photo OWNER to mphoto_user;

-- Create bib_photo table
CREATE TABLE IF NOT EXISTS mphoto.bib_photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    bib_number character varying(10)  NOT NULL,
    photo_id INTEGER NOT NULL REFERENCES mphoto.photo(id) ON DELETE CASCADE,
    confidence FLOAT NOT NULL,
    CONSTRAINT unique_bib_photo UNIQUE (bib_id, photo_id)
);
ALTER TABLE IF EXISTS mphoto.bib_photo OWNER to mphoto_user;

-- Create face_photo table（使用 pgvector）
CREATE TABLE IF NOT EXISTS mphoto.face_photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    photo_id INTEGER NOT NULL REFERENCES mphoto.photo(id) ON DELETE CASCADE,
    embedding VECTOR(512) NOT NULL,
    confidence FLOAT NOT NULL
);
ALTER TABLE IF EXISTS mphoto.bib_photo OWNER to mphoto_user;

-- Grant mphoto_user to all table
GRANT ALL ON SCHEMA mphoto TO mphoto_user;
GRANT ALL ON ALL TABLES IN SCHEMA mphoto TO mphoto_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA mphoto TO mphoto_user;

-- Create index
CREATE INDEX idx_event_name ON mphoto.event(name);
CREATE INDEX idx_bib_event_id ON mphoto.bib(event_id);
CREATE INDEX idx_bib_bib_number ON mphoto.bib(bib_number);
CREATE INDEX idx_photo_event_id ON mphoto.photo(event_id);
CREATE INDEX idx_bib_photo_bib_id ON mphoto.bib_photo(bib_id);
CREATE INDEX idx_face_photo_event_id ON mphoto.face_photo(event_id);
CREATE INDEX idx_face_photo_photo_id ON mphoto.face_photo(photo_id);
CREATE INDEX idx_face_photo_embedding ON mphoto.face_photo USING hnsw (embedding vector_l2_ops);

-- Truncate
-- TRUNCATE TABLE event RESTART IDENTITY CASCADE;

-- Test data (event)
INSERT INTO mphoto.event (name, enabled, expiry) VALUES
    ('2025 Chilly Half Marathon', TRUE, '2026-03-17 21:34:58.763336'),
    ('Sprint Challenge', FALSE, '2026-03-17 21:34:58.763336');

-- Test data (bib)
INSERT INTO mphoto.bib (event_id, bib_number, enabled, expiry, name, code) VALUES
    (1, '1024', TRUE, '2026-03-17 21:34:58.763336', 'Allen Zhao', '1234567890'),
    (1, '1704', TRUE, '2026-03-17 21:34:58.763336', 'Robert Luo', '1234567891'),
    (1, '2001', FALSE, '2025-06-30', 'Charlie', '0000000001');

