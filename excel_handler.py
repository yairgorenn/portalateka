import pandas as pd
import io
import os
from openpyxl.styles import Font, PatternFill, Alignment

SKU_LENGTH = 9


def process_excel(uploaded_file, original_file_name):
    """
    מקבלת קובץ שהועלה, מעבדת אותו, ומחזירה:
    (buffer, new_file_name, warnings_list, error_message)
    """
    try:
        # קריאת הקובץ תוך התעלמות מוחלטת מהשורה הראשונה (skiprows=1)
        if original_file_name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, skiprows=1, header=None)
        else:
            df = pd.read_excel(uploaded_file, skiprows=1, header=None)

        # בדיקה שיש לפחות שתי עמודות בנתונים
        if df.shape[1] < 2:
            return None, None, [], "❌ שגיאה: הקובץ חייב להכיל לפחות שתי עמודות (מק\"ט וכמות)."

        cleaned_skus = []
        cleaned_qtys = []
        qty_warnings = []
        sku_warnings = []

        # לולאה שעוברת שורה-שורה על הקובץ ומבצעת ולידציה
        for idx, row in df.iterrows():
            excel_row_num = idx + 2
            orig_sku = row[0]
            orig_qty = row[1]

            # --- בדיקת תקינות מק"ט ---
            if pd.isna(orig_sku) or str(orig_sku).strip() == "":
                sku_val = ""
                sku_warnings.append(f"שים לב מקט לא מלא בשורה {excel_row_num}")
            else:
                sku_str = str(orig_sku).strip()
                if sku_str.endswith('.0'):
                    sku_str = sku_str[:-2]

                if len(sku_str) < 7:
                    sku_val = sku_str
                    sku_warnings.append(f"שים לב מקט לא מלא בשורה {excel_row_num}")
                else:
                    sku_val = sku_str.zfill(SKU_LENGTH)

            # --- בדיקת תקינות כמות ---
            qty_is_valid = False
            qty_val = orig_qty

            if not pd.isna(orig_qty):
                try:
                    qty_float = float(orig_qty)
                    if qty_float.is_integer() and int(qty_float) > 0:
                        qty_val = int(qty_float)
                        qty_is_valid = True
                except ValueError:
                    pass

            if not qty_is_valid:
                qty_warnings.append(f"שים לב בשורה מספר {excel_row_num} חסר כמות")
                if pd.isna(orig_qty):
                    qty_val = ""

            cleaned_skus.append(sku_val)
            cleaned_qtys.append(qty_val)

        # בניית ה-DataFrame החדש
        df_clean = pd.DataFrame({'מק"ט': cleaned_skus, 'כמות': cleaned_qtys})

        # יצירת קובץ אקסל חדש בזיכרון
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_clean.to_excel(writer, index=False)

            # הגדרות עיצוב אקסל
            workbook = writer.book
            worksheet = workbook.active
            worksheet.views.sheetView[0].showGridLines = True
            worksheet.sheet_properties.pageSetUpPr.fitToPage = True
            worksheet.sheet_view.rightToLeft = True

            font_tahoma_regular = Font(name='Tahoma', size=14)
            font_tahoma_header = Font(name='Tahoma', size=14, bold=True, color='FFFFFF')
            fill_header = PatternFill(start_color='1F497D', end_color='1F497D', fill_type='solid')
            center_align = Alignment(horizontal='center', vertical='center')

            for row in worksheet.iter_rows():
                for cell in row:
                    cell.alignment = center_align
                    if cell.row == 1:
                        cell.font = font_tahoma_header
                        cell.fill = fill_header
                    else:
                        cell.font = font_tahoma_regular

            worksheet.column_dimensions['A'].width = 20
            worksheet.column_dimensions['B'].width = 15

        all_warnings = qty_warnings + sku_warnings
        original_name, _ = os.path.splitext(original_file_name)
        new_file_name = f"{original_name}_מוכן_לפורטל.xlsx"

        return buffer, new_file_name, all_warnings, None

    except Exception as e:
        return None, None, [], f"שגיאה בעיבוד הקובץ. ודאו שהקובץ תקין ושיש בו נתונים החל מהשורה השנייה."