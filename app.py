import streamlit as st
import pandas as pd
import io
import os
from openpyxl.styles import Font, PatternFill, Alignment

# הגדרת אורך המק"ט הרצוי בפוריטי (מעודכן ל-9 ספרות)
SKU_LENGTH = 9

# הגדרות עמוד ועיצוב בסיסי לעברית עם האייקון (גלגל שיניים)
st.set_page_config(page_title="חברת אטקה - מתקן קבצי הזמנה", page_icon="⚙️", layout="centered")

# CSS מורחב ליישור מלא לימין של כל סוגי הטקסטים והכותרות בדף
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
st.title("⚙️חברת אטקה - מערכת תיקון קבצי הזמנות")
st.write(
    "העלו את קובץ ההזמנה שלכם כאן. המערכת תסדר את האפסים במק\"ט ותנקה שורות ריקות או שגויות.")
st.write("**שימו לב:** שורות ללא כמות תקינה או ללא מק\"ט יימחקו מהקובץ הסופי באופן אוטומטי.")

# רכיב העלאת קובץ
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
            # לקיחת 2 העמודות הראשונות בלבד ומתן שמות זמניים לעיבוד
            df_clean = df.iloc[:, [0, 1]].copy()
            df_clean.columns = ['SKU', 'QTY']


            # פונקציה לתיקון המק"ט - מחזירה None אם המק"ט לא תקין או ריק
            def fix_sku(val):
                if pd.isna(val) or str(val).strip() == "":
                    return None
                val_str = str(val).strip()
                if val_str.endswith('.0'):
                    val_str = val_str[:-2]
                return val_str.zfill(SKU_LENGTH)


            # פונקציה לניקוי הכמות - מחזירה מספר שלם גדול מ-0. אחרת מחזירה None
            def fix_qty(val):
                if pd.isna(val):
                    return None
                try:
                    num = int(float(val))
                    if num > 0:
                        return num
                    return None
                except:
                    return None  # למקרה שזה טקסט שלא ניתן להפוך למספר


            # הרצת התיקונים על העמודות
            df_clean['SKU'] = df_clean['SKU'].apply(fix_sku)
            df_clean['QTY'] = df_clean['QTY'].apply(fix_qty)

            # --- מחיקת השורות הלא תקינות ---
            # פונקציה זו מוחקת כל שורה שיש בה None (כלומר, מק"ט חסר או כמות לא תקינה)
            df_clean.dropna(subset=['SKU', 'QTY'], inplace=True)

            # קביעת שמות עמודות סופיים לעברית
            df_clean.columns = ['מק"ט', 'כמות']

            # יצירת קובץ אקסל חדש בזיכרון
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_clean.to_excel(writer, index=False)

                # הגדרות עיצוב אקסל (RTL, פונטים, צבעים)
                workbook = writer.book
                worksheet = workbook.active

                # הגדרות גיליון
                worksheet.views.sheetView[0].showGridLines = True
                worksheet.sheet_properties.pageSetUpPr.fitToPage = True
                worksheet.sheet_view.rightToLeft = True

                # הגדרת סגנונות
                font_tahoma_regular = Font(name='Tahoma', size=14)
                font_tahoma_header = Font(name='Tahoma', size=14, bold=True, color='FFFFFF')  # לבן
                fill_header = PatternFill(start_color='1F497D', end_color='1F497D', fill_type='solid')  # כחול כהה
                center_align = Alignment(horizontal='center', vertical='center')

                # החלת העיצוב על כל התאים בקובץ
                for row in worksheet.iter_rows():
                    for cell in row:
                        cell.alignment = center_align
                        if cell.row == 1:  # שורת הכותרת
                            cell.font = font_tahoma_header
                            cell.fill = fill_header
                        else:  # שאר הנתונים
                            cell.font = font_tahoma_regular

                # הרחבת העמודות שייראה אסתטי
                worksheet.column_dimensions['A'].width = 20
                worksheet.column_dimensions['B'].width = 15

            st.success("✨ הקובץ נוקה ותוקן בהצלחה! לחצו על הכפתור הירוק למטה כדי להוריד אותו:")

            # דינמיות לשם הקובץ: חילוץ השם המקורי והוספת הטקסט
            original_name, _ = os.path.splitext(uploaded_file.name)
            new_file_name = f"{original_name}_מוכן_לפורטל.xlsx"

            # כפתור הורדה
            st.download_button(
                label="⬇️ הורד קובץ מתוקן לפורטל",
                data=buffer.getvalue(),
                file_name=new_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"שגיאה בעיבוד הקובץ. ודאו שהקובץ תקין ושיש בו נתונים החל מהשורה השנייה.")

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