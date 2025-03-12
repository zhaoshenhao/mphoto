import sqlite3
import numpy as np
import faiss

class Database:
    def __init__(self, config, logger=None):
        self.config = config
        self.conn = sqlite3.connect(config['database']['file'])
        self.faiss_index = None
        self.logger = logger
        self.setup_tables()

    def setup_tables(self):
        c = self.conn.cursor()
        # 为 face_table 添加唯一性约束：photo_path 和 embedding 组合唯一
        c.execute(f'''CREATE TABLE IF NOT EXISTS {self.config['database']['face_table']}
                     (embedding BLOB, photo_path TEXT, confidence REAL,
                      UNIQUE(photo_path, embedding))''')
        # 为 bib_table 添加唯一性约束：bib 和 photo_path 组合唯一
        c.execute(f'''CREATE TABLE IF NOT EXISTS {self.config['database']['bib_table']}
                     (bib TEXT, photo_path TEXT, confidence REAL,
                      UNIQUE(bib, photo_path))''')
        self.conn.commit()

    def add_face(self, embedding, photo_path, confidence):
        c = self.conn.cursor()
        embedding = np.array(embedding, dtype=np.float32).flatten()
        expected_dim = self.config.get('deepface', {}).get('embedding_dim', 512)
        if len(embedding) != expected_dim and self.logger:
            self.logger.error(f"Embedding dimension mismatch in add_face for {photo_path}: expected {expected_dim}, got {len(embedding)}")
            raise ValueError(f"Invalid embedding dimension for {photo_path}")
        
        embedding_bytes = embedding.tobytes()
        # 使用 INSERT OR REPLACE 更新或插入记录
        c.execute(f"INSERT OR REPLACE INTO {self.config['database']['face_table']} (embedding, photo_path, confidence) VALUES (?, ?, ?)",
                  (embedding_bytes, photo_path, confidence))
        self.conn.commit()
        
        if self.logger:
            self.logger.debug(f"Added/Update face embedding for {photo_path} with dimension {len(embedding)}, confidence {confidence}")

    def add_bib(self, bib, photo_path, confidence):
        c = self.conn.cursor()
        
        # 使用 INSERT OR REPLACE 更新或插入记录
        c.execute(f"INSERT OR REPLACE INTO {self.config['database']['bib_table']} (bib, photo_path, confidence) VALUES (?, ?, ?)",
                  (bib, photo_path, confidence))
        self.conn.commit()
        
        if self.logger:
            self.logger.debug(f"Added/Update new bib {bib} for {photo_path} with confidence {confidence}")

    def build_faiss_index(self):
        c = self.conn.cursor()
        c.execute(f"SELECT embedding, photo_path FROM {self.config['database']['face_table']}")
        rows = c.fetchall()
        
        embeddings = []
        paths = []
        expected_dimension = self.config.get('deepface', {}).get('embedding_dim', 512)
        
        for emb, path in rows:
            embedding = [float(x) for x in np.frombuffer(emb, dtype=np.float32)]
            if len(embedding) != expected_dimension:
                if self.logger:
                    self.logger.warning(f"Skipping embedding for {path} with inconsistent dimension "
                                      f"(expected {expected_dimension}, got {len(embedding)})")
                continue
            embeddings.append(embedding)
            paths.append(path)
        
        if not embeddings:
            self.faiss_index = None
            if self.logger:
                self.logger.warning("No valid embeddings found in database")
            return paths
        
        dimension = len(embeddings[0])
        metric = self.config['search']['similarity_metric']

        if metric == 'cosine':
            self.faiss_index = faiss.index_factory(dimension, "Flat", faiss.METRIC_INNER_PRODUCT)
            embeddings = np.array(embeddings, dtype=np.float32)
            faiss.normalize_L2(embeddings)
        else:  # 默认 L2
            self.faiss_index = faiss.index_factory(dimension, "Flat", faiss.METRIC_L2)

        self.faiss_index.add(embeddings)
        if self.logger:
            self.logger.info(f"FAISS index built with dimension {dimension} and {len(embeddings)} embeddings")
        return paths

    def search_bib(self, bib, sub_bib=False, min_confidence=0.3):
        c = self.conn.cursor()
        query = f"SELECT photo_path FROM {self.config['database']['bib_table']} WHERE confidence >= ?"
        if sub_bib:
            query += " AND bib LIKE ?"
            c.execute(query, (min_confidence, f"%{bib}%"))
        else:
            query += " AND bib = ?"
            c.execute(query, (min_confidence, bib))
        return [row[0] for row in c.fetchall()]
