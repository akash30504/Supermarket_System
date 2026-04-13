"""
auth.py
-------
Authentication and Role-Based Access Control (RBAC) module.
Handles login, session management, and permission enforcement.

Roles & Permissions:
  admin   → all operations
  manager → view reports, manage products/inventory, view transactions
  cashier → process transactions, view own transactions
"""

from modules.database import get_connection, verify_password, hash_password
from datetime import datetime

# ── Permission Matrix ────────────────────────────────────────────────────────
PERMISSIONS = {
    "admin": {
        "manage_users", "manage_products", "process_transaction",
        "view_reports", "view_all_transactions", "manage_inventory",
        "view_audit_log", "run_benchmarks", "delete_product"
    },
    "manager": {
        "manage_products", "view_reports", "view_all_transactions",
        "manage_inventory", "run_benchmarks"
    },
    "cashier": {
        "process_transaction", "view_own_transactions", "view_products"
    },
}


class AuthSession:
    """Represents an authenticated user session."""

    def __init__(self, user_id: int, username: str, role: str):
        self.user_id   = user_id
        self.username  = username
        self.role      = role
        self.login_time = datetime.now()

    def has_permission(self, permission: str) -> bool:
        return permission in PERMISSIONS.get(self.role, set())

    def __repr__(self):
        return f"<Session user={self.username} role={self.role}>"


# ── Global current session ───────────────────────────────────────────────────
_current_session: AuthSession = None


def login(username: str, password: str) -> AuthSession:
    """
    Authenticate a user. Returns AuthSession on success, raises ValueError on failure.
    Also writes to audit_log.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id, username, password_hash, salt, role, is_active "
            "FROM users WHERE username = ?", (username,)
        )
        row = cursor.fetchone()

        if row is None:
            _audit(conn, None, "LOGIN_FAILED", f"Unknown user: {username}")
            raise ValueError("Invalid username or password.")

        if not row["is_active"]:
            _audit(conn, row["user_id"], "LOGIN_BLOCKED", "Account disabled")
            raise ValueError("Account is disabled. Contact administrator.")

        if not verify_password(password, row["password_hash"], row["salt"]):
            _audit(conn, row["user_id"], "LOGIN_FAILED", "Wrong password")
            raise ValueError("Invalid username or password.")

        global _current_session
        _current_session = AuthSession(row["user_id"], row["username"], row["role"])
        _audit(conn, row["user_id"], "LOGIN_SUCCESS", f"Role: {row['role']}")
        conn.commit()
        return _current_session

    finally:
        conn.close()


def logout():
    """Log out the current session."""
    global _current_session
    if _current_session:
        conn = get_connection()
        _audit(conn, _current_session.user_id, "LOGOUT",
               f"Session duration: {(datetime.now() - _current_session.login_time).seconds}s")
        conn.commit()
        conn.close()
    _current_session = None
    print("[Auth] Logged out successfully.")


def get_session() -> AuthSession:
    """Return current active session or None."""
    return _current_session


def require_permission(permission: str):
    """Raise PermissionError if current session lacks the required permission."""
    if _current_session is None:
        raise PermissionError("Not logged in.")
    if not _current_session.has_permission(permission):
        conn = get_connection()
        _audit(conn, _current_session.user_id, "ACCESS_DENIED",
               f"Permission required: {permission}")
        conn.commit()
        conn.close()
        raise PermissionError(
            f"Access denied. '{permission}' requires role: "
            + str([r for r, p in PERMISSIONS.items() if permission in p])
        )


def create_user(username: str, password: str, role: str):
    """Admin-only: create a new user."""
    require_permission("manage_users")
    if role not in PERMISSIONS:
        raise ValueError(f"Invalid role '{role}'. Choose from: {list(PERMISSIONS.keys())}")
    h, s = hash_password(password)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?,?,?,?)",
            (username, h, s, role)
        )
        _audit(conn, _current_session.user_id, "CREATE_USER", f"Created: {username} [{role}]")
        conn.commit()
        print(f"[Auth] User '{username}' created with role '{role}'.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_users():
    """Admin/manager: list all users."""
    require_permission("manage_users")
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, username, role, is_active, created_at FROM users ORDER BY user_id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_user(username: str):
    """Admin-only: deactivate a user account."""
    require_permission("manage_users")
    conn = get_connection()
    conn.execute("UPDATE users SET is_active=0 WHERE username=?", (username,))
    _audit(conn, _current_session.user_id, "DEACTIVATE_USER", f"Deactivated: {username}")
    conn.commit()
    conn.close()
    print(f"[Auth] User '{username}' deactivated.")


# ── Internal helper ───────────────────────────────────────────────────────────
def _audit(conn, user_id, action, details=""):
    conn.execute(
        "INSERT INTO audit_log (user_id, action, details) VALUES (?,?,?)",
        (user_id, action, details)
    )
