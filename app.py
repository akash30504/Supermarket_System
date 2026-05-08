"""
app.py
------
Flask web application for the Secure Supermarket System.
Run with: python app.py
Then open: http://localhost:5000
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps

from modules.database import initialize_database
from modules.auth import login as auth_login, logout as auth_logout, PERMISSIONS
from modules.auth import create_user, list_users, deactivate_user
from modules.inventory import (add_product, update_product, delete_product,
                                list_products, search_products, adjust_stock,
                                get_low_stock_products, get_inventory_summary, get_product)
from modules.transactions import (process_transaction, process_batch_sequential,
                                   process_batch_threaded, process_batch_multiprocessing,
                                   list_transactions)
from modules.analytics import (sales_summary, sales_by_category, sales_by_product,
                                sales_by_cashier, inventory_report,
                                inventory_valuation_by_category, audit_log_report,
                                demand_forecast, sales_over_time)
from modules.benchmarks import (benchmark_transaction_throughput, benchmark_security_overhead,
                                 benchmark_vectorized_vs_loop)
from modules.seeder import run_full_seed
import modules.auth as auth_module

app = Flask(__name__)
app.secret_key = "supermarket_secure_key_2024_pusl3190"


# ── Auth Helpers ──────────────────────────────────────────────────────────────

def set_flask_session(auth_session):
    session["user_id"]   = auth_session.user_id
    session["username"]  = auth_session.username
    session["role"]      = auth_session.role

def restore_auth_session():
    """Restore auth module session from Flask session."""
    if "user_id" in session and auth_module._current_session is None:
        from modules.auth import AuthSession
        auth_module._current_session = AuthSession(
            session["user_id"], session["username"], session["role"]
        )

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))
        restore_auth_session()
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "role" not in session or session["role"] not in roles:
                flash("Access denied: insufficient permissions.", "error")
                return redirect(url_for("dashboard"))
            restore_auth_session()
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        try:
            auth_session = auth_login(username, password)
            set_flask_session(auth_session)
            return redirect(url_for("dashboard"))
        except (ValueError, PermissionError) as e:
            flash(str(e), "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    auth_logout()
    session.clear()
    return redirect(url_for("login_page"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    try:
        inv_summary = get_inventory_summary()
        low_stock   = get_low_stock_products()[:5]
        recent_txns = list_transactions(limit=5)
        try:
            s_summary = sales_summary()
        except Exception:
            s_summary = {}
        return render_template("dashboard.html",
                               inv=inv_summary,
                               low_stock=low_stock,
                               recent_txns=recent_txns,
                               sales=s_summary)
    except Exception as e:
        flash(str(e), "error")
        return render_template("dashboard.html", inv={}, low_stock=[], recent_txns=[], sales={})


# ── Products ──────────────────────────────────────────────────────────────────

@app.route("/products")
@login_required
def products():
    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    if keyword:
        prods = search_products(keyword)
    elif category:
        prods = list_products(category)
    else:
        prods = list_products()
    categories = sorted(set(p["category"] for p in list_products()))
    return render_template("products.html", products=prods,
                           categories=categories, keyword=keyword, selected_cat=category)

@app.route("/products/add", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager")
def add_product_route():
    if request.method == "POST":
        try:
            pid = add_product(
                request.form["product_name"],
                request.form["category"],
                float(request.form["unit_price"]),
                int(request.form["stock_qty"]),
                int(request.form.get("reorder_level", 10))
            )
            flash(f"Product added successfully (ID: {pid})", "success")
            return redirect(url_for("products"))
        except Exception as e:
            flash(str(e), "error")
    return render_template("product_form.html", product=None, action="Add")

@app.route("/products/edit/<int:pid>", methods=["GET", "POST"])
@login_required
@role_required("admin", "manager")
def edit_product_route(pid):
    product = get_product(pid)
    if request.method == "POST":
        try:
            update_product(pid,
                product_name=request.form["product_name"],
                category=request.form["category"],
                unit_price=float(request.form["unit_price"]),
                reorder_level=int(request.form["reorder_level"])
            )
            flash("Product updated.", "success")
            return redirect(url_for("products"))
        except Exception as e:
            flash(str(e), "error")
    return render_template("product_form.html", product=product, action="Edit")

@app.route("/products/delete/<int:pid>", methods=["POST"])
@login_required
@role_required("admin")
def delete_product_route(pid):
    try:
        delete_product(pid)
        flash("Product deleted.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("products"))

@app.route("/products/stock/<int:pid>", methods=["POST"])
@login_required
@role_required("admin", "manager")
def adjust_stock_route(pid):
    try:
        delta  = int(request.form["delta"])
        reason = request.form.get("reason", "manual adjustment")
        new_qty = adjust_stock(pid, delta, reason)
        flash(f"Stock updated to {new_qty} units.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("products"))


# ── Transactions ──────────────────────────────────────────────────────────────

@app.route("/transactions")
@login_required
def transactions():
    txns = list_transactions(limit=50)
    prods = list_products()
    return render_template("transactions.html", transactions=txns, products=prods)

@app.route("/transactions/process", methods=["POST"])
@login_required
def process_txn():
    try:
        pid = int(request.form["product_id"])
        qty = int(request.form["quantity"])
        result = process_transaction(pid, qty)
        flash(f"Transaction #{result['txn_id']} completed — LKR {result['total_value']:.2f}", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("transactions"))

@app.route("/transactions/batch", methods=["POST"])
@login_required
@role_required("admin", "manager")
def batch_txn():
    try:
        pid   = int(request.form["product_id"])
        qty   = int(request.form["quantity"])
        count = int(request.form["count"])
        mode  = request.form.get("mode", "sequential")
        batch = [{"product_id": pid, "quantity": qty} for _ in range(count)]

        if mode == "threaded":
            result = process_batch_threaded(batch, num_threads=4)
        elif mode == "multiprocessing":
            result = process_batch_multiprocessing(batch, num_processes=2)
        else:
            result = process_batch_sequential(batch)

        flash(f"Batch complete: {result['success']}/{result['total']} transactions "
              f"in {result['elapsed_sec']}s ({result['throughput']} tx/s)", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("transactions"))


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.route("/analytics")
@login_required
@role_required("admin", "manager")
def analytics():
    try:
        summary  = sales_summary()
        by_cat   = sales_by_category().to_dict(orient="records")
        top_prod = sales_by_product(10).to_dict(orient="records")
        by_cash  = sales_by_cashier().to_dict(orient="records")
        daily    = sales_over_time("D").tail(30).to_dict(orient="records")
        inv_val  = inventory_valuation_by_category().to_dict(orient="records")
    except Exception as e:
        flash(str(e), "error")
        summary = {}; by_cat = []; top_prod = []; by_cash = []; daily = []; inv_val = []
    return render_template("analytics.html",
                           summary=summary, by_cat=by_cat, top_prod=top_prod,
                           by_cash=by_cash, daily=daily, inv_val=inv_val)

@app.route("/analytics/inventory")
@login_required
@role_required("admin", "manager")
def inventory_analytics():
    try:
        inv = inventory_report().to_dict(orient="records")
        low = get_low_stock_products()
        # Send summary report email with ALL low stock products
        if low:
            send_low_stock_report_email(low)
    except Exception as e:
        flash(str(e), "error")
        inv = []; low = []
    return render_template("inventory_report.html", inventory=inv, low_stock=low)


# ── Benchmarks ────────────────────────────────────────────────────────────────

@app.route("/benchmarks")
@login_required
@role_required("admin", "manager")
def benchmarks():
    return render_template("benchmarks.html")

@app.route("/benchmarks/run", methods=["POST"])
@login_required
@role_required("admin", "manager")
def run_benchmark():
    btype = request.form.get("type", "vectorized")
    try:
        if btype == "vectorized":
            result = benchmark_vectorized_vs_loop(100_000)
        elif btype == "security":
            result = benchmark_security_overhead(300)
        elif btype == "throughput":
            result = benchmark_transaction_throughput([5, 10])
        else:
            result = {}
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ── Users ─────────────────────────────────────────────────────────────────────

@app.route("/users")
@login_required
@role_required("admin")
def users():
    all_users = list_users()
    return render_template("users.html", users=all_users)

@app.route("/users/add", methods=["POST"])
@login_required
@role_required("admin")
def add_user():
    try:
        create_user(request.form["username"], request.form["password"], request.form["role"])
        flash(f"User '{request.form['username']}' created.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("users"))

@app.route("/users/deactivate/<username>", methods=["POST"])
@login_required
@role_required("admin")
def deactivate_user_route(username):
    try:
        deactivate_user(username)
        flash(f"User '{username}' deactivated.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("users"))


# ── Audit Log ─────────────────────────────────────────────────────────────────

@app.route("/audit")
@login_required
@role_required("admin")
def audit():
    try:
        logs = audit_log_report(limit=100).to_dict(orient="records")
    except Exception as e:
        flash(str(e), "error")
        logs = []
    return render_template("audit.html", logs=logs)


# ── Seed Data ─────────────────────────────────────────────────────────────────

@app.route("/seed", methods=["POST"])
@login_required
@role_required("admin")
def seed():
    try:
        run_full_seed(1000, 100_000)
        flash("Demo data seeded successfully (1,000 products + 100,000 transactions).", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    initialize_database()
    print("\n" + "="*55)
    print("  Secure Supermarket System — Web UI")
    print("  Open in browser: http://localhost:5000")
    print("  Login: admin / Admin@123")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)