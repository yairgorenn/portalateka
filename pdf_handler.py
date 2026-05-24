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
        description="רשימה של כל המק\"טים והקודים שנמצאו בשורה זו. הכנס לכאן רק מספרים וקודים (למשל EEELE00139 או 2CDS271001R0104). אל תכניס תיאורי מוצר!")
    qty: str = Field(description="הכמות המוזמנת. חובה: התעלם מנקודות עשרוניות (1.00 זה 1). החזר כמספר שלם בפורמט טקסט.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש (PO Number) המופיע במסמך")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית - הסינון החכם בפייתון
# ==========================================
def process_pdf(pdf_file, openai_api_key):
    client = OpenAI(api_key=openai_api_key)

    # חידוש 1: החזרת "סמן הקריאה" של הקובץ להתחלה כדי למנוע קריאת קובץ ריק
    pdf_file.seek(0)

    pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
    base64_images = []

    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)

        # חידוש 2: alpha=False מבטל שקיפות ומכריח רקע לבן, כדי שהטקסט לא יהפוך לשחור על שחור!
        pix = page.get_pixmap(dpi=200, alpha=False)

        img_bytes = pix.tobytes("png")
        encoded = base64.b64encode(img_bytes).decode('utf-8')
        base64_images.append(encoded)

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח הזמנות רכש (B2B). סרוק את המסמך וחלץ את כל שורות ההזמנה.
            לכל שורה, חלץ את הכמות (מספרים שלמים בלבד, התעלם מאפסים אחרי הנקודה).
            אסוף את *כל* הקודים / מק"טים שאתה רואה באותה שורה לתוך הרשימה skus_found.

            אזהרות חמורות:
            1. אסור לך לחלוץ את "תיאור המוצר". חלץ אך ורק קודי פריט.
            2. חוק ברזל: אסור לך להמציא נתונים בשום פנים ואופן. אם התמונות ריקות, שחורות, או שאינך מצליח לקרוא מהן כלום, עליך להחזיר תחת order_number את הטקסט 'ERROR_BLANK_IMAGE' ולהשאיר את רשימת הפריטים ריקה."""
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

    # אנחנו משתמשים במודל החזק והמדויק (gpt-4o)
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

    # הדפסה ללוג לבקרה
    print(f"\n=======================================================")
    print(f"=== פלט גולמי מה-AI (מספר הזמנה: {parsed_data.order_number}) ===")
    for item in parsed_data.items:
        print(f"שורה {item.row_number}: מק\"טים שנמצאו: {item.skus_found} | כמות: {item.qty}")
    print(f"=======================================================\n")

    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []

    for item in parsed_data.items:
        chosen_sku = ""

        # סריקה 1: מק"ט אטקה
        for candidate in item.skus_found:
            clean_val = candidate.strip()
            if not clean_val: continue
            if clean_val in ateka_set or clean_val.lstrip('0') in ateka_set:
                chosen_sku = clean_val
                break

                # סריקה 2: מק"ט יצרן
        if not chosen_sku:
            for candidate in item.skus_found:
                clean_val = candidate.strip()
                if not clean_val: continue
                X_upper = clean_val.upper()
                if X_upper in vendor_to_ateka or X_upper.lstrip('0') in vendor_to_ateka:
                    chosen_sku = clean_val
                    break

                    # סריקה 3: לא מצא כלום בקטלוג
        if not chosen_sku and len(item.skus_found) > 0:
            chosen_sku = item.skus_found[0]

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    return items_list, parsed_data.order_number