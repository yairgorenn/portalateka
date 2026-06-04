import streamlit as st
import pandas as pd
from pdf_handler import process_pdf
from excel_handler import process_excel, process_unified_data
import os

# הגדרת ה-API Key (יש לוודא שהוא מוגדר ב-Secrets של Streamlit או כמשתנה סביבה)
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")

st.set_page_config(page_title="אוטומציה הזמנות אטקה", layout="wide")
st.title("🚀 מערכת אוטומציה להזמנות רכש")

uploaded_file = st.file_uploader("העלה הזמנת רכש (PDF/Excel)", type=["pdf", "xlsx", "csv"])

if uploaded_file:
    # זיהוי סוג הקובץ והפעלת המנוע המתאים
    if uploaded_file.name.lower().endswith('.pdf'):
        if st.button("🚀 התחל פענוח אוטומטי"):
            with st.spinner('המערכת מעבדת את המסמך באמצעות ה-AI...'):
                try:
                    # מנוע ה-AI הוא המנוע הקבוע והיחיד כעת
                    items_list, order_number = process_pdf(uploaded_file, OPENAI_API_KEY)

                    original_name = f"Order_{order_number}" if order_number else "Digital_PDF"

                    buffer, new_file_name, warnings, error = process_unified_data(items_list, f"{original_name}.xlsx")

                    if error:
                        st.error(error)
                    else:
                        st.success("הפענוח הושלם בהצלחה!")
                        st.download_button(
                            label="📥 הורד קובץ אקסל מוכן",
                            data=buffer,
                            file_name=new_file_name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                        # הצגת אזהרות (השורות הכתומות) למשתמש
                        if warnings:
                            st.warning("שים לב, נמצאו שורות שדורשות בדיקה:")
                            for warning in warnings:
                                st.write(warning)

                except Exception as e:
                    st.error(f"שגיאה בתהליך הפענוח: {str(e)}")

    else:
        # טיפול בקבצי אקסל/CSV קיימים
        if st.button("עיבוד קובץ אקסל"):
            buffer, new_file_name, warnings, error = process_excel(uploaded_file, uploaded_file.name)
            if error:
                st.error(error)
            else:
                st.download_button(
                    label="📥 הורד קובץ אקסל מוכן",
                    data=buffer,
                    file_name=new_file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )