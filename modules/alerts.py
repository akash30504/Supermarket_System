"""
alerts.py
---------
Sends email alerts for low stock events.
Uses Gmail SMTP with App Password authentication.
"""

import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Try to load email credentials from project root first, then data/ folder
EMAIL_ENABLED = False
try:
    from email_config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
    EMAIL_ENABLED = True
except ImportError:
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data'))
        from email_config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
        EMAIL_ENABLED = True
    except ImportError:
        EMAIL_SENDER = EMAIL_PASSWORD = EMAIL_RECEIVER = ""


def send_low_stock_email(product_name: str, stock_qty: int,
                          reorder_level: int, product_id: int,
                          txn_id: int = None, quantity_sold: int = None):
    """
    Send an email alert when a product stock falls at or below 50 units.
    Called automatically after every transaction that deducts stock.
    """
    if not EMAIL_ENABLED:
        print(f"[Alert] Email not configured — Low stock: {product_name} "
              f"({stock_qty} units left). Move email_config.py to project root.")
        return

    subject = f"LOW STOCK ALERT — {product_name} ({stock_qty} units left)"
    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
Alert Trigger : Stock has reached or fallen below 50 units
{txn_line}
ACTION REQUIRED
---------------
This product needs restocking. Please arrange a purchase order
or stock adjustment as soon as possible.

To update stock: Login → Products → find product → click ± button

— SuperMart Automated Alert System
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print(f"[Alert] ✔ Low stock email sent: {product_name} ({stock_qty} units left).")
    except Exception as e:
        print(f"[Alert] ✖ Failed to send email for {product_name}: {e}")