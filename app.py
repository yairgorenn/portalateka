import streamlit as st
import os
import time
from pdf_router import split_pdf_to_orders
from db_handler import ensure_catalog_db

from excel_handler import process_excel, process_unified_data
from pdf_handler import process_pdf
from telegram_handler import send_telegram_message

# משיכת מפתחות ה-API ומשתני הסביבה של השרת (Railway)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# סיסמת הגישה שהגדרת לפענוח
PDF_PASSWORD = "9876"

ensure_catalog_db("PB.csv")
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
                        try:
                            # שלב א': חיתוך הקובץ למנות (הזמנות)
                            with st.spinner("מנתח את הקובץ ומחפש הזמנות רכש..."):
                                split_orders = split_pdf_to_orders(uploaded_file)
                                total_orders = len(split_orders)

                            if total_orders == 1:
                                pass
                            else:
                                st.info(f"✂️ הקובץ פוצל ל-{total_orders} הזמנות שונות! מפענח אותן אחת-אחת...")
                                # --- יצירת "מקום שמור" לאזהרה שתשתנה בסיום ---
                                warning_placeholder = st.empty()
                                warning_placeholder.warning(
                                    "⚠️ המערכת מעבדת מספר הזמנות ברצף. **נא לא ללחוץ על כפתורי ההורדה** עד לסיום מלא של כל הרשימה (כדי לא לעצור את התהליך)!")

                            # שלב ב': ריצה על כל הזמנה בנפרד
                            for i, order_dict in enumerate(split_orders):
                                order_name = order_dict["order_name"]
                                pdf_buffer = order_dict["pdf_obj"]

                                #st.markdown(f"### 📦 מעבד: {order_name} ({i + 1}/{total_orders})")

                                # שלב א': חיתוך הקובץ למנות (הזמנות)
                                with st.spinner("מנתח את הקובץ ומחפש הזמנות רכש..."):
                                    split_orders = split_pdf_to_orders(uploaded_file)
                                    total_orders = len(split_orders)

                                if total_orders == 1:
                                    st.info("🎯 פוענחה הזמנה אחת מהמסמך. ניגש לעבודה...")
                                else:
                                    st.info(f"✂️ הקובץ פוצל ל-{total_orders} הזמנות שונות! מפענח אותן אחת-אחת...")

                                    # --- יצירת "מקום שמור" לאזהרה שתשתנה בסיום ---
                                    warning_placeholder = st.empty()
                                    warning_placeholder.warning(
                                        "⚠️ המערכת מעבדת מספר הזמנות ברצף. **נא לא ללחוץ על כפתורי ההורדה** עד לסיום מלא של כל הרשימה (כדי לא לעצור את התהליך)!")

                                # שלב ב': ריצה על כל הזמנה בנפרד
                                for i, order_dict in enumerate(split_orders):
                                    order_name = order_dict["order_name"]
                                    pdf_buffer = order_dict["pdf_obj"]

                                    st.markdown(f"### 📦 מעבד: {order_name} ({i + 1}/{total_orders})")

                                    with st.spinner(f"מפענח נתונים ב-AI עבור {order_name}..."):
                                        items_list, returned_order_num = process_pdf(pdf_buffer, OPENAI_API_KEY)

                                        final_order_name = f"Order_{returned_order_num}" if returned_order_num else order_name

                                        excel_name = f"{final_order_name}.xlsx"
                                        buffer, new_file_name, warnings, error = process_unified_data(items_list,
                                                                                                      excel_name)

                                        if error:
                                            st.error(f"❌ שגיאה בהזמנה {final_order_name}: {error}")
                                        elif buffer:
                                            # חילוץ נתונים לשליחה בטלגרם
                                            rows_count = len(items_list) if items_list else 0
                                            warnings_count = len(warnings) if warnings else 0

                                            send_telegram_message(final_order_name, rows_count, warnings_count)

                                            st.success(f"✅ הזמנה {final_order_name} פוענחה בהצלחה!")

                                            if warnings:
                                                st.warning(
                                                    f"⚠️ שימו לב: המערכת זיהתה **{len(warnings)}** שורות שדורשות את תשומת לבכם.\n\nאנא פתחו את הקובץ המצורף ובדקו את השורות המסומנות בכתום (הסבר מפורט ממתין לכם בעמודה C).")
                                            else:
                                                st.info("🎯 הקובץ תקין לחלוטין - לא נמצאו הערות מערכת.")

                                            st.download_button(
                                                label=f"⬇️ הורד קובץ מוכן ({final_order_name})",
                                                data=buffer.getvalue(),
                                                file_name=new_file_name,
                                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                key=f"dl_btn_{i}_{final_order_name}"
                                            )

                                    # שלב ג': השהיה למניעת עומס
                                    if i < total_orders - 1:
                                        with st.spinner("ממתין 20 שניות למניעת עומס על שרתי ה-AI..."):
                                            time.sleep(20)

                                # --- שלב ד': סיום הלולאה והחלפת האזהרה ---
                                if total_orders > 1:
                                    warning_placeholder.success(
                                        "🎉 פענוח כל ההזמנות הסתיים! כעת ניתן להוריד את כל הקבצים בבטחה.")

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