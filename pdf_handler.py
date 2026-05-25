import fitz  # PyMuPDF
import base64
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


# ==========================================
# 1. הגדרת המבנה - הוספנו "פח אשפה" לתיאור!
# ==========================================
class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    product_description: str = Field(
        description="תיאור המוצר המלא (למשל 'MCB S201M-C10' או 'X1TC 3P...'). חובה לחלוץ אותו לשדה זה בלבד, כדי לא ללכלך את המק\"טים!")
    skus_found: list[str] = Field(
        description="רשימת המק\"טים/קודים בלבד. קודים רציפים (כמו EEELE00139 או 2CDS271001R0104).")
    qty: str = Field(description="הכמות המוזמנת. חובה: התעלם מנקודות עשרוניות (1.00 זה 1). החזר כמספר שלם בפורמט טקסט.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש (PO Number) המופיע במסמך")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית - הסינון החכם בפייתון
# ==========================================
def process_pdf(pdf_file, openai_api_key):
    client = OpenAI(api_key=openai_api_key)

    pdf_file.seek(0)
    pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
    base64_images = []

    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        # רזולוציה גבוהה (300) ורקע לבן לזיהוי אותיות קטנות (L לעומת B)
        pix = page.get_pixmap(dpi=300, alpha=False)
        img_bytes = pix.tobytes("png")
        encoded = base64.b64encode(img_bytes).decode('utf-8')
        base64_images.append(encoded)

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח הזמנות רכש (B2B). סרוק את המסמך וחלץ את כל שורות ההזמנה.
            הפרד בבירור בין "תיאור המוצר" (שיכנס לשדה product_description) לבין הקודים/מק"טים (שיכנסו לרשימת skus_found).

            אזהרות חמורות:
            1. רשימת skus_found צריכה להכיל רק קודים רציפים!
            2. אל תמציא נתונים. אם התמונה ריקה, החזר תחת order_number את הטקסט 'ERROR_BLANK_IMAGE'."""
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "פענח את הזמנת הרכש המצורפת."}]
        }
    ]

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

    # לוג לבקרה
    print(f"\n=======================================================")
    print(f"=== פלט גולמי מה-AI (מספר הזמנה: {parsed_data.order_number}) ===")
    for item in parsed_data.items:
        print(
            f"שורה {item.row_number}: תיאור: {item.product_description} | מק\"טים: {item.skus_found} | כמות: {item.qty}")
    print(f"=======================================================\n")

    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []

    for item in parsed_data.items:
        chosen_sku = ""

        # --- סינון ראשוני: העפת תיאורים שהסתננו ---
        valid_skus = []
        for candidate in item.skus_found:
            # אם יש יותר מרווח אחד, זה בטוח תיאור ולא מק"ט
            if candidate.count(' ') > 1:
                continue
            valid_skus.append(candidate)

        # סריקה 1: מק"ט אטקה
        for candidate in valid_skus:
            clean_val = candidate.strip()
            if not clean_val: continue

            # ניקוי רווחים ומקווים לפני בדיקה
            clean_to_check = clean_val.replace(" ", "").replace("-", "")
            if clean_to_check in ateka_set or clean_to_check.lstrip('0') in ateka_set:
                chosen_sku = clean_val
                break

                # סריקה 2: מק"ט יצרן
        if not chosen_sku:
            for candidate in valid_skus:
                clean_val = candidate.strip()
                if not clean_val: continue

                clean_to_check = clean_val.upper().replace(" ", "").replace("-", "")
                if clean_to_check in vendor_to_ateka or clean_to_check.lstrip('0') in vendor_to_ateka:
                    chosen_sku = clean_val
                    break

                    # סריקה 3: לא מצא כלום בקטלוג
        if not chosen_sku and len(valid_skus) > 0:
            chosen_sku = valid_skus[0]

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    return items_list, parsed_data.order_number