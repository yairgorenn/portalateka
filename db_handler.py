import os
import pandas as pd
from sqlalchemy import create_engine, text

# ברירת המחדל היא ה-DB המקומי שלנו, ב-Railway זה יתחלף אוטומטית למשתנה הסביבה
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/postgres")

# SQLAlchemy Engine
engine = create_engine(DB_URL)


def init_catalog_db(csv_path="PB.csv"):
    """
    טוענת את הקטלוג המלא מתוך קובץ ה-CSV לתוך מסד הנתונים.
    מנקה נתונים ומשלימה מק"ט אטקה ל-9 ספרות.
    """
    print("מתחיל טעינת קטלוג למסד הנתונים...")
    if not os.path.exists(csv_path):
        print(f"❌ קובץ {csv_path} לא נמצא.")
        return

    # קריאת הקובץ (4 עמודות)
    df = pd.read_csv(csv_path, header=None, dtype=str)
    df.columns = ['ateka_sku', 'vendor_sku', 'hebrew_desc', 'english_desc']

    # טיפול בתאים ריקים בעמודות המשניות
    df['vendor_sku'] = df['vendor_sku'].fillna('')
    df['hebrew_desc'] = df['hebrew_desc'].fillna('')
    df['english_desc'] = df['english_desc'].fillna('')

    # מק"ט אטקה: ניקוי רווחים
    df['ateka_sku'] = df['ateka_sku'].astype(str).str.strip()

    # סינון שורות לא תקינות (לפני הוספת האפסים)
    df = df[(df['ateka_sku'] != 'nan') & (df['ateka_sku'] != '') & (df['ateka_sku'] != 'None')]

    # === השלמה ל-9 ספרות למק"ט אטקה ===
    df['ateka_sku'] = df['ateka_sku'].str.zfill(9)

    # ניקוי מק"ט יצרן
    df['vendor_sku'] = df['vendor_sku'].astype(str).str.replace(" ", "").str.replace("-", "").str.upper()

    # ניקוי תיאורים
    df['hebrew_desc'] = df['hebrew_desc'].astype(str).str.strip()
    df['english_desc'] = df['english_desc'].astype(str).str.strip()

    # שמירה למסד הנתונים
    df.to_sql('catalog', engine, if_exists='replace', index=False)
    print("✅ קטלוג מלא נטען למסד הנתונים עם מק\"טים מנורמלים (9 ספרות)!")


def find_sku_in_db(search_sku):
    """
    מקבלת מק"ט, מחפשת במסד הנתונים, ומחזירה את מק"ט אטקה התקין.

    סדר החיפוש:
    1. מק"ט כמו שהתקבל
    2. מק"ט בלי אפסים מובילים
    3. מק"ט אטקה עם השלמה ל-9 ספרות
    4. כלל אוריאל שי לווידמולר:
       800101000 -> 1010000000
    """
    if search_sku is None:
        return None

    clean_sku = str(search_sku).replace(" ", "").replace("-", "").upper().strip()

    # חסימת ברזל: לא מחפשים מק"ט ריק או קצר מדי
    if not clean_sku:
        return None

    if len(clean_sku) < 3:
        return None

    stripped_sku = clean_sku.lstrip('0')
    padded_sku = clean_sku.zfill(9)

    query = text("""
        SELECT DISTINCT ateka_sku
        FROM catalog
        WHERE
            (
                vendor_sku <> ''
                AND (
                    vendor_sku = :clean_sku
                    OR vendor_sku = :stripped_sku
                )
            )
            OR ateka_sku = :padded_sku
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {
            "clean_sku": clean_sku,
            "stripped_sku": stripped_sku,
            "padded_sku": padded_sku
        }).fetchall()

        # אם נמצאה התאמה יחידה - מחזירים אותה
        if len(result) == 1:
            return result[0][0]

        # אם נמצאו כמה מק"טי אטקה שונים - לא בוחרים אוטומטית
        if len(result) > 1:
            print(f"⚠️ נמצאו מספר התאמות עבור {clean_sku}: {[row[0] for row in result]}")
            return None

        # === כלל אוריאל שי / ויידמולר ===
        # דוגמה:
        # 800101000 -> הסרת 800 -> 101000 -> הוספת 0000 -> 1010000000
        if clean_sku.startswith("800") and clean_sku.isdigit() and len(clean_sku) == 9:
            weidmuller_sku = clean_sku[3:] + "0000"

            weidmuller_query = text("""
                SELECT DISTINCT ateka_sku
                FROM catalog
                WHERE vendor_sku <> ''
                  AND vendor_sku = :weidmuller_sku
            """)

            weidmuller_result = conn.execute(weidmuller_query, {
                "weidmuller_sku": weidmuller_sku
            }).fetchall()

            if len(weidmuller_result) == 1:
                print(f"✅ התאמת אוריאל שי/ויידמולר: {clean_sku} -> {weidmuller_sku} -> {weidmuller_result[0][0]}")
                return weidmuller_result[0][0]

            if len(weidmuller_result) > 1:
                print(f"⚠️ נמצאו מספר התאמות ויידמולר עבור {clean_sku} -> {weidmuller_sku}: {[row[0] for row in weidmuller_result]}")
                return None

        return None

def ensure_catalog_db(csv_path="PB.csv"):
    """
    בודקת אם טבלת catalog קיימת ב-DB.
    אם לא קיימת - טוענת את PB.csv ויוצרת אותה.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM catalog LIMIT 1"))
        print("✅ טבלת catalog קיימת. אין צורך בטעינה מחדש.")
    except Exception as e:
        print(f"⚠️ טבלת catalog לא קיימת או לא נגישה. טוען מחדש מתוך {csv_path}...")
        init_catalog_db(csv_path)

if __name__ == "__main__":
    # הרצת בדיקה מקומית
    init_catalog_db("PB.csv")

    print("\n🔍 שולף נתונים מהטבלה לבדיקה (שים לב לאפסים המובילים):")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM catalog LIMIT 5")).fetchall()
            for row in result:
                print(row)
        print("\n✅ הבדיקה המקומית עברה בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה בשליפת הנתונים: {e}")