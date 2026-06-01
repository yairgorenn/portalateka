import fitz
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(description="רשימת המק\"טים. חובה להעתיק במדויק!")
    qty: str = Field(
        description="הכמות המוזמנת. חוק ברזל: עליך להחזיר רק את המספר המדויק כמספר שלם! התעלם ממילים כמו 'יח' או אחוזים, והתעלם מאפסים אחרי הנקודה (למשל '8.00' נרשם כ-'8').")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנה")
    items: list[OrderRow]


def process_pdf(pdf_file, openai_api_key):
    file_bytes = pdf_file.getvalue()
    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק.")

    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")

    extracted_text = ""
    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        extracted_text += page.get_text("text") + "\n"

    # אם הקובץ ריק מטקסט, אנחנו חוסמים מיד!
    is_scanned = len(extracted_text.strip()) < 50
    if is_scanned:
        raise ValueError("SCANNED_PDF_BLOCKED")

    # טיפול דיגיטלי טהור
    client = OpenAI(api_key=openai_api_key)
    messages = [
        {
            "role": "system",
            "content": """אתה חולץ נתונים מתוך טבלאות של הזמנות רכש (B2B). 
                    חוקי ברזל למניעת הסטת שורות:
                    1. קרא את המסמך שורה אחר שורה במדויק. חפש את "המספר הסידורי" של הלקוח (למשל: 10, 20, 30 או 1, 2, 3) בעמודה הראשונה.
                    2. לכל מספר סידורי, אתר בדיוק באותו קו אופקי את המק"ט ואת הכמות. 
                    3. בשום אופן אל תיקח כמות שנמצאת בשורה של מק"ט אחר! אם התיאור גולש לשורה מתחת, התעלם מהגלישה וחזור לשורה של המק"ט.
                    4. החזר אך ורק את הכמות (Integer)."""
        },
        {
            "role": "user",
            "content": f"להלן הטקסט מההזמנה (חלץ ממנו את הנתונים במדויק שורה מול שורה):\n{extracted_text}"
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
        valid_skus = [c for c in item.skus_found if c.count(' ') <= 1]

        for candidate in valid_skus:
            clean_val = candidate.strip()
            if not clean_val: continue
            clean_to_check = clean_val.replace(" ", "").replace("-", "")
            if clean_to_check in ateka_set or clean_to_check.lstrip('0') in ateka_set:
                chosen_sku = clean_val
                break

        if not chosen_sku:
            for candidate in valid_skus:
                clean_val = candidate.strip()
                if not clean_val: continue
                clean_to_check = clean_val.upper().replace(" ", "").replace("-", "")
                if clean_to_check in vendor_to_ateka or clean_to_check.lstrip('0') in vendor_to_ateka:
                    chosen_sku = clean_val
                    break

        if not chosen_sku and len(valid_skus) > 0:
            chosen_sku = valid_skus[0]

        items_list.append({'row_num': item.row_number, 'sku': chosen_sku, 'qty': item.qty})

    return items_list, parsed_data.order_number