"""
alerts.py
---------
Sends email alerts for low stock events.
Uses Gmail SMTP with App Password authentication.
Falls back to console alert if network blocks SMTP.
"""

import smtplib
import datetime
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Load credentials ──────────────────────────────────────────────────────────
EMAIL_ENABLED = False
EMAIL_SENDER = EMAIL_PASSWORD = EMAIL_RECEIVER = ""

try:
    from email_config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
    EMAIL_ENABLED = True
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data'))
        from email_config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
        EMAIL_ENABLED = True
    except ImportError:
        pass

# ── Alert log file (always written, even if email fails) ──────────────────────
ALERT_LOG = os.path.join(os.path.dirname(__file__), '..', 'data', 'alert_log.txt')


def _write_alert_log(product_name, stock_qty, reorder_level,
                     product_id, txn_id, quantity_sold):
    """Always write alert to a local log file — proof for viva even if email blocked."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txn_info = f"Transaction #{txn_id} ({quantity_sold} units sold)" if txn_id else "Manual check"
    line = (f"[{now}] LOW STOCK: {product_name} (ID:{product_id}) — "
            f"{stock_qty} units left | Triggered by: {txn_info}\n")
    try:
        with open(ALERT_LOG, 'a', encoding='utf-8') as f:
            f.write(line)
        print(f"[Alert] ✔ Written to alert_log.txt: {product_name} ({stock_qty} units left)")
    except Exception as e:
        print(f"[Alert] Could not write log: {e}")


def _try_send_smtp(msg, sender, password, receiver):
    """Try SMTP_SSL port 465 first, then STARTTLS port 587."""
    # Attempt 1 — SMTP_SSL port 465
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=8) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return True, None
    except Exception as e1:
        pass

    # Attempt 2 — STARTTLS port 587
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=8) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return True, None
    except Exception as e2:
        return False, str(e2)


def send_low_stock_email(product_name: str, stock_qty: int,
                          reorder_level: int, product_id: int,
                          txn_id: int = None, quantity_sold: int = None):
    """
    Send an email alert when stock falls at or below 50 units.
    Always writes to alert_log.txt (works even if network blocks email).
    Tries two SMTP ports (465 and 587) before giving up.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txn_line = ""
    if txn_id and quantity_sold:
        txn_line = f"Triggered by  : Transaction #{txn_id} — {quantity_sold} unit(s) sold\n"

    # Always write to local log file first
    _write_alert_log(product_name, stock_qty, reorder_level,
                     product_id, txn_id, quantity_sold)

    if not EMAIL_ENABLED:
        print(f"[Alert] Email not configured — check email_config.py exists in project root.")
        return

    subject = f"LOW STOCK ALERT — {product_name} ({stock_qty} units left)"

    body = f"""SuperMart Management System — Low Stock Alert
==============================================
Time          : {now}
Product       : {product_name}
Product ID    : {product_id}
Stock Left    : {stock_qty} units
Reorder Level : {reorder_level} units
Alert Trigger : Stock has reached or fallen below 50 units
{txn_line}
ACTION REQUIRED
---------------
This product needs restocking. Please arrange a purchase order
or stock adjustment as soon as possible.

To update stock: Login to SuperMart → Products → find product → click ± button

— SuperMart Automated Alert System
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    success, error = _try_send_smtp(msg, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER)

    if success:
        print(f"[Alert] ✔ Email sent successfully: {product_name} ({stock_qty} units left).")
    else:
        print(f"[Alert] ✖ Email blocked by network (SMTP ports 465/587 unavailable).")
        print(f"[Alert]   Alert saved to data/alert_log.txt instead.")
        print(f"[Alert]   Error: {error}")