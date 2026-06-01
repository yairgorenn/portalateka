import pdfplumber
import re
from excel_handler import load_catalog


def process_pdf_exact(pdf_file):
    # 1. טעינת בסיס הנתונים (האמת המוחלטת שלנו)
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")

    items_list = []
    row_counter = 1

    # פתיחת ה-PDF תוך שמירה על רווחים ועמודות פיזיות
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages[:10]:  # סורק עד 10 עמודים למקרה של הזמנות ענק
            text = page.extract_text(layout=True)
            if not text:
                continue

            # פירוק הטקסט לשורות פיזיות - כל שורה נבדקת בנפרד!
            lines = text.split('\n')
            for line in lines:
                if not line.strip():
                    continue

                # --- שלב א: נטרול מוקשים (מחיקת מחירים ואחוזים) ---
                # מוחק מחירים כמו 74.00 ש"ח או ש"ח 118.78
                safe_line = re.sub(r'\d+(?:,\d+)?\.\d+\s*(?:ש"ח|₪|שקל)', '', line)
                safe_line = re.sub(r'(?:ש"ח|₪)\s*\d+(?:,\d+)?\.\d+', '', safe_line)
                safe_line = re.sub(r'\d+(?:,\d+)?\.\d+\s*%', '', safe_line)  # מוחק הנחות (אחוזים)

                # --- שלב ב: חיפוש מק"ט ---
                words = line.split()
                chosen_sku = None

                for word in words:
                    clean_word = word.replace("-", "").replace(" ", "").upper()

                    # בדיקה האם המילה קיימת בקטלוג אטקה
                    if clean_word in ateka_set or clean_word.lstrip('0') in ateka_set:
                        chosen_sku = word
                        break

                    # בדיקה האם המילה קיימת במק"טי יצרן
                    if clean_word in vendor_to_ateka or clean_word.lstrip('0') in vendor_to_ateka:
                        chosen_sku = word
                        break

                # --- שלב ג: אם מצאנו מק"ט, שולפים כמות מאותה השורה בלבד! ---
                if chosen_sku:
                    qty = "1"  # ברירת מחדל אם משהו נמחק

                    # מחפש מספרים שלמים (או עם .00) שאולי מחוברים למילה "יח"
                    # חיפוש מתבצע על safe_line (אחרי שניקינו מחירים)
                    qty_matches = re.findall(r'\b(\d+)(?:\.00)?\s*(?:יח|יחידה|pcs)?\b', safe_line)

                    if qty_matches:
                        # מסנן מספרים ארוכים מדי (כמו ברקודים שהשתרבבו)
                        valid_qtys = [q for q in qty_matches if len(q) < 5]
                        if valid_qtys:
                            # לרוב הכמות היא המספר התקין הראשון או האחרון שנשאר
                            qty = valid_qtys[-1] if len(valid_qtys) > 1 else valid_qtys[0]

                    items_list.append({
                        'row_num': row_counter,
                        'sku': chosen_sku,
                        'qty': qty
                    })
                    row_counter += 1

    return items_list, "Digital_Order"