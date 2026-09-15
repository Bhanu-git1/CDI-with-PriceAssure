import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("history-service")

class HistoryService:
    """
    Manages persistence and retrieval of chat sessions and transcripts in MySQL.
    """

    def __init__(self, db_service):
        self.db_service = db_service
        self._initialized = False

    def init_db(self):
        """
        Creates the chat sessions and chat messages tables if they do not exist.
        """
        if self._initialized:
            return

        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()

            # Create sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dce_chat_sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL DEFAULT 'default_user',
                    title VARCHAR(255) NOT NULL,
                    is_pinned TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_updated (user_id, updated_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Create messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dce_chat_messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL,
                    sender VARCHAR(20) NOT NULL,
                    text MEDIUMTEXT NOT NULL,
                    sql_query TEXT NULL,
                    data_json MEDIUMTEXT NULL,
                    error TEXT NULL,
                    source VARCHAR(50) NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_session_time (session_id, timestamp ASC),
                    CONSTRAINT fk_chat_session FOREIGN KEY (session_id) 
                        REFERENCES dce_chat_sessions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()
            self._initialized = True
            logger.info("Successfully initialized chat history database tables.")
        except Exception as e:
            logger.error(f"Failed to initialize chat history tables in MySQL: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List lightweight session records for sidebar display.
        Supports case-insensitive user filtering, and automatically returns
        all sessions if user_id is unspecified or has no matched records.
        """
        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor(dictionary=True)

            rows = []
            if user_id and user_id.strip() and user_id.strip().lower() not in ("all", "*"):
                query_user = """
                    SELECT 
                        s.id, 
                        s.user_id, 
                        s.title, 
                        s.is_pinned, 
                        s.created_at, 
                        s.updated_at,
                        COUNT(m.id) AS message_count
                    FROM dce_chat_sessions s
                    LEFT JOIN dce_chat_messages m ON s.id = m.session_id
                    WHERE LOWER(s.user_id) = LOWER(%s)
                    GROUP BY s.id, s.user_id, s.title, s.is_pinned, s.created_at, s.updated_at
                    ORDER BY s.is_pinned DESC, s.created_at DESC, s.updated_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query_user, (user_id.strip(), limit, offset))
                rows = cursor.fetchall()
            else:
                query_all = """
                    SELECT 
                        s.id, 
                        s.user_id, 
                        s.title, 
                        s.is_pinned, 
                        s.created_at, 
                        s.updated_at,
                        COUNT(m.id) AS message_count
                    FROM dce_chat_sessions s
                    LEFT JOIN dce_chat_messages m ON s.id = m.session_id
                    GROUP BY s.id, s.user_id, s.title, s.is_pinned, s.created_at, s.updated_at
                    ORDER BY s.is_pinned DESC, s.created_at DESC, s.updated_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query_all, (limit, offset))
                rows = cursor.fetchall()

            sessions = []
            for row in rows:
                updated_dt = row["updated_at"]
                created_dt = row["created_at"]

                updated_iso = (updated_dt.isoformat() + "Z") if isinstance(updated_dt, datetime) else str(updated_dt or "")
                created_iso = (created_dt.isoformat() + "Z") if isinstance(created_dt, datetime) else str(created_dt or "")

                sessions.append({
                    "id": row["id"],
                    "title": row["title"],
                    "isPinned": bool(row["is_pinned"]),
                    "timestamp": created_iso or updated_iso,
                    "createdAt": created_iso,
                    "updatedAt": updated_iso,
                    "messageCount": row["message_count"]
                })
            return sessions
        except Exception as e:
            logger.error(f"Failed to list chat sessions: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a session and its full message history.
        """
        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Get session info
            cursor.execute("""
                SELECT id, user_id, title, is_pinned, created_at, updated_at
                FROM dce_chat_sessions
                WHERE id = %s
            """, (session_id,))
            session = cursor.fetchone()

            if not session:
                return None

            # Get messages
            cursor.execute("""
                SELECT id, sender, text, sql_query, data_json, error, source, timestamp
                FROM dce_chat_messages
                WHERE session_id = %s
                ORDER BY id ASC
            """, (session_id,))
            msg_rows = cursor.fetchall()

            messages = []
            for m in msg_rows:
                data_val = None
                if m["data_json"]:
                    try:
                        data_val = json.loads(m["data_json"])
                    except Exception:
                        data_val = m["data_json"]

                msg_obj = {
                    "id": m["id"],
                    "sender": m["sender"],
                    "text": m["text"],
                    "sql": m["sql_query"],
                    "data": data_val,
                    "error": m["error"],
                    "source": m["source"],
                    "timestamp": m["timestamp"].isoformat() if isinstance(m["timestamp"], datetime) else str(m["timestamp"])
                }
                messages.append(msg_obj)

            updated_iso = session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else str(session["updated_at"])
            created_iso = session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else str(session["created_at"])

            return {
                "id": session["id"],
                "title": session["title"],
                "isPinned": bool(session["is_pinned"]),
                "timestamp": updated_iso,
                "createdAt": created_iso,
                "messages": messages
            }
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_session(self, session_id: str, title: str, messages: List[Dict[str, Any]],
                     user_id: str = "default_user", is_pinned: bool = False) -> bool:
        """
        Save or update a session with its messages in a single transaction.
        """
        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()

            # Upsert session
            cursor.execute("""
                INSERT INTO dce_chat_sessions (id, user_id, title, is_pinned, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    is_pinned = VALUES(is_pinned),
                    updated_at = NOW()
            """, (session_id, user_id, title, 1 if is_pinned else 0))

            # Delete existing messages for session to rewrite cleanly
            cursor.execute("DELETE FROM dce_chat_messages WHERE session_id = %s", (session_id,))

            # Insert all messages
            if messages:
                insert_query = """
                    INSERT INTO dce_chat_messages 
                    (session_id, sender, text, sql_query, data_json, error, source, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                msg_records = []
                for msg in messages:
                    sender = msg.get("sender", "user")
                    text = msg.get("text", "")
                    sql_query = msg.get("sql")
                    data_val = msg.get("data")
                    data_json_str = json.dumps(data_val) if data_val is not None else None
                    error = msg.get("error")
                    source = msg.get("source")
                    ts = msg.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Handle ISO format timestamp conversion if necessary
                    if isinstance(ts, str) and "T" in ts:
                        try:
                            ts = ts.replace("Z", "+00:00")
                            ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    msg_records.append((
                        session_id, sender, text, sql_query, data_json_str, error, source, ts
                    ))

                cursor.executemany(insert_query, msg_records)

            conn.commit()
            return True
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Failed to save session {session_id}: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_session(self, session_id: str, title: Optional[str] = None, is_pinned: Optional[bool] = None) -> bool:
        """
        Update session metadata (title, pin status).
        """
        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()

            updates = []
            params = []
            if title is not None:
                updates.append("title = %s")
                params.append(title)
            if is_pinned is not None:
                updates.append("is_pinned = %s")
                params.append(1 if is_pinned else 0)

            if not updates:
                return True

            updates.append("updated_at = NOW()")
            params.append(session_id)

            sql = f"UPDATE dce_chat_sessions SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and cascade delete its messages.
        """
        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM dce_chat_sessions WHERE id = %s", (session_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
