import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_deterministic(pdf_file):
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []
    row_counter = 1

    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            # --- שלב א': קיבוץ המילים לשורות לפי גובה פיזי (ציר Y) ---
            lines = []
            words.sort(key=lambda w: (w['top'], w['x0']))

            current_line = []
            current_top = words[0]['top']

            for w in words:
                if abs(w['top'] - current_top) <= 5:
                    current_line.append(w)
                else:
                    lines.append(current_line)
                    current_line = [w]
                    current_top = w['top']
            if current_line:
                lines.append(current_line)

            # --- שלב ב': כיול העמודה (חיתוך ציר ה-X של "כמות") ---
            qty_x0 = -1
            qty_x1 = -1

            print(f"\n--- 📄 מתחיל סריקת עמוד {page_num + 1} ---")

            for line in lines:
                for w in line:
                    if "כמות" in w['text']:
                        # הרחבנו משמעותית את החלון ל-80 פיקסלים כדי לכסות טבלאות מפוזרות
                        qty_x0 = w['x0'] - 80
                        qty_x1 = w['x1'] + 80
                        print(f"🔍 [DEBUG] נמצאה כותרת 'כמות'! טווח חיתוך X נקבע ל: {qty_x0:.1f} עד {qty_x1:.1f}")
                        break
                if qty_x0 != -1:
                    break

            if qty_x0 == -1:
                print("⚠️ [DEBUG] אזהרה: לא נמצאה המילה 'כמות' בכותרות של עמוד זה!")

            # --- שלב ג': סריקת השורות וחילוץ מתמטי ---
            for line in lines:
                chosen_sku = None
                is_exact_match = False

                # 1. חיפוש עוגן (מק"ט חוקי)
                for w in line:
                    word_text = w['text']
                    clean_word = word_text.replace("-", "").replace(" ", "").replace("*", "").replace("'", "").replace(
                        '"', "").upper()

                    if clean_word in ateka_set or clean_word.lstrip('0') in ateka_set:
                        chosen_sku = word_text.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                    if clean_word in vendor_to_ateka or clean_word.lstrip('0') in vendor_to_ateka:
                        chosen_sku = word_text.replace("*", "").replace("'", "").replace('"', "")
                        is_exact_match = True
                        break

                # 2. חיתוך עמודת הכמות ושליפת הנתון
                if is_exact_match and chosen_sku:
                    qty = ""
                    print(f"\n💡 [DEBUG] נמצא מק\"ט בשורה: {chosen_sku}")

                    # הדפסת כל המילים בשורה כדי שנראה את המטריצה בעיניים
                    line_texts = [(w['text'], round(w['x0'], 1)) for w in line]
                    print(f"   [DEBUG] כל המילים בשורה והמיקום שלהן (מילה, ציר X): {line_texts}")

                    if qty_x0 != -1:
                        words_in_qty_column = [w for w in line if w['x0'] >= qty_x0 and w['x1'] <= qty_x1]
                        print(f"   [DEBUG] המילים שנפלו בתוך חלון הכמות: {[w['text'] for w in words_in_qty_column]}")

                        for cw in words_in_qty_column:
                            c_text = cw['text']
                            # מנקים תווים נלווים
                            c_text_clean = re.sub(r'(?:יח|יחידה|יחידות|ש"ח|₪|שקל|שח|%)', '', c_text).strip()

                            qty_match = re.search(r'\b(\d+)(?:\.\d+)?\b', c_text_clean)
                            if qty_match and qty_match.group(1) != '0':
                                qty = qty_match.group(1)
                                print(f"   ✅ [DEBUG] כמות שחולצה בהצלחה: {qty}")
                                break

                    if not qty:
                        print("   ❌ [DEBUG] שגיאה - לא חולצה כמות! (אולי המספר מחוץ לחלון ה-X?)")

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty,
                        'is_error': qty == ""
                    })
                    row_counter += 1

    return items_list, "Deterministic_Geometric_Engine"