"""
inventory.py
------------
Product and Inventory Management Module.
Handles CRUD operations for products, stock adjustments, and low-stock alerts.
"""

from modules.database import get_connection
from modules.auth import require_permission, get_session, _audit
from modules.alerts import send_low_stock_email

# ── Products ─────────────────────────────────────────────────────────────────

def add_product(product_name: str, category: str, unit_price: float,
                stock_qty: int, reorder_level: int = 10) -> int:
    """Add a new product. Returns new product_id."""
    require_permission("manage_products")
    if unit_price < 0 or stock_qty < 0:
        raise ValueError("Price and quantity must be non-negative.")
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO products (product_name, category, unit_price, stock_qty, reorder_level) "
            "VALUES (?,?,?,?,?)",
            (product_name, category, unit_price, stock_qty, reorder_level)
        )
        pid = cursor.lastrowid
        session = get_session()
        _audit(conn, session.user_id, "ADD_PRODUCT",
               f"ID={pid} Name='{product_name}' Price={unit_price} Qty={stock_qty}")
        conn.commit()
        print(f"[Inventory] Product added: ID={pid}, '{product_name}'")
        return pid
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_product(product_id: int, **kwargs):
    """
    Update product fields. Allowed fields: product_name, category, unit_price,
    reorder_level.
    """
    require_permission("manage_products")
    allowed = {"product_name", "category", "unit_price", "reorder_level"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        raise ValueError("No valid fields provided for update.")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [product_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE products SET {set_clause} WHERE product_id=?", values)
        session = get_session()
        _audit(conn, session.user_id, "UPDATE_PRODUCT",
               f"ID={product_id} Fields={list(updates.keys())}")
        conn.commit()
        print(f"[Inventory] Product {product_id} updated: {updates}")
    finally:
        conn.close()


def delete_product(product_id: int):
    """Admin-only: delete a product (no linked transactions)."""
    require_permission("delete_product")
    conn = get_connection()
    try:
        txn = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE product_id=?", (product_id,)
        ).fetchone()[0]
        if txn > 0:
            raise ValueError(f"Cannot delete product {product_id}: has {txn} transactions.")
        conn.execute("DELETE FROM products WHERE product_id=?", (product_id,))
        session = get_session()
        _audit(conn, session.user_id, "DELETE_PRODUCT", f"ID={product_id}")
        conn.commit()
        print(f"[Inventory] Product {product_id} deleted.")
    finally:
        conn.close()


def get_product(product_id: int) -> dict:
    """Fetch a single product by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM products WHERE product_id=?", (product_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"Product ID {product_id} not found.")
    return dict(row)


def list_products(category: str = None) -> list:
    """List all products, optionally filtered by category."""
    conn = get_connection()
    if category:
        rows = conn.execute(
            "SELECT * FROM products WHERE category=? ORDER BY product_name", (category,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM products ORDER BY category, product_name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_products(keyword: str) -> list:
    """Search products by name or category (case-insensitive)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE LOWER(product_name) LIKE ? OR LOWER(category) LIKE ? "
        "ORDER BY product_name",
        (f"%{keyword.lower()}%", f"%{keyword.lower()}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stock Management ──────────────────────────────────────────────────────────

def adjust_stock(product_id: int, delta: int, reason: str = "manual adjustment"):
    """
    Increase (delta > 0) or decrease (delta < 0) stock for a product.
    Used for restocking and corrections.
    """
    require_permission("manage_inventory")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT stock_qty FROM products WHERE product_id=?", (product_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Product {product_id} not found.")
        new_qty = row["stock_qty"] + delta
        if new_qty < 0:
            raise ValueError(f"Insufficient stock. Current: {row['stock_qty']}, Requested change: {delta}")
        conn.execute(
            "UPDATE products SET stock_qty=? WHERE product_id=?", (new_qty, product_id)
        )
        session = get_session()
        _audit(conn, session.user_id, "STOCK_ADJUST",
               f"ProductID={product_id} Delta={delta} NewQty={new_qty} Reason={reason}")
        conn.commit()
        print(f"[Inventory] Stock adjusted: Product {product_id} → {new_qty} units ({reason})")
        return new_qty
    finally:
        conn.close()


def _deduct_stock_unsafe(conn, product_id: int, quantity: int,
                         txn_id: int = None):
    """
    Internal: deduct stock within an existing connection/transaction.
    Raises ValueError if insufficient stock.
    Sends email alert if stock falls to or below 50 units.
    """
    row = conn.execute(
        "SELECT stock_qty FROM products WHERE product_id=?", (product_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Product {product_id} not found.")
    if row["stock_qty"] < quantity:
        raise ValueError(
            f"Insufficient stock for product {product_id}. "
            f"Available: {row['stock_qty']}, Required: {quantity}"
        )
    conn.execute(
        "UPDATE products SET stock_qty = stock_qty - ? WHERE product_id=?",
        (quantity, product_id)
    )
    # Check if stock dropped to or below 50 units after deduction
    updated = conn.execute(
        "SELECT product_name, stock_qty, reorder_level FROM products WHERE product_id=?",
        (product_id,)
    ).fetchone()
    if updated and updated["stock_qty"] <= 50:
        send_low_stock_email(
            product_name  = updated["product_name"],
            stock_qty     = updated["stock_qty"],
            reorder_level = updated["reorder_level"],
            product_id    = product_id,
            txn_id        = txn_id,
            quantity_sold = quantity,
        )

LOW_STOCK_THRESHOLD = 50   # alert when stock falls at or below this number

def get_low_stock_products(threshold: int = None) -> list:
    """Return products with stock at or below threshold (default: 50 units)."""
    conn = get_connection()
    limit = threshold if threshold is not None else LOW_STOCK_THRESHOLD
    rows = conn.execute(
        "SELECT * FROM products WHERE stock_qty <= ? ORDER BY stock_qty",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_summary() -> dict:
    """Return aggregate inventory statistics."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*)                          AS total_products,
            SUM(stock_qty)                    AS total_units,
            SUM(stock_qty * unit_price)       AS total_stock_value,
            COUNT(CASE WHEN stock_qty=0 THEN 1 END) AS out_of_stock,
            COUNT(CASE WHEN stock_qty <= 50 THEN 1 END) AS low_stock_count
        FROM products
    """).fetchone()
    conn.close()
    return dict(row)