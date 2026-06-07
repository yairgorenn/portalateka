import pdfplumber
import io
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(description="רשימת המק\"טים. חובה להעתיק במדויק!")
    qty: str = Field(
        description="הכמות המוזמנת. חוק ברזל: החזר רק את הכמות המדויקת כמספר שלם! אם הכמות חסרה, לא ברורה לחלוטין, או שיש חשש להסטה משורה אחרת - החזר מחרוזת ריקה \"\" ואל תנחש בשום אופן!"
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
    extracted_text = ""
    with pdfplumber.open(pdf_bytes_io) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                extracted_text += text + "\n"

    client = OpenAI(api_key=openai_api_key)
    messages = [
        {
            "role": "system",
            "content": """אתה מומחה לחילוץ נתונים מטבלאות הזמנות רכש.

                חוקי ברזל מחמירים:
                1. שורת פריט חייבת להכיל מק"ט ו/או כמות. אם אתה רואה מזהה טקסט (כמו 'מספר דרישה', 'PD...', 'מספר הזמנה') שנמצא מחוץ לטבלה הראשית או בתחתית העמוד - התעלם ממנו לחלוטין!
                2. התעלם מכל מה שנמצא אחרי שורת "סה"כ" או בסעיפים תחתונים כמו "תנאי תשלום".
                3. לעולם אל תיצור שורת פריט מתוך נתונים שאינם חלק מטבלת המוצרים.
                4. מק"ט הוא רצף של אותיות ומספרים. אם זה נראה כמו מספר הזמנה או מספר דרישה, זה לא מק"ט מוצר."""
        },
        {
            "role": "user",
            "content": f"חלץ רק את שורות הטבלה מהטקסט הבא, תוך התעלמות ממידע מחוץ לטבלה:\n{extracted_text}"
        }
    ]

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )
    parsed_data = response.choices[0].message.parsed

    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []

    for item in parsed_data.items:
        chosen_sku = ""
        is_exact_match = False

        # ניקוי המק"טים שה-AI הביא
        cleaned_candidates = [c.replace("*", "").replace("'", "").replace('"', "").strip() for c in item.skus_found]
        valid_skus = [c for c in cleaned_candidates if c and c.count(' ') <= 1]

        # שלב 1: חיפוש התאמה מלאה (אטקה)
        for candidate in valid_skus:
            clean_to_check = candidate.replace(" ", "").replace("-", "")
            if clean_to_check in ateka_set or clean_to_check.lstrip('0') in ateka_set:
                chosen_sku = candidate
                is_exact_match = True
                break

        # שלב 2: חיפוש התאמה מלאה (יצרן)
        if not is_exact_match:
            for candidate in valid_skus:
                clean_to_check = candidate.upper().replace(" ", "").replace("-", "")
                if clean_to_check in vendor_to_ateka or clean_to_check.lstrip('0') in vendor_to_ateka:
                    # כרגע שולחים מקט יצרן בלבד לאקסל
                    #chosen_sku = vendor_to_ateka.get(clean_to_check) or vendor_to_ateka.get(clean_to_check.lstrip('0'))
                    chosen_sku = candidate
                    is_exact_match = True
                    break

        # שלב 3: חוסר התאמה מוחלט - העברת אחריות למשתמש
        if not is_exact_match:
            chosen_sku = max(valid_skus, key=len) if valid_skus else ""

        # אם ה-AI החזיר כמות ריקה, ה-is_error יהפוך ל-True אוטומטית בהמשך התהליך ויצבע בכתום
        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty,
            'is_error': not is_exact_match
        })

    return items_list, parsed_data.order_number