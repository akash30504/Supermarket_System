"""
analytics.py
------------
Analytics & Reporting Module.
Uses NumPy vectorized operations and pandas for fast aggregations.
Generates sales summaries, inventory reports, and performance metrics.
"""

import time
import numpy as np
import pandas as pd
from modules.database import get_connection
from modules.auth import require_permission


def _fetch_transactions_df() -> pd.DataFrame:
    """Load all transactions into a pandas DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT t.txn_id, t.product_id, p.product_name, p.category,
               t.quantity, t.unit_price, t.total_value, t.txn_time, t.cashier_id,
               u.username AS cashier_name
        FROM transactions t
        JOIN products p ON t.product_id = p.product_id
        JOIN users    u ON t.cashier_id  = u.user_id
    """, conn, parse_dates=["txn_time"])
    conn.close()
    return df


def _fetch_products_df() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM products", conn)
    conn.close()
    return df


# ── Sales Reports ─────────────────────────────────────────────────────────────

def sales_summary() -> dict:
    """
    Overall sales summary using NumPy vectorized operations.
    Returns totals, averages, and top metrics.
    """
    require_permission("view_reports")
    start = time.perf_counter()

    df = _fetch_transactions_df()
    if df.empty:
        return {"message": "No transactions found.", "elapsed_sec": 0}

    # NumPy vectorized computation on the total_value column
    values = df["total_value"].values  # numpy array
    elapsed = time.perf_counter() - start

    return {
        "total_transactions":   int(len(df)),
        "total_revenue":        float(np.sum(values)),
        "avg_transaction_value": float(np.mean(values)),
        "max_transaction":      float(np.max(values)),
        "min_transaction":      float(np.min(values)),
        "std_deviation":        float(np.std(values)),
        "total_units_sold":     int(df["quantity"].values.sum()),
        "unique_products_sold": int(df["product_id"].nunique()),
        "unique_cashiers":      int(df["cashier_id"].nunique()),
        "elapsed_sec":          round(time.perf_counter() - start, 6),
    }


def sales_by_category() -> pd.DataFrame:
    """Revenue and units sold grouped by product category."""
    require_permission("view_reports")
    df = _fetch_transactions_df()
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("category")
          .agg(
              total_revenue=("total_value", "sum"),
              total_units=("quantity", "sum"),
              num_transactions=("txn_id", "count"),
              avg_order_value=("total_value", "mean")
          )
          .sort_values("total_revenue", ascending=False)
          .reset_index()
    )


def sales_by_product(top_n: int = 10) -> pd.DataFrame:
    """Top N products by revenue."""
    require_permission("view_reports")
    df = _fetch_transactions_df()
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["product_id", "product_name"])
          .agg(
              total_revenue=("total_value", "sum"),
              units_sold=("quantity", "sum"),
              transactions=("txn_id", "count")
          )
          .sort_values("total_revenue", ascending=False)
          .head(top_n)
          .reset_index()
    )


def sales_by_cashier() -> pd.DataFrame:
    """Sales performance per cashier."""
    require_permission("view_reports")
    df = _fetch_transactions_df()
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["cashier_id", "cashier_name"])
          .agg(
              total_revenue=("total_value", "sum"),
              units_sold=("quantity", "sum"),
              transactions=("txn_id", "count"),
              avg_txn_value=("total_value", "mean")
          )
          .sort_values("total_revenue", ascending=False)
          .reset_index()
    )


def sales_over_time(freq: str = "D") -> pd.DataFrame:
    """
    Revenue aggregated over time.
    freq: 'H' = hourly, 'D' = daily, 'W' = weekly, 'ME' = monthly
    """
    require_permission("view_reports")
    df = _fetch_transactions_df()
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("txn_time")
    return (
        df["total_value"]
          .resample(freq)
          .agg(["sum", "count", "mean"])
          .rename(columns={"sum": "revenue", "count": "transactions", "mean": "avg_value"})
          .reset_index()
    )


# ── Inventory Reports ─────────────────────────────────────────────────────────

def inventory_report() -> pd.DataFrame:
    """Full inventory status with stock value calculations."""
    require_permission("view_reports")
    df = _fetch_products_df()
    if df.empty:
        return pd.DataFrame()
    # Vectorized stock value computation
    df["stock_value"] = df["stock_qty"].values * df["unit_price"].values
    df["status"] = np.where(
        df["stock_qty"].values == 0, "OUT_OF_STOCK",
        np.where(df["stock_qty"].values <= df["reorder_level"].values, "LOW_STOCK", "OK")
    )
    return df[["product_id", "product_name", "category", "unit_price",
               "stock_qty", "reorder_level", "stock_value", "status"]]


def inventory_valuation_by_category() -> pd.DataFrame:
    """Total stock value grouped by category."""
    require_permission("view_reports")
    df = _fetch_products_df()
    if df.empty:
        return pd.DataFrame()
    df["stock_value"] = df["stock_qty"] * df["unit_price"]
    return (
        df.groupby("category")
          .agg(
              total_stock_value=("stock_value", "sum"),
              total_units=("stock_qty", "sum"),
              product_count=("product_id", "count"),
              avg_unit_price=("unit_price", "mean")
          )
          .sort_values("total_stock_value", ascending=False)
          .reset_index()
    )


# ── Audit Log Report ──────────────────────────────────────────────────────────

def audit_log_report(limit: int = 100) -> pd.DataFrame:
    """Recent audit log entries."""
    require_permission("view_audit_log")
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT a.log_id, u.username, a.action, a.details, a.log_time
        FROM audit_log a
        LEFT JOIN users u ON a.user_id = u.user_id
        ORDER BY a.log_time DESC
        LIMIT ?
    """, conn, params=(limit,), parse_dates=["log_time"])
    conn.close()
    return df


# ── Demand Forecast (simple moving average) ───────────────────────────────────

def demand_forecast(product_id: int, window: int = 7) -> dict:
    """
    Simple moving-average demand forecast for a product.
    Uses NumPy convolution for vectorized rolling average.
    """
    require_permission("view_reports")
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT DATE(txn_time) AS day, SUM(quantity) AS units
        FROM transactions
        WHERE product_id = ?
        GROUP BY DATE(txn_time)
        ORDER BY day
    """, conn, params=(product_id,))
    conn.close()

    if df.empty or len(df) < 2:
        return {"product_id": product_id, "message": "Insufficient data for forecast."}

    units = df["units"].values.astype(float)
    # Vectorized moving average using NumPy convolution
    kernel = np.ones(min(window, len(units))) / min(window, len(units))
    ma = np.convolve(units, kernel, mode="valid")

    return {
        "product_id":    product_id,
        "days_of_data":  len(df),
        "avg_daily_demand": round(float(np.mean(units)), 2),
        "forecast_next_day": round(float(ma[-1]), 2) if len(ma) > 0 else None,
        "window_days":   window,
        "trend":         "increasing" if len(ma) > 1 and ma[-1] > ma[0] else "stable/decreasing"
    }


# ── Pretty Print Helpers ──────────────────────────────────────────────────────

def print_report(df: pd.DataFrame, title: str = ""):
    """Print a DataFrame as a formatted table."""
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    if df is None or df.empty:
        print("  No data available.")
    else:
        print(df.to_string(index=False))
    print()


def print_summary(summary: dict, title: str = "Sales Summary"):
    """Print a summary dict."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k:<30}: {v:,.4f}")
        else:
            print(f"  {k:<30}: {v}")
    print()
