import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(order_number, rows_count, warnings_count):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return  # מדלג אם המשתנים לא מוגדרים בשרת

    message = (
        f"🚀 בקשת פענוח חדשה במערכת אטקה!\n"
        f"📄 מס' הזמנה/קובץ: {order_number}\n"
        f"✅ שורות שפוענחו: {rows_count}\n"
        f"⚠️ שורות בכתום (דורשות בדיקה): {warnings_count}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        # שליחת ההודעה מאחורי הקלעים ללא עיכוב המשתמש
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")
