import fitz  # PyMuPDF
import base64
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(description="רשימת המק\"טים בלבד. חובה להעתיק במדויק!")
    qty: str = Field(description="הכמות המוזמנת.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש")
    items: list[OrderRow]


def process_pdf(pdf_file, openai_api_key):
    client = OpenAI(api_key=openai_api_key)
    file_bytes = pdf_file.getvalue()

    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק.")

    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")

    # שלב א': נסיון חילוץ טקסט דיגיטלי
    extracted_text = ""
    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        extracted_text += page.get_text("text") + "\n"

    # בודקים אם יש מספיק טקסט כדי להיחשב קובץ דיגיטלי
    is_scanned = len(extracted_text.strip()) < 50

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח הזמנות רכש (B2B). סרוק את הנתונים וחלץ את כל שורות ההזמנה.
            הפרד בין "תיאור המוצר" לקודים/מק"טים.
            חוק ברזל: העתק את המק"טים בדיוק מוחלט כפי שהם. אסור לשנות אף תו!"""
        }
    ]

    if not is_scanned:
        # הקובץ דיגיטלי - שולחים טקסט מדויק ל-AI
        st.success("📄 זוהה מסמך דיגיטלי מקורי. שולף נתונים באמינות מקסימלית...")
        messages.append({
            "role": "user",
            "content": f"להלן הטקסט הגולמי מההזמנה (חלץ ממנו את הנתונים במדויק):\n{extracted_text}"
        })
    else:
        # הקובץ סרוק - עוברים למצב זיהוי תמונה
        st.warning("🖼️ זוהה מסמך סרוק. מפעיל מנוע זיהוי תמונה (AI)...")
        base64_images = []
        for page_num in range(min(len(pdf_document), 3)):
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(dpi=300, alpha=False)
            img_bytes = pix.tobytes("png")
            st.image(img_bytes, caption=f"עמוד {page_num + 1}", use_container_width=True)
            encoded = base64.b64encode(img_bytes).decode('utf-8')
            base64_images.append(encoded)

        user_content = [{"type": "text", "text": "פענח את תמונות הזמנת הרכש המצורפת."}]
        for b64_img in base64_images:
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}})
        messages.append({"role": "user", "content": user_content})

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

    print(f"\n=== פלט גולמי מה-AI (הזמנה: {parsed_data.order_number}) ===")
    for item in parsed_data.items:
        print(
            f"שורה {item.row_number}: תיאור: {item.product_description} | מק\"טים: {item.skus_found} | כמות: {item.qty}")

    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []

    for item in parsed_data.items:
        chosen_sku = ""
        valid_skus = [c for c in item.skus_found if c.count(' ') <= 1]

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

        if not chosen_sku and len(valid_skus) > 0:
            chosen_sku = valid_skus[0]

        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    # שינוי קריטי: מחזירים גם את דגל הסריקה
    return items_list, parsed_data.order_number, is_scanned