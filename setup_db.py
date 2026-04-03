"""
UniPredict AI — One-time CSV Setup
Run this ONCE before starting the app:  python setup_db.py

It will:
1. Create the  data/  folder
2. Create all CSV table files
3. Seed default users
4. Import students from student_dataset.csv
"""
import database as db


def run():
    print("=" * 50)
    print(" UniPredict AI — CSV Setup")
    print("=" * 50)

    print("\n[1] Initialising CSV data store...")
    db.init_db()

    print("\n✅ Setup complete!")
    print("\nDefault login credentials:")
    print("  Admin:     admin_laishram        / Admin@2026")
    print("  Admin:     admin_thounaojam      / Admin@2026")
    print("  Teacher:   teacher_ningthoujam   / Teach@2026")
    print("  Teacher:   teacher_konthoujam    / Teach@2026")
    print("  Teacher:   teacher_oinam         / Teach@2026")
    print("  Teacher:   teacher_wangkhem      / Teach@2026")
    print("  Counselor: counselor_pukhrambam  / Counsel@2026")
    print("  Counselor: counselor_yumnam      / Counsel@2026")
    print("  Parent:    parent_thangjam_1     / par1@2026")
    print("  Parent:    parent_thangjam_2     / par2@2026")
    print("\nNow run:  python app.py")
    return True


if __name__ == "__main__":
    run()
