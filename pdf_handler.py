import pdfplumber
import io
import re
from openai import OpenAI
from pydantic import BaseModel, Field
from db_handler import find_sku_in_db  # ייבוא מנוע החיפוש מול ה-DB במקום הקובץ הישן

# רשימת תחיליות שלקוחות מוסיפים בטעות וצריך לנקות (אפשר להוסיף לכאן עוד בהמשך)
KNOWN_PREFIXES = ["AT-", "AT_", "AT", "A-"]


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(
        description="רשימת כל המחרוזות בשורה שנראות כמו מק\"ט. חובה לחלץ אך ורק מהטקסט! אם אין מק\"ט בשורה (למשל שורת הובלה/אספקה), החזר רשימה ריקה []. לעולם אל תמציא!"
    )
    qty: str = Field(
        description="הכמות המוזמנת. חפש מספרים שמופיעה לידם המילה 'יח', 'יח.', או 'יח''."
    )


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנה")
    items: list[OrderRow]


def process_pdf(pdf_file, openai_api_key):
    file_bytes = pdf_file.getvalue()
    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק.")

    # מנוע קריאה מרחבי: שומר על העמודות והרווחים המדויקים של המסמך!
    pdf_bytes_io = io.BytesIO(file_bytes)
    with pdfplumber.open(pdf_bytes_io) as pdf:
        extracted_text = "\n".join([page.extract_text(layout=True) for page in pdf.pages])

    client = OpenAI(api_key=openai_api_key)

    # הפרומפט המשופר והקשוח
    system_instruction = (
        "אתה מומחה לחילוץ נתונים מטבלאות הזמנות רכש מורכבות בעברית/אנגלית.\n"
        "חוקים קריטיים להצלחה:\n"
        "1. כמויות (qty): הכמות היא מספר. לעיתים קרובות מופיע לידה או מתחתיה הצירוף 'יח', 'יח.', 'יח'' או 'EA'. אם הכמות כתובה כ-'80.00' החזר '80'. אל תבלבל עם עמודת ה'שורה'!\n"
        "2. מק\"טים (skus_found): חלץ את *כל* המחרוזות האלפנומריות בשורה שנראות כמו מק\"ט ספק או מק\"ט יצרן (למשל 1SDA0..., או 0025..., או AT-1217139). \n"
        "**אזהרה קריטית:** התעלם לחלוטין ממספרי פרויקט שמתחילים ב-PR (כמו PR26E00489) - הם אינם מק\"טים ואסור להכניס אותם לרשימה!\n"
        "3. אל תתייחס לנתונים בכותרת המסמך.\n"
        "4. **סריקת סיכומים:** התעלם לחלוטין משורות של 'סיכום כמויות', 'סה\"כ' או ממספר הספק (510050). אל תיצור עבורם שורות פיקטיביות!\n"
        "5. אם יש ספק לגבי הכמות, או שהיא חסרה, החזר מחרוזת ריקה \"\". אל תנחש.\n"
        "6. **איסור המצאות (No Hallucinations):** חלץ מק\"טים אך ורק ממה שכתוב פיזית במסמך! לעולם אל תשער, תנחש או תמציא מק\"ט עבור שורות הובלה, משלוח או אספקה. אם לא מודפס מק\"ט בשורה, החזר רשימה ריקה."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"להלן תוכן ההזמנה, חלץ את הפריטים:\n{extracted_text}"}
        ],
        response_format=PurchaseOrder,
    )

    result = completion.choices[0].message.parsed

    items_list = []
    for item in result.items:
        # --- חומת אש קפדנית נגד הזיות ---
        valid_skus = []
        if item.skus_found:
            for s in item.skus_found:
                if s and not s.upper().startswith("PR"):
                    # מנקים רק את המק"ט שה-AI מצא
                    clean_s = s.replace(" ", "").replace("-", "")

                    # מסירים מקפים מהמסמך, אבל משאירים את הרווחים!
                    text_without_hyphens = extracted_text.replace("-", "")

                    # בדיקה קפדנית: המק"ט חייב להופיע בשלמותו בטקסט
                    if clean_s in text_without_hyphens or s in extracted_text:
                        valid_skus.append(clean_s)  # מעבירים את המק"ט הנקי
                    else:
                        print(f"🚫 חסימת הזיה: ה-AI המציא את המק\"ט '{s}' בשורה {item.row_number}")
        # ----------------------------------

        chosen_sku = ""
        is_exact_match = False

        # מעבר על המק"טים שה-AI זיהה כדי למצוא אחד שאכן קיים במסד הנתונים
        for candidate in valid_skus:
            # 1. בדיקה ישירה מול מסד הנתונים
            if find_sku_in_db(candidate):
                chosen_sku = candidate
                is_exact_match = True
                break

            # 2. אם לא נמצא, ננסה להסיר תחיליות בעייתיות (כמו AT-) ולבדוק שוב
            clean_candidate = candidate.upper().strip()
            removed_prefix = False
            for prefix in KNOWN_PREFIXES:
                if clean_candidate.startswith(prefix):
                    clean_candidate = clean_candidate[len(prefix):]  # חיתוך התחילית
                    removed_prefix = True
                    break

            if removed_prefix:
                # בדיקה מחדש מול מסד הנתונים ללא התחילית
                if find_sku_in_db(clean_candidate):
                    chosen_sku = clean_candidate  # שמירת המספר הנקי ללא הקידומת
                    is_exact_match = True
                    break

        # חוסר התאמה מוחלט - ניקח את המחרוזת הארוכה ביותר כדי שלמשתמש תהיה אינדיקציה כלשהי באקסל
        if not is_exact_match:
            chosen_sku = max(valid_skus, key=len) if valid_skus else ""

        # --- חסימת ברזל: העפת מספר הספק 510050 ---
        if chosen_sku == "510050":
            continue

        # ניקוי הכמות (הסרת מילים כמו "יח" אם ה-AI הכניס אותן בטעות)
        clean_qty = item.qty
        if clean_qty:
            clean_qty = re.sub(r'[^\d.]', '', clean_qty)  # משאיר רק ספרות ונקודה עשרונית
            if clean_qty.endswith('.'):
                clean_qty = clean_qty[:-1]
            try:
                # הופך "80.00" ל-"80"
                clean_qty = str(int(float(clean_qty)))
            except ValueError:
                clean_qty = ""

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': clean_qty
        })

    return items_list, result.order_number