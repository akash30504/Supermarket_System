"""
tests/test_system.py
---------------------
Unit and integration tests for the Secure Supermarket System.
Run with:  python -m pytest tests/ -v
       or: python tests/test_system.py
"""

import sys
import os
import gc
import time
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Isolated test DB ──────────────────────────────────────────────────────────
import modules.database as db_module

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_supermarket.db")
db_module.DB_PATH = TEST_DB   # Redirect to test DB before importing anything else

from modules.database  import initialize_database, hash_password, verify_password
from modules.auth      import login, logout, get_session, create_user, PERMISSIONS
from modules.inventory import (add_product, list_products, search_products,
                                adjust_stock, get_inventory_summary, get_low_stock_products)
from modules.transactions import (process_transaction, process_batch_sequential,
                                   process_batch_threaded, list_transactions)
from modules.analytics import sales_summary, inventory_report


# ── Helpers ───────────────────────────────────────────────────────────────────

def close_all_connections():
    """Force close all SQLite connections — required on Windows."""
    import modules.auth as auth_mod
    auth_mod._current_session = None
    gc.collect()
    time.sleep(0.05)


def setup_db():
    """Initialize fresh test DB — Windows compatible."""
    close_all_connections()
    if os.path.exists(TEST_DB):
        for attempt in range(10):
            try:
                os.remove(TEST_DB)
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.15)
    initialize_database()


def admin_login():
    return login("admin", "Admin@123")


def cashier_login():
    return login("cashier1", "Cashier@123")


# ── Test Classes ──────────────────────────────────────────────────────────────

class TestDatabase(unittest.TestCase):
    def setUp(self):
        setup_db()

    def tearDown(self):
        close_all_connections()

    def test_db_created(self):
        self.assertTrue(os.path.exists(TEST_DB))

    def test_default_users_seeded(self):
        conn = db_module.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        self.assertEqual(count, 3)

    def test_hash_and_verify(self):
        h, s = hash_password("MySecret@123")
        self.assertTrue(verify_password("MySecret@123", h, s))
        self.assertFalse(verify_password("WrongPass", h, s))

    def test_unique_salts(self):
        _, s1 = hash_password("same")
        _, s2 = hash_password("same")
        self.assertNotEqual(s1, s2)


class TestAuth(unittest.TestCase):
    def setUp(self):
        setup_db()
        logout()

    def tearDown(self):
        logout()
        close_all_connections()

    def test_valid_login(self):
        session = admin_login()
        self.assertEqual(session.role, "admin")
        self.assertEqual(session.username, "admin")

    def test_invalid_password(self):
        with self.assertRaises(ValueError):
            login("admin", "wrongpassword")

    def test_invalid_username(self):
        with self.assertRaises(ValueError):
            login("nobody", "pass")

    def test_admin_has_all_permissions(self):
        admin_login()
        session = get_session()
        for perm in PERMISSIONS["admin"]:
            self.assertTrue(session.has_permission(perm))

    def test_cashier_cannot_view_reports(self):
        cashier_login()
        session = get_session()
        self.assertFalse(session.has_permission("view_reports"))

    def test_create_user_requires_admin(self):
        cashier_login()
        with self.assertRaises(PermissionError):
            create_user("newuser", "Pass@123", "cashier")

    def test_create_user_as_admin(self):
        admin_login()
        create_user("testcashier", "Pass@123", "cashier")
        conn = db_module.get_connection()
        users = conn.execute(
            "SELECT * FROM users WHERE username='testcashier'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(users)

    def test_session_cleared_on_logout(self):
        admin_login()
        logout()
        self.assertIsNone(get_session())


class TestInventory(unittest.TestCase):
    def setUp(self):
        setup_db()
        admin_login()

    def tearDown(self):
        logout()
        close_all_connections()

    def test_add_product(self):
        pid = add_product("Test Bread", "Bakery", 1.50, 100, 10)
        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)

    def test_list_products(self):
        add_product("Test Milk", "Dairy", 0.99, 50, 5)
        products = list_products()
        self.assertGreater(len(products), 0)

    def test_search_products(self):
        add_product("Organic Apple", "Produce", 0.60, 200, 20)
        results = search_products("apple")
        self.assertTrue(any("Apple" in r["product_name"] for r in results))

    def test_search_no_match(self):
        results = search_products("xyznonexistent999")
        self.assertEqual(results, [])

    def test_adjust_stock_increase(self):
        pid = add_product("Rice Bag", "Pantry", 2.00, 50, 10)
        new_qty = adjust_stock(pid, 25, "restock")
        self.assertEqual(new_qty, 75)

    def test_adjust_stock_decrease(self):
        pid = add_product("Pasta Pack", "Pantry", 1.20, 30, 5)
        new_qty = adjust_stock(pid, -10, "correction")
        self.assertEqual(new_qty, 20)

    def test_adjust_stock_below_zero_fails(self):
        pid = add_product("Butter", "Dairy", 1.80, 5, 2)
        with self.assertRaises(ValueError):
            adjust_stock(pid, -100)

    def test_inventory_summary_keys(self):
        summary = get_inventory_summary()
        self.assertIn("total_products", summary)
        self.assertIn("total_stock_value", summary)

    def test_low_stock(self):
        pid = add_product("Rare Item", "Snacks", 5.00, 1, 10)
        low = get_low_stock_products()
        self.assertTrue(any(p["product_id"] == pid for p in low))

    def test_negative_price_rejected(self):
        with self.assertRaises(ValueError):
            add_product("Bad Product", "Misc", -1.00, 10)


class TestTransactions(unittest.TestCase):
    def setUp(self):
        setup_db()
        admin_login()
        self._pid = add_product("Test Cola", "Beverages", 1.50, 500, 10)

    def tearDown(self):
        logout()
        close_all_connections()

    def test_single_transaction(self):
        result = process_transaction(self._pid, 3)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["quantity"], 3)
        self.assertAlmostEqual(result["total_value"], 4.50)

    def test_transaction_deducts_stock(self):
        from modules.inventory import get_product
        before = get_product(self._pid)["stock_qty"]
        process_transaction(self._pid, 10)
        after = get_product(self._pid)["stock_qty"]
        self.assertEqual(after, before - 10)

    def test_insufficient_stock_raises(self):
        pid = add_product("Scarce Item", "Bakery", 2.00, 2, 1)
        with self.assertRaises(ValueError):
            process_transaction(pid, 100)

    def test_batch_sequential(self):
        batch = [{"product_id": self._pid, "quantity": 1} for _ in range(5)]
        result = process_batch_sequential(batch)
        self.assertEqual(result["success"], 5)
        self.assertEqual(result["mode"], "sequential")

    def test_batch_threaded(self):
        batch = [{"product_id": self._pid, "quantity": 1} for _ in range(5)]
        result = process_batch_threaded(batch, num_threads=2)
        self.assertGreater(result["success"], 0)
        self.assertIn("threaded", result["mode"])

    def test_batch_has_throughput(self):
        batch = [{"product_id": self._pid, "quantity": 1} for _ in range(3)]
        result = process_batch_sequential(batch)
        self.assertGreater(result["throughput"], 0)

    def test_list_transactions_returns_list(self):
        process_transaction(self._pid, 1)
        txns = list_transactions(limit=5)
        self.assertIsInstance(txns, list)
        self.assertGreater(len(txns), 0)

    def test_cashier_sees_only_own_transactions(self):
        logout()
        cashier_login()
        txns = list_transactions(limit=50)
        session = get_session()
        for t in txns:
            self.assertEqual(t["cashier_id"], session.user_id)


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        setup_db()
        admin_login()
        pid = add_product("Analytics Product", "Produce", 2.00, 1000, 5)
        for _ in range(10):
            process_transaction(pid, 2)

    def tearDown(self):
        logout()
        close_all_connections()

    def test_sales_summary_keys(self):
        summary = sales_summary()
        self.assertIn("total_transactions", summary)
        self.assertIn("total_revenue", summary)
        self.assertGreater(summary["total_transactions"], 0)

    def test_sales_summary_cashier_blocked(self):
        logout()
        cashier_login()
        with self.assertRaises(PermissionError):
            sales_summary()

    def test_inventory_report_not_empty(self):
        df = inventory_report()
        self.assertFalse(df.empty)
        self.assertIn("status", df.columns)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running Supermarket System Test Suite...\n")
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for tc in [TestDatabase, TestAuth, TestInventory, TestTransactions, TestAnalytics]:
        suite.addTests(loader.loadTestsFromTestCase(tc))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    # Cleanup test DB
    close_all_connections()
    if os.path.exists(TEST_DB):
        for attempt in range(10):
            try:
                os.remove(TEST_DB)
                break
            except PermissionError:
                time.sleep(0.15)
    sys.exit(0 if result.wasSuccessful() else 1)
