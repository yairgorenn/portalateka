import streamlit as st
import os
import requests

from excel_handler import process_excel, process_unified_data
from pdf_handler import process_pdf

# משיכת מפתחות ה-API ומשתני הסביבה של השרת (Railway)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# סיסמת הגישה שהגדרת לפענוח
PDF_PASSWORD = "9876"


# פונקציה לשליחת התראה לטלגרם
def send_telegram_alert(order_number, rows_count, warnings_count):
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


st.set_page_config(page_title="חברת אטקה - מתקן קבצי הזמנה יאיר גורן", page_icon="⚙️", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: RTL; text-align: right; }
    .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp span { text-align: right !important; direction: RTL !important; }
    [data-testid="stFileUploadDropzone"] { direction: RTL; text-align: right !important; }
    [data-testid="stFileUploadDropzone"] * { text-align: right !important; direction: RTL !important; }
    div.stButton > button:first-child { background-color: #2e7d32; color: white; width: 100%; font-size: 20px; font-weight: bold; padding: 12px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚙️ מערכת חכמה לקליטת הזמנות")
st.write("העלו קובץ Excel, CSV או **PDF**. המערכת תבדוק מק\"טים ותכין קובץ נקי לפורטל אטקה. לשאלות ותמיכה יאיר גורן")

# המערכת מקבלת רק קבצי מקור - הורדנו תמיכה ב-png/jpg
uploaded_file = st.file_uploader("בחרו קובץ", type=["xlsx", "csv", "pdf"], label_visibility="collapsed")

if uploaded_file is not None:
    file_ext = uploaded_file.name.lower().split('.')[-1]

    # --- מסלול 1: אקסל/CSV ---
    if file_ext in ['xlsx', 'csv']:
        with st.spinner('מעבד קובץ, אנא המתן...'):
            buffer, new_file_name, warnings, error = process_excel(uploaded_file, uploaded_file.name)

            if error:
                st.error(error)
            elif buffer:
                if warnings:
                    with st.expander(f"הערות בקובץ - נמצאו {len(warnings)} הערות (לחצו לצפייה)", expanded=True):
                        for warning in warnings:
                            if "✅" in warning:
                                st.success(warning)
                            elif "❌" in warning:
                                st.error(warning)
                            else:
                                st.warning(warning)
                st.success("✅ הקובץ פוענח בהצלחה ומוכן להורדה!")

                if warnings:
                    st.warning(
                        f"⚠️ שימו לב: המערכת זיהתה **{len(warnings)}** שורות שדורשות את תשומת לבכם.\n\nאנא פתחו את הקובץ המצורף ובדקו את השורות המסומנות בכתום (הסבר מפורט ממתין לכם בעמודה C).")
                else:
                    st.info("🎯 הקובץ תקין לחלוטין - לא נמצאו הערות מערכת.")
                st.download_button(label="⬇️ הורד קובץ מוכן לפורטל", data=buffer.getvalue(), file_name=new_file_name,
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # --- מסלול 2: PDF ---
    elif file_ext == 'pdf':
        st.info("ℹ️ פענוח מסמכי PDF דורש הרשאה מיוחדת.")
        user_password = st.text_input("הזן סיסמת מורשה:", type="password")

        if user_password:
            if user_password != PDF_PASSWORD:
                st.error("❌ סיסמה שגויה.")
            else:
                if not OPENAI_API_KEY:
                    st.error("❌ תקלת שרת: מפתח API לא מוגדר ב-Railway. אנא פנה למנהל המערכת.")
                else:
                    if st.button("🚀 התחל פענוח"):
                        with st.spinner('המערכת מעבדת את המסמך...'):
                            try:
                                items_list, order_number = process_pdf(uploaded_file, OPENAI_API_KEY)

                                original_name = f"Order_{order_number}" if order_number else "Digital_PDF"

                                buffer, new_file_name, warnings, error = process_unified_data(items_list,
                                                                                              f"{original_name}.xlsx")

                                if error:
                                    st.error(error)
                                elif buffer:
                                    # חילוץ נתונים לשליחה בטלגרם
                                    rows_count = len(items_list) if items_list else 0
                                    warnings_count = len(warnings) if warnings else 0

                                    # הפעלת שליחת ההודעה לטלגרם
                                    send_telegram_alert(original_name, rows_count, warnings_count)

                                    st.success("✅ הקובץ פוענח בהצלחה ומוכן להורדה!")

                                    if warnings:
                                        st.warning(
                                            f"⚠️ שימו לב: המערכת זיהתה **{len(warnings)}** שורות שדורשות את תשומת לבכם.\n\nאנא פתחו את הקובץ המצורף ובדקו את השורות המסומנות בכתום (הסבר מפורט ממתין לכם בעמודה C).")
                                    else:
                                        st.info("🎯 הקובץ תקין לחלוטין - לא נמצאו הערות מערכת.")
                                    st.download_button(label="⬇️ הורד קובץ מוכן לפורטל", data=buffer.getvalue(),
                                                       file_name=new_file_name,
                                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                            except ValueError as ve:
                                if str(ve) == "SCANNED_PDF_BLOCKED":
                                    st.error("🛑 **שגיאה: זוהה מסמך סרוק או תמונה.**")
                                    st.warning(
                                        "מערכת אטקה מקבלת קבצי Excel, CSV או PDF **דיגיטליים מקוריים בלבד** למניעת טעויות באספקה.")
                                else:
                                    st.error(f"❌ שגיאה: {ve}")
                            except Exception as e:
                                st.error(f"❌ תקלה בלתי צפויה: {e}")

# תחתית הדף
st.write("")
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("ATEKA_Logo_He.png"): st.image("ATEKA_Logo_He.png", width=160)
with col2:
    if os.path.exists("yg_logo.png"): st.image("yg_logo.png", width=100)