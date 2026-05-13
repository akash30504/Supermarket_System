import sqlite3
import os
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "supermarket.db")


def get_connection():
    """Return a thread-safe SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Write-Ahead Logging for concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(password: str, salt: str = None):
    """Hash a password with SHA-256 + salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify a plaintext password against stored hash."""
    hashed, _ = hash_password(password, salt)
    return hashed == stored_hash


def initialize_database():
    """Create all tables and seed default data."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    # ── Users ──────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT    UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt      TEXT    NOT NULL,
            role      TEXT    NOT NULL CHECK(role IN ('admin','manager','cashier')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active  INTEGER DEFAULT 1
        )
    """)

    # ── Products ───────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            unit_price   REAL    NOT NULL CHECK(unit_price >= 0),
            stock_qty    INTEGER NOT NULL DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Transactions ───────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            txn_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER NOT NULL REFERENCES products(product_id),
            cashier_id   INTEGER NOT NULL REFERENCES users(user_id),
            quantity     INTEGER NOT NULL CHECK(quantity > 0),
            unit_price   REAL    NOT NULL,
            total_value  REAL    GENERATED ALWAYS AS (quantity * unit_price) STORED,
            txn_time     DATETIME DEFAULT CURRENT_TIMESTAMP,
            status       TEXT DEFAULT 'completed'
        )
    """)

    # ── Audit Log ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            action    TEXT    NOT NULL,
            details   TEXT,
            ip_addr   TEXT    DEFAULT 'localhost',
            log_time  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # ── Seed default users if table is empty ──────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_users = [
            ("admin",   "Admin@123",   "admin"),
            ("manager", "Manager@123", "manager"),
            ("cashier1","Cashier@123", "cashier"),
        ]
        for uname, pwd, role in default_users:
            h, s = hash_password(pwd)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt, role) VALUES (?,?,?,?)",
                (uname, h, s, role)
            )
        conn.commit()
        print("[DB] Default users seeded.")

    conn.close()
    print(f"[DB] Database initialized at: {DB_PATH}")


if __name__ == "__main__":
    initialize_database()
