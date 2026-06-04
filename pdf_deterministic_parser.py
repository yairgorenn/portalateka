import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            # חילוץ טקסט ששומר על המבנה המקורי
            text = page.extract_text(layout=True)
            if not text:
                continue

            lines = text.split('\n')

            for line in lines:
                if not line.strip():
                    continue

                # נטרול רעשים בסיסי - מחיקת תאריכים
                safe_line = re.sub(r'\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b', ' ', line)

                words = safe_line.split()
                chosen_sku = None
                is_exact_match = False

                # 1. חיפוש מק"ט (העוגן של השורה) - התאמה מלאה ומוחלטת בלבד!
                for word in words:
                    clean_word = word.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace('"',
                                                                                                                  "").upper()

                    # סינון מינימלי למילים של אות אחת או שתיים
                    if len(clean_word) < 3:
                        continue

                    # הפעולה היחידה המותרת: ריפוד אפסים משמאל עד ל-9 תווים
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

                # 2. חילוץ כמות - רץ אך ורק אם מצאנו מק"ט ודאי מהקטלוג!
                if is_exact_match and chosen_sku:
                    qty = ""

                    # ניקוי השורה ממחירי ש"ח לפני חיפוש הכמות
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל|שח|חש)', '', safe_line)
                    clean_for_qty = re.sub(r'(?:ש"ח|₪|שקל|שח|חש)\s*\d+(?:,\d+)?\.\d+', '', clean_for_qty)
                    clean_for_qty = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', clean_for_qty)

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

                    # אם לא הייתה מילת יחידה בכלל בשורה
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
                        'is_error': qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Engine"