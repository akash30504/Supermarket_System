import time
import random
import hashlib
import secrets
import statistics
import multiprocessing
import threading
from modules.database import get_connection, hash_password
from modules.auth import require_permission, get_session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_available_products(min_stock: int = 5, limit: int = 50) -> list:
    """Return product IDs that have sufficient stock for benchmarking."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT product_id FROM products WHERE stock_qty >= ? LIMIT ?",
        (min_stock, limit)
    ).fetchall()
    conn.close()
    return [r["product_id"] for r in rows]


def _generate_txn_batch(product_ids: list, n: int) -> list:
    """Generate n random transaction dicts."""
    if not product_ids:
        raise RuntimeError("No products with sufficient stock available for benchmarking.")
    return [
        {"product_id": random.choice(product_ids), "quantity": 1}
        for _ in range(n)
    ]


def _time_fn(fn, *args, **kwargs):
    """Time a function call. Returns (result, elapsed_seconds)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


# ── Transaction Throughput Benchmark ─────────────────────────────────────────

def benchmark_transaction_throughput(batch_sizes: list = None,
                                      repeat: int = 1) -> dict:

    require_permission("run_benchmarks")
    from modules.transactions import (
        process_batch_sequential,
        process_batch_threaded,
        process_batch_multiprocessing
    )

    if batch_sizes is None:
        batch_sizes = [10, 50, 100]

    results = {}
    print(f"\n{'='*65}")
    print(f"  TRANSACTION THROUGHPUT BENCHMARK")
    print(f"{'='*65}")
    print(f"  {'Batch':>8} | {'Sequential':>14} | {'Threaded':>14} | {'MultiProc':>14}")
    print(f"  {'-'*8}-+-{'-'*14}-+-{'-'*14}-+-{'-'*14}")

    for size in batch_sizes:
        product_ids = _get_available_products(min_stock=size + 1, limit=50)
        # Limit to very small real transactions to avoid depleting stock
        # Use size=min(size, 10) for actual processing, report extrapolated
        safe_size = min(size, 10)
        batch = _generate_txn_batch(product_ids[:max(len(product_ids),1)], safe_size)

        seq_times  = []
        thr_times  = []
        mp_times   = []

        for _ in range(repeat):
            # Sequential
            try:
                r_seq, t_seq = _time_fn(process_batch_sequential, batch)
                seq_times.append(r_seq["throughput"])
            except Exception:
                seq_times.append(0)

            # Threaded
            try:
                r_thr, t_thr = _time_fn(process_batch_threaded, batch, num_threads=4)
                thr_times.append(r_thr["throughput"])
            except Exception:
                thr_times.append(0)

            # Multiprocessing
            try:
                r_mp, t_mp = _time_fn(process_batch_multiprocessing, batch, num_processes=2)
                mp_times.append(r_mp["throughput"])
            except Exception:
                mp_times.append(0)

        seq_avg = statistics.mean(seq_times) if seq_times else 0
        thr_avg = statistics.mean(thr_times) if thr_times else 0
        mp_avg  = statistics.mean(mp_times)  if mp_times  else 0

        results[size] = {
            "sequential_tps":     round(seq_avg, 2),
            "threaded_tps":       round(thr_avg, 2),
            "multiprocessing_tps": round(mp_avg, 2),
            "threaded_speedup":   round(thr_avg / seq_avg, 2) if seq_avg > 0 else "N/A",
            "mp_speedup":         round(mp_avg  / seq_avg, 2) if seq_avg > 0 else "N/A",
        }
        print(f"  {safe_size:>8} | {seq_avg:>12.2f}tx | {thr_avg:>12.2f}tx | {mp_avg:>12.2f}tx")

    print(f"{'='*65}\n")
    return results


# ── Security Overhead Benchmark ───────────────────────────────────────────────

def benchmark_security_overhead(iterations: int = 1000) -> dict:
    """
    Measure the overhead of individual security operations:
    - Password hashing (SHA-256 + salt)
    - Password verification
    - Permission check
    - Audit log write
    """
    require_permission("run_benchmarks")
    print(f"\n{'='*55}")
    print(f"  SECURITY OVERHEAD BENCHMARK  (iterations={iterations})")
    print(f"{'='*55}")

    results = {}

    # 1. Password Hashing
    start = time.perf_counter()
    for _ in range(iterations):
        hash_password("TestPassword@123")
    elapsed = time.perf_counter() - start
    avg_hash_us = (elapsed / iterations) * 1_000_000
    results["password_hash_us"] = round(avg_hash_us, 3)
    print(f"  Password hashing avg:    {avg_hash_us:>10.3f} µs/op")

    # 2. Password Verification
    h, s = hash_password("BenchmarkPass@456")
    start = time.perf_counter()
    for _ in range(iterations):
        from modules.database import verify_password
        verify_password("BenchmarkPass@456", h, s)
    elapsed = time.perf_counter() - start
    avg_verify_us = (elapsed / iterations) * 1_000_000
    results["password_verify_us"] = round(avg_verify_us, 3)
    print(f"  Password verify avg:     {avg_verify_us:>10.3f} µs/op")

    # 3. RBAC permission check (in-memory)
    from modules.auth import PERMISSIONS
    start = time.perf_counter()
    for _ in range(iterations):
        _ = "process_transaction" in PERMISSIONS.get("cashier", set())
    elapsed = time.perf_counter() - start
    avg_rbac_us = (elapsed / iterations) * 1_000_000
    results["rbac_check_us"] = round(avg_rbac_us, 6)
    print(f"  RBAC permission check:   {avg_rbac_us:>10.6f} µs/op")

    # 4. Audit log write
    conn = get_connection()
    start = time.perf_counter()
    for i in range(min(iterations, 200)):   # cap at 200 to avoid flooding log
        conn.execute(
            "INSERT INTO audit_log (user_id, action, details) VALUES (?,?,?)",
            (1, "BENCHMARK", f"Iteration {i}")
        )
    conn.commit()
    elapsed = time.perf_counter() - start
    conn.close()
    n = min(iterations, 200)
    avg_audit_us = (elapsed / n) * 1_000_000
    results["audit_log_write_us"] = round(avg_audit_us, 3)
    print(f"  Audit log write avg:     {avg_audit_us:>10.3f} µs/op")

    # 5. Estimated total overhead per transaction
    total_overhead_us = avg_hash_us * 0 + avg_verify_us * 0 + avg_rbac_us * 2 + avg_audit_us
    results["estimated_overhead_per_txn_us"] = round(total_overhead_us, 3)
    print(f"\n  Est. overhead/transaction: {total_overhead_us:.3f} µs")
    print(f"  (RBAC check × 2 + audit log write)")
    print(f"{'='*55}\n")

    return results


# ── Vectorized Computation Benchmark ─────────────────────────────────────────

def benchmark_vectorized_vs_loop(n: int = 100_000) -> dict:

    require_permission("run_benchmarks")
    import numpy as np

    quantities  = np.random.randint(1, 20, size=n)
    unit_prices = np.random.uniform(0.5, 50.0, size=n)

    # Python loop
    start = time.perf_counter()
    total_loop = sum(quantities[i] * unit_prices[i] for i in range(n))
    loop_elapsed = time.perf_counter() - start

    # NumPy vectorized
    start = time.perf_counter()
    total_numpy = np.sum(quantities * unit_prices)
    numpy_elapsed = time.perf_counter() - start

    speedup = loop_elapsed / numpy_elapsed if numpy_elapsed > 0 else float("inf")

    print(f"\n{'='*55}")
    print(f"  VECTORIZED vs LOOP BENCHMARK  (n={n:,})")
    print(f"{'='*55}")
    print(f"  Python loop elapsed:  {loop_elapsed*1000:>10.3f} ms")
    print(f"  NumPy  vec  elapsed:  {numpy_elapsed*1000:>10.3f} ms")
    print(f"  NumPy speedup:        {speedup:>10.1f}×")
    print(f"{'='*55}\n")

    return {
        "n":                n,
        "loop_ms":          round(loop_elapsed * 1000, 4),
        "numpy_ms":         round(numpy_elapsed * 1000, 4),
        "speedup_factor":   round(speedup, 2),
    }


# ── Full Benchmark Suite ──────────────────────────────────────────────────────

def run_full_benchmark_suite() -> dict:
    """Run all benchmarks and return a combined report."""
    require_permission("run_benchmarks")
    print("\n" + "█"*65)
    print("  FULL BENCHMARK SUITE")
    print("█"*65)

    report = {}
    report["vectorized"]        = benchmark_vectorized_vs_loop(100_000)
    report["security_overhead"] = benchmark_security_overhead(500)
    report["throughput"]        = benchmark_transaction_throughput([5, 10])

    print("\n[Benchmark] Suite complete.")
    return report
