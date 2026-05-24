import fitz  # PyMuPDF
import base64
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


# ==========================================
# 1. הגדרת המבנה שאנחנו דורשים מ-OpenAI
# ==========================================
class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    skus_found: list[str] = Field(
        description="רשימה של כל המק\"טים והקודים שנמצאו בשורה זו (מק\"ט ספק, מק\"ט יצרן, קוד פריט, מק\"ט אטקה). הכנס את כולם למערך זה.")
    qty: str = Field(description="הכמות המוזמנת. חובה: התעלם מנקודות עשרוניות (1.00 זה 1). החזר כמספר שלם בפורמט טקסט.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש (PO Number) המופיע במסמך")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית לפענוח והכנת הנתונים
# ==========================================
def process_pdf(pdf_file, openai_api_key):
    """
    מקבלת קובץ PDF (מ-Streamlit), קוראת אותו מול OpenAI,
    ומחזירה רשימת מילונים שמתאימה בדיוק ל-process_unified_data.
    """
    client = OpenAI(api_key=openai_api_key)

    # פתיחת ה-PDF מהזיכרון של האתר
    pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
    base64_images = []

    # המרת העמודים לתמונות (עד 3 עמודים ראשונים כדי לא להעמיס סתם על API, אפשר לשנות)
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
            לכל שורה, חלץ את הכמות (מספרים שלמים בלבד, התעלם מ-.00).
            בנוסף, אסוף את כל הקודים / מק"טים שאתה רואה באותה שורה (מק"ט ספק, קוד יצרן, מק"ט פנימי) לתוך רשימה אחת."""
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

    # קריאה ל-OpenAI
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

    # טעינת הקטלוג שלנו כדי למצוא את המק"ט המנצח
    ateka_set, vendor_to_ateka = load_catalog("PB.csv")

    items_list = []

    # בניית הרשימה שתעבור ל-excel_handler
    for item in parsed_data.items:
        chosen_sku = ""

        # מעבר על כל המק"טים שה-AI מצא בשורה
        for sku_candidate in item.skus_found:
            clean_candidate = sku_candidate.strip()
            if not clean_candidate:
                continue

            X_upper = clean_candidate.upper()
            X_no_zeros = clean_candidate.lstrip('0')

            # אם מצאנו מק"ט שקיים באטקה או ביצרן, אנחנו בוחרים בו ויוצאים מהלולאה
            if clean_candidate in ateka_set or X_no_zeros in ateka_set or X_upper in vendor_to_ateka or X_upper.lstrip(
                    '0') in vendor_to_ateka:
                chosen_sku = clean_candidate
                break

        # אם ה-AI לא מצא אף מק"ט שמוכר לנו, ניקח פשוט את הראשון שמצא כדי שהמערכת תזרוק עליו שגיאה אדומה
        if not chosen_sku and len(item.skus_found) > 0:
            chosen_sku = item.skus_found[0]

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    # מחזירים את הרשימה המוכנה ואת מספר ההזמנה שה-AI מצא
    return items_list, parsed_data.order_number