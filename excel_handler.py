import pandas as pd
import io
import os
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from db_handler import find_sku_in_db

SKU_LENGTH = 9


def process_unified_data(items_list, original_file_name):
    """
    מקבלת רשימת פריטים ומייצרת קובץ אקסל בעל שתי לשוניות:
    1. העתקה לפריוריטי: מק"ט | ריק (רווח צר) | כמות | הערות
    2. טעינה לפורטל: מבנה רגיל (מק"ט | כמות | הערות)
    """
    if not items_list:
        return None, None, [], "❌ שגיאה: לא נמצאו פריטים תקינים לפענוח במסמך."

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
        is_valid = True

        # === 1. חיפוש חכם במסד הנתונים ===
        found_sku = find_sku_in_db(clean_sku)

        if found_sku:
            final_sku = str(found_sku).zfill(SKU_LENGTH)
        else:
            status_note = "❌ מק\"ט לא מוכר"
            is_valid = False
            warnings.append(item)

        # === 2. בדיקת כמות ===
        if not clean_qty or not clean_qty.replace('.', '', 1).isdigit():
            status_note += " | ⚠️ חסרה כמות תקינה"
            is_valid = False
            if item not in warnings:
                warnings.append(item)

        # === 3. הרכבת הנתונים לגיליון פריוריטי ===
        priority_data.append({
            'מק"ט': final_sku,
            'תיאור (רווח)': "",  # עמודה B נשארת ריקה
            'כמות': clean_qty,
            'הערות מערכת': status_note,
            'is_valid': is_valid  # שדה עזר לעיצוב הצבעים (נסיר אותו לפני ההדפסה לאקסל)
        })

        # === 4. הרכבת הנתונים לגיליון הפורטל ===
        portal_data.append({
            'מק"ט': final_sku,
            'כמות': clean_qty,
            'הערות מערכת': status_note
        })

    df_priority = pd.DataFrame(priority_data)
    df_portal = pd.DataFrame(portal_data)

    buffer = io.BytesIO()

    # יצירת קובץ אקסל רב-לשוניות
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # מסירים את עמודת ה-is_valid מגיליון הפריוריטי לפני הכתיבה לקובץ
        df_priority.drop(columns=['is_valid']).to_excel(writer, sheet_name='העתקה לפריוריטי', index=False)
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

        # הגדרת מסגרת דקה וסטנדרטית לכל תא
        thin_border = Border(left=Side(style='thin'),
                             right=Side(style='thin'),
                             top=Side(style='thin'),
                             bottom=Side(style='thin'))

        for cell in ws_priority[1]:
            cell.font = font_bold
            cell.alignment = alignment_center
            cell.border = thin_border  # מסגרת לכותרות

        # מעבר על כל השורות והוספת עיצוב ומסגרות
        for row_idx, row in enumerate(
                ws_priority.iter_rows(min_row=2, max_row=ws_priority.max_row, min_col=1, max_col=4)):
            # שולפים את הסטטוס מהמילון כדי לדעת איזה צבע לשים
            current_is_valid = priority_data[row_idx]['is_valid']

            for cell in row:
                cell.alignment = alignment_right
                cell.border = thin_border  # מסגרת לכל תא בטבלה

            if not current_is_valid:
                for cell in row:
                    cell.fill = fill_warning
            else:
                # אם השורה תקינה, נצבע רק את עמודות A, B, C בירוק
                row[0].fill = fill_success
                row[1].fill = fill_success
                row[2].fill = fill_success

        ws_priority.column_dimensions['A'].width = 20
        ws_priority.column_dimensions['B'].width = 5
        ws_priority.column_dimensions['C'].width = 15
        ws_priority.column_dimensions['D'].width = 50  # תוקן מ-5 ל-50 כדי שיראו את ההערות

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