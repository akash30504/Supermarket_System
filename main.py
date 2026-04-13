"""
main.py
-------
Main CLI Menu for the Secure High-Performance Supermarket System.
Entry point for all user interactions.

Default Credentials:
  admin    / Admin@123
  manager  / Manager@123
  cashier1 / Cashier@123
"""

import os
import sys

# Ensure modules are importable regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database  import initialize_database
from modules.auth      import login, logout, get_session, create_user, list_users, deactivate_user
from modules.inventory import (add_product, update_product, delete_product,
                                list_products, search_products, adjust_stock,
                                get_low_stock_products, get_inventory_summary)
from modules.transactions import (process_transaction, process_batch_sequential,
                                   process_batch_threaded, process_batch_multiprocessing,
                                   list_transactions)
from modules.analytics import (sales_summary, sales_by_category, sales_by_product,
                                sales_by_cashier, inventory_report,
                                inventory_valuation_by_category, audit_log_report,
                                demand_forecast, print_report, print_summary)
from modules.benchmarks import (benchmark_transaction_throughput, benchmark_security_overhead,
                                 benchmark_vectorized_vs_loop, run_full_benchmark_suite)
from modules.seeder import run_full_seed


# ── Utilities ─────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def pause():
    input("\n  Press Enter to continue...")

def hr(char="─", width=60):
    print(char * width)

def header(title: str):
    hr("═")
    print(f"  {title}")
    hr("═")

def success(msg):  print(f"\n  ✔  {msg}")
def error(msg):    print(f"\n  ✘  ERROR: {msg}")
def info(msg):     print(f"\n  ℹ  {msg}")

def prompt(label, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val if val else default

def prompt_int(label, default=None):
    while True:
        try:
            return int(prompt(label, default))
        except (TypeError, ValueError):
            error("Please enter a valid integer.")

def prompt_float(label, default=None):
    while True:
        try:
            return float(prompt(label, default))
        except (TypeError, ValueError):
            error("Please enter a valid number.")


# ── Login Screen ──────────────────────────────────────────────────────────────

def login_screen():
    while True:
        clear()
        header("SECURE SUPERMARKET SYSTEM  –  Login")
        print()
        username = prompt("Username")
        password = prompt("Password")
        if not username or not password:
            error("Username and password are required.")
            pause()
            continue
        try:
            session = login(username, password)
            success(f"Welcome, {session.username}! Role: {session.role.upper()}")
            pause()
            return session
        except (ValueError, PermissionError) as e:
            error(str(e))
            pause()


# ── Main Menu ─────────────────────────────────────────────────────────────────

def main_menu():
    session = get_session()
    while True:
        clear()
        header(f"SUPERMARKET SYSTEM  –  Logged in as: {session.username} [{session.role.upper()}]")
        print()
        print("  [1]  Product & Inventory Management")
        print("  [2]  Transaction Processing")
        print("  [3]  Analytics & Reports")
        print("  [4]  Performance Benchmarks")
        if session.role == "admin":
            print("  [5]  User Management")
            print("  [6]  Audit Log")
            print("  [7]  Seed Demo Data")
        print()
        print("  [0]  Logout")
        print()
        choice = prompt("Select option")

        if choice == "1":   inventory_menu()
        elif choice == "2": transaction_menu()
        elif choice == "3": analytics_menu()
        elif choice == "4": benchmarks_menu()
        elif choice == "5" and session.role == "admin": user_management_menu()
        elif choice == "6" and session.role == "admin": audit_log_menu()
        elif choice == "7" and session.role == "admin": seed_menu()
        elif choice == "0":
            logout()
            return
        else:
            error("Invalid option or insufficient permissions.")
            pause()


# ── Inventory Menu ────────────────────────────────────────────────────────────

def inventory_menu():
    while True:
        clear()
        header("PRODUCT & INVENTORY MANAGEMENT")
        print("  [1]  List all products")
        print("  [2]  Search products")
        print("  [3]  Add product")
        print("  [4]  Update product")
        print("  [5]  Delete product (admin)")
        print("  [6]  Adjust stock")
        print("  [7]  Low stock alerts")
        print("  [8]  Inventory summary")
        print("  [0]  Back")
        choice = prompt("Select option")

        if choice == "1":
            clear(); header("ALL PRODUCTS")
            prods = list_products()
            _print_products(prods)
            pause()

        elif choice == "2":
            kw = prompt("Search keyword")
            clear(); header(f"SEARCH: '{kw}'")
            _print_products(search_products(kw))
            pause()

        elif choice == "3":
            clear(); header("ADD PRODUCT")
            try:
                name     = prompt("Product name")
                category = prompt("Category")
                price    = prompt_float("Unit price (£)")
                qty      = prompt_int("Initial stock quantity")
                reorder  = prompt_int("Reorder level", 10)
                pid      = add_product(name, category, price, qty, reorder)
                success(f"Product added with ID={pid}")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice == "4":
            clear(); header("UPDATE PRODUCT")
            try:
                pid   = prompt_int("Product ID to update")
                field = prompt("Field to update (product_name/category/unit_price/reorder_level)")
                value = prompt("New value")
                if field == "unit_price":
                    value = float(value)
                elif field == "reorder_level":
                    value = int(value)
                update_product(pid, **{field: value})
                success("Product updated.")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice == "5":
            clear(); header("DELETE PRODUCT")
            try:
                pid = prompt_int("Product ID to delete")
                confirm = prompt(f"Confirm delete product {pid}? (yes/no)")
                if confirm.lower() == "yes":
                    delete_product(pid)
                    success("Product deleted.")
                else:
                    info("Cancelled.")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice == "6":
            clear(); header("ADJUST STOCK")
            try:
                pid    = prompt_int("Product ID")
                delta  = prompt_int("Quantity to add (negative to reduce)")
                reason = prompt("Reason", "manual adjustment")
                new_qty = adjust_stock(pid, delta, reason)
                success(f"New stock level: {new_qty}")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice == "7":
            clear(); header("LOW STOCK ALERTS")
            items = get_low_stock_products()
            if items:
                print(f"\n  {'ID':>5}  {'Name':<30}  {'Stock':>6}  {'Reorder':>7}")
                hr()
                for p in items:
                    status = "OUT" if p["stock_qty"] == 0 else "LOW"
                    print(f"  {p['product_id']:>5}  {p['product_name']:<30}  "
                          f"{p['stock_qty']:>6}  {p['reorder_level']:>7}  [{status}]")
            else:
                success("All products are adequately stocked.")
            pause()

        elif choice == "8":
            clear(); header("INVENTORY SUMMARY")
            summary = get_inventory_summary()
            for k, v in summary.items():
                print(f"  {k:<30}: {v:,.2f}" if isinstance(v, float) else f"  {k:<30}: {v:,}")
            pause()

        elif choice == "0":
            return
        else:
            error("Invalid option.")
            pause()


def _print_products(prods):
    if not prods:
        info("No products found.")
        return
    print(f"\n  {'ID':>5}  {'Name':<30}  {'Category':<15}  {'Price':>8}  {'Stock':>6}")
    print("  " + "─"*70)
    for p in prods[:100]:  # Cap display at 100
        print(f"  {p['product_id']:>5}  {p['product_name']:<30}  "
              f"{p['category']:<15}  £{p['unit_price']:>7.2f}  {p['stock_qty']:>6}")
    if len(prods) > 100:
        info(f"Showing 100 of {len(prods)} results.")


# ── Transaction Menu ──────────────────────────────────────────────────────────

def transaction_menu():
    while True:
        clear()
        header("TRANSACTION PROCESSING")
        print("  [1]  Process single transaction")
        print("  [2]  Process batch – Sequential")
        print("  [3]  Process batch – Threaded")
        print("  [4]  Process batch – Multiprocessing")
        print("  [5]  View recent transactions")
        print("  [0]  Back")
        choice = prompt("Select option")

        if choice == "1":
            clear(); header("SINGLE TRANSACTION")
            try:
                pid = prompt_int("Product ID")
                qty = prompt_int("Quantity")
                result = process_transaction(pid, qty)
                success("Transaction completed!")
                print(f"\n  TxnID:       {result['txn_id']}")
                print(f"  Product ID:  {result['product_id']}")
                print(f"  Quantity:    {result['quantity']}")
                print(f"  Unit Price:  £{result['unit_price']:.2f}")
                print(f"  Total:       £{result['total_value']:.2f}")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice in ("2", "3", "4"):
            clear()
            modes = {"2": "Sequential", "3": "Threaded", "4": "Multiprocessing"}
            header(f"BATCH TRANSACTION – {modes[choice]}")
            try:
                n = prompt_int("Number of transactions to process", 20)
                pid = prompt_int("Product ID (same for all in batch)")

                batch = [{"product_id": pid, "quantity": 1} for _ in range(n)]
                if choice == "2":
                    r = process_batch_sequential(batch)
                elif choice == "3":
                    workers = prompt_int("Number of threads", 4)
                    r = process_batch_threaded(batch, num_threads=workers)
                else:
                    workers = prompt_int("Number of processes", 2)
                    r = process_batch_multiprocessing(batch, num_processes=workers)

                print(f"\n  Mode:        {r['mode']}")
                print(f"  Total:       {r['total']}")
                print(f"  Success:     {r['success']}")
                print(f"  Failed:      {r['failed']}")
                print(f"  Elapsed:     {r['elapsed_sec']} s")
                print(f"  Throughput:  {r['throughput']} tx/s")
                if r["errors"]:
                    print(f"\n  Errors ({len(r['errors'])}):")
                    for e in r["errors"][:5]:
                        print(f"    {e}")
            except (ValueError, PermissionError) as e:
                error(str(e))
            pause()

        elif choice == "5":
            clear(); header("RECENT TRANSACTIONS")
            txns = list_transactions(limit=20)
            if txns:
                print(f"\n  {'TxnID':>6}  {'Product':<22}  {'Qty':>4}  {'Price':>8}  {'Total':>9}  {'Time':<19}")
                hr()
                for t in txns:
                    print(f"  {t['txn_id']:>6}  {t['product_name'][:22]:<22}  "
                          f"{t['quantity']:>4}  £{t['unit_price']:>7.2f}  "
                          f"£{t['total_value']:>8.2f}  {str(t['txn_time'])[:19]}")
            else:
                info("No transactions recorded yet.")
            pause()

        elif choice == "0":
            return
        else:
            error("Invalid option.")
            pause()


# ── Analytics Menu ────────────────────────────────────────────────────────────

def analytics_menu():
    while True:
        clear()
        header("ANALYTICS & REPORTS")
        print("  [1]  Sales summary")
        print("  [2]  Sales by category")
        print("  [3]  Top 10 products by revenue")
        print("  [4]  Sales by cashier")
        print("  [5]  Sales over time (daily)")
        print("  [6]  Inventory report")
        print("  [7]  Inventory valuation by category")
        print("  [8]  Demand forecast for product")
        print("  [0]  Back")
        choice = prompt("Select option")

        if choice == "1":
            clear()
            try:
                summary = sales_summary()
                print_summary(summary, "OVERALL SALES SUMMARY")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "2":
            clear()
            try: print_report(sales_by_category(), "SALES BY CATEGORY")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "3":
            clear()
            try: print_report(sales_by_product(10), "TOP 10 PRODUCTS BY REVENUE")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "4":
            clear()
            try: print_report(sales_by_cashier(), "SALES BY CASHIER")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "5":
            clear()
            try: print_report(sales_over_time("D"), "DAILY SALES OVER TIME")
            except Exception as e: error(str(e))
            pause()

        elif choice == "6":
            clear()
            try: print_report(inventory_report(), "FULL INVENTORY REPORT")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "7":
            clear()
            try: print_report(inventory_valuation_by_category(), "INVENTORY VALUATION BY CATEGORY")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "8":
            clear(); header("DEMAND FORECAST")
            try:
                pid = prompt_int("Product ID")
                w   = prompt_int("Moving average window (days)", 7)
                result = demand_forecast(pid, w)
                for k, v in result.items():
                    print(f"  {k:<30}: {v}")
            except (ValueError, PermissionError) as e: error(str(e))
            pause()

        elif choice == "0":
            return
        else:
            error("Invalid option.")
            pause()


# Need to import after definition
from modules.analytics import sales_over_time


# ── Benchmarks Menu ───────────────────────────────────────────────────────────

def benchmarks_menu():
    while True:
        clear()
        header("PERFORMANCE BENCHMARKS")
        print("  [1]  Transaction throughput (seq vs threaded vs multiprocessing)")
        print("  [2]  Security overhead measurement")
        print("  [3]  Vectorized vs loop computation")
        print("  [4]  Run full benchmark suite")
        print("  [0]  Back")
        choice = prompt("Select option")

        if choice == "1":
            clear()
            try: benchmark_transaction_throughput([5, 10, 20])
            except (PermissionError, RuntimeError) as e: error(str(e))
            pause()

        elif choice == "2":
            clear()
            try: benchmark_security_overhead(500)
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "3":
            clear()
            try: benchmark_vectorized_vs_loop(100_000)
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "4":
            clear()
            try: run_full_benchmark_suite()
            except (PermissionError, RuntimeError) as e: error(str(e))
            pause()

        elif choice == "0":
            return
        else:
            error("Invalid option.")
            pause()


# ── User Management Menu ──────────────────────────────────────────────────────

def user_management_menu():
    while True:
        clear()
        header("USER MANAGEMENT  (Admin Only)")
        print("  [1]  List all users")
        print("  [2]  Create new user")
        print("  [3]  Deactivate user")
        print("  [0]  Back")
        choice = prompt("Select option")

        if choice == "1":
            clear(); header("ALL USERS")
            try:
                users = list_users()
                print(f"\n  {'ID':>4}  {'Username':<20}  {'Role':<10}  {'Active':<8}  Created")
                hr()
                for u in users:
                    active = "YES" if u["is_active"] else "NO"
                    print(f"  {u['user_id']:>4}  {u['username']:<20}  {u['role']:<10}  {active:<8}  {u['created_at']}")
            except PermissionError as e: error(str(e))
            pause()

        elif choice == "2":
            clear(); header("CREATE USER")
            try:
                uname = prompt("Username")
                pwd   = prompt("Password")
                role  = prompt("Role (admin/manager/cashier)")
                create_user(uname, pwd, role)
                success(f"User '{uname}' created.")
            except (ValueError, PermissionError) as e: error(str(e))
            pause()

        elif choice == "3":
            clear(); header("DEACTIVATE USER")
            try:
                uname = prompt("Username to deactivate")
                confirm = prompt(f"Deactivate '{uname}'? (yes/no)")
                if confirm.lower() == "yes":
                    deactivate_user(uname)
                    success(f"User '{uname}' deactivated.")
                else:
                    info("Cancelled.")
            except (ValueError, PermissionError) as e: error(str(e))
            pause()

        elif choice == "0":
            return
        else:
            error("Invalid option.")
            pause()


# ── Audit Log Menu ────────────────────────────────────────────────────────────

def audit_log_menu():
    clear(); header("AUDIT LOG  (Admin Only)")
    try:
        df = audit_log_report(limit=50)
        print_report(df, "RECENT AUDIT LOG ENTRIES")
    except PermissionError as e:
        error(str(e))
    pause()


# ── Seed Menu ─────────────────────────────────────────────────────────────────

def seed_menu():
    clear(); header("SEED DEMO DATA")
    print("  This will insert ~1,000 products and ~100,000 transactions.")
    confirm = prompt("Proceed? (yes/no)")
    if confirm.lower() == "yes":
        run_full_seed(1000, 100_000)
        success("Demo data seeded successfully.")
    else:
        info("Cancelled.")
    pause()


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    print("\n[System] Initializing database...")
    initialize_database()
    print("[System] Ready.\n")

    while True:
        session = login_screen()
        if session:
            main_menu()
        else:
            break


if __name__ == "__main__":
    main()
