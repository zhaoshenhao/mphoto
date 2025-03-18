# database.py
import psycopg2
import numpy as np
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS, TABLES, DEFAULT_SEARCH_LIMIT, config
from pgvector.psycopg2 import register_vector

class Database:
    def __init__(self, logger):
        self.config = config
        self.logger = logger
        self.conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        with self.conn.cursor() as cur:
            cur.execute("ALTER DATABASE mphoto_db SET search_path TO mphoto, public")
            cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
        self.conn.commit()
        register_vector(self.conn)
        self.cursor = self.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    # Insert an event
    def add_event(self, name, enabled, expiry):
        query = f"INSERT INTO {TABLES['event']} (name, enabled, expiry) VALUES (%s, %s, %s) RETURNING id"
        self.cursor.execute(query, (name, enabled, expiry))
        return self.cursor.fetchone()[0]

    # Insert a bib
    def add_bib(self, event_id, bib_number, enabled, expiry, name=None):
        query = f"INSERT INTO {TABLES['bib']} (event_id, bib_number, enabled, expiry, name) VALUES (%s, %s, %s, %s, %s) RETURNING id"
        self.cursor.execute(query, (event_id, bib_number, enabled, expiry, name))
        return self.cursor.fetchone()[0]

    # Insert a photo
    def add_photo(self, event_id, photo_path, timestamp):
        query = f"""
            INSERT INTO {TABLES['photo']} (event_id, photo_path, last_updated) VALUES (%s, %s, %s)
                ON CONFLICT(event_id, photo_path) DO UPDATE SET last_updated = %s RETURNING id
            """
        self.cursor.execute(query, (event_id, photo_path, timestamp, timestamp))
        return self.cursor.fetchone()[0]

    def update_photo(self, photo_id, timestamp):
        query = f"UPDATE {TABLES['photo']} SET last_updated = %s WHERE id = %s"
        self.cursor.execute(query, (timestamp, photo_id))

    # Insert a bib-photo relationship
    def add_bib_photo(self, event_id, bib_number, photo_id, confidence):
        query = f"INSERT INTO {TABLES['bib_photo']} (event_id, bib_number, photo_id, confidence) VALUES (%s, %s, %s, %s)"
        self.cursor.execute(query, (event_id, bib_number, photo_id, confidence))

    # Insert a face-photo record
    def add_face_photo(self, event_id, photo_id, embedding, confidence):
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        if len(embedding) != expected_dim:
            self.logger.error(f"Embedding dimension mismatch for photo_id {photo_id}: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension")
        query = f"INSERT INTO {TABLES['face_photo']} (event_id, photo_id, embedding, confidence) VALUES (%s, %s, %s, %s)"
        self.cursor.execute(query, (event_id, photo_id, embedding.tolist(), confidence))

    def get_event_count(self, event_id):
        self.cursor.execute(f"SELECT COUNT(*) FROM {TABLES['bib']} WHERE event_id = %s", (event_id))
        total_bibs = self.cursor.fetchone()[0]
        self.cursor.execute(f"SELECT COUNT(*) FROM {TABLES['face_photo']} WHERE event_id = %s", (event_id))
        total_faces = self.cursor.fetchone()[0]
        self.cursor.execute(f"SELECT COUNT(*) FROM {TABLES['bib_photo']} WHERE event_id = %s", (event_id))
        total_bib_photos = self.cursor.fetchone()[0]
        return total_bibs, total_bib_photos, total_bib_photos

    def get_event_photo_info(self, event_id):
        c = self.conn.cursor()
        c.execute(f"SELECT id, photo_path, last_updated FROM {TABLES['photo']} p WHERE p.event_id = %s", (event_id))
        return {row[1]: (row[0], row[2]) for row in c.fetchall()}  # {path: (id, timestamp)}

    # Get photo paths for a bib
    def search_bib_photo(self, event_id, bib, sub_bib, bib_conf):
        query = f"""
            SELECT p.photo_path
            FROM {TABLES['bib_photo']} bp
            JOIN {TABLES['photo']} p ON bp.photo_id = p.id
            WHERE bp.event_id = %s and bp.confidence >= %s
        """
        if sub_bib:
            query += " AND bp.bib_number LIKE %s"
            self.cursor.execute(query, (event_id, bib_conf, f"%{bib}%"))
        else:
            query += " AND bp.bib_number = %s"
            self.cursor.execute(query, (event_id, bib_conf, bib))
        return [row[0] for row in self.cursor.fetchall()]

    def search_face_photo(self, event_id, embedding, min_confidence, min_similarity, limit=DEFAULT_SEARCH_LIMIT):
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        distance = 1 - min_similarity
        if len(embedding) != expected_dim:
            self.logger.error(f"Embedding dimension mismatch for photo_id {photo_id}: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension")
        emblist = embedding.tolist()
        query = f"""
            SELECT p.photo_path, (1 - (fp.embedding <=> %s::vector)) AS similarity, fp.confidence
            FROM {TABLES['face_photo']} fp
            JOIN {TABLES['photo']} p ON fp.photo_id = p.id
            WHERE fp.event_id = %s
            AND fp.confidence >= %s
            AND  fp.embedding <=> %s::vector < %s
            ORDER BY p.photo_path
            LIMIT %s
        """
        self.cursor.execute(query, (emblist, event_id, min_confidence, emblist, distance, limit))
        return self.cursor.fetchall()

    # Delete references to a photo in bib_photo and face_photo
    def delete_photo_ref(self, photo_id):
        """
        Delete all rows in bib_photo and face_photo for the given photo_id
        :param photo_id: ID of the photo whose references should be deleted
        """
        self.cursor.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))
        self.logger.debug(f"Deleted face and bib data for photo_id {photo_id}")

    # Delete a photo and its references
    def delete_photo(self, photo_id):
        """
        Delete the photo row and all related rows in bib_photo and face_photo
        :param photo_id: ID of the photo to delete
        """
        self.cursor.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['photo']} WHERE id = %s", (photo_id,))
        self.logger.debug(f"Deleted data for photo_id {photo_id}")

