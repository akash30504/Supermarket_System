from modules.alerts import send_low_stock_email

print("Sending test email...")
send_low_stock_email(
    product_name  = "Chicken Breast",
    stock_qty     = 3,
    reorder_level = 15,
    product_id    = 99,
)
print("Done. Check your inbox.")