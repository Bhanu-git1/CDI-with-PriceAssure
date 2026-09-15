import hashlib
import os
import secrets
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("auth-service")

class AuthService:
    """
    Handles user management, registration, password hashing/verification,
    and authentication against the MySQL 'users' table.
    """

    def __init__(self, db_service):
        self.db_service = db_service
        self._initialized = False

    def _hash_password(self, password: str, salt: Optional[str] = None) -> str:
        """
        Hashes a password using PBKDF2 HMAC SHA-256 with a unique salt.
        Returns formatted string 'salt$hash'.
        """
        if not salt:
            salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return f"{salt}${key.hex()}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """
        Verifies a password against a stored 'salt$hash' or raw SHA256 string.
        """
        if not stored_hash:
            return False
        try:
            if '$' in stored_hash:
                salt, key_hex = stored_hash.split('$', 1)
                expected_hash = self._hash_password(password, salt=salt)
                return secrets.compare_digest(stored_hash, expected_hash)
            else:
                # Fallback for simple SHA-256 hash if any existing
                plain_sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
                return secrets.compare_digest(stored_hash, plain_sha)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False

    def init_db(self):
        """
        Ensures the 'users' table exists and contains all required columns:
        username, first_name, last_name, password_hash, role.
        Also cleans up any restrictive legacy constraints on email/full_name.
        """
        if self._initialized:
            return

        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()

            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    is_active TINYINT(1) DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_username (username)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Check existing columns to add any missing columns safely if table already existed
            cursor.execute("DESCRIBE users;")
            existing_columns = [col[0].lower() for col in cursor.fetchall()]

            if "username" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(100) NULL UNIQUE;")
            if "first_name" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN first_name VARCHAR(100) NULL;")
            if "last_name" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN last_name VARCHAR(100) NULL;")
            if "password_hash" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL;")
            if "role" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(50) NULL;")
            if "updated_at" not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;")

            # If legacy email column exists, make it nullable and drop unique index if present
            if "email" in existing_columns:
                try:
                    cursor.execute("ALTER TABLE users MODIFY COLUMN email VARCHAR(255) NULL DEFAULT NULL;")
                except Exception as e:
                    logger.debug(f"Email modify notice: {e}")
                
                try:
                    cursor.execute("ALTER TABLE users DROP INDEX ix_users_email;")
                except Exception:
                    pass

                # Update any empty string emails to NULL so they don't trigger unique index collisions
                try:
                    cursor.execute("UPDATE users SET email = NULL WHERE email = '';")
                except Exception:
                    pass

            if "full_name" in existing_columns:
                try:
                    cursor.execute("ALTER TABLE users MODIFY COLUMN full_name VARCHAR(100) NULL DEFAULT NULL;")
                except Exception:
                    pass

            conn.commit()
            self._initialized = True
            logger.info("Successfully verified and initialized 'users' table in MySQL.")
        except Exception as e:
            logger.error(f"Failed to initialize 'users' table in MySQL: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def check_username_exists(self, username: str) -> bool:
        """
        Checks if a username already exists in the users table (case-insensitive).
        """
        if not username or not username.strip():
            return False

        self.init_db()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1",
                (username.strip(),)
            )
            row = cursor.fetchone()
            return row is not None
        except Exception as e:
            logger.error(f"Error checking username existence: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def register_user(
        self,
        first_name: str,
        last_name: str,
        username: str,
        password: str,
        confirm_password: str,
        role: str
    ) -> Dict[str, Any]:
        """
        Validates inputs, checks username uniqueness, confirms matching passwords,
        and saves the user in MySQL.
        """
        self.init_db()

        # 1. Validation checks
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        username = (username or "").strip()
        password = password or ""
        confirm_password = confirm_password or ""
        role = (role or "").strip()

        if not first_name:
            return {"success": False, "error": "First Name is required."}
        if not last_name:
            return {"success": False, "error": "Last Name is required."}
        if not username:
            return {"success": False, "error": "Username is required."}
        if not role:
            return {"success": False, "error": "Role is required."}
        if not password:
            return {"success": False, "error": "Password is required."}
        if len(password) < 4:
            return {"success": False, "error": "Password must be at least 4 characters."}

        # 2. Check Password vs Confirm Password
        if password != confirm_password:
            return {"success": False, "error": "Password and Confirm Password do not match."}

        # 3. Check Username availability
        if self.check_username_exists(username):
            return {
                "success": False,
                "error": f"Username '{username}' is already taken. Please choose a different username."
            }

        # 4. Hash Password and Insert
        password_hash = self._hash_password(password)
        full_name = f"{first_name} {last_name}".strip()
        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor()
            
            # Check if columns like full_name / email exist to supply safe values
            cursor.execute("DESCRIBE users;")
            cols = [c[0].lower() for c in cursor.fetchall()]

            fields = ["username", "first_name", "last_name", "password_hash", "role", "is_active", "created_at", "updated_at"]
            placeholders = ["%s", "%s", "%s", "%s", "%s", "1", "NOW()", "NOW()"]
            values = [username, first_name, last_name, password_hash, role]

            if "full_name" in cols:
                fields.append("full_name")
                placeholders.append("%s")
                values.append(full_name)

            if "email" in cols:
                fields.append("email")
                placeholders.append("%s")
                values.append(None)

            sql = f"INSERT INTO users ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cursor.execute(sql, tuple(values))
            conn.commit()
            new_id = cursor.lastrowid
            logger.info(f"Successfully registered new user: {username} (ID: {new_id}, Role: {role})")

            return {
                "success": True,
                "user": {
                    "id": new_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name,
                    "role": role
                }
            }
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Failed to register user in MySQL: {e}")
            err_str = str(e).lower()
            if "username" in err_str and ("duplicate" in err_str or "1062" in err_str):
                return {
                    "success": False,
                    "error": f"Username '{username}' already exists. Please choose a different username."
                }
            return {"success": False, "error": f"Database error during registration: {str(e)}"}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticates a user by username and password.
        """
        self.init_db()
        username = (username or "").strip()
        password = password or ""

        if not username or not password:
            return {"success": False, "error": "Username and password are required."}

        conn = None
        cursor = None
        try:
            conn = self.db_service.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, username, first_name, last_name, password_hash, role, is_active
                FROM users
                WHERE LOWER(username) = LOWER(%s)
                LIMIT 1
                """,
                (username,)
            )
            user_row = cursor.fetchone()

            if not user_row:
                return {"success": False, "error": "Invalid username or password."}

            if not self._verify_password(password, user_row.get("password_hash", "")):
                return {"success": False, "error": "Invalid username or password."}

            first_name = user_row.get("first_name") or ""
            last_name = user_row.get("last_name") or ""
            full_name = f"{first_name} {last_name}".strip() or user_row.get("username")

            return {
                "success": True,
                "user": {
                    "id": user_row.get("id"),
                    "username": user_row.get("username"),
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name,
                    "role": user_row.get("role") or "User"
                }
            }
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return {"success": False, "error": f"Authentication error: {str(e)}"}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
