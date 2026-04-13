# Secure High-Performance Supermarket Data Processing & Analysis System
### PUSL3190 Computing Project – Ranawaka Mihisara (10953227)
**Supervisor:** Dr. Pabudi Abeyrathne | **Degree:** BSc(Hons) Computer Security

---

## Project Overview

This system demonstrates the integration of **High-Performance Computing (HPC)** techniques
with **Computer Security** principles in a supermarket data processing context. It is a
direct implementation of the Project Initiation Document (PID) submitted for PUSL3190.

---

## Project Structure

```
supermarket_system/
│
├── main.py                    ← Entry point (CLI menu)
├── requirements.txt
├── README.md
│
├── data/
│   └── supermarket.db         ← SQLite database (auto-created)
│
├── modules/
│   ├── __init__.py
│   ├── database.py            ← DB init, schema, hashing utilities
│   ├── auth.py                ← Authentication + RBAC
│   ├── inventory.py           ← Product & inventory management
│   ├── transactions.py        ← Sequential, threaded & multiprocessing transactions
│   ├── analytics.py           ← NumPy/pandas reports & forecasting
│   ├── benchmarks.py          ← Performance & security overhead benchmarks
│   └── seeder.py              ← Simulated dataset generator (1k products, 100k txns)
│
└── tests/
    └── test_system.py         ← Full unit + integration test suite
```

---

## Requirements

- Python **3.9+**
- Standard library: `sqlite3`, `multiprocessing`, `threading`, `hashlib`, `secrets`
- Third-party:

```
pip install numpy pandas
```

Or:

```
pip install -r requirements.txt
```

---

## Quick Start

### 1. Run the application

```bash
cd supermarket_system
python main.py
```

### 2. Login credentials (seeded by default)

| Username  | Password      | Role     |
|-----------|---------------|----------|
| admin     | Admin@123     | admin    |
| manager   | Manager@123   | manager  |
| cashier1  | Cashier@123   | cashier  |

### 3. Seed demo data (optional, admin only)

Login as `admin` → Option `[7] Seed Demo Data`

This generates ~1,000 products and ~100,000 historical transactions for full analytics.

---

## Module Details

### `database.py`
- Initializes SQLite DB with WAL journaling for concurrent access
- Tables: `users`, `products`, `transactions`, `audit_log`
- SHA-256 + random salt password hashing via `hashlib` + `secrets`

### `auth.py`
- Role-Based Access Control (RBAC) with 3 roles: `admin`, `manager`, `cashier`
- Every action is checked via `require_permission()`
- All login attempts, access denials, and user changes are written to `audit_log`

### `inventory.py`
- Full CRUD for products
- Thread-safe stock deduction using SQLite `BEGIN IMMEDIATE` transactions
- Low-stock alerts based on configurable reorder levels

### `transactions.py`
- **Sequential**: one transaction at a time (baseline)
- **Threaded**: `threading.Thread` pool (configurable workers)
- **Multiprocessing**: `multiprocessing.Pool` (each worker gets its own DB connection)
- All modes return: throughput (tx/s), elapsed time, success/failure counts

### `analytics.py`
- NumPy vectorized operations for revenue aggregation
- Pandas `groupby` for category/cashier/product breakdowns
- Time-series resampling for daily/weekly/monthly revenue
- Simple moving-average demand forecast using `np.convolve`

### `benchmarks.py`
- Transaction throughput: compares all 3 processing modes side-by-side
- Security overhead: measures hashing, RBAC check, and audit log latency in µs
- Vectorized vs loop: demonstrates NumPy speedup over pure Python

---

## Running Tests

```bash
cd supermarket_system
python tests/test_system.py
```

Or with pytest:

```bash
pip install pytest
pytest tests/ -v
```

Tests cover: DB initialization, auth/RBAC, inventory CRUD, transaction processing,
concurrency safety, analytics, and permission enforcement.

---

## Key Technical Features

| Feature | Implementation |
|---------|----------------|
| Parallel transaction processing | `multiprocessing.Pool`, `threading.Thread` |
| Race condition prevention | `threading.Lock`, `BEGIN IMMEDIATE` SQL transactions |
| Password security | SHA-256 + random salt (`hashlib`, `secrets`) |
| Access control | RBAC permission matrix, `require_permission()` guard |
| Audit trail | Every state-changing action logged to `audit_log` table |
| Vectorized computation | NumPy array ops, pandas aggregations |
| Performance measurement | `time.perf_counter()` for µs-precision timing |

---

## Security Mechanisms

1. **Authentication**: Username/password with salted SHA-256 hashing
2. **RBAC**: 3 roles with granular permission sets enforced on every operation
3. **Audit Logging**: Tamper-evident log of all logins, failures, and data changes
4. **SQL Injection Prevention**: All queries use parameterised statements
5. **Concurrency Safety**: `BEGIN IMMEDIATE` prevents dirty reads/writes under load
6. **Principle of Least Privilege**: Cashiers cannot access reports or admin functions

---

## Performance Benchmarks (example, varies by hardware)

| Mode            | Throughput (tx/s) | Notes                         |
|-----------------|-------------------|-------------------------------|
| Sequential      | ~200–500          | Baseline, single-threaded     |
| Threaded (4w)   | ~400–900          | I/O overlap, GIL-limited      |
| Multiprocessing | ~300–800          | True parallelism, spawn overhead |
| NumPy speedup   | ~50–200×          | vs pure Python loop           |
| Security overhead| ~10–50 µs/txn    | RBAC + audit log combined     |

*Actual values depend on CPU, disk speed, and transaction batch size.*

---

## Alignment with PID Business Objectives

| PID Objective | Implementation |
|---------------|----------------|
| ≥1,000 tx/s (parallel mode) | `process_batch_multiprocessing()` benchmarks |
| Report generation in seconds | Pandas/NumPy analytics on 100k records |
| 100% authenticated access | `require_permission()` on every function |
| ≥3 RBAC user types | admin / manager / cashier |
| <15% security overhead | Measured in `benchmark_security_overhead()` |
