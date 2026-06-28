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
    מקבלת מק"ט, מחפשת במסד הנתונים, ומחזירה את מק"ט אטקה התקין (עם אפסים).
    """
    clean_sku = str(search_sku).replace(" ", "").replace("-", "").upper()

    # מכינים את 3 התרחישים לחיפוש:
    stripped_sku = clean_sku.lstrip('0')  # למקרה שמק"ט יצרן הוקלד בלי אפסים
    padded_sku = clean_sku.zfill(9)  # למקרה שזה מק"ט אטקה שהוקלד בלי אפסים

    # אנחנו מחפשים התאמה למק"ט יצרן (עם או בלי אפסים) או למק"ט אטקה המושלם
    query = text("""
        SELECT ateka_sku 
        FROM catalog 
        WHERE vendor_sku = :clean_sku 
           OR vendor_sku = :stripped_sku
           OR ateka_sku = :padded_sku
        LIMIT 1
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {
            "clean_sku": clean_sku,
            "stripped_sku": stripped_sku,
            "padded_sku": padded_sku
        }).fetchone()

        if result:
            return result[0]  # יחזיר אוטומטית מק"ט של 9 ספרות כי ככה שמרנו ב-DB
        return None


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