import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # במקום לחלץ טקסט, אנחנו מחלצים מילים עם קואורדינטות פיזיות (X, Y)
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            # --- שלב א': קיבוץ המילים לשורות לפי גובה פיזי (ציר Y) ---
            lines = []
            # מיון המילים מהגבוה לנמוך, ומימין לשמאל
            words.sort(key=lambda w: (w['top'], w['x0']))

            current_line = []
            current_top = words[0]['top']

            for w in words:
                # אם המילה באותו גובה (סובלנות של 5 פיקסלים להדפסה עקומה)
                if abs(w['top'] - current_top) <= 5:
                    current_line.append(w)
                else:
                    lines.append(current_line)
                    current_line = [w]
                    current_top = w['top']
            if current_line:
                lines.append(current_line)

            # --- שלב ב': כיול העמודה (חיתוך ציר ה-X של "כמות") ---
            qty_x0 = -1  # גבול שמאלי
            qty_x1 = -1  # גבול ימני

            for line in lines:
                for w in line:
                    if "כמות" in w['text']:
                        # חותכים רצועה ברוחב של כ-100 פיקסלים סביב המילה "כמות"
                        qty_x0 = w['x0'] - 50
                        qty_x1 = w['x1'] + 50
                        break
                if qty_x0 != -1:
                    break

            # --- שלב ג': סריקת השורות וחילוץ מתמטי ---
            for line in lines:
                chosen_sku = None
                is_exact_match = False

                # 1. חיפוש מק"ט (העוגן של השורה)
                for w in line:
                    word_text = w['text']
                    clean_word = word_text.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace(
                        '"', "").upper()

                    # בדיקת מק"ט אטקה
                    if clean_word in ateka_set or clean_word.lstrip('0') in ateka_set:
                        chosen_sku = word_text.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    # בדיקת מק"ט יצרן
                    if clean_word in vendor_to_ateka or clean_word.lstrip('0') in vendor_to_ateka:
                        chosen_sku = word_text.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                # 2. חיתוך עמודת הכמות ושליפת הנתון
                if is_exact_match and chosen_sku:
                    qty = ""

                    # מוודאים שמצאנו איפה העמודה נמצאת בעמוד הזה
                    if qty_x0 != -1:
                        # הקסם: לוקחים רק את המילים שהקואורדינטה שלהן נופלת בדיוק בתוך עמודת הכמות!
                        words_in_qty_column = [w for w in line if w['x0'] >= qty_x0 and w['x1'] <= qty_x1]

                        for cw in words_in_qty_column:
                            c_text = cw['text']
                            # מסננים אם נכנס בטעות "יח" או סימן מחיר, ומשאירים רק את המספר
                            c_text = re.sub(r'(?:יח|יחידה|יחידות|ש"ח|₪|שקל|שח|%)', '', c_text).strip()

                            # שליפת המספר המושלם (למשל 1, או 1.00)
                            qty_match = re.search(r'\b(\d+)(?:\.\d+)?\b', c_text)
                            if qty_match and qty_match.group(1) != '0':
                                qty = qty_match.group(1)
                                break  # מצאנו את הכמות בגזרה, אפשר לעצור

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        'is_error': qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Geometric_Engine"