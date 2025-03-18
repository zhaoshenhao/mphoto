import psycopg
from psycopg_pool import AsyncConnectionPool
import numpy as np
from config import config, DEFAULT_SEARCH_LIMIT
from utils import setup_logging
from datetime import datetime

# Table names from config
TABLES = config['table_names']

# Async connection pool management
class DatabasePool:
    _pool = None
    _vector_extension_installed = False

    @classmethod
    async def initialize(cls, logger):
        if cls._pool is None:
            try:
                # Create the pool
                cls._pool = AsyncConnectionPool(
                    conninfo=f"dbname={config['database']['database']} user={config['database']['username']} password={config['database']['password']} host={config['database']['host']} port={config['database']['port']}",
                    min_size=config['database'].get('min_size', 1),
                    max_size=config['database'].get('max_size', 10),
                    kwargs={"options": "-c search_path=mphoto,public"}
                )
                await cls._pool.open()
                await cls._pool.wait()
                logger.info(f"Psycopg 3 async connection pool initialized with min_size={config['database'].get('min_size', 1)}, max_size={config['database'].get('max_size', 10)}")

                async with cls._pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
                        await conn.commit()  # Commit the extension creation
                        logger.info("Vector extension ensured for the database")
                cls._vector_extension_installed = True

            except Exception as e:
                logger.error(f"Failed to initialize Psycopg 3 async pool or vector extension: {str(e)}")
                raise

    @classmethod
    async def get_pool(cls, logger):
        if cls._pool is None:
            await cls.initialize(logger)
        return cls._pool

    @classmethod
    async def close_all(cls):
        if cls._pool is not None:
            await cls._pool.close()

class Database:
    def __init__(self, logger):
        self.config = config
        self.logger = logger
        self.pool = None  # Will be set in async context

    async def _ensure_pool(self):
        """Ensure the pool is initialized."""
        if self.pool is None:
            self.pool = await DatabasePool.get_pool(self.logger)

    # Removed _ensure_vector_extension since it’s handled in pool initialization

    async def add_event(self, name, enabled, expiry):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT INTO {TABLES['event']} (name, enabled, expiry) VALUES (%s, %s, %s) RETURNING id",
                    (name, enabled, expiry)
                )
                return (await cur.fetchone())[0]

    async def add_bib(self, event_id, bib_number, enabled, expiry, name=None):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT INTO {TABLES['bib']} (event_id, bib_number, enabled, expiry, name) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (event_id, bib_number, enabled, expiry, name)
                )
                return (await cur.fetchone())[0]

    async def add_photo(self, event_id, photo_path, timestamp):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO {TABLES['photo']} (event_id, photo_path, last_updated) VALUES (%s, %s, %s)
                        ON CONFLICT(event_id, photo_path) DO UPDATE SET last_updated = %s RETURNING id
                    """,
                    (event_id, photo_path, timestamp, timestamp)
                )
                return (await cur.fetchone())[0]

    async def update_photo(self, photo_id, timestamp):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE {TABLES['photo']} SET last_updated = %s WHERE id = %s",
                    (timestamp, photo_id)
                )

    async def add_bib_photo(self, event_id, bib_number, photo_id, confidence):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT INTO {TABLES['bib_photo']} (event_id, bib_number, photo_id, confidence) VALUES (%s, %s, %s, %s)",
                    (event_id, bib_number, photo_id, confidence)
                )

    async def add_face_photo(self, event_id, photo_id, embedding, confidence):
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        if len(embedding) != expected_dim:
            self.logger.error(f"Embedding dimension mismatch for photo_id {photo_id}: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension")
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT INTO {TABLES['face_photo']} (event_id, photo_id, embedding, confidence) VALUES (%s, %s, %s, %s)",
                    (event_id, photo_id, embedding.tolist(), confidence)
                )

    async def get_event_count(self, event_id):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT COUNT(*) FROM {TABLES['bib']} WHERE event_id = %s", (event_id,))
                total_bibs = (await cur.fetchone())[0]
                await cur.execute(f"SELECT COUNT(*) FROM {TABLES['face_photo']} WHERE event_id = %s", (event_id,))
                total_faces = (await cur.fetchone())[0]
                await cur.execute(f"SELECT COUNT(*) FROM {TABLES['bib_photo']} WHERE event_id = %s", (event_id,))
                total_bib_photos = (await cur.fetchone())[0]
                return total_bibs, total_bib_photos, total_bib_photos

    async def get_event_photo_info(self, event_id):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT id, photo_path, last_updated FROM {TABLES['photo']} p WHERE p.event_id = %s",
                    (event_id,)
                )
                return {row[1]: (row[0], row[2]) for row in await cur.fetchall()}

    async def search_bib_photo(self, event_id, bib, sub_bib, bib_conf):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                query = f"""
                    SELECT p.photo_path
                    FROM {TABLES['bib_photo']} bp
                    JOIN {TABLES['photo']} p ON bp.photo_id = p.id
                    WHERE bp.event_id = %s AND bp.confidence >= %s
                """
                if sub_bib:
                    query += " AND bp.bib_number LIKE %s"
                    await cur.execute(query, (event_id, bib_conf, f"%{bib}%"))
                else:
                    query += " AND bp.bib_number = %s"
                    await cur.execute(query, (event_id, bib_conf, bib))
                return [row[0] for row in await cur.fetchall()]

    async def search_face_photo(self, event_id, embedding, min_confidence, min_similarity, limit=DEFAULT_SEARCH_LIMIT):
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        distance = 1 - min_similarity
        if len(embedding) != expected_dim:
            self.logger.error(f"Embedding dimension mismatch: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension")
        emblist = embedding.tolist()
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT p.photo_path, (1 - (fp.embedding <=> %s::vector)) AS similarity, fp.confidence
                    FROM {TABLES['face_photo']} fp
                    JOIN {TABLES['photo']} p ON fp.photo_id = p.id
                    WHERE fp.event_id = %s
                    AND fp.confidence >= %s
                    AND fp.embedding <=> %s::vector < %s
                    ORDER BY p.photo_path
                    LIMIT %s
                    """,
                    (emblist, event_id, min_confidence, emblist, distance, limit)
                )
                return await cur.fetchall()

    async def delete_photo_ref(self, photo_id):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
                await cur.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))
                self.logger.debug(f"Deleted face and bib data for photo_id {photo_id}")

    async def delete_photo(self, photo_id):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
                await cur.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))
                await cur.execute(f"DELETE FROM {TABLES['photo']} WHERE id = %s", (photo_id,))
                self.logger.debug(f"Deleted data for photo_id {photo_id}")

    async def get_event_bib_by_code(self, code: str):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT b.id AS bib_id, b.event_id, b.bib_number, b.code, b.expiry AS bib_expiry, b.name, 
                           b.enabled AS bib_enabled, e.name AS event_name, e.enabled AS event_enabled, 
                           e.expiry AS event_expiry
                    FROM bib b
                    JOIN event e ON b.event_id = e.id
                    WHERE b.code = %s
                    """,
                    (code,)
                )
                row = await cur.fetchone()
                if not row:
                    return {"error": "No matching bib found for the provided code"}
                return {
                    "bib_id": row[0],
                    "event_id": row[1],
                    "bib": row[2],
                    "code": row[3],
                    "bib_expiry": row[4],
                    "name": row[5],
                    "bib_enabled": row[6],
                    "event_name": row[7],
                    "event_enabled": row[8],
                    "event_expiry": row[9]
                }

    async def get_download_limit(self, bib_id: int):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT SUM(total_size) AS total FROM {TABLES['download_history']} WHERE bib_id = %s",
                    (bib_id,)
                )
                result = await cur.fetchone()
                return result[0] or 0

    async def log_download(self, bib_id: int, total_size: int):
        await self._ensure_pool()
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT INTO {TABLES['download_history']} (bib_id, total_size) VALUES (%s, %s)",
                    (bib_id, total_size)
                )
