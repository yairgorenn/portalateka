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

                # 1. חיפוש מק"ט (העוגן של השורה)
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

                # 2. חילוץ כמות חכם עם תמיכה בעברית הפוכה ("חי" במקום "יח")
                if is_exact_match and chosen_sku:
                    qty = ""

                    # ניקוי השורה ממחירי ש"ח לפני חיפוש הכמות
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל|שח|חש)', '', safe_line)
                    clean_for_qty = re.sub(r'(?:ש"ח|₪|שקל|שח|חש)\s*\d+(?:,\d+)?\.\d+', '', clean_for_qty)
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', clean_for_qty)

                    # חיפוש מספר שצמוד לאחת ממילות היחידה (כולל הפוכות!)
                    # המילים: יח, יחידה, יחידות, חי (יח הפוך), הדיחי (יחידה הפוך)
                    unit_words = r'(?:יח|יחידה|יחידות|חי|הדיחי|pcs|ea)'

                    # בודק קודם "מילה מספר" (למשל "יח 1.00" או "חי 1.00")
                    sem_matches = re.findall(rf'{unit_words}\s*(\d+)(?:\.\d+)?', clean_for_qty.lower())
                    if not sem_matches:
                        # בודק "מספר מילה" (למשל "1.00 יח" או "1.00 חי")
                        sem_matches = re.findall(rf'(\d+)(?:\.\d+)?\s*{unit_words}', clean_for_qty.lower())

                    if sem_matches:
                        valid_sem = [q for q in sem_matches if q != '0' and len(q) < 5]
                        if valid_sem:
                            qty = valid_sem[0]

                    # אם לא הייתה מילת יחידה בכלל בשורה (כמו בהזמנות אחרות), קח את המספר הבודד האחרון
                    if not qty:
                        qty_matches = re.findall(r'\b(\d+)(?:\.\d+)?\b', clean_for_qty)
                        valid_qtys = []
                        for q in qty_matches:
                            # מסננים את המק"ט עצמו ומספרים לא הגיוניים
                            if q not in chosen_sku and q != '0' and len(q) < 5:
                                valid_qtys.append(q)
                        if valid_qtys:
                            qty = valid_qtys[-1]

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        'is_error': qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Engine"