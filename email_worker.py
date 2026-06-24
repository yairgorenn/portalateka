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

# משיכת משתני סביבה מ-Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # האימייל של הבוט
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # סיסמת ה-16 תווים של הבוט

# דומיינים מורשים
AUTHORIZED_DOMAINS = ["ateka.co.il", "contel.co.il"]


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


def send_reply_email(to_address, subject, text_body, attachment_buffer=None, attachment_name=None):
    """פונקציה ששולחת אימייל תגובה לאיש המכירות"""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("❌ שגיאה: משתני הסביבה של המייל לא מוגדרים בשרת.")
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_address
    msg.set_content(text_body)

    # הוספת קובץ האקסל אם קיים
    if attachment_buffer and attachment_name:
        attachment_data = attachment_buffer.getvalue()
        msg.add_attachment(
            attachment_data,
            maintype='application',
            subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=attachment_name
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

        # חיפוש מיילים שלא נקראו
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

            # חילוץ שולח
            from_header = decode_mime_header(msg.get("From"))
            sender_email = email.utils.parseaddr(from_header)[1].lower().strip()

            print(f"📥 התקבלה הודעה חדשה מ: {sender_email}")

            # בדיקת הרשאות דומיין
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

            # מעבר על חלקי המייל למציאת קבצים מצורפים
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue

                raw_filename = part.get_filename()
                if not raw_filename:
                    continue

                filename = decode_mime_header(raw_filename)
                file_ext = filename.split('.')[-1].lower() if '.' in filename else ''

                # תמיכה ב-PDF ובקובצי אקסל/CSV
                if file_ext in ['pdf', 'xlsx', 'xls', 'csv']:
                    file_found = True
                    file_bytes = part.get_payload(decode=True)
                    file_io = io.BytesIO(file_bytes)

                    try:
                        if file_ext == 'pdf':
                            print(f"📄 מפענח קובץ PDF: {filename}...")
                            items_list, order_number = process_pdf(file_io, OPENAI_API_KEY)
                            original_name = f"Order_{order_number}" if order_number else "Digital_PDF"
                            excel_name = f"{original_name}.xlsx"
                            buffer, new_file_name, warnings, error = process_unified_data(items_list, excel_name)
                        else:
                            print(f"📊 מעבד קובץ אקסל/CSV: {filename}...")
                            # שימוש במנגנון האקסל הקיים שמתקן מק"טים ומוסיף אפסים
                            buffer, new_file_name, warnings, error = process_excel(file_io, filename)
                            original_name = filename.rsplit('.', 1)[0]

                        if error:
                            print(f"❌ שגיאה בעיבוד הקובץ {filename}: {error}")
                            send_reply_email(sender_email, "שגיאת פענוח מסמך 🛑",
                                             f"שלום,\n\nהתרחשה שגיאה בעיבוד הקובץ: {error}")
                        elif buffer:
                            # שליחת התראה לטלגרם
                            rows_count = len(items_list) if 'items_list' in locals() and items_list else "N/A"
                            warnings_count = len(warnings) if warnings else 0
                            send_telegram_message(original_name, rows_count, warnings_count)

                            # בניית הודעת התשובה
                            reply_body = f"שלום,\n\nהקובץ '{filename}' עובד ופוענח בהצלחה על ידי המערכת האוטומטית.\n"
                            if warnings:
                                reply_body += f"\n⚠️ שים לב: המערכת זיהתה {len(warnings)} שורות שדורשות בדיקה (מסומנות בכתום, פירוט מלא ממתין בעמודה C).\n"
                            else:
                                reply_body += "\n🎯 הקובץ נמצא תקין לחלוטין ללא הערות מיוחדות.\n"

                            reply_body += "\nקובץ האקסל המעודכן מוכן לטעינה ומצורף למייל זה."

                            send_reply_email(sender_email, f"אקסל מוכן: {new_file_name} ✅", reply_body, buffer,
                                             new_file_name)
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

            # סימון המייל כנקרא בסיום הטיפול
            mail.store(e_id, '+FLAGS', '\\Seen')

        mail.logout()

    except Exception as e:
        print(f"Error checking emails: {e}")


if __name__ == "__main__":
    print("🚀 שרת המייל (Email Worker) מתחיל לרוץ...")
    print("ממתין להזמנות חדשות...")
    while True:
        check_and_process_emails()
        time.sleep(15)  # בדיקה כל 15 שניות