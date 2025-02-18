import psycopg2
import psycopg2.extras
from psycopg2 import pool
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
import uuid
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from typing import List
import json
import regex
import nltk
import os

class PostgresBM25Retriever(BaseRetriever):
    connection_uri: str
    table_name: str
    k: int
    connection_pool: psycopg2.pool.SimpleConnectionPool = None

    def __init__(self, **data):
        super().__init__(**data)
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=15,
                dsn=self.connection_uri
            )
            if self.connection_pool:
                print("Connection pool created successfully.")
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            raise
        self.setup_database()
    
    def escape_query(self, query):
        # Tokenize the query into words
        tokens = nltk.word_tokenize(query)
        # Use regex to keep alphanumeric characters and diacritics, remove all others
        tokens = [regex.sub(r'[^\p{L}\p{N}\s]', '', token) for token in tokens]
        # Rejoin tokens into a sanitized string
        sanitized_query = ' '.join(tokens)
        return sanitized_query

    def setup_database(self):
        conn = None
        try:
            conn = self.connection_pool.getconn()
            with conn.cursor() as cursor:
                # Ensure pg_search extension is installed
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_search;")
                
                # Create table if not exists
                cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            id SERIAL PRIMARY KEY,
                            hash char(32) UNIQUE,
                            content TEXT,
                            metadata TEXT
                        );""")
                # Create BM25 index
                cursor.execute(fr"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = lower('{self.table_name}_bm25_bm25_index')
                            AND n.nspname = 'public'
                            AND c.relkind = 'i'
                        ) THEN
                            CALL paradedb.create_bm25(
                                index_name => '{self.table_name}_bm25',
                                table_name => '{self.table_name}',
                                key_field => 'id',
                                text_fields => paradedb.field('content') || paradedb.field('metadata')
                            );
                        END IF;
                    END $$;
                """)
                conn.commit()
        except Exception as e:
            print(f"Error fetching results: {e}")
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def add_documents(self, documents: List[Document], ids: List[str] = None) -> List[str]:
        conn = None
        try:
            conn = self.connection_pool.getconn()
            with conn.cursor() as cursor:
                if ids is None:
                    ids = [str(uuid.uuid4()) for _ in range(len(documents))]
                
                if len(ids) != len(documents):
                    raise ValueError("Number of ids must match number of documents")
                
                records = [
                    (doc_id, self.escape_query(doc.page_content), psycopg2.extras.Json(doc.metadata))
                    for doc, doc_id in zip(documents, ids)
                ]

                psycopg2.extras.execute_batch(
                    cursor,
                    f"""
                        INSERT INTO {self.table_name} (hash, content, metadata)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (hash) DO NOTHING
                    """,
                    records
                )
                
                conn.commit()
                return ids
        except Exception as e:
            print(f"Error executing query: {e}")
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        conn = None
        try:
            conn = self.connection_pool.getconn()
            with conn.cursor() as cursor:
                # Perform BM25 search using pg_search
                if os.getenv("use_re2") == "True":
                    os.getenv("re2_prompt")
                    index = query.find(f"\n{os.getenv('re2_prompt')}")
                    query = query[:index]
                
                search_command = f"""
                        SELECT 
                            id, 
                            content, 
                            metadata, 
                            paradedb.score(id) AS score_bm25
                        FROM {self.table_name}
                        WHERE content @@@ %s
                        ORDER BY score_bm25 DESC
                        LIMIT %s;
                    """
                cursor.execute(search_command, (query, self.k))
                
                results = cursor.fetchall()
                
                return [Document(page_content=content, metadata={**json.loads(metadata), 'id': id, 'relevance_score': score}) for id, content, metadata, score in results]
        except Exception as e:
            print(f"Error executing query: {e}")
        finally:
            # Return the connection to the pool
            if conn:
                self.connection_pool.putconn(conn)

    def delete(self, ids: List[str]) -> None:
        conn = None
        try:
            conn = self.connection_pool.getconn()
            with conn.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(ids))
                cursor.execute(f"DELETE FROM {self.table_name} WHERE id IN ({placeholders});", tuple(ids))
                cursor.execute(f"VACUUM {self.table_name};")
                conn.commit()
        except Exception as e:
            print(f"Error executing query: {e}")
            if conn:
                conn.rollback()
        finally:
            # Return the connection to the pool
            if conn:
                self.connection_pool.putconn(conn)

    def close(self):
        try:
            self.connection_pool.closeall()
            print("Connection pool closed.")
        except Exception as e:
            print(f"Error closing connection pool: {e}")