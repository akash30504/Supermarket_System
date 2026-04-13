"""
seeder.py
---------
Generates simulated supermarket data:
  - ~1,000 product records across categories
  - ~100,000 transaction records
Used for performance benchmarking and testing as described in the PID.
"""

import random
import time
import sqlite3
from modules.database import get_connection, DB_PATH

# ── Product Templates ─────────────────────────────────────────────────────────
CATEGORIES = {
    "Bakery":       ["Sourdough Bread", "Croissant", "Bagel", "Baguette", "Rye Loaf",
                     "Whole Wheat Bread", "Ciabatta", "Brioche", "Focaccia", "Pita Bread"],
    "Dairy":        ["Whole Milk", "Skimmed Milk", "Greek Yogurt", "Cheddar Cheese",
                     "Mozzarella", "Butter", "Cream Cheese", "Sour Cream", "Kefir", "Feta"],
    "Beverages":    ["Orange Juice", "Apple Juice", "Sparkling Water", "Green Tea",
                     "Black Coffee", "Energy Drink", "Lemonade", "Coconut Water", "Iced Tea", "Smoothie"],
    "Snacks":       ["Potato Chips", "Popcorn", "Granola Bar", "Trail Mix", "Rice Cakes",
                     "Pretzels", "Nachos", "Crackers", "Nuts Mix", "Dark Chocolate"],
    "Produce":      ["Banana", "Apple", "Carrot", "Broccoli", "Spinach", "Tomato",
                     "Avocado", "Bell Pepper", "Cucumber", "Lettuce"],
    "Meat":         ["Chicken Breast", "Ground Beef", "Pork Ribs", "Salmon Fillet",
                     "Turkey Mince", "Beef Steak", "Lamb Chops", "Tuna Steak", "Sausages", "Bacon"],
    "Frozen":       ["Frozen Pizza", "Ice Cream", "Frozen Peas", "Fish Fingers",
                     "Frozen Chips", "Frozen Waffles", "Edamame", "Frozen Berries", "Frozen Lasagna", "Sorbet"],
    "Pantry":       ["Pasta", "White Rice", "Olive Oil", "Soy Sauce", "Tomato Sauce",
                     "Honey", "Peanut Butter", "Flour", "Sugar", "Salt"],
    "Household":    ["Dish Soap", "Laundry Detergent", "Toilet Paper", "Paper Towels",
                     "Bin Bags", "Sponges", "Cling Film", "Foil Wrap", "Bleach", "Air Freshener"],
    "Personal Care":["Shampoo", "Conditioner", "Toothpaste", "Body Wash", "Deodorant",
                     "Face Moisturizer", "Lip Balm", "Sunscreen", "Hand Cream", "Razors"],
}

PRICE_RANGES = {
    "Bakery":        (0.80, 4.50),
    "Dairy":         (0.60, 6.00),
    "Beverages":     (0.90, 4.00),
    "Snacks":        (0.80, 3.50),
    "Produce":       (0.30, 3.00),
    "Meat":          (3.00, 18.00),
    "Frozen":        (1.50, 9.00),
    "Pantry":        (0.50, 8.00),
    "Household":     (0.80, 12.00),
    "Personal Care": (1.50, 15.00),
}


def seed_products(target: int = 1000) -> int:
    """Seed approximately `target` product records."""
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if existing >= target:
        print(f"[Seeder] Products already seeded ({existing} records). Skipping.")
        conn.close()
        return existing

    products = []
    cat_list = list(CATEGORIES.keys())
    per_cat  = target // len(cat_list)

    for category in cat_list:
        base_names = CATEGORIES[category]
        pmin, pmax = PRICE_RANGES[category]
        for i in range(per_cat):
            base = base_names[i % len(base_names)]
            # Add variant suffix to avoid duplicate names
            variant = f"{base} #{i // len(base_names) + 1}" if i >= len(base_names) else base
            price    = round(random.uniform(pmin, pmax), 2)
            stock    = random.randint(20, 500)
            reorder  = random.randint(5, 30)
            products.append((variant, category, price, stock, reorder))

    conn.executemany(
        "INSERT OR IGNORE INTO products (product_name, category, unit_price, stock_qty, reorder_level) "
        "VALUES (?,?,?,?,?)",
        products
    )
    conn.commit()
    new_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()
    print(f"[Seeder] Products seeded: {new_count} records.")
    return new_count


def seed_transactions(target: int = 100_000, batch_size: int = 5000) -> int:
    """
    Seed approximately `target` transaction records using batch inserts.
    Does NOT deduct stock (historical data simulation).
    Uses a default cashier_id=1 (admin) for seeded data.
    """
    conn = get_connection()
    existing = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if existing >= target:
        print(f"[Seeder] Transactions already seeded ({existing} records). Skipping.")
        conn.close()
        return existing

    product_rows = conn.execute(
        "SELECT product_id, unit_price FROM products"
    ).fetchall()
    if not product_rows:
        print("[Seeder] No products found. Run seed_products() first.")
        conn.close()
        return 0

    cashier_ids = [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM users WHERE role='cashier'"
    ).fetchall()] or [1]

    needed   = target - existing
    inserted = 0
    start    = time.time()

    print(f"[Seeder] Seeding {needed:,} transactions (batch={batch_size:,})...")

    # Use direct SQLite connection for speed (bypass ORM layer)
    raw_conn = sqlite3.connect(DB_PATH)
    raw_conn.execute("PRAGMA journal_mode=WAL")
    raw_conn.execute("PRAGMA synchronous=NORMAL")

    import datetime
    base_time = datetime.datetime(2026, 2, 27, 8, 0, 0)
    seconds_per_txn = (30 * 24 * 3600) / target  # spread over 30 days (Feb 27 – Mar 29 2026)

    while inserted < needed:
        batch = []
        for j in range(min(batch_size, needed - inserted)):
            p    = random.choice(product_rows)
            qty  = random.randint(1, 10)
            cid  = random.choice(cashier_ids)
            txn_time = base_time + datetime.timedelta(
                seconds=(inserted + j) * seconds_per_txn
            )
            batch.append((p["product_id"], cid, qty, p["unit_price"],
                          txn_time.strftime("%Y-%m-%d %H:%M:%S")))

        raw_conn.executemany(
            "INSERT INTO transactions (product_id, cashier_id, quantity, unit_price, txn_time) "
            "VALUES (?,?,?,?,?)",
            batch
        )
        raw_conn.commit()
        inserted += len(batch)
        elapsed = time.time() - start
        rate    = inserted / elapsed if elapsed > 0 else 0
        print(f"  Inserted {inserted:>8,}/{needed:,}  ({rate:,.0f} rows/sec)", end="\r")

    raw_conn.close()
    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    print(f"\n[Seeder] Transactions seeded: {total:,} records in {time.time()-start:.1f}s.")
    return total


def run_full_seed(products: int = 1000, transactions: int = 100_000):
    """Seed both products and transactions."""
    print("\n[Seeder] Starting full data seed...")
    seed_products(products)
    seed_transactions(transactions)
    print("[Seeder] Full seed complete.\n")


if __name__ == "__main__":
    from modules.database import initialize_database
    initialize_database()
    run_full_seed()
