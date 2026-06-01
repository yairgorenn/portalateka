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
    # קורא את כל עמודי המסמך מהתחלה ועד הסוף (ללא הגבלת 3 עמודים)
    for page_num in range(len(pdf_document)):
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
                    חוקי ברזל:
                    1. עוגן שורות: קרא את המסמך שורה אחר שורה לפי "המספר הסידורי". אל תערבב נתונים!
                    2. איסוף כל המק"טים: לכל שורה, חלץ את כל סוגי המק"טים (עד 3 מק"טים שונים) והחזר אותם כרשימה.
                       - חובה לחפש: מק"ט אטקה (7-9 ספרות), ומק"ט יצרן/ספק (כגון 1SDA072614R1).
                       - חובה לאסוף גם מק"ט פנימי של הלקוח או מק"ט חלקי. אל תסנן שום מק"ט בעצמך, אסוף הכל!
                    3. כמות: חלץ את הכמות מאותה שורה בלבד כמספר שלם. התעלם ממחירים ואחוזים."""
        },
        {
            "role": "user",
            "content": f"להלן הטקסט מההזמנה (חלץ נתונים במדויק שורה מול שורה):\n{extracted_text}"
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
        is_exact_match = False

        # ניקוי מקדים: מסיר כוכביות, גרשיים או פסיקים (נפוץ במסמכי לב חשמל)
        cleaned_candidates = [c.replace("*", "").replace("'", "").replace('"', "").strip() for c in item.skus_found]
        valid_skus = [c for c in cleaned_candidates if c and c.count(' ') <= 1]

        # שלב 1: חיפוש מק"ט אטקה מתוך הרשימה
        for candidate in valid_skus:
            clean_to_check = candidate.replace(" ", "").replace("-", "")
            if clean_to_check in ateka_set or clean_to_check.lstrip('0') in ateka_set:
                chosen_sku = candidate
                is_exact_match = True
                break

        # שלב 2: חיפוש מק"ט יצרן מתוך הרשימה (אם לא נמצא אטקה)
        if not chosen_sku:
            for candidate in valid_skus:
                clean_to_check = candidate.upper().replace(" ", "").replace("-", "")
                if clean_to_check in vendor_to_ateka or clean_to_check.lstrip('0') in vendor_to_ateka:
                    chosen_sku = candidate
                    is_exact_match = True
                    break

                # שלב 3: אם לא הייתה התאמה מלאה - נשאיר את מה שה-AI מצא, אבל השורה תצבע בכתום באקסל
                if not is_exact_match:
                    # נבחר את המק"ט הארוך ביותר שזוהה כדי שהמשתמש יראה מה היה שם
                    chosen_sku = max(cleaned_candidates, key=len) if cleaned_candidates else ""
                    # כאן לא נסמן is_exact_match = True, מה שיגרום לאקסל לצבוע בכתום!

        # כתיבה לרשימה הסופית
        items_list.append({
            'row_num': item.row_number,
            'sku': chosen_sku,
            'qty': item.qty
        })

    return items_list, parsed_data.order_number