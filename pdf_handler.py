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
            "content": """אתה חולץ נתונים מתוך טבלאות של הזמנות רכש (B2B). 
            הטקסט שמועבר אליך מסודר ויזואלית עם רווחים כדי לשמור על מבנה העמודות המדויק.

            חוקי ברזל:
            1. עוגן שורות: קרא את המסמך שורה מול שורה בדיוק על אותו קו אופקי. אל תגלוש לשורה מתחת!
            2. איסוף כל המק"טים: חלץ את כל המק"טים באותה שורה בלבד (אטקה, יצרן, פנימי, חלקי).
            3. כמות: חלץ את הכמות מאותה שורה אופקית בלבד. אם אתה לא בטוח ב-100% מה הכמות של השורה הזו, החזר ריק ("")!"""
        },
        {
            "role": "user",
            "content": f"להלן הטקסט מההזמנה (חלץ נתונים במדויק שורה מול שורה):\n{extracted_text}"
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
                    chosen_sku = vendor_to_ateka.get(clean_to_check) or vendor_to_ateka.get(clean_to_check.lstrip('0'))
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