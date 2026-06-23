import os
import time
import imaplib
import smtplib
import email
from email.message import EmailMessage
import io

from pdf_handler import process_pdf
from excel_handler import process_unified_data

# משיכת משתני סביבה מ-Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # האימייל החדש של הבוט
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # סיסמת ה-16 תווים של הבוט


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

    # שליחה דרך השרת המאובטח של גוגל
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
            print(f"📧 תגובה נשלחה בהצלחה ל: {to_address}")
    except Exception as e:
        print(f"❌ שגיאה בשליחת המייל: {e}")


def check_and_process_emails():
    """הפונקציה המרכזית שבודקת את התיבה ומעבדת PDFים"""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")

        # חיפוש הודעות שלא נקראו בלבד (UNSEEN)
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            return  # אין הודעות חדשות

        email_ids = messages[0].split()
        for e_id in email_ids:
            res, msg_data = mail.fetch(e_id, '(RFC822)')
            if res != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # חילוץ כתובת השולח
            sender_email = email.utils.parseaddr(msg.get("From"))[1].strip().lower()
            print(f"📥 התקבלה הודעה חדשה מ: {sender_email}")

            # --- בדיקת מורשים: הגנה מספאם וחסימת כתובות חיצוניות ---
            if not sender_email.endswith('@ateka.co.il'):
                print(f"🚫 חסימה: השולח {sender_email} אינו דומיין מורשה.")
                unauthorized_body = (
                    "שלום,\n\n"
                    "אתה לא ברשימת המורשים נא לפנות במייל ליאיר גורן yairg@ateka.co.il ."
                )
                send_reply_email(sender_email, "שגיאת הרשאה במערכת אטקה 🚫", unauthorized_body)

                # סימון המייל כנקרא כדי שהמערכת לא תעבד אותו שוב ושוב בלולאה
                mail.store(e_id, '+FLAGS', '\\Seen')
                continue

            pdf_found = False

            # מעבר על חלקי המייל (טקסט, קבצים מצורפים)
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                filename = part.get_filename()
                if filename and filename.lower().endswith('.pdf'):
                    pdf_found = True
                    print(f"📄 מפענח קובץ: {filename}...")

                    # חילוץ הקובץ לזיכרון והפיכתו לאובייקט שמדמה קובץ רגיל
                    pdf_bytes = part.get_payload(decode=True)
                    file_obj = io.BytesIO(pdf_bytes)
                    file_obj.name = filename

                    try:
                        # הפעלת הלוגיקה הקיימת במערכת
                        items_list, order_number = process_pdf(file_obj, OPENAI_API_KEY)
                        original_name = f"Order_{order_number}" if order_number else "Digital_PDF"
                        buffer, new_file_name, warnings, error = process_unified_data(items_list,
                                                                                      f"{original_name}.xlsx")

                        if error:
                            reply_body = f"שלום,\n\nהתגלתה שגיאה בעיבוד הקובץ {filename}:\n{error}"
                            send_reply_email(sender_email, "שגיאה בפענוח הזמנה ❌", reply_body)
                        elif buffer:
                            reply_body = f"היי,\n\nהקובץ {filename} פוענח בהצלחה על ידי המערכת.\nמצורף קובץ אקסל מוכן לטעינה.\n"

                            # הוספת ההערות (שורות כתומות/אדומות) ישירות לגוף המייל בדומה לאתר
                            if warnings:
                                reply_body += f"\n⚠️ שים לב! נמצאו {len(warnings)} הערות שדורשות את בדיקתך בקובץ:\n"
                                for warning in warnings:
                                    reply_body += f"- {warning}\n"
                                reply_body += "\nאנא ודא את השורות הללו בקובץ האקסל המצורף לפני הטעינה פריוריטי/פורטל."

                            send_reply_email(sender_email, f"אקסל מוכן: {new_file_name} ✅", reply_body, buffer,
                                             new_file_name)

                    except ValueError as ve:
                        if str(ve) == "SCANNED_PDF_BLOCKED":
                            reply_body = "שלום,\n\nהמערכת זיהתה שהקובץ המצורף הוא מסמך סרוק או תמונה. למניעת טעויות באספקה, ניתן לשלוח מסמכי PDF דיגיטליים מקוריים בלבד."
                        else:
                            reply_body = f"שגיאה בפענוח: {ve}"
                        send_reply_email(sender_email, "שגיאת פענוח מסמך 🛑", reply_body)
                    except Exception as e:
                        reply_body = f"תקלה בלתי צפויה: {str(e)}"
                        send_reply_email(sender_email, "תקלת מערכת", reply_body)

            if not pdf_found:
                print(f"הודעה ללא PDF מ- {sender_email}. מדלג.")

            # סימון המייל כנקרא בסיום הטיפול
            mail.store(e_id, '+FLAGS', '\\Seen')

        mail.logout()
    except Exception as e:
        print(f"Error checking emails: {e}")


if __name__ == "__main__":
    print("🚀 שרת המייל (Email Worker) מתחיל לרוץ...")
    print("ממתין להזמנות חדשות...")

    # לולאה אינסופית שרצה כל 60 שניים
    while True:
        check_and_process_emails()
        time.sleep(60)