import fitz
import base64
import streamlit as st
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog
from image_handler import process_images  # <-- הייבוא של הקובץ החדש!


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(description="רשימת המק\"טים. חובה להעתיק במדויק!")
    qty: str = Field(description="הכמות המוזמנת.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנה")
    items: list[OrderRow]


def process_pdf(pdf_file, openai_api_key):
    file_bytes = pdf_file.getvalue()
    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק.")

    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")

    # בדיקת טקסט דיגיטלי
    extracted_text = ""
    for page_num in range(min(len(pdf_document), 3)):
        page = pdf_document.load_page(page_num)
        extracted_text += page.get_text("text") + "\n"

    is_scanned = len(extracted_text.strip()) < 50

    if not is_scanned:
        # טיפול דיגיטלי טהור (כמו קודם)
        st.success("📄 זוהה מסמך דיגיטלי מקורי. שולף נתונים באמינות מקסימלית...")
        client = OpenAI(api_key=openai_api_key)
        messages = [
            {
                "role": "system",
                "content": """אתה מנתח הזמנות רכש (B2B). הפרד בין "תיאור המוצר" לקודים/מק"טים.
                חוק ברזל: העתק את המק"טים בדיוק מוחלט!"""
            },
            {
                "role": "user",
                "content": f"להלן הטקסט הגולמי מההזמנה (חלץ ממנו את הנתונים במדויק):\n{extracted_text}"
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

        return items_list, parsed_data.order_number, False

    else:
        # הקובץ סרוק! אנחנו גוזרים תמונות ומעבירים ל-image_handler
        st.warning("🖼️ זוהה מסמך סרוק. מעביר למנוע זיהוי תמונה (AI)...")
        base64_images = []
        for page_num in range(min(len(pdf_document), 3)):
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(dpi=300, alpha=False)
            img_bytes = pix.tobytes("png")
            st.image(img_bytes, caption=f"עמוד {page_num + 1}", use_container_width=True)
            encoded = base64.b64encode(img_bytes).decode('utf-8')
            base64_images.append(encoded)

        # שימוש במודול החדש שלנו
        items_list, order_number = process_images(base64_images, openai_api_key)
        return items_list, order_number, True