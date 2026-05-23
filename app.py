import streamlit as st
import pandas as pd
import io
import os

# הגדרת אורך המק"ט הרצוי בפוריטי (מעודכן ל-9 ספרות)
SKU_LENGTH = 9

# הגדרות עמוד ועיצוב בסיסי לעברית עם האייקון (גלגל שיניים)
st.set_page_config(page_title="חברת אטקה - מתקן קבצי הזמנה", page_icon="⚙️", layout="centered")

# CSS מורחב ליישור מלא לימין של כל סוגי הטקסטים והכותרות בדף
st.markdown("""
    <style>
    /* הגדרת כיוון כללי לימין עבור כל האפליקציה */
    .stApp {
        direction: RTL;
        text-align: right;
    }
    /* יישור כותרות, טקסטים ותוויות באופן מפורש לימין */
    .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label, .stApp span {
        text-align: right !important;
        direction: RTL !important;
    }
    /* יישור מלא של אזור גרירת הקבצים והטקסטים שבתוכו לימין */
    [data-testid="stFileUploadDropzone"] {
        direction: RTL;
        text-align: right !important;
    }
    [data-testid="stFileUploadDropzone"] * {
        text-align: right !important;
        direction: RTL !important;
    }
    /* עיצוב כפתור ההורדה הירוק */
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
    "העלו את קובץ ההזמנה שלכם כאן. המערכת תסדר אוטומטית את האפסים החסרים במק\"ט (תשלים ל-9 ספרות) ותכין קובץ נקי לפורטל.")
st.write("**שימו לב:** השורה הראשונה בקובץ המקורי (שורת הכותרת) מושמטת אוטומטית.")

# רכיב העלאת קובץ - תומך באקסל וב-CSV
uploaded_file = st.file_uploader("בחרו קובץ אקסל (xlsx) או CSV", type=["xlsx", "csv"], label_visibility="collapsed")

if uploaded_file is not None:
    try:
        # קריאת הקובץ תוך התעלמות מוחלטת מהשורה הראשונה (skiprows=1)
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, skiprows=1, header=None)
        else:
            df = pd.read_excel(uploaded_file, skiprows=1, header=None)

        # בדיקה שיש לפחות שתי עמודות בנתונים
        if df.shape[1] < 2:
            st.error("❌ שגיאה: הקובץ חייב להכיל לפחות שתי עמודות (מק\"ט וכמות).")
        else:
            # לקיחת 2 העמודות הראשונות בלבד (מתעלם מכל השאר)
            df_clean = df.iloc[:, [0, 1]].copy()

            # ניקוי שורות ריקות לחלוטין
            df_clean.dropna(how='all', inplace=True)


            # פונקציה לתיקון המק"ט והוספת האפסים
            def fix_sku(val):
                if pd.isna(val):
                    return ""
                val_str = str(val).strip()
                if val_str.endswith('.0'):
                    val_str = val_str[:-2]
                return val_str.zfill(SKU_LENGTH)


            # פונקציה לניקוי הכמות (הפיכה למספר שלם)
            def fix_qty(val):
                if pd.isna(val):
                    return 0
                try:
                    return int(float(val))
                except:
                    return val


            # הרצת התיקונים על העמודות
            df_clean.iloc[:, 0] = df_clean.iloc[:, 0].apply(fix_sku)
            df_clean.iloc[:, 1] = df_clean.iloc[:, 1].apply(fix_qty)

            # קביעת שמות עמודות קבועים
            df_clean.columns = ['מק"ט', 'כמות']

            # יצירת קובץ אקסל חדש בזיכרון
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_clean.to_excel(writer, index=False)

                # הגדרת כיוון הגיליון מימין לשמאל (RTL) באקסל החדש שיוצא
                workbook = writer.book
                worksheet = workbook.active
                worksheet.views.sheetView[0].showGridLines = True  # שמירה על קווי רשת גלויים
                worksheet.sheet_properties.pageSetUpPr.fitToPage = True
                worksheet.sheet_view.rightToLeft = True  # הפיכת כיוון הגיליון באקסל

            st.success("✨ הקובץ תוקן בהצלחה! לחצו על הכפתור הירוק למטה כדי להוריד אותו:")

            # דינמיות לשם הקובץ: חילוץ השם המקורי והוספת המילה "_מתוקן"
            original_name, _ = os.path.splitext(uploaded_file.name)
            new_file_name = f"{original_name}_מתוקן.xlsx"

            # כפתור הורדה גדול ובולט
            st.download_button(
                label="⬇️ הורד קובץ מתוקן לפורטל",
                data=buffer.getvalue(),
                file_name=new_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"שגיאה בעיבוד הקובץ. ודאו שהקובץ תקין ושיש בו נתונים החל מהשורה השנייה.")

# --- אזור הלוגואים (הועבר לתחתית הדף והוקטן) ---
st.write("")  # מרווח קטן מהכפתור
st.write("")
st.markdown("---")  # קו הפרדה ויזואלי דק מעל הפוטר

# יצירת שתי עמודות קטנות יותר בתחתית הדף
col1, col2 = st.columns([3, 1])

with col1:
    if os.path.exists("ATEKA_Logo_He.png"):
        st.image("ATEKA_Logo_He.png", width=160)  # הוקטן מ-250 ל-160
    else:
        st.write("לוגו אטקה (חסר קובץ ATEKA_Logo_He.png)")

with col2:
    if os.path.exists("yg_logo.png"):
        st.image("yg_logo.png", width=80)  # הוקטן מ-120 ל-80
    else:
        st.write("לוגו YG (חסר קובץ yg_logo.png)")