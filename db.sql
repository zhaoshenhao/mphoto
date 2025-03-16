-- 以超级用户身份创建数据库和用户
-- CREATE ROLE mphoto_user WITH LOGIN PASSWORD 'your_secure_password';
-- CREATE DATABASE mphoto_db OWNER mphoto_user;

-- 连接到 mphoto_db 数据库
\connect mphoto_db

-- 授予用户权限
GRANT ALL PRIVILEGES ON DATABASE mphoto_db TO mphoto_user;

-- 创建 schema
CREATE SCHEMA IF NOT EXISTS mphoto AUTHORIZATION mphoto_user;

-- 设置默认 schema
SET search_path TO mphoto, public;

-- 创建 event 表
CREATE TABLE IF NOT EXISTS mphoto.event (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    expiry TEXT NOT NULL
);

-- 创建 bib 表
CREATE TABLE IF NOT EXISTS mphoto.bib (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    bib_number TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    expiry TEXT NOT NULL,
    name TEXT,
    CONSTRAINT unique_bib_number UNIQUE (event_id, bib_number)
);

-- 创建 download_history 表
CREATE TABLE IF NOT EXISTS mphoto.download_history (
    id SERIAL PRIMARY KEY,
    bib_number TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建 photo 表
CREATE TABLE IF NOT EXISTS mphoto.photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    photo_path TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建 bib_photo 表
CREATE TABLE IF NOT EXISTS mphoto.bib_photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    bib_id INTEGER NOT NULL REFERENCES mphoto.bib(id) ON DELETE CASCADE,
    photo_id INTEGER NOT NULL REFERENCES mphoto.photo(id) ON DELETE CASCADE,
    CONSTRAINT unique_bib_photo UNIQUE (bib_id, photo_id)
);

-- 创建 face_photo 表（使用 pgvector）
CREATE TABLE IF NOT EXISTS mphoto.face_photo (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES mphoto.event(id) ON DELETE CASCADE,
    photo_id INTEGER NOT NULL REFERENCES mphoto.photo(id) ON DELETE CASCADE,
    embedding VECTOR(512), -- 假设人脸向量维度为 512，可根据模型调整
    confidence FLOAT NOT NULL
);

-- 授予 mphoto_user 对所有表的权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mphoto TO mphoto_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA mphoto TO mphoto_user;

-- 创建索引
CREATE INDEX idx_event_name ON mphoto.event(name);
CREATE INDEX idx_bib_event_id ON mphoto.bib(event_id);
CREATE INDEX idx_bib_bib_number ON mphoto.bib(bib_number);
CREATE INDEX idx_photo_event_id ON mphoto.photo(event_id);
CREATE INDEX idx_bib_photo_event_id ON mphoto.bib_photo(event_id);
CREATE INDEX idx_face_photo_event_id ON mphoto.face_photo(event_id);
CREATE INDEX idx_face_photo_embedding ON mphoto.face_photo USING hnsw (embedding vector_l2_ops); -- pgvector HNSW 索引

-- 插入测试数据 (event)
INSERT INTO mphoto.event (name, enabled, expiry) VALUES
    ('Marathon 2025', TRUE, '2025-12-31'),
    ('Sprint Challenge', FALSE, '2025-06-30');

-- 插入测试数据 (bib)
INSERT INTO mphoto.bib (event_id, bib_number, enabled, expiry, name) VALUES
    (1, '1001', TRUE, '2025-12-31', 'Alice'),
    (1, '1002', TRUE, '2025-12-31', 'Bob'),
    (2, '2001', FALSE, '2025-06-30', 'Charlie');


