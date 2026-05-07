"""
fix_products.py
---------------
Run this script ONCE inside your Supermarket_System folder.
It updates all 1000 product names and prices to correct LKR values.
Your transactions, audit log, and all other data are NOT touched.

How to run:
    python fix_products.py
"""

import sqlite3
import random
import os

# ── Find the database ──────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "supermarket.db")
if not os.path.exists(DB_PATH):
    print("[ERROR] Cannot find data/supermarket.db")
    print("        Make sure you are running this script from inside Supermarket_System/")
    exit(1)

# ── Your correct product names (exactly as you provided) ──────────────────────
CORRECT_NAMES = {
    "Bakery":        ["Hot Dog", "Croissant", "Bagel", "Eclair", "Cookie",
                      "Donut", "Ciabatta", "Muffin", "Brownie", "Pizza"],
    "Dairy":         ["Fresh Milk", "Chocolate Milk", "Yogurt", "Cheese",
                      "Mozzarella", "Butter", "Cream Cheese", "Sour Cream", "Kefir", "Feta"],
    "Beverages":     ["Orange Juice", "Apple Juice", "Frappe", "Green Tea",
                      "Black Coffee", "Hot Chocolate", "Lemonade", "Mocha", "Iced Tea", "Smoothie"],
    "Snacks":        ["Chips", "Popcorn", "Patties", "Fish Rolls", "Rice Cakes",
                      "Pretzels", "Nachos", "Crackers", "Nuts Mix", "Dark Chocolate"],
    "Produce":       ["Banana", "Apple", "Carrot", "Beets", "Spinach", "Tomato",
                      "Avocado", "Bell Pepper", "Cucumber", "Grapes"],
    "Meat":          ["Chicken Breast", "Ground Beef", "Pork Ribs", "Salmon Fillet",
                      "Turkey Mince", "Beef Steak", "Prawns", "Tuna Steak", "Sausages", "Bacon"],
    "Frozen":        ["Frozen Pizza", "Ice Cream", "Popsicles", "Fish Fingers",
                      "Frozen Chips", "Frozen Waffles", "Meatballs", "Ice Cones",
                      "Frozen Lasagna", "Ice Cups"],
    "Pantry":        ["Pasta", "White Rice", "Olive Oil", "Soy Sauce", "Tomato Sauce",
                      "Honey", "Peanut Butter", "Flour", "Sugar", "Salt"],
    "Household":     ["Soap", "Detergent", "Toilet Paper", "Paper Towels",
                      "Bin Bags", "Sponges", "Mop", "Foil Wrap", "Bleach", "Air Freshener"],
    "Personal Care": ["Shampoo", "Conditioner", "Toothpaste", "Body Wash", "Deodorant",
                      "Face Moisturizer", "Lip Balm", "Sunscreen", "Hand Cream", "Razors"],
}

# ── Realistic LKR price ranges per category ───────────────────────────────────
LKR_PRICES = {
    "Bakery":        (150,   850),
    "Dairy":         (120,  1200),
    "Beverages":     (180,   900),
    "Snacks":        (150,   750),
    "Produce":       ( 60,   600),
    "Meat":          (600,  3500),
    "Frozen":        (300,  1800),
    "Pantry":        (100,  1600),
    "Household":     (150,  2400),
    "Personal Care": (300,  3000),
}

random.seed(42)   # fixed seed → same prices every run (reproducible)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print("=" * 55)
print("  SuperMart — Fix Product Names & Prices to LKR")
print("=" * 55)
print(f"  Database: {DB_PATH}")
print()

total_updated = 0

for category, base_names in CORRECT_NAMES.items():
    pmin, pmax = LKR_PRICES[category]
    base_count = len(base_names)   # always 10

    # Get all product IDs in this category, ordered by product_id
    rows = conn.execute(
        "SELECT product_id FROM products WHERE category = ? ORDER BY product_id",
        (category,)
    ).fetchall()

    if not rows:
        print(f"  [WARN] No products found for category: {category}")
        continue

    updates = []
    for idx, row in enumerate(rows):
        pid        = row["product_id"]
        base       = base_names[idx % base_count]
        variant_no = idx // base_count + 1
        # First 10 have no suffix, #11–20 get #2, #21–30 get #3, etc.
        new_name   = base if idx < base_count else f"{base} #{variant_no}"
        new_price  = round(random.uniform(pmin, pmax), 2)
        updates.append((new_name, new_price, pid))

    conn.executemany(
        "UPDATE products SET product_name = ?, unit_price = ? WHERE product_id = ?",
        updates
    )
    total_updated += len(updates)
    print(f"  ✔  {category:<15} — {len(updates)} products updated  "
          f"(LKR {pmin:>5} – {pmax:>5})")

conn.commit()

# ── Quick verification ────────────────────────────────────────────────────────
print()
print("  Sample check — first 3 products per category:")
print("  " + "-" * 50)
for category in CORRECT_NAMES:
    samples = conn.execute(
        "SELECT product_name, unit_price FROM products "
        "WHERE category = ? ORDER BY product_id LIMIT 3",
        (category,)
    ).fetchall()
    for s in samples:
        print(f"  {category:<15}  {s['product_name']:<22}  LKR {s['unit_price']:>8.2f}")

conn.close()

print()
print("=" * 55)
print(f"  Done! {total_updated} products updated.")
print("  Your transactions and all other data are untouched.")
print("  Refresh your browser to see the new names and prices.")
print("=" * 55)