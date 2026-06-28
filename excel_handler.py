import pandas as pd
import io
import os
from openpyxl.styles import Font, PatternFill, Alignment
from functools import lru_cache

SKU_LENGTH = 9


@lru_cache(maxsize=1)
def load_catalog(csv_path="PB.csv"):
    """
    טוען את הקטלוג לזיכרון. רץ רק פעם אחת כשהשרת עולה (Cache).
    """
    ateka_set = set()
    vendor_to_ateka = {}

    if not os.path.exists(csv_path):
        return ateka_set, vendor_to_ateka

    df = pd.read_csv(csv_path, header=None, dtype=str)
    for _, row in df.iterrows():
        ateka_sku = str(row[0]).strip()
        vendor_sku = str(row[1]).replace(" ", "").replace("-", "").strip()

        if ateka_sku != 'nan':
            ateka_set.add(ateka_sku.lstrip('0'))
            ateka_set.add(ateka_sku)

        if vendor_sku != 'nan':
            vendor_to_ateka[vendor_sku.upper()] = ateka_sku
            vendor_to_ateka[vendor_sku.upper().lstrip('0')] = ateka_sku

    return ateka_set, vendor_to_ateka


def process_unified_data(items_list, original_file_name):
    """
    מקבלת רשימת פריטים ומייצרת קובץ אקסל בעל שתי לשוניות:
    1. העתקה לפריוריטי: מק"ט | ריק (רווח צר) | כמות | הערות
    2. טעינה לפורטל: מבנה רגיל (מק"ט | כמות | הערות)
    """
    if not items_list:
        return None, None, [], "❌ שגיאה: לא נמצאו פריטים תקינים לפענוח במסמך."

    ateka_set, vendor_to_ateka = load_catalog()

    priority_data = []
    portal_data = []
    warnings = []

    for item in items_list:
        orig_sku = str(item.get('sku', '')).strip()
        orig_qty = str(item.get('qty', '')).strip()

        # סינון שורות ריקות לחלוטין
        if not orig_sku and not orig_qty:
            continue

        clean_sku = orig_sku.upper().replace(" ", "").replace("-", "")
        clean_qty = orig_qty

        final_sku = orig_sku
        status_note = ""

        is_exact_match = False
        is_vendor_match = False

        # 1. בדיקת התאמה מלאה לאטקה
        if clean_sku in ateka_set:
            final_sku = clean_sku
            is_exact_match = True
        elif clean_sku.lstrip('0') in ateka_set:
            final_sku = clean_sku.lstrip('0').zfill(SKU_LENGTH)
            is_exact_match = True
            status_note = "✅ נוספו אפסים מובילים"

        # 2. בדיקת התאמה לפי יצרן
        if not is_exact_match:
            if clean_sku in vendor_to_ateka:
                final_sku = vendor_to_ateka[clean_sku]
                is_vendor_match = True
                status_note = "✅ הומר ממק\"ט יצרן למק\"ט אטקה"
            elif clean_sku.lstrip('0') in vendor_to_ateka:
                final_sku = vendor_to_ateka[clean_sku.lstrip('0')]
                is_vendor_match = True
                status_note = "✅ הומר ממק\"ט יצרן למק\"ט אטקה"

        # 3. טיפול במק"ט לא מזוהה
        if not is_exact_match and not is_vendor_match:
            final_sku = orig_sku
            if not final_sku:
                status_note = "❌ חסר מק\"ט"
                warnings.append(item)
            else:
                status_note = "❌ מק\"ט לא מוכר במערכת – אנא בדוק"
                warnings.append(item)

        # 4. בדיקת כמות
        if not clean_qty or not clean_qty.replace('.', '', 1).isdigit():
            status_note += " | ⚠️ חסרה כמות תקינה"
            if item not in warnings:
                warnings.append(item)

        # הרכבת הנתונים לגיליון פריוריטי
        priority_data.append({
            'מק"ט': final_sku,
            'תיאור (רווח)': "",  # עמודה B נשארת ריקה
            'כמות': clean_qty,
            'הערות מערכת': status_note
        })

        # הרכבת הנתונים לגיליון הפורטל הישן והמוכר
        portal_data.append({
            'מק"ט': final_sku,
            'כמות': clean_qty,
            'הערות מערכת': status_note
        })

    df_priority = pd.DataFrame(priority_data)
    df_portal = pd.DataFrame(portal_data)

    buffer = io.BytesIO()

    # יצירת קובץ אקסל רב-לשוניות
    # יצירת קובץ אקסל רב-לשוניות
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_priority.to_excel(writer, sheet_name='העתקה לפריוריטי', index=False)
        df_portal.to_excel(writer, sheet_name='טעינה לפורטל', index=False)

        workbook = writer.book
        fill_warning = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid")
        fill_success = PatternFill(start_color="E6FFCC", end_color="E6FFCC",
                                   fill_type="solid")  # ירוק בהיר לשורות תקינות
        font_bold = Font(bold=True)
        alignment_center = Alignment(horizontal='center', vertical='center')
        alignment_right = Alignment(horizontal='right', vertical='center')

        # === עיצוב גיליון 1: העתקה לפריוריטי ===
        ws_priority = workbook['העתקה לפריוריטי']
        ws_priority.sheet_view.rightToLeft = True

        for cell in ws_priority[1]:
            cell.font = font_bold
            cell.alignment = alignment_center

        for row in ws_priority.iter_rows(min_row=2, max_row=ws_priority.max_row, min_col=1, max_col=4):
            for cell in row:
                cell.alignment = alignment_right

            note_cell = row[3].value
            if note_cell and ("❌" in str(note_cell) or "⚠️" in str(note_cell)):
                for cell in row:
                    cell.fill = fill_warning
            else:
                # אם השורה תקינה, נצבע רק את עמודות A, B, C בירוק
                row[0].fill = fill_success
                row[1].fill = fill_success
                row[2].fill = fill_success

        ws_priority.column_dimensions['A'].width = 20
        ws_priority.column_dimensions['B'].width = 5  # רוחב צר מאוד לעמודה הריקה
        ws_priority.column_dimensions['C'].width = 15
        ws_priority.column_dimensions['D'].width = 50  # הערות נכנסו לעמודה D

        # === עיצוב גיליון 2: טעינה לפורטל ===
        ws_portal = workbook['טעינה לפורטל']
        ws_portal.sheet_view.rightToLeft = True

        for cell in ws_portal[1]:
            cell.font = font_bold
            cell.alignment = alignment_center

        for row in ws_portal.iter_rows(min_row=2, max_row=ws_portal.max_row, min_col=1, max_col=3):
            for cell in row:
                cell.alignment = alignment_right

            note_cell = row[2].value
            if note_cell and ("❌" in str(note_cell) or "⚠️" in str(note_cell)):
                for cell in row:
                    cell.fill = fill_warning

        ws_portal.column_dimensions['A'].width = 20
        ws_portal.column_dimensions['B'].width = 15
        ws_portal.column_dimensions['C'].width = 50

    buffer.seek(0)
    original_name, _ = os.path.splitext(original_file_name)
    new_file_name = f"{original_name}_מוכן_לפורטל.xlsx"

    return buffer, new_file_name, warnings, None


def process_excel(uploaded_file, original_file_name):
    """
    פונקציית מעטפת לאקסל: קוראת את הקובץ וממירה אותו לרשימת מילונים
    שמתאימה לפונקציית הליבה.
    """
    try:
        if original_file_name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, skiprows=1, header=None)
        else:
            df = pd.read_excel(uploaded_file, skiprows=1, header=None)

        if df.shape[1] < 2:
            return None, None, [], "❌ שגיאה: הקובץ חייב להכיל לפחות שתי עמודות (מק\"ט וכמות)."

        items_list = []
        for index, row in df.iterrows():
            items_list.append({
                'row_num': index + 1,
                'sku': str(row[0]),
                'qty': str(row[1]) if pd.notna(row[1]) else ""
            })

        return process_unified_data(items_list, original_file_name)

    except Exception as e:
        return None, None, [], f"❌ שגיאה בלתי צפויה: {e}"