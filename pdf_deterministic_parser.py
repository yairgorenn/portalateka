import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # חזרנו לחילוץ שורות פשוט ששומר על רווחים
            text = page.extract_text(layout=True)
            if not text:
                continue

            lines = text.split('\n')

            for line in lines:
                if not line.strip():
                    continue

                # נטרול רעשים בסיסי
                safe_line = re.sub(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b', ' ', line)

                words = safe_line.split()
                chosen_sku = None
                is_exact_match = False

                # 1. חיפוש מק"ט (העוגן של השורה) - התייחסות כמחרוזת וריפוד אפסים בלבד!
                potential_unknown_sku = None

                for word in words:
                    clean_word = word.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace('"',
                                                                                                                  "").upper()

                    if len(clean_word) < 3:
                        continue

                    padded_word = clean_word.zfill(9)

                    # בדיקת מק"ט אטקה
                    if clean_word in ateka_set or padded_word in ateka_set:
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    # בדיקת מק"ט יצרן
                    if clean_word in vendor_to_ateka or padded_word in vendor_to_ateka:
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    # לוכד מק"טים לא מוכרים: אם המילה לא נמצאה בקטלוג, אבל היא ארוכה ומכילה מספרים
                    if len(clean_word) >= 7 and any(c.isdigit() for c in clean_word):
                        potential_unknown_sku = word.replace("*", "").replace("'", "").replace('"', "")

                # אם סיימנו לסרוק את השורה ולא מצאנו התאמה מושלמת, נשתמש ב"מק"ט החשוד" שמצאנו
                if not is_exact_match and potential_unknown_sku:
                    chosen_sku = potential_unknown_sku
                    # is_exact_match נשאר False !

                # 2. חילוץ כמות חכם
                # (שימו לב: הפעולה עכשיו רצה גם אם מצאנו מק"ט לא מוכר, כדי לחלץ לו כמות!)
                if chosen_sku:
                    qty = ""

                    # ניקוי השורה ממחירי ש"ח לפני חיפוש הכמות
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל|שח|חש)', '', safe_line)
                    clean_for_qty = re.sub(r'(?:ש"ח|₪|שקל|שח|חש)\s*\d+(?:,\d+)?\.\d+', '', clean_for_qty)
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', clean_for_qty)

                    unit_words = r'(?:יח|יחידה|יחידות|חי|הדיחי|pcs|ea)'

                    sem_matches = re.findall(rf'{unit_words}\s*(\d+)(?:\.\d+)?', clean_for_qty.lower())
                    if not sem_matches:
                        sem_matches = re.findall(rf'(\d+)(?:\.\d+)?\s*{unit_words}', clean_for_qty.lower())

                    if sem_matches:
                        valid_sem = [q for q in sem_matches if q != '0' and len(q) < 5]
                        if valid_sem:
                            qty = valid_sem[0]

                    if not qty:
                        qty_matches = re.findall(r'\b(\d+)(?:\.\d+)?\b', clean_for_qty)
                        valid_qtys = []
                        for q in qty_matches:
                            if q not in chosen_sku and q != '0' and len(q) < 5:
                                valid_qtys.append(q)
                        if valid_qtys:
                            qty = valid_qtys[-1]

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        # השורה תיצבע בכתום אם חסרה כמות, **או** אם המק"ט לא קיים בקטלוג (is_exact_match=False)!
                        'is_error': not is_exact_match or qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Engine"