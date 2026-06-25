import os
import time
import imaplib
import smtplib
import email
from email.message import EmailMessage
from email.header import decode_header
import io

from pdf_handler import process_pdf
from excel_handler import process_excel, process_unified_data
from telegram_handler import send_telegram_message
from pdf_router import split_pdf_to_orders  # ייבוא הנתב החכם שכתבנו

# משיכת משתני סביבה מ-Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # האימייל של הבוט
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # סיסמת ה-16 תווים של הבוט

# דומיינים מורשים
AUTHORIZED_DOMAINS = ["ateka.co.il", "afcon.co.il", "contel.co.il"]


def decode_mime_header(s):
    """מפענחת שמות קבצים וכותרות בעברית כדי למנוע שיבושים במייל"""
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    pieces = []
    for text, encoding in decoded_fragments:
        if isinstance(text, bytes):
            pieces.append(text.decode(encoding or 'utf-8', errors='ignore'))
        else:
            pieces.append(text)
    return "".join(pieces)


def is_authorized(email_address):
    """בדיקה האם השולח מגיע מדומיין מורשה"""
    if not email_address:
        return False
    domain = email_address.split("@")[-1].lower().strip()
    return domain in AUTHORIZED_DOMAINS


def send_reply_email(to_address, subject, text_body, attachments=None):
    """
    פונקציה ששולחת אימייל תגובה מיושר לימין (RTL) לאיש המכירות.
    attachments: רשימה של טאפלים במבנה: [(buffer, filename), ...]
    תומכת בזיהוי אוטומטי של קבצי PDF ואקסל.
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("❌ שגיאה: משתני הסביבה של המייל לא מוגדרים בשרת.")
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_address

    # הפיכת הטקסט ל-HTML תקני ומיושר לימין עבור קליינטים כמו אאוטלוק וג'ימייל
    html_body = f"""
    <div dir="rtl" style="text-align: right; font-family: Tahoma, Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #333333;">
        {text_body.replace('\n', '<br>')}
    </div>
    """

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype='html')

    # הוספת הקבצים המצורפים תוך זיהוי סוג הקובץ (PDF או Excel)
    if attachments:
        for attr_buffer, attr_name in attachments:
            if attr_buffer and attr_name:
                attachment_data = attr_buffer.getvalue()
                file_ext = attr_name.split('.')[-1].lower() if '.' in attr_name else ''

                if file_ext == 'pdf':
                    maintype = 'application'
                    subtype = 'pdf'
                else:
                    maintype = 'application'
                    subtype = 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'

                msg.add_attachment(
                    attachment_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attr_name
                )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"❌ שגיאה בשליחת המייל: {e}")


def check_and_process_emails():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("❌ שגיאה: פרטי התחברות למייל חסרים.")
        return

    try:
        mail = imaplib.IMAP4_SSL("smtp.gmail.com")
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            return

        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return

        print(f"📬 נמצאו {len(email_ids)} מיילים חדשים לטיפול.")

        for e_id in email_ids:
            res, msg_data = mail.fetch(e_id, '(RFC822)')
            if res != 'OK':
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            from_header = decode_mime_header(msg.get("From"))
            sender_email = email.utils.parseaddr(from_header)[1].lower().strip()

            print(f"📥 התקבלה הודעה חדשה מ: {sender_email}")

            if not is_authorized(sender_email):
                print(f"🚫 חסימה: השולח {sender_email} אינו דומיין מורשה.")
                reject_body = (
                    "שלום,\n\n"
                    "מערכת הפענוח האוטומטית של אטקה חסמה את פנייתך.\n"
                    "השירות מוגבל למשתמשים מורשים בלבד מאותם דומיינים של החברה."
                )
                send_reply_email(sender_email, "חסימת גישה - מערכת אטקה 🚫", reject_body)
                mail.store(e_id, '+FLAGS', '\\Seen')
                continue

            file_found = False

            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                raw_filename = part.get_filename()
                if not raw_filename:
                    continue

                filename = decode_mime_header(raw_filename)
                file_ext = filename.split('.')[-1].lower() if '.' in filename else ''

                if file_ext in ['pdf', 'xlsx', 'xls', 'csv']:
                    file_found = True
                    file_bytes = part.get_payload(decode=True)
                    file_io = io.BytesIO(file_bytes)

                    attachments_to_send = []
                    global_warnings_count = 0

                    try:
                        # --- א) מסלול טיפול ב-PDF (כולל פיצול והצמדת המקור החתוך) ---
                        if file_ext == 'pdf':
                            print(f"📄 מנתח ומפצל קובץ PDF: {filename}...")
                            split_orders = split_pdf_to_orders(file_io)
                            total_orders = len(split_orders)

                            print(f"✂️ הקובץ פוצל בהצלחה ל-{total_orders} הזמנות נפרדות.")

                            for i, order_dict in enumerate(split_orders):
                                order_name = order_dict["order_name"]
                                pdf_chunk_buffer = order_dict["pdf_obj"]

                                print(f"📦 מעבד חלק {i + 1}/{total_orders}: {order_name}...")
                                items_list, returned_order_num = process_pdf(pdf_chunk_buffer, OPENAI_API_KEY)

                                final_order_name = f"Order_{returned_order_num}" if returned_order_num else order_name
                                excel_name = f"{final_order_name}.xlsx"

                                buffer, new_file_name, warnings, error = process_unified_data(items_list, excel_name)

                                if error:
                                    print(f"❌ שגיאה בעיבוד {final_order_name}: {error}")
                                elif buffer:
                                    # 1. הוספת קובץ האקסל המפוענח
                                    attachments_to_send.append((buffer, new_file_name))
                                    # 2. הוספת קובץ ה-PDF המפוצל המקורי כנספח תואם!
                                    attachments_to_send.append((pdf_chunk_buffer, f"{final_order_name}.pdf"))

                                    rows_count = len(items_list) if items_list else 0
                                    warnings_count = len(warnings) if warnings else 0
                                    global_warnings_count += warnings_count

                                    send_telegram_message(final_order_name, rows_count, warnings_count)

                                if i < total_orders - 1:
                                    print("⏳ ממתין 20 שניות למניעת עומס טוקנים...")
                                    time.sleep(20)

                            if attachments_to_send:
                                reply_body = (
                                    f"שלום,\n\n"
                                    f"קובץ ה-PDF המרוכז '{filename}' עובד ופוצל בהצלחה.\n"
                                    f"המערכת חילקה את המסמך המקורי ל-{total_orders} הזמנות שונות.\n"
                                    f"לנוחיותך, לכל הזמנה צורף קובץ אקסל לטעינה מהירה וקובץ ה-PDF המקורי החתוך שלה כנספח למערכת.\n"
                                )
                                if global_warnings_count > 0:
                                    reply_body += f"\n⚠️ שים לב: זוהו שורות שדורשות בדיקה מצידך (מסומנות בכתום בעמודה C של קבצי האקסל).\n"
                                else:
                                    reply_body += "\n🎯 כל קבצי האקסל נמצאו תקינים לחלוטין ומוכנים לעבודה.\n"

                                reply_body += "\nבברכה,\nמערכת הפענוח האוטומטית אטקה"

                                send_reply_email(sender_email, f"פיענוח קובץ הושלם: {total_orders} הזמנות מוכנות ✅",
                                                 reply_body, attachments_to_send)
                                print(f"📧 מייל סיכום מועשר נשלח בהצלחה ל: {sender_email}")

                        # --- ב) מסלול טיפול באקסל/CSV ---
                        else:
                            print(f"📊 מעבד קובץ אקסל/CSV: {filename}...")
                            buffer, new_file_name, warnings, error = process_excel(file_io, filename)
                            original_name = filename.rsplit('.', 1)[0]

                            if error:
                                print(f"❌ שגיאה בעיבוד הקובץ {filename}: {error}")
                                send_reply_email(sender_email, "שגיאת פענוח מסמך 🛑",
                                                 f"שלום,\n\nהתרחשה שגיאה בעיבוד הקובץ: {error}")
                            elif buffer:
                                warnings_count = len(warnings) if warnings else 0
                                send_telegram_message(original_name, "Excel File", warnings_count)

                                reply_body = f"שלום,\n\nקובץ האקסל '{filename}' עובד וטופל בהצלחה על ידי המערכת.\n"
                                if warnings:
                                    reply_body += f"\n⚠️ שים לב: המערכת זיהתה {len(warnings)} שורות שדורשות בדיקה (מסומנות בכתום, פירוט מלא ממתין בעמודה D).\n"
                                else:
                                    reply_body += "\n🎯 הקובץ נמצא תקין לחלוטין ללא הערות מיוחדות.\n"

                                reply_body += "\nקובץ האקסל המעודכן מוכן לטעינה ומצורף למייל זה.\n\nבברכה,\nמערכת אטקה"

                                send_reply_email(sender_email, f"אקסל מוכן: {new_file_name} ✅", reply_body,
                                                 [(buffer, new_file_name)])
                                print(f"📧 תגובה נשלחה בהצלחה ל: {sender_email}")

                    except ValueError as ve:
                        if str(ve) == "SCANNED_PDF_BLOCKED":
                            reply_body = "שלום,\n\nהמערכת זיהתה שהקובץ המצורף הוא מסמך סרוק או תמונה. למניעת טעויות באספקה, ניתן לשלוח מסמכי PDF דיגיטליים מקוריים בלבד."
                        else:
                            reply_body = f"שגיאה בפענוח: {ve}"
                        send_reply_email(sender_email, "שגיאת פענוח מסמך 🛑", reply_body)
                    except Exception as e:
                        reply_body = f"תקלה בלתי צפויה במערכת: {str(e)}"
                        send_reply_email(sender_email, "תקלת מערכת ❌", reply_body)

            if not file_found:
                print(f"הודעה ללא קובץ תואם (PDF/Excel) מ- {sender_email}. מדלג.")

            mail.store(e_id, '+FLAGS', '\\Seen')

        mail.logout()

    except Exception as e:
        print(f"Error checking emails: {e}")


if __name__ == "__main__":
    print("🚀 שרת המייל (Email Worker) מתחיל לרוץ...")
    print("ממתין להזמנות חדשות...")
    while True:
        check_and_process_emails()
        time.sleep(15)