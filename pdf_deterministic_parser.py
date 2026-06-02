import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        # סריקת כל העמודים
        for page in pdf.pages:
            # layout=True שומר על השורות הפיזיות (ציר Y)
            text = page.extract_text(layout=True)
            if not text:
                continue

            lines = text.split('\n')
            for line in lines:
                if not line.strip():
                    continue

                # --- 1. נטרול רעשים (מחיקת מחירים ואחוזים כדי שלא יתבלבלו עם כמות) ---
                safe_line = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל)', '', line)
                safe_line = re.sub(r'(?:ש"ח|₪)\s*\d+(?:,\d+)?\.\d+', '', safe_line)
                safe_line = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', safe_line)

                words = safe_line.split()
                chosen_sku = None
                is_exact_match = False

                # --- 2. חיפוש מק"ט (העוגן של השורה) ---
                for word in words:
                    # ניקוי תווים זרים שמפריעים להשוואה
                    clean_word = word.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace('"',
                                                                                                                  "").upper()

                    # בדיקה מול קטלוג אטקה
                    if clean_word in ateka_set or clean_word.lstrip('0') in ateka_set:
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    # בדיקה מול קטלוג יצרנים
                    if clean_word in vendor_to_ateka or clean_word.lstrip('0') in vendor_to_ateka:
                        # מעבירים את מק"ט היצרן במדויק כדי ש excel_handler ימיר וידפיס הערה ירוקה
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                # --- 3. חילוץ כמות (רק אם נמצא מק"ט חוקי באותה שורה!) ---
                if is_exact_match and chosen_sku:
                    qty = ""
                    # חיפוש כל המספרים השלמים (או עם .00) בשורה
                    qty_matches = re.findall(r'\b(\d+)(?:\.00)?\b', safe_line)

                    valid_qtys = []
                    for q in qty_matches:
                        # מסננים את המק"ט עצמו, ברקודים ארוכים, ומספר 0
                        if q not in chosen_sku and len(q) < 5 and q != '0':
                            valid_qtys.append(q)

                    if valid_qtys:
                        # לרוב הכמות נמצאת בסוף השורה (או כמספר עצמאי יחיד)
                        qty = valid_qtys[-1]

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        # אם שורה זוהתה אבל לא מצאנו כמות ודאית, היא תיצבע בכתום!
                        'is_error': qty == ""
                    })
                    row_counter += 1

                # אם הגיע טקסט כמו "3X16A", המנוע פשוט לא ימצא לו מק"ט בקטלוג וידלג עליו - אפס המצאות.

    return items_list, "Deterministic_Engine"