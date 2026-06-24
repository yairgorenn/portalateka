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

    pdf_bytes_io = io.BytesIO(file_bytes)
    # חילוץ טקסט גולמי בצורה ששומרת על מבנה הטבלה
    with pdfplumber.open(pdf_bytes_io) as pdf:
        extracted_text = "\n".join([page.extract_text(layout=True) for page in pdf.pages])

    client = OpenAI(api_key=openai_api_key)

    # הפרומפט החדש והקשוח
    system_instruction = (
        "אתה עוזר מומחה לחילוץ נתונים מהזמנות רכש של חברת 'אטקה'. "
        "עליך לחלץ פריטים מתוך טבלת ההזמנה בלבד. "
        "כללים קריטיים: \n"
        "1. עמודת 'שורה' היא מספר סידורי בלבד. חלץ אותה לשדה row_number, אך לעולם אל תבלבל בינה לבין עמודת הכמות.\n"
        "2. עמודת 'כמות' היא הכמות להזמנה. אם הכמות לא מופיעה במפורש בעמודת הכמות, או שיש ספק - אל תנחש! החזר מחרוזת ריקה.\n"
        "3. אל תתייחס לנתונים בכותרת המסמך (כגון 'מספר ספק', 'תאריך', 'שם פרויקט'). התמקד רק בטבלה עצמה.\n"
        "4. אם כמות מופיעה בצורה של '80.00' או '12.00', החזר אותה כמספר שלם ('80', '12').\n"
        "5. בצע סריקה קפדנית: אם יש ערכים בעמודת הכמות בכל השורות (למשל '12' בכל השורות), וודא שאתה משייך את ה-'12' לכל פריט, ולא את מספר השורה."
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

    # המרה לפורמט הפנימי של המערכת
    items_list = []
    for item in result.items:
        items_list.append({
            'row_num': item.row_number,
            'sku': item.skus_found[0] if item.skus_found else "",
            'qty': item.qty
        })

    return items_list, result.order_number