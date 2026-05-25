import fitz  # PyMuPDF
import base64
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


# ==========================================
# 1. הגדרת המבנה - ה-AI מפריד תיאורים למקום נפרד
# ==========================================
class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    product_description: str = Field(
        description="תיאור המוצר המלא (למשל 'MCB S201M-C10' או 'X1TC 3P...'). חובה לחלוץ אותו לשדה זה בלבד!")
    skus_found: list[str] = Field(
        description="רשימת המק\"טים/קודים בלבד. קודים רציפים (כמו EEELE00139 או 2CDS271001R0104).")
    qty: str = Field(description="הכמות המוזמנת. חובה: התעלם מנקודות עשרוניות (1.00 זה 1). החזר כמספר שלם בפורמט טקסט.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש (PO Number) המופיע במסמך")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית
# ==========================================
def process_pdf(pdf_file, openai_api_key):
    client = OpenAI(api_key=openai_api_key)

    # התיקון הקריטי: קריאת הביטים בצורה בטוחה מ-Streamlit
    file_bytes = pdf_file.getvalue()

    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק (0 bytes).")

    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
    base64_images = []

    # תצוגה מקדימה לאתר (הברקה שלך!)
    st.info("👀 מציג את התמונות כפי שהן נשלחות ל-AI (לצורכי בקרת איכות):")

    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(dpi=300, alpha=False)
        img_bytes = pix.tobytes("png")

        # הדפסת התמונה ישירות למסך האתר!
        st.image(img_bytes, caption=f"עמוד {page_num + 1} נסרק ונשלח", use_container_width=True)

        encoded = base64.b64encode(img_bytes).decode('utf-8')
        base64_images.append(encoded)

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח הזמנות רכש (B2B). סרוק את המסמך וחלץ את כל שורות ההזמנה.
            הפרד בבירור בין "תיאור המוצר" (שיכנס לשדה product_description) לבין הקודים/מק"טים (שיכנסו לרשימת skus_found).

            אזהרות חמורות:
            1. רשימת skus_found צריכה להכיל רק קודים רציפים!
            2. אל תמציא נתונים. אם התמונה ריקה או בלתי קריאה, החזר תחת order_number את הטקסט 'ERROR_BLANK_IMAGE'."""
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
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

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

        # סינון ראשוני: העפת תיאורים שהסתננו לרשימת המק"טים (מסנן רווחים)
        valid_skus = []
        for candidate in item.skus_found:
            if candidate.count(' ') > 1:
                continue
            valid_skus.append(candidate)

        # סריקה 1: מק"ט אטקה
        for candidate in valid_skus:
            clean_val = candidate.strip()
            if not clean_val: continue

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

                    # סריקה 3: לא מצא כלום
        if not chosen_sku and len(valid_skus) > 0:
            chosen_sku = valid_skus[0]

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    return items_list, parsed_data.order_number