import base64
from openai import OpenAI
from pydantic import BaseModel, Field
from excel_handler import load_catalog


# ==========================================
# 1. הגדרת המבנה - עם חוקים נוקשים נגד הזיות
# ==========================================
class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלה")
    product_description: str = Field(description="תיאור המוצר המלא.")
    skus_found: list[str] = Field(
        description="רשימת המק\"טים. אם הטקסט מטושטש אפילו קצת ואתה לא בטוח, הכנס את הערך 'ERROR_UNCLEAR_TEXT'. אל תנחש!")
    qty: str = Field(description="הכמות המוזמנת.")


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש")
    items: list[OrderRow]


# ==========================================
# 2. הפונקציה המרכזית לטיפול בתמונות
# ==========================================
def process_images(base64_images, openai_api_key):
    client = OpenAI(api_key=openai_api_key)

    messages = [
        {
            "role": "system",
            "content": """אתה מנתח תמונות / סריקות של הזמנות רכש (B2B).
            הפרד בין תיאור המוצר למק"טים.

            חוק ברזל נגד הזיות (Anti-Hallucination):
            מכיוון שזו תמונה, יש סכנה שתתבלבל בין 5 ל-6, או בין 0 ל-O. 
            אסור לך לנחש! אם הטקסט מטושטש, קטוע, או שאתה לא בטוח ב-100% - אל תמציא! 
            במקרה של ספק הקטן ביותר, החזר ב-skus_found את הטקסט המדויק 'ERROR_UNCLEAR_TEXT'. אנחנו מעדיפים לקבל שגיאה מאשר לספק ללקוח מק"ט שגוי."""
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "פענח את התמונות המצורפות."}]
        }
    ]

    for b64_img in base64_images:
        messages[1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}})

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=PurchaseOrder,
    )

    parsed_data = response.choices[0].message.parsed

    print(f"\n=== פלט זיהוי תמונה מ-image_handler (הזמנה: {parsed_data.order_number}) ===")
    for item in parsed_data.items:
        print(
            f"שורה {item.row_number}: תיאור: {item.product_description} | מק\"טים: {item.skus_found} | כמות: {item.qty}")

    ateka_set, vendor_to_ateka = load_catalog("PB.csv")
    items_list = []

    for item in parsed_data.items:
        chosen_sku = ""
        valid_skus = [c for c in item.skus_found if c.count(' ') <= 1]

        # טיפול במקרה של טקסט מטושטש
        if "ERROR_UNCLEAR_TEXT" in item.skus_found:
            chosen_sku = "ERROR_UNCLEAR_TEXT"
        else:
            # סריקה 1: אטקה
            for candidate in valid_skus:
                clean_val = candidate.strip()
                if not clean_val: continue
                clean_to_check = clean_val.replace(" ", "").replace("-", "")
                if clean_to_check in ateka_set or clean_to_check.lstrip('0') in ateka_set:
                    chosen_sku = clean_val
                    break

                    # סריקה 2: יצרן
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

    return items_list, parsed_data.order_number