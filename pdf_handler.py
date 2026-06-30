import os
import io
import re
import json
import pdfplumber
from openai import OpenAI
from pydantic import BaseModel, Field
from db_handler import find_sku_in_db

# =========================
# pdf_handler.py
# גרסה: 2026-06-30-no-hallucinations-v3
# =========================

DEBUG_PDF_HANDLER = os.getenv("DEBUG_PDF_HANDLER", "false").lower() in ("1", "true", "yes", "on")

# תחיליות שלקוחות מוסיפים בטעות לפני מק"ט אטקה/יצרן
KNOWN_PREFIXES = ["AT-", "AT_", "AT", "A-"]

# מילים שמאפיינות שורת שירות / הובלה / אספקה ולא שורת מוצר רגילה
# שמים גם עברית תקינה וגם עברית הפוכה, כי pdfplumber לפעמים מחלץ עברית הפוכה.
LOGISTICS_KEYWORDS = [
    "אספקה",
    "הובלה",
    "משלוח",
    "דמי משלוח",
    "תעודת משלוח",
    "delivery",
    "shipping",
    "freight",
    "transport",

    # RTL reversed words from some PDF extractions
    "הקפסא",
    "הלבוה",
    "חולשמ",
    "חולשמ תדועת",
]

# ערכים ידועים שאסור להפוך למק"ט גם אם הופיעו במסמך
BLOCKED_SKUS = {
    "510050",  # מספר ספק ידוע
}

# טקסטים / תבניות רעש שאינם שורות פריט
SUMMARY_KEYWORDS = [
    "סה\"כ",
    "סהכ",
    "כ\"הס",
    "מחיר כולל",
    "ללוכ ריחמ",
    "מע\"מ",
    "מעמ",
    "מ\"עמ",
    "תנאי תשלום",
    "םולשת יאנת",
    "מס' ספק",
    "מספר ספק",
    "הזמנת לקוח",
    "חוקל תנמזה",
    "מהדורה נוכחית",
    "תיחכונ הרודהמ",
]


class OrderRow(BaseModel):
    row_number: int = Field(description="מספר השורה בטבלת ההזמנה")
    product_description: str = Field(description="תיאור המוצר המלא כפי שמופיע בשורת ההזמנה")
    skus_found: list[str] = Field(
        description=(
            "רשימת מקטים שמופיעים פיזית בשורת הפריט בלבד. "
            "אסור להמציא, להשלים, לנחש או להסיק מקט לפי תיאור. "
            "אם אין מקט מודפס בשורה, החזר רשימה ריקה []. "
            "בשורות אספקה/הובלה/משלוח החזר תמיד [] אם אין מקט מודפס ברור."
        )
    )
    qty: str = Field(
        description=(
            "הכמות המוזמנת. חפש מספר שמופיע לידו או תחתיו יח, יח', יח. או EA. "
            "אם הכמות כתובה כ-80.00 החזר 80. אם חסרה כמות החזר מחרוזת ריקה."
        )
    )


class PurchaseOrder(BaseModel):
    order_number: str = Field(description="מספר הזמנת הרכש")
    items: list[OrderRow]


def _debug(msg):
    if DEBUG_PDF_HANDLER:
        print(msg)


def _normalize_sku(value):
    """
    ניקוי בסיסי למקט: הסרת רווחים/מקפים/קו תחתון/נקודות/סלאשים והמרה לאותיות גדולות.
    לא מוסיף אפסים ולא משנה משמעות עסקית.
    """
    if value is None:
        return ""
    return (
        str(value)
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
        .replace("/", "")
        .upper()
    )


def _clean_quantity(raw_qty):
    """
    ניקוי כמות בלבד. לא מחליט כאן אם הכמות תקינה לטעינה - זה נשאר באקסל.
    """
    clean_qty = str(raw_qty or "").strip()

    if clean_qty:
        clean_qty = re.sub(r"[^\d.]", "", clean_qty)
        if clean_qty.endswith("."):
            clean_qty = clean_qty[:-1]

        try:
            # 80.00 -> 80
            # 1.000 -> 1
            clean_qty = str(int(float(clean_qty)))
        except ValueError:
            clean_qty = ""

    return clean_qty


def _is_summary_or_noise_line(text):
    """בודקת אם השורה היא סיכום/מע״מ/תנאי תשלום ולא שורת פריט."""
    if not text:
        return False

    text_lower = str(text).lower()
    return any(keyword.lower() in text_lower for keyword in SUMMARY_KEYWORDS)


def _is_logistics_or_service_line(text):
    """בודקת אם מדובר בשורת אספקה/הובלה/משלוח ולא בשורת מוצר רגילה."""
    if not text:
        return False

    text_lower = str(text).lower()
    return any(keyword.lower() in text_lower for keyword in LOGISTICS_KEYWORDS)


def _is_plausible_sku(candidate):
    """
    סינון ראשוני למחרוזות שנראות כמו מקט.
    לא מחליף בדיקת DB ולא מחליף בדיקת הופעה במסמך.
    """
    if not candidate:
        return False

    s = _normalize_sku(candidate)

    if not s:
        return False

    if s in BLOCKED_SKUS:
        return False

    if s.startswith("PR"):
        return False

    # לא לקבל מספרים קצרים, אחוזים, מחירים או כמויות כמקט
    if len(s) < 5:
        return False

    # אם זה מספר בלבד, נאפשר כרגע רק 7 או 9 ספרות
    # 7 = מקט ספק נפוץ, 9 = מקט אטקה עם אפסים מובילים
    # 10 weidmueller
    if s.isdigit() and len(s) not in (7, 9, 10):
        return False

    return True


def _extract_document_tokens(extracted_text):
    """
    יוצר סט של טוקנים אלפא-נומריים שמופיעים פיזית במסמך.
    חשוב: התאמה היא לטוקן שלם אחרי ניקוי, לא substring בתוך כל המסמך.
    זה מונע מצב שמקט מומצא נוצר מצירוף מקרי של מספרים במסמך.
    """
    if not extracted_text:
        return set()

    text_upper = extracted_text.upper()

    # טוקנים כמו:
    # 1215356
    # 1SDA066652R1
    # AF80-40-00-13
    # SO26007641
    # office@elipur.co.il
    raw_tokens = re.findall(r"[A-Z0-9][A-Z0-9_\-/.@]{3,}[A-Z0-9]", text_upper)

    normalized_tokens = set()
    for token in raw_tokens:
        clean_token = _normalize_sku(token)
        if clean_token:
            normalized_tokens.add(clean_token)

    return normalized_tokens


def _candidate_appears_as_document_token(candidate, document_tokens):
    """
    חומת אש נגד הזיות:
    מקט יתקבל רק אם הוא מופיע פיזית במסמך כטוקן שלם.
    """
    if not candidate:
        return False

    clean_candidate = _normalize_sku(candidate)

    if not clean_candidate:
        return False

    if clean_candidate in document_tokens:
        return True

    # אם הלקוח כתב AT-1217139 וה-AI החזיר 1217139, נאפשר רק עם תחילית מוכרת
    for prefix in KNOWN_PREFIXES:
        clean_prefix = _normalize_sku(prefix)
        if f"{clean_prefix}{clean_candidate}" in document_tokens:
            return True

    return False


def _strip_known_prefixes(candidate):
    """
    מסיר תחיליות מוכרות כמו AT- רק אחרי שהמחרוזת המקורית עברה בדיקת הופעה במסמך.
    """
    clean_candidate = _normalize_sku(candidate)

    for prefix in KNOWN_PREFIXES:
        clean_prefix = _normalize_sku(prefix)
        if clean_candidate.startswith(clean_prefix):
            return clean_candidate[len(clean_prefix):]

    return clean_candidate


def _debug_ai_result(result, document_tokens):
    _debug("\n================ PDF HANDLER DEBUG ================")
    _debug(f"Loaded pdf_handler from: {__file__}")
    _debug(f"DEBUG_PDF_HANDLER={DEBUG_PDF_HANDLER}")
    _debug(f"Order number from AI: {result.order_number}")
    _debug(f"Document tokens count: {len(document_tokens)}")
    for probe in ["001340034", "1340034", "1215356", "1215899", "2321550"]:
        _debug(f"Document contains token {probe}? {_normalize_sku(probe) in document_tokens}")

    _debug("\nAI parsed rows:")
    for item in result.items:
        try:
            row_as_dict = item.model_dump()
        except Exception:
            row_as_dict = item.dict()
        _debug(json.dumps(row_as_dict, ensure_ascii=False))
    _debug("===================================================\n")


def process_pdf(pdf_file, openai_api_key):
    file_bytes = pdf_file.getvalue()
    if not file_bytes:
        raise Exception("הקובץ שהועלה ריק.")

    _debug(f"✅ Loaded pdf_handler v3 from: {__file__}")

    # מנוע קריאה מרחבי: שומר על העמודות והרווחים של המסמך ככל האפשר
    pdf_bytes_io = io.BytesIO(file_bytes)
    with pdfplumber.open(pdf_bytes_io) as pdf:
        extracted_text = "\n".join([
            page.extract_text(layout=True) or ""
            for page in pdf.pages
        ])

    document_tokens = _extract_document_tokens(extracted_text)

    if DEBUG_PDF_HANDLER:
        _debug("\n--- Extracted PDF text first 2500 chars ---")
        _debug(extracted_text[:2500])
        _debug("--- End extracted PDF text preview ---\n")

    client = OpenAI(api_key=openai_api_key)

    system_instruction = (
        "אתה מומחה לחילוץ נתונים מטבלאות הזמנות רכש בעברית/אנגלית.\n"
        "המטרה שלך היא חילוץ בלבד - לא השלמה, לא ניחוש ולא תיקון לפי ידע כללי.\n\n"

        "חוקים קריטיים:\n"
        "1. חלץ רק שורות פריט מתוך טבלת ההזמנה. אל תיצור שורות מסיכומים, מע\"מ, מחיר כולל, תנאי תשלום או פרטי מסמך.\n"
        "2. כמויות qty: הכמות היא מספר שמופיע לידו/תחתיו יח, יח', יח. או EA. אם הכמות כתובה 80.00 החזר 80. אם אין כמות ברורה החזר \"\".\n"
        "3. skus_found: חלץ אך ורק מקטים שמופיעים פיזית בשורת הפריט. אסור להמציא, להשלים, לשער או להסיק מקט לפי תיאור המוצר.\n"
        "4. אם בשורת פריט אין מקט מודפס, החזר skus_found=[] גם אם אפשר לנחש לפי התיאור.\n"
        "5. התעלם לחלוטין ממספרי פרויקט שמתחילים ב-PR, מספרי ספק, מספרי דרישה, מספרי לקוח, תאריכים, מחירים, אחוזי הנחה וכמויות.\n"
        "6. שורות אספקה/הובלה/משלוח/delivery/shipping/freight: אם אין מקט מודפס בשורה, החזר skus_found=[] והשאר רק את הכמות אם קיימת.\n"
        "7. אל תבלבל בין עמודת שורה לבין כמות.\n"
        "8. אם יש ספק - החזר פחות מידע, לא יותר. עדיף skus_found=[] מאשר מקט שגוי.\n"
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"להלן תוכן ההזמנה. חלץ את שורות הפריטים בלבד:\n{extracted_text}"},
        ],
        response_format=PurchaseOrder,
    )

    result = completion.choices[0].message.parsed

    _debug_ai_result(result, document_tokens)

    items_list = []

    for item in result.items:
        description_text = item.product_description or ""
        clean_qty = _clean_quantity(item.qty)

        _debug(f"\n--- Processing AI row {item.row_number} ---")
        _debug(f"description: {description_text}")
        _debug(f"qty raw: {item.qty} -> clean: {clean_qty}")
        _debug(f"skus_found raw: {item.skus_found}")

        # לא להחזיר שורות סיכום בכלל
        if _is_summary_or_noise_line(description_text):
            print(f"🚫 דילוג על שורת סיכום/רעש: {description_text}")
            continue

        # שורות הובלה/אספקה/משלוח - לא מאפשרים ל-AI להשלים מקט.
        # משאירים אותן ככתומות באקסל: מקט ריק + כמות אם קיימת.
        if _is_logistics_or_service_line(description_text):
            print(f"🚚 שורת אספקה/הובלה/משלוח זוהתה - מקט יושאר ריק: {description_text}")
            items_list.append({
                "row_num": item.row_number,
                "sku": "",
                "qty": clean_qty,
                "description": description_text,
            })
            continue

        valid_skus = []

        if item.skus_found:
            for raw_candidate in item.skus_found:
                normalized_candidate = _normalize_sku(raw_candidate)
                appears = _candidate_appears_as_document_token(raw_candidate, document_tokens)
                plausible = _is_plausible_sku(raw_candidate)

                _debug(
                    f"candidate raw='{raw_candidate}', normalized='{normalized_candidate}', "
                    f"plausible={plausible}, appears_in_pdf_tokens={appears}"
                )

                if not plausible:
                    print(f"🚫 חסימת ערך שאינו נראה כמקט: '{raw_candidate}' בשורה {item.row_number}")
                    continue

                if not appears:
                    print(
                        f"🚫 חסימת הזיה: המקט '{raw_candidate}' לא מופיע כטוקן במסמך "
                        f"(normalized='{normalized_candidate}') בשורה {item.row_number}"
                    )
                    continue

                clean_candidate = _strip_known_prefixes(raw_candidate)

                if clean_candidate in BLOCKED_SKUS:
                    print(f"🚫 חסימת מקט/מספר אסור: '{clean_candidate}' בשורה {item.row_number}")
                    continue

                if clean_candidate not in valid_skus:
                    valid_skus.append(clean_candidate)

        chosen_sku = ""
        is_exact_match = False

        # קודם כל מנסים למצוא התאמה ודאית ב-DB
        for candidate in valid_skus:
            db_match = find_sku_in_db(candidate)
            _debug(f"DB lookup candidate='{candidate}' -> {db_match}")

            if db_match:
                # חשוב: מחזירים את המועמד שהיה במסמך.
                # excel_handler כבר יהפוך אותו למקט אטקה לפי DB.
                chosen_sku = candidate
                is_exact_match = True
                break

        # אם יש מקט שהופיע פיזית במסמך אבל לא נמצא ב-DB:
        # משאירים אותו באקסל כדי שהמשתמש יראה מה היה במסמך, אבל excel_handler יסמן כתום.
        # לא בוחרים הכי ארוך ולא מנחשים.
        if not is_exact_match:
            chosen_sku = valid_skus[0] if valid_skus else ""

        _debug(f"Final chosen_sku='{chosen_sku}' for row {item.row_number}")

        items_list.append({
            "row_num": item.row_number,
            "sku": chosen_sku,
            "qty": clean_qty,
            "description": description_text,
        })

    _debug("\nFinal items_list:")
    _debug(json.dumps(items_list, ensure_ascii=False, indent=2))
    _debug("===================================================\n")

    return items_list, result.order_number
