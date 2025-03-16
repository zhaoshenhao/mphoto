CREATE TABLE event (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    expiry TEXT NOT NULL
);

CREATE TABLE bib (
    event_id INTEGER NOT NULL,
    bib TEXT NOT NULL,
    code TEXT NOT NULL,
    expiry TEXT NOT NULL,
    name TEXT,
    PRIMARY KEY (event_id, bib)
);

CREATE TABLE download_history (
    event_id INTEGER NOT NULL,
    bib_number TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    files INTEGER NOT NULL,
    total_size INTEGER NOT NULL
);

-- 示例数据
INSERT INTO event (id, name, enabled, expiry) VALUES (1, 'Event 1', 1, '2025-12-31T00:00:00Z');
INSERT INTO bib (event_id, bib, code, expiry, name) VALUES (1, '1024', '9876543210', '2025-12-31T00:00:00Z', 'John Doe');
