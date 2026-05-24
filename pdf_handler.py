import fitz  # PyMuPDF
import base64
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


# ==========================================
# 1. הגדרת המבנה - ה-AI פשוט שואב את כל הקודים
# ==========================================
class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    skus_found: list[str] = Field(
        description="רשימה של כל המק\"טים והקודים שנמצאו בשורה זו (מק\"ט ספק, קוד פריט, מק\"ט אטקה). הכנס את כולם למערך זה.")
    qty: str = Field(description="הכמות המוזמנת. חובה: התעלם מנקודות עשרוניות (1.00 זה 1). החזר כמספר שלם בפורמט טקסט.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש (PO Number) המופיע במסמך")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית - הסינון החכם בפייתון
# ==========================================
def process_pdf(pdf_file, openai_api_key):
    client = OpenAI(api_key=openai_api_key)

    pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
    base64_images = []

    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        encoded = base64.b64encode(img_bytes).decode('utf-8')
        base64_images.append(encoded)

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח הזמנות רכש (B2B). סרוק את המסמך וחלץ את כל שורות ההזמנה.
            לכל שורה, חלץ את הכמות (מספרים שלמים בלבד, התעלם מאפסים אחרי הנקודה).
            אסוף את *כל* הקודים / מק"טים שאתה רואה באותה שורה (לא משנה אם זה יצרן או אטקה) לתוך הרשימה skus_found."""
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "פענח את הזמנת הרכש המצורפת."}]
        }
    ]

    for b64_img in base64_images:
        messages[1]["content"].append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64_img}"}
        })

    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")

    items_list = []

    # הלוגיקה שבקשת: מעבר על כל שורה לפי סדר עדיפויות קפדני
    for item in parsed_data.items:
        chosen_sku = ""

        # --- סריקה 1: מחפשים קודם כל מק"ט אטקה בתוך כל המק"טים שה-AI מצא ---
        for candidate in item.skus_found:
            clean_val = candidate.strip()
            if not clean_val:
                continue

            if clean_val in ateka_set or clean_val.lstrip('0') in ateka_set:
                chosen_sku = clean_val
                break  # מצאנו אטקה! עוצרים את החיפוש לשורה זו.

        # --- סריקה 2: אם לא מצאנו אטקה, מחפשים מק"ט יצרן ---
        if not chosen_sku:
            for candidate in item.skus_found:
                clean_val = candidate.strip()
                if not clean_val:
                    continue

                X_upper = clean_val.upper()
                if X_upper in vendor_to_ateka or X_upper.lstrip('0') in vendor_to_ateka:
                    chosen_sku = clean_val
                    break  # מצאנו יצרן! עוצרים.

        # --- סריקה 3: אם גם אטקה וגם יצרן לא קיימים בקטלוג ---
        if not chosen_sku and len(item.skus_found) > 0:
            chosen_sku = item.skus_found[0]  # לוקחים משהו כדי שהמערכת תצעק עליו שגיאה אדומה

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    return items_list, parsed_data.order_number