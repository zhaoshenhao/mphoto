import sqlite3
import numpy as np
import faiss
import logging

class Database:
    def __init__(self, config, logger=None):
        self.config = config
        self.conn = sqlite3.connect(config['database']['file'])
        self.faiss_index = None
        self.logger = logger or logging.getLogger(__name__)
        self.setup_tables()

    def setup_tables(self):
        c = self.conn.cursor()
        # Photo 表
        c.execute(f'''CREATE TABLE IF NOT EXISTS {self.config['database']['photo_table']}
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      photo_path TEXT UNIQUE,
                      last_updated REAL)''')
        # Face 表
        c.execute(f'''CREATE TABLE IF NOT EXISTS {self.config['database']['face_table']}
                     (embedding BLOB,
                      photo_id INTEGER,
                      confidence REAL,
                      FOREIGN KEY (photo_id) REFERENCES {self.config['database']['photo_table']}(id))''')
        # Bib 表
        c.execute(f'''CREATE TABLE IF NOT EXISTS {self.config['database']['bib_table']}
                     (bib TEXT,
                      photo_id INTEGER,
                      confidence REAL,
                      FOREIGN KEY (photo_id) REFERENCES {self.config['database']['photo_table']}(id))''')
        self.conn.commit()

    def add_photo(self, photo_path, timestamp):
        c = self.conn.cursor()
        c.execute(f"INSERT OR REPLACE INTO {self.config['database']['photo_table']} (photo_path, last_updated) VALUES (?, ?)",
                  (photo_path, timestamp))
        self.conn.commit()
        c.execute(f"SELECT id FROM {self.config['database']['photo_table']} WHERE photo_path = ?", (photo_path,))
        return c.fetchone()[0]

    def add_face(self, embedding, photo_id, confidence):
        c = self.conn.cursor()
        embedding = np.array(embedding, dtype=np.float32).flatten()
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        if len(embedding) != expected_dim:
            self.logger.error(f"Embedding dimension mismatch for photo_id {photo_id}: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension")
        self.logger.debug(f"Adding embedding for photo_id {photo_id} with dimension {len(embedding)}")
        c.execute(f"INSERT INTO {self.config['database']['face_table']} (embedding, photo_id, confidence) VALUES (?, ?, ?)",
                  (embedding.tobytes(), photo_id, confidence))
        self.conn.commit()

    def add_bib(self, bib, photo_id, confidence):
        c = self.conn.cursor()
        c.execute(f"INSERT INTO {self.config['database']['bib_table']} (bib, photo_id, confidence) VALUES (?, ?, ?)",
                  (bib, photo_id, confidence))
        self.conn.commit()

    def build_faiss_index(self):
        c = self.conn.cursor()
        c.execute(f"SELECT embedding, photo_id FROM {self.config['database']['face_table']}")
        rows = c.fetchall()
        
        embeddings = []
        photo_ids = []
        expected_dimension = self.config.get('deepface', {}).get('embedding_dim', 512)
        
        for emb, photo_id in rows:
            embedding = [float(x) for x in np.frombuffer(emb, dtype=np.float32)]
            if len(embedding) != expected_dimension:
                self.logger.warning(f"Skipping embedding for photo_id {photo_id} with inconsistent dimension "
                                   f"(expected {expected_dimension}, got {len(embedding)})")
                continue
            embeddings.append(embedding)
            photo_ids.append(photo_id)
        
        if not embeddings:
            self.faiss_index = None
            self.logger.warning("No valid embeddings found in database")
            return self.faiss_index
        
        dimension = len(embeddings[0])
        metric = self.config['search']['similarity_metric']

        if metric == 'cosine':
            self.faiss_index = faiss.index_factory(dimension, "Flat", faiss.METRIC_INNER_PRODUCT)
            embeddings = np.array(embeddings, dtype=np.float32)
            faiss.normalize_L2(embeddings)
        else:  # 默认 L2
            self.faiss_index = faiss.index_factory(dimension, "Flat", faiss.METRIC_L2)

        self.faiss_index.add(embeddings)
        self.logger.info(f"FAISS index built with dimension {dimension} and {len(embeddings)} embeddings")
        return self.faiss_index

    def search_bib(self, bib, sub_bib=False, min_confidence=0.3):
        c = self.conn.cursor()
        query = (f"SELECT p.photo_path FROM {self.config['database']['bib_table']} b "
                 f"JOIN {self.config['database']['photo_table']} p ON b.photo_id = p.id "
                 f"WHERE b.confidence >= ?")
        if sub_bib:
            query += " AND b.bib LIKE ?"
            c.execute(query, (min_confidence, f"%{bib}%"))
        else:
            query += " AND b.bib = ?"
            c.execute(query, (min_confidence, bib))
        return [row[0] for row in c.fetchall()]

    def get_photo_info(self):
        c = self.conn.cursor()
        c.execute(f"SELECT id, photo_path, last_updated FROM {self.config['database']['photo_table']}")
        return {row[1]: (row[0], row[2]) for row in c.fetchall()}  # {path: (id, timestamp)}

    def delete_photo_data(self, photo_id):
        c = self.conn.cursor()
        c.execute(f"DELETE FROM {self.config['database']['face_table']} WHERE photo_id = ?", (photo_id,))
        c.execute(f"DELETE FROM {self.config['database']['bib_table']} WHERE photo_id = ?", (photo_id,))
        c.execute(f"DELETE FROM {self.config['database']['photo_table']} WHERE id = ?", (photo_id,))
        self.conn.commit()
        self.logger.debug(f"Deleted data for photo_id {photo_id}")

    def delete_by_photo_id(self, photo_id):
        c = self.conn.cursor()
        c.execute(f"DELETE FROM {self.config['database']['face_table']} WHERE photo_id = ?", (photo_id,))
        c.execute(f"DELETE FROM {self.config['database']['bib_table']} WHERE photo_id = ?", (photo_id,))
        self.conn.commit()
        self.logger.debug(f"Deleted face and bib data for photo_id {photo_id}")
