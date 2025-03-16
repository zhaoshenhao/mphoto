# database.py
import psycopg2
import numpy as np
from psycopg2.extras import RealDictCursor
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, TABLES, logger, config

# Default search limit from config.yaml
DEFAULT_SEARCH_LIMIT = config.get("database", {}).get("default_search_limit", 100)

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            cursor_factory=RealDictCursor
        )
        self.cursor = self.conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    # Insert an event
    def insert_event(self, name, enabled, expiry):
        query = f"INSERT INTO {TABLES['event']} (name, enabled, expiry) VALUES (%s, %s, %s) RETURNING id"
        self.cursor.execute(query, (name, enabled, expiry))
        return self.cursor.fetchone()["id"]

    # Insert a bib
    def insert_bib(self, event_id, bib_number, enabled, expiry, name=None):
        query = f"INSERT INTO {TABLES['bib']} (event_id, bib_number, enabled, expiry, name) VALUES (%s, %s, %s, %s, %s) RETURNING id"
        self.cursor.execute(query, (event_id, bib_number, enabled, expiry, name))
        return self.cursor.fetchone()["id"]

    # Insert a photo
    def insert_photo(self, event_id, photo_path):
        query = f"INSERT INTO {TABLES['photo']} (event_id, photo_path) VALUES (%s, %s) RETURNING id"
        self.cursor.execute(query, (event_id, photo_path))
        return self.cursor.fetchone()["id"]

    # Insert a bib-photo relationship
    def insert_bib_photo(self, event_id, bib_id, photo_id):
        query = f"INSERT INTO {TABLES['bib_photo']} (event_id, bib_id, photo_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
        self.cursor.execute(query, (event_id, bib_id, photo_id))

    # Insert a face-photo record
    def insert_face_photo(self, event_id, photo_id, embedding, confidence):
        query = f"INSERT INTO {TABLES['face_photo']} (event_id, photo_id, embedding, confidence) VALUES (%s, %s, %s, %s)"
        self.cursor.execute(query, (event_id, photo_id, embedding.tolist(), confidence))

    # Search for similar faces
    def search_similar_faces(self, embedding, event_id, min_confidence, min_similarity, limit=DEFAULT_SEARCH_LIMIT):
        """
        Search for similar faces based on embedding, sorted by similarity DESC
        :param embedding: Face embedding vector
        :param event_id: Event ID to filter by
        :param min_confidence: Minimum confidence threshold
        :param min_similarity: Minimum cosine similarity (1 - distance)
        :param limit: Maximum number of records to return
        :return: List of dicts with event_id, photo_id, confidence, similarity
        """
        max_distance = 1 - min_similarity
        query = f"""
            SELECT 
                fp.event_id,
                fp.photo_id,
                fp.confidence,
                (1 - (fp.embedding <=> %s)) AS similarity
            FROM {TABLES['face_photo']} fp
            JOIN {TABLES['photo']} p ON fp.photo_id = p.id
            WHERE fp.event_id = %s
            AND fp.confidence >= %s
            AND (fp.embedding <=> %s) <= %s
            ORDER BY similarity DESC
            LIMIT %s
        """
        self.cursor.execute(query, (embedding.tolist(), event_id, min_confidence, embedding.tolist(), max_distance, limit))
        return self.cursor.fetchall()

    # Search photos by bib with confidence filter
    def search_photos_by_bib(self, event_id, bib_id, min_confidence):
        """
        Search photos associated with a specific bib, filtered by minimum confidence
        :param event_id: Event ID to filter by
        :param bib_id: Bib ID to search for
        :param min_confidence: Minimum confidence threshold from face_photo table
        :return: List of dicts with event_id, bib_id, photo_path
        """
        query = f"""
            SELECT 
                bp.event_id,
                bp.bib_id,
                p.photo_path
            FROM {TABLES['bib_photo']} bp
            JOIN {TABLES['photo']} p ON bp.photo_id = p.id
            JOIN {TABLES['face_photo']} fp ON bp.photo_id = fp.photo_id
            WHERE bp.event_id = %s
            AND bp.bib_id = %s
            AND fp.confidence >= %s
        """
        self.cursor.execute(query, (event_id, bib_id, min_confidence))
        return self.cursor.fetchall()

    # Delete references to a photo in bib_photo and face_photo
    def delete_photo_ref(self, photo_id):
        """
        Delete all rows in bib_photo and face_photo for the given photo_id
        :param photo_id: ID of the photo whose references should be deleted
        """
        self.cursor.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))

    # Delete a photo and its references
    def delete_photo(self, photo_id):
        """
        Delete the photo row and all related rows in bib_photo and face_photo
        :param photo_id: ID of the photo to delete
        """
        self.cursor.execute(f"DELETE FROM {TABLES['bib_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['face_photo']} WHERE photo_id = %s", (photo_id,))
        self.cursor.execute(f"DELETE FROM {TABLES['photo']} WHERE id = %s", (photo_id,))

    # Get photo paths for a bib
    def get_bib_photos(self, bib_id):
        query = f"""
            SELECT p.photo_path
            FROM {TABLES['bib_photo']} bp
            JOIN {TABLES['photo']} p ON bp.photo_id = p.id
            WHERE bp.bib_id = %s
        """
        self.cursor.execute(query, (bib_id,))
        return [row["photo_path"] for row in self.cursor.fetchall()]
