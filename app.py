import streamlit as st
import os

# ייבוא הפונקציה מהקובץ החדש שיצרנו
from excel_handler import process_excel

# הגדרות עמוד ועיצוב בסיסי לעברית
st.set_page_config(page_title="חברת אטקה - מתקן קבצי הזמנה", page_icon="⚙️", layout="centered")

# CSS מורחב ליישור מלא לימין
st.markdown("""
    <style>
    .stApp {
        direction: RTL;
        text-align: right;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp span {
        text-align: right !important;
        direction: RTL !important;
    }
    [data-testid="stFileUploadDropzone"] {
        direction: RTL;
        text-align: right !important;
    }
    [data-testid="stFileUploadDropzone"] * {
        text-align: right !important;
        direction: RTL !important;
    }
    div.stButton > button:first-child {
        background-color: #2e7d32;
        color: white;
        width: 100%;
        font-size: 20px;
        font-weight: bold;
        padding: 12px;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- כותרות וטקסט ---
st.title("⚙️ מערכת תיקון קבצי הזמנות")
st.write(
    "העלו את קובץ ההזמנה שלכם כאן. המערכת תסדר את האפסים במק\"ט ותבדוק תקינות של כמויות ומק\"טים.")

# רכיב העלאת קובץ
uploaded_file = st.file_uploader("בחרו קובץ אקסל (xlsx) או CSV", type=["xlsx", "csv"], label_visibility="collapsed")

if uploaded_file is not None:
    # שליחת הקובץ לטיפול במודול החיצוני (excel_handler)
    buffer, new_file_name, warnings, error = process_excel(uploaded_file, uploaded_file.name)

    if error:
        # במקרה של שגיאה חמורה בקובץ
        st.error(error)
    else:
        # הצגת אזהרות (אם יש)
        # הצגת אזהרות (אם יש) עם צבעים לפי האירוע
        if warnings:
            with st.expander(f"הערות בקובץ - נמצאו {len(warnings)} הערות (לחצו לצפייה)", expanded=True):
                for warning in warnings:
                    if "✅" in warning:
                        st.success(warning)  # ירוק
                    elif "❌" in warning:
                        st.error(warning)  # אדום
                    else:
                        st.warning(warning)  # צהוב

        st.success("✨ עיבוד הקובץ הסתיים בהצלחה!")

        # כפתור הורדה
        st.download_button(
            label="⬇️ הורד קובץ מוכן לפורטל",
            data=buffer.getvalue(),
            file_name=new_file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- אזור הלוגואים בתחתית הדף ---
st.write("")
st.write("")
st.markdown("---")

col1, col2 = st.columns([3, 1])

with col1:
    if os.path.exists("ATEKA_Logo_He.png"):
        st.image("ATEKA_Logo_He.png", width=160)
    else:
        st.write("לוגו אטקה (חסר קובץ ATEKA_Logo_He.png)")

with col2:
    if os.path.exists("yg_logo.png"):
        st.image("yg_logo.png", width=80)
    else:
        st.write("לוגו YG (חסר קובץ yg_logo.png)")