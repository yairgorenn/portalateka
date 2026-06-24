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
    פונקציית הליבה המאוחדת!
    מקבלת רשימת פריטים ממקור כלשהו (אקסל או AI) ומעבירה בשרשרת החיול.
    """
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")

    cleaned_skus = []
    cleaned_qtys = []
    row_notes = []  # רשימה חדשה לאיסוף ההערות לעמודה C
    warnings = []
    row_has_error = []

    for item in items_list:
        row_num = item.get('row_num', '?')
        orig_sku = item.get('sku', '')
        orig_qty = item.get('qty', '')
        is_error = item.get('is_error', False)

        current_row_notes = []  # איסוף ההערות לשורה הספציפית הזו

        # --- א) לוגיקת מק"ט והצלבת קטלוג ---
        if pd.isna(orig_sku) or str(orig_sku).strip() == "" or str(orig_sku).strip().lower() == 'nan':
            sku_val = ""
            msg = "מקט לא מלא (חסר ערך)"
            current_row_notes.append(f"⚠️ {msg}")
            warnings.append(f"⚠️ שורה {row_num}: שים לב - {msg}.")
            is_error = True
        else:
            sku_str = str(orig_sku).strip()
            if sku_str.endswith('.0'):
                sku_str = sku_str[:-2]

            clean_sku = sku_str.replace(" ", "").replace("-", "")
            X_upper = clean_sku.upper()
            X_no_zeros = clean_sku.lstrip('0')

            # 1. בדיקה אם זה מק"ט אטקה
            if sku_str in ateka_set or X_no_zeros in ateka_set:
                matched_ateka = sku_str if sku_str in ateka_set else X_no_zeros
                if matched_ateka.lstrip('0') == '888888':
                    sku_val = sku_str
                    msg = "הפריט לא קיים במערכת (מקט 888888). הושאר מק\"ט מקורי"
                    current_row_notes.append(f"❌ {msg}")
                    warnings.append(f"❌ שורה {row_num}: {msg}.")
                    is_error = True
                else:
                    sku_val = matched_ateka.zfill(SKU_LENGTH)

            # 2. בדיקה אם זה מק"ט יצרן
            elif X_upper in vendor_to_ateka or X_upper.lstrip('0') in vendor_to_ateka:
                matched_ateka = vendor_to_ateka.get(X_upper) or vendor_to_ateka.get(X_upper.lstrip('0'))
                if matched_ateka.lstrip('0') == '888888':
                    sku_val = sku_str
                    msg = "הפריט לא קיים במערכת (מקט 888888). הושאר מק\"ט יצרן"
                    current_row_notes.append(f"❌ {msg}")
                    warnings.append(f"❌ שורה {row_num}: {msg}.")
                    is_error = True
                else:
                    sku_val = matched_ateka.zfill(SKU_LENGTH)
                    msg = "הומר ממק\"ט יצרן למק\"ט אטקה"
                    current_row_notes.append(f"✅ {msg}")
                    warnings.append(f"✅ שורה {row_num}: תקין - {msg} ({sku_val}).")

            # 3. לא קיים בשום מקום
            else:
                sku_val = sku_str
                msg = "מק\"ט לא מוכר במערכת – אנא בדוק"
                current_row_notes.append(f"❌ {msg}")
                warnings.append(f"❌ שורה {row_num}: {msg} ({sku_str}).")
                is_error = True

        # --- ב) בדיקת כמות ---
        qty_is_valid = False
        qty_val = orig_qty

        if not pd.isna(orig_qty) and str(orig_qty).strip() != "":
            try:
                qty_float = float(orig_qty)
                if qty_float.is_integer() and int(qty_float) > 0:
                    qty_val = int(qty_float)
                    qty_is_valid = True
            except ValueError:
                pass

        if not qty_is_valid:
            msg = "חסרה כמות תקינה"
            current_row_notes.append(f"⚠️ {msg}")
            warnings.append(f"⚠️ שורה {row_num}: שים לב - {msg}.")
            is_error = True
            if pd.isna(orig_qty) or str(orig_qty).strip() == "":
                qty_val = ""

        cleaned_skus.append(sku_val)
        cleaned_qtys.append(qty_val)
        row_has_error.append(is_error)

        # חיבור כל ההערות של השורה למחרוזת אחת (למקרה שיש גם שגיאת מק"ט וגם כמות)
        row_notes.append(" | ".join(current_row_notes))

    # --- ג) יצירת האקסל עם עמודת ההערות החדשה ---
    df_clean = pd.DataFrame({'מק"ט': cleaned_skus, 'כמות': cleaned_qtys, 'הערות מערכת': row_notes})
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_clean.to_excel(writer, index=False)
        workbook = writer.book
        worksheet = workbook.active
        worksheet.views.sheetView[0].showGridLines = True
        worksheet.sheet_properties.pageSetUpPr.fitToPage = True
        worksheet.sheet_view.rightToLeft = True

        font_tahoma_regular = Font(name='Tahoma', size=14)
        font_tahoma_header = Font(name='Tahoma', size=14, bold=True, color='FFFFFF')

        # הגדרת הצבעים
        fill_header = PatternFill(start_color='1F497D', end_color='1F497D', fill_type='solid')
        fill_warning = PatternFill(start_color='FFD580', end_color='FFD580', fill_type='solid')

        center_align = Alignment(horizontal='center', vertical='center')

        for row in worksheet.iter_rows():
            for cell in row:
                cell.alignment = center_align

                if cell.row == 1:
                    # שורת הכותרת (שורה 1)
                    cell.font = font_tahoma_header
                    cell.fill = fill_header
                else:
                    # שורות הנתונים
                    cell.font = font_tahoma_regular

                    # בדיקה האם השורה הזו סומנה עם תקלה
                    if row_has_error[cell.row - 2]:
                        cell.fill = fill_warning  # צביעה בכתום

        worksheet.column_dimensions['A'].width = 20
        worksheet.column_dimensions['B'].width = 15
        worksheet.column_dimensions['C'].width = 50  # הוספת רוחב לעמודת ההערות החדשה

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

        # הפיכת ה-DataFrame לרשימה אחידה שהמוח (process_unified_data) יודע לקרוא
        items_list = []
        for idx, row in df.iterrows():
            items_list.append({
                'row_num': idx + 2,
                'sku': row[0],
                'qty': row[1]
            })

        # שליחה לפונקציה המרכזית
        return process_unified_data(items_list, original_file_name)

    except Exception as e:
        return None, None, [], "שגיאה בעיבוד הקובץ. ודאו שהקובץ תקין ושיש בו נתונים החל מהשורה השנייה."