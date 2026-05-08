"""
alerts.py
---------
Sends email alerts for low stock events.
Uses Gmail SMTP with TLS (port 587) — works on all networks.
"""

import smtplib
import datetime
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Load credentials ──────────────────────────────────────────────────────────
EMAIL_ENABLED = False
EMAIL_SENDER = EMAIL_PASSWORD = EMAIL_RECEIVER = ""

try:
    # Try root folder first (correct location)
    import importlib.util, os, sys

    # Build absolute path to email_config.py in project root
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _cfg  = os.path.join(_root, "email_config.py")

    if os.path.exists(_cfg):
        spec   = importlib.util.spec_from_file_location("email_config", _cfg)
        _mod   = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
        EMAIL_SENDER   = _mod.EMAIL_SENDER
        EMAIL_PASSWORD = _mod.EMAIL_PASSWORD
        EMAIL_RECEIVER = _mod.EMAIL_RECEIVER
        EMAIL_ENABLED  = True
        print(f"[Alert] Email configured for: {EMAIL_SENDER}")
    else:
        print(f"[Alert] email_config.py not found at: {_cfg}")
except Exception as e:
    print(f"[Alert] Could not load email_config: {e}")


def send_low_stock_email(product_name: str, stock_qty: int,
                          reorder_level: int, product_id: int,
                          txn_id: int = None, quantity_sold: int = None):
    """
    Send a low-stock email alert via Gmail SMTP (TLS port 587).
    Triggered automatically when stock falls to or below 50 units.
    """
    if not EMAIL_ENABLED:
        print(f"[Alert] Email not configured. Low stock: {product_name} ({stock_qty} left)")
        return

    now      = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject  = f"LOW STOCK ALERT — {product_name} ({stock_qty} units left)"
    txn_line = ""
    if txn_id and quantity_sold:
        txn_line = f"Triggered by  : Transaction #{txn_id} — {quantity_sold} unit(s) sold\n"

    body = f"""SuperMart Management System — Low Stock Alert
==============================================
Time          : {now}
Product       : {product_name}
Product ID    : {product_id}
Stock Left    : {stock_qty} units
Reorder Level : {reorder_level} units
Alert Trigger : Stock reached or fell below 50 units
{txn_line}
ACTION REQUIRED
---------------
This product needs restocking urgently.
Login to SuperMart → Products → find product → click ± to adjust stock.

— SuperMart Automated Alert System
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Force IPv4 to avoid IPv6 issues on some networks
    _orig_getaddrinfo = socket.getaddrinfo
    def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        # Use TLS port 587 — works on all networks including university WiFi
        socket.getaddrinfo = _ipv4_only          # force IPv4
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"[Alert] Email sent: {product_name} ({stock_qty} units left)")
    except smtplib.SMTPAuthenticationError:
        print(f"[Alert] Authentication failed — check App Password in email_config.py")
        print(f"[Alert] Get a new App Password: myaccount.google.com → Security → App passwords")
    except Exception as e:
        print(f"[Alert] Email failed: {e}")
    finally:
        socket.getaddrinfo = _orig_getaddrinfo   # restore original


def send_low_stock_report_email(low_stock_products: list):
    """
    Send a summary report email listing ALL products with stock <= 50.
    Triggered when admin/manager clicks the Full Report button.
    """
    if not EMAIL_ENABLED:
        print(f"[Alert] Email not configured. {len(low_stock_products)} low stock products found.")
        return

    if not low_stock_products:
        print("[Alert] No low stock products found — report email not sent.")
        return

    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count   = len(low_stock_products)
    subject = f"LOW STOCK REPORT — {count} products need restocking ({now[:10]})"

    # Build product rows for the report
    rows = ""
    for i, p in enumerate(low_stock_products, 1):
        status = "OUT OF STOCK" if p.get("stock_qty", 0) == 0 else "LOW STOCK"
        rows += (
            f"  {i:>3}. {p.get('product_name','Unknown'):<28} "
            f"Stock: {p.get('stock_qty',0):>4}  "
            f"Reorder: {p.get('reorder_level',0):>4}  "
            f"[{status}]\n"
        )

    body = f"""SuperMart Management System — Low Stock Report
================================================
Generated   : {now}
Report Type : Full Low Stock Summary (stock <= 50 units)
Total Items : {count} products need attention

PRODUCTS REQUIRING RESTOCKING
------------------------------
{rows}
ACTION REQUIRED
---------------
Please arrange purchase orders or stock adjustments for the
items listed above. Login to SuperMart → Products → find
each product → click the ± button to adjust stock.

— SuperMart Automated Report System
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    _orig_getaddrinfo = socket.getaddrinfo
    def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    try:
        socket.getaddrinfo = _ipv4_only
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"[Alert] Report email sent: {count} low stock products listed.")
    except smtplib.SMTPAuthenticationError:
        print("[Alert] Authentication failed — check App Password in email_config.py")
    except Exception as e:
        print(f"[Alert] Report email failed: {e}")
    finally:
        socket.getaddrinfo = _orig_getaddrinfo