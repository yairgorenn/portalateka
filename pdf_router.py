import io
import re
from pypdf import PdfReader, PdfWriter

# רשימת התבניות לזיהוי התחלה של הזמנה חדשה (אפשר להוסיף כאן בעתיד)
ORDER_IDENTIFIERS = [
    r"PO\d+",  # מזהה מילים שמתחילות ב-PO ואחריהן מספרים (למשל PO26E13328)
    r"הזמנת רכש מספר",  # מזהה את צמד המילים הזה
]


def find_order_name_in_text(text):
    """
    מחפשת בטקסט של העמוד האם יש ביטוי שמעיד על הזמנה חדשה.
    אם כן, מחזירה את השם שיהיה לקובץ (למשל 'PO26E13328'). אם לא, מחזירה None.
    """
    if not text:
        return None

    for pattern in ORDER_IDENTIFIERS:
        match = re.search(pattern, text)
        if match:
            # במקרה שזה מצא PO עם מספרים, נשתמש בזה בתור שם הקובץ!
            if pattern.startswith(r"PO"):
                # נחפש את המילה המלאה שמתחילה ב-PO
                full_po_match = re.search(r"PO\S+", text)
                if full_po_match:
                    return full_po_match.group(0).strip()
            return "New_Order"  # ברירת מחדל אם מצאנו "הזמנת רכש" בלי שם מובהק
    return None


def split_pdf_to_orders(file_bytes_io):
    """
    מקבלת אובייקט PDF מהזיכרון.
    מחזירה רשימה של מילונים, כל אחד מכיל את אובייקט ה-PDF הקטן ושם ההזמנה.
    """
    reader = PdfReader(file_bytes_io)
    split_orders = []

    current_writer = PdfWriter()
    current_order_name = "Order_Part_1"

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        found_name = find_order_name_in_text(text)

        # האם מצאנו שם הזמנה, והוא *שונה* מהשם הנוכחי שאנחנו אוספים?
        is_different_order = False
        if found_name and found_name != current_order_name:
            is_different_order = True

        # הגנה 1: אם מצאנו ביטוי כללי (New_Order) אבל יש לנו כבר שם אמיתי, לא לפצל
        if is_different_order and found_name == "New_Order" and current_order_name != "Order_Part_1":
            is_different_order = False

        # הגנה 2: אם זה עמוד מתקדם שמצאנו בו שם לראשונה, לא לפצל מהעמוד הראשון אלא לאחד אותם
        if is_different_order and current_order_name == "Order_Part_1":
            is_different_order = False

        # אם אכן מדובר בהזמנה חדשה ושונה, ויש לנו כבר עמודים בקובץ הקודם
        if is_different_order and i != 0 and len(current_writer.pages) > 0:
            # סגירת הקובץ הקודם לתוך הזיכרון
            pdf_buffer = io.BytesIO()
            current_writer.write(pdf_buffer)
            pdf_buffer.seek(0)

            split_orders.append({
                "pdf_obj": pdf_buffer,
                "order_name": current_order_name
            })

            # פתיחת קובץ חדש ועדכון השם להזמנה החדשה שמצאנו
            current_writer = PdfWriter()
            current_order_name = found_name

        elif found_name and i == 0:
            # עמוד ראשון לגמרי - קביעת השם הראשוני
            current_order_name = found_name

        elif found_name and current_order_name == "Order_Part_1":
            # הגנה 2 המשך: מעדכנים רטרואקטיבית את שם ההזמנה לעמודים הראשונים
            current_order_name = found_name

        # בכל מקרה - מוסיפים את העמוד לקובץ הפתוח הנוכחי
        current_writer.add_page(page)

    # סגירת ההזמנה האחרונה בסיום הלולאה
    if len(current_writer.pages) > 0:
        pdf_buffer = io.BytesIO()
        current_writer.write(pdf_buffer)
        pdf_buffer.seek(0)
        split_orders.append({
            "pdf_obj": pdf_buffer,
            "order_name": current_order_name
        })

    return split_orders