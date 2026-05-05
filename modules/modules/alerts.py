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

try:
    from email_config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
    EMAIL_ENABLED = True
except ImportError:
    EMAIL_ENABLED = False


def send_low_stock_email(product_name: str, stock_qty: int,
                          reorder_level: int, product_id: int):
    """
    Send an email alert when a product falls below reorder level.
    Called automatically after every transaction that deducts stock.
    """
    if not EMAIL_ENABLED:
        print(f"[Alert] Email not configured. Low stock: {product_name} ({stock_qty} left)")
        return

    subject = f"LOW STOCK ALERT — {product_name}"
    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    body = f"""
SuperMart — Low Stock Alert
============================
Time       : {now}
Product    : {product_name} (ID: {product_id})
Stock Left : {stock_qty} units
Reorder At : {reorder_level} units

ACTION REQUIRED: This product has fallen below its reorder level.
Please arrange restocking as soon as possible.

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
        print(f"[Alert] Low stock email sent for {product_name}.")
    except Exception as e:
        print(f"[Alert] Failed to send email: {e}")
