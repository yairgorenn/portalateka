import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        # עוברים עמוד-עמוד
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if not text:
                continue

            lines = text.split('\n')

            # --- שלב 0: כיול הכוונת (מציאת עמודת הכמות בעמוד הנוכחי) ---
            qty_start_idx = -1
            qty_end_idx = -1

            for line in lines:
                if "כמות" in line:
                    # מציאת האינדקס (מיקום התו) של המילה "כמות" בשורת הכותרת
                    match = re.search(r'כמות', line)
                    if match:
                        center = match.start()
                        # פתיחת "חלון" אנכי של 15 תווים ימינה ושמאלה.
                        # זה מספיק רחב כדי לתפוס את המספר, אבל צר מספיק כדי לחתוך עמודות אחרות
                        qty_start_idx = max(0, center - 15)
                        qty_end_idx = center + 15
                        break  # ברגע שמצאנו כותרת בעמוד, עוצרים את החיפוש

            # --- שלב 1: סריקת השורות ---
            for line in lines:
                if not line.strip():
                    continue

                # נטרול רעשים בסיסי (מוחק תאריכים מכל השורה כדי לא להפריע למק"טים)
                safe_line = re.sub(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b', ' ', line)

                words = safe_line.split()
                chosen_sku = None
                is_exact_match = False

                # --- 2. חיפוש עוגן (מק"ט חוקי) ---
                for word in words:
                    clean_word = word.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace('"',
                                                                                                                  "").upper()

                    if clean_word in ateka_set or clean_word.lstrip('0') in ateka_set:
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    if clean_word in vendor_to_ateka or clean_word.lstrip('0') in vendor_to_ateka:
                        chosen_sku = word.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                # --- 3. חילוץ כמות (מתוך ה"מנהרה" בלבד!) ---
                if is_exact_match and chosen_sku:
                    qty = ""

                    # אם מצאנו את עמודת הכמות והשורה הזו ארוכה מספיק
                    if qty_start_idx != -1 and len(safe_line) > qty_start_idx:
                        # חותכים את השורה רק בטווח התווים של עמודת הכמות!
                        column_chunk = safe_line[qty_start_idx:min(len(safe_line), qty_end_idx)]

                        # ניקוי רעשי מחיר שנכנסו בטעות לגזרה
                        column_chunk = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל|שח)', '', column_chunk)
                        column_chunk = re.sub(r'(?:ש"ח|₪|שקל|שח)\s*\d+(?:,\d+)?\.\d+', '', column_chunk)
                        column_chunk = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', column_chunk)

                        # שליפת המספר היחיד שנמצא בתוך החלון הזה
                        qty_matches = re.findall(r'\b(\d+)(?:\.00)?\b', column_chunk)
                        valid_qtys = [q for q in qty_matches if q != '0' and len(q) < 5]

                        if valid_qtys:
                            # לוקחים את המספר הראשון שמצאנו בחלון הכמות
                            qty = valid_qtys[0]

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        # אם לא הייתה כמות בחלון הזה, השורה תחזור ריקה ותיצבע בכתום
                        'is_error': qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Engine"