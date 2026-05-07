"""
transactions.py
---------------
Transaction Processing Module.
Supports both sequential and parallel (multiprocessing + multithreading) processing.
Thread-safe via locks; uses process-safe queues for multiprocessing mode.
"""

import time
import threading
import multiprocessing
from multiprocessing import Pool, Queue, Manager
from modules.database import get_connection
from modules.auth import require_permission, get_session, _audit
from modules.inventory import _deduct_stock_unsafe

# Global threading lock for single-process concurrent writes
_db_lock = threading.Lock()


# ── Single Transaction ────────────────────────────────────────────────────────

def process_transaction(product_id: int, quantity: int, cashier_id: int = None) -> dict:
    """
    Process a single sales transaction.
    - Checks stock availability
    - Deducts stock atomically
    - Records transaction
    - Returns transaction record
    """
    require_permission("process_transaction")
    session = get_session()
    c_id = cashier_id if cashier_id else session.user_id

    with _db_lock:
        conn = get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")  # Prevent concurrent writes

            # Get product price
            prod = conn.execute(
                "SELECT product_id, unit_price, stock_qty FROM products WHERE product_id=?",
                (product_id,)
            ).fetchone()
            if prod is None:
                raise ValueError(f"Product {product_id} not found.")

            # Insert transaction record first to get txn_id
            cursor = conn.execute(
                "INSERT INTO transactions (product_id, cashier_id, quantity, unit_price) "
                "VALUES (?,?,?,?)",
                (product_id, c_id, quantity, prod["unit_price"])
            )
            txn_id = cursor.lastrowid

            # Deduct stock and trigger email alert if stock <= 50
            _deduct_stock_unsafe(conn, product_id, quantity, txn_id=txn_id)
            _audit(conn, c_id, "TRANSACTION",
                   f"TxnID={txn_id} ProductID={product_id} Qty={quantity}")
            conn.commit()

            return {
                "txn_id":      txn_id,
                "product_id":  product_id,
                "quantity":    quantity,
                "unit_price":  prod["unit_price"],
                "total_value": quantity * prod["unit_price"],
                "cashier_id":  c_id,
                "status":      "completed"
            }
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()


# ── Batch Sequential Processing ───────────────────────────────────────────────

def process_batch_sequential(transactions: list, cashier_id: int = None) -> dict:
    """
    Process a list of transaction dicts sequentially.
    Each item: {"product_id": int, "quantity": int}
    Returns summary with results and timing.
    """
    require_permission("process_transaction")
    session = get_session()
    c_id = cashier_id if cashier_id else session.user_id

    results = []
    errors  = []
    start   = time.perf_counter()

    for txn in transactions:
        try:
            r = process_transaction(txn["product_id"], txn["quantity"], c_id)
            results.append(r)
        except Exception as e:
            errors.append({"input": txn, "error": str(e)})

    elapsed = time.perf_counter() - start
    throughput = len(results) / elapsed if elapsed > 0 else 0

    return {
        "mode":        "sequential",
        "total":       len(transactions),
        "success":     len(results),
        "failed":      len(errors),
        "elapsed_sec": round(elapsed, 4),
        "throughput":  round(throughput, 2),
        "results":     results,
        "errors":      errors,
    }


# ── Threaded Batch Processing ─────────────────────────────────────────────────

def _thread_worker(txn, cashier_id, results_list, errors_list):
    """Worker function for threading."""
    try:
        r = process_transaction(txn["product_id"], txn["quantity"], cashier_id)
        results_list.append(r)
    except Exception as e:
        errors_list.append({"input": txn, "error": str(e)})


def process_batch_threaded(transactions: list, cashier_id: int = None,
                            num_threads: int = 4) -> dict:
    """
    Process transactions using multithreading (num_threads workers).
    Good for I/O-bound workloads. Protected by _db_lock per transaction.
    """
    require_permission("process_transaction")
    session = get_session()
    c_id = cashier_id if cashier_id else session.user_id

    results = []
    errors  = []
    start   = time.perf_counter()

    semaphore = threading.Semaphore(num_threads)
    threads   = []

    def guarded_worker(txn):
        with semaphore:
            _thread_worker(txn, c_id, results, errors)

    for txn in transactions:
        t = threading.Thread(target=guarded_worker, args=(txn,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    elapsed = time.perf_counter() - start
    throughput = len(results) / elapsed if elapsed > 0 else 0

    return {
        "mode":        f"threaded (workers={num_threads})",
        "total":       len(transactions),
        "success":     len(results),
        "failed":      len(errors),
        "elapsed_sec": round(elapsed, 4),
        "throughput":  round(throughput, 2),
        "results":     results,
        "errors":      errors,
    }


# ── Multiprocessing Batch Processing ─────────────────────────────────────────

def _mp_worker(args):
    """
    Isolated worker for multiprocessing pool.
    Cannot share DB connection or auth session — uses direct DB write.
    """
    product_id, quantity, cashier_id = args
    import sqlite3
    import os
    from modules.database import DB_PATH, get_connection

    try:
        with threading.Lock():
            conn = get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                prod = conn.execute(
                    "SELECT unit_price, stock_qty FROM products WHERE product_id=?",
                    (product_id,)
                ).fetchone()
                if prod is None:
                    return {"error": f"Product {product_id} not found", "product_id": product_id}
                if prod["stock_qty"] < quantity:
                    return {"error": f"Insufficient stock for {product_id}", "product_id": product_id}

                conn.execute(
                    "UPDATE products SET stock_qty = stock_qty - ? WHERE product_id=?",
                    (quantity, product_id)
                )
                cursor = conn.execute(
                    "INSERT INTO transactions (product_id, cashier_id, quantity, unit_price) "
                    "VALUES (?,?,?,?)",
                    (product_id, cashier_id, quantity, prod["unit_price"])
                )
                conn.commit()
                return {
                    "txn_id":     cursor.lastrowid,
                    "product_id": product_id,
                    "quantity":   quantity,
                    "unit_price": prod["unit_price"],
                    "total_value": quantity * prod["unit_price"],
                    "status":     "completed"
                }
            except Exception as e:
                conn.rollback()
                return {"error": str(e), "product_id": product_id}
            finally:
                conn.close()
    except Exception as e:
        return {"error": str(e), "product_id": product_id}


def process_batch_multiprocessing(transactions: list, cashier_id: int = None,
                                   num_processes: int = None) -> dict:
    """
    Process transactions using multiprocessing Pool.
    Achieves true CPU parallelism. Each process gets its own DB connection.
    """
    require_permission("process_transaction")
    session = get_session()
    c_id = cashier_id if cashier_id else session.user_id

    if num_processes is None:
        num_processes = min(multiprocessing.cpu_count(), 4)

    args = [(t["product_id"], t["quantity"], c_id) for t in transactions]
    start = time.perf_counter()

    with Pool(processes=num_processes) as pool:
        raw_results = pool.map(_mp_worker, args)

    elapsed = time.perf_counter() - start

    results = [r for r in raw_results if "error" not in r]
    errors  = [r for r in raw_results if "error" in r]
    throughput = len(results) / elapsed if elapsed > 0 else 0

    return {
        "mode":        f"multiprocessing (workers={num_processes})",
        "total":       len(transactions),
        "success":     len(results),
        "failed":      len(errors),
        "elapsed_sec": round(elapsed, 4),
        "throughput":  round(throughput, 2),
        "results":     results,
        "errors":      errors,
    }


# ── Query Helpers ─────────────────────────────────────────────────────────────

def get_transaction(txn_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT t.*, p.product_name, u.username AS cashier_name "
        "FROM transactions t "
        "JOIN products p ON t.product_id = p.product_id "
        "JOIN users    u ON t.cashier_id  = u.user_id "
        "WHERE t.txn_id = ?", (txn_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"Transaction {txn_id} not found.")
    return dict(row)


def list_transactions(limit: int = 50, cashier_id: int = None) -> list:
    session = get_session()
    # Cashiers can only see their own transactions
    if session.role == "cashier":
        cashier_id = session.user_id
    conn = get_connection()
    if cashier_id:
        rows = conn.execute(
            "SELECT t.txn_id, t.product_id, p.product_name, t.quantity, "
            "t.unit_price, t.total_value, t.txn_time, t.cashier_id "
            "FROM transactions t JOIN products p ON t.product_id=p.product_id "
            "WHERE t.cashier_id=? ORDER BY t.txn_time DESC LIMIT ?",
            (cashier_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT t.txn_id, t.product_id, p.product_name, t.quantity, "
            "t.unit_price, t.total_value, t.txn_time, t.cashier_id "
            "FROM transactions t JOIN products p ON t.product_id=p.product_id "
            "ORDER BY t.txn_time DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]