import streamlit as st
import os

from excel_handler import process_excel, process_unified_data
from pdf_handler import process_pdf

# משיכת מפתח ה-API ממשתני הסביבה של השרת (Railway)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# סיסמת הגישה שהגדרת לפענוח
PDF_PASSWORD = "9876"

st.set_page_config(page_title="חברת אטקה - מתקן קבצי הזמנה", page_icon="⚙️", layout="centered")

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
st.write("העלו קובץ Excel, CSV או **PDF**. המערכת תבדוק מק\"טים ותכין קובץ נקי לפורטל אטקה.")

# הרחבנו את סוגי הקבצים לתמיכה בתמונות!
uploaded_file = st.file_uploader("בחרו קובץ", type=["xlsx", "csv", "pdf", "png", "jpg", "jpeg"],
                                 label_visibility="collapsed")

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
                st.success("✨ עיבוד הקובץ הסתיים בהצלחה!")
                st.download_button(label="⬇️ הורד קובץ מוכן לפורטל", data=buffer.getvalue(), file_name=new_file_name,
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # --- מסלול 2: PDF ותמונות (דורש AI וסיסמה) ---
    elif file_ext in ['pdf', 'png', 'jpg', 'jpeg']:
        st.info("ℹ️ פענוח מסמכים חכמים / תמונות דורש הרשאה מיוחדת.")
        user_password = st.text_input("הזן סיסמת מורשה:", type="password")

        if user_password:
            if user_password != PDF_PASSWORD:
                st.error("❌ סיסמה שגויה.")
            else:
                if not OPENAI_API_KEY:
                    st.error("❌ תקלת שרת: מפתח API לא מוגדר ב-Railway. אנא פנה למנהל המערכת.")
                else:
                    if st.button("🚀 התחל פענוח AI"):
                        with st.spinner('רובוט ה-AI קורא את המסמך, זה עשוי לקחת מספר שניות...'):
                            try:
                                if file_ext == 'pdf':
                                    items_list, order_number, is_scanned = process_pdf(uploaded_file, OPENAI_API_KEY)
                                else:
                                    # אם הועלתה תמונה ישירות
                                    from image_handler import process_images
                                    import base64

                                    img_bytes = uploaded_file.getvalue()
                                    st.image(img_bytes, caption="תמונה נסרקת", use_container_width=True)
                                    encoded = base64.b64encode(img_bytes).decode('utf-8')
                                    items_list, order_number = process_images([encoded], OPENAI_API_KEY)
                                    is_scanned = True

                                original_name = f"Order_{order_number}" if order_number else "Scanned_Document"

                                if is_scanned:
                                    st.error(
                                        "⚠️ אזהרה חמורה: הנתונים חולצו מתוך תמונה/סריקה (לא חד-ערכי). חובה לעבור שורה-שורה בקובץ המקורי ולוודא שהמק\"טים והכמויות זוהו נכון!")

                                buffer, new_file_name, warnings, error = process_unified_data(items_list,
                                                                                              f"{original_name}.xlsx")

                                if error:
                                    st.error(error)
                                elif buffer:
                                    if warnings:
                                        with st.expander(f"הערות בקובץ - נמצאו {len(warnings)} הערות (לחצו לצפייה)",
                                                         expanded=True):
                                            for warning in warnings:
                                                if "✅" in warning:
                                                    st.success(warning)
                                                elif "❌" in warning:
                                                    st.error(warning)
                                                else:
                                                    st.warning(warning)
                                    st.success("✨ המסמך פוענח בהצלחה!")
                                    st.download_button(label="⬇️ הורד קובץ מוכן לפורטל", data=buffer.getvalue(),
                                                       file_name=new_file_name,
                                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                            except Exception as e:
                                st.error(f"❌ שגיאה בפענוח המסמך: {e}")

# תחתית הדף
st.write("")
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    if os.path.exists("ATEKA_Logo_He.png"): st.image("ATEKA_Logo_He.png", width=160)
with col2:
    if os.path.exists("yg_logo.png"): st.image("yg_logo.png", width=80)