# UniPredict AI — Combined v4.0

## What's New in This Version
- **Educational Friendly Background** on all pages (light theme with animated floating icons, soft gradients, grid pattern)
- **Student Reports visible to Teacher, Admin & Counselor** — all three roles can view full student reports and email them to parents
- Combined best features from both source versions

## Setup
```bash
pip install -r requirements.txt
python setup_db.py   # creates DB and seeds demo data
python app.py        # starts on http://localhost:5000
```

## Credentials
| Role       | Username                | Password      |
|------------|-------------------------|---------------|
| 👑 Admin    | admin_thounaojam        | Admin@2026    |
| 👑 Admin    | admin_laishram          | Admin@2026    |
| 📖 Teacher  | teacher_ningthoujam     | Teach@2026    |
| 📖 Teacher  | teacher_konthoujam      | Teach@2026    |
| 📖 Teacher  | teacher_oinam           | Teach@2026    |
| 📖 Teacher  | teacher_wangkhem        | Teach@2026    |
| 🤝 Counselor| counselor_pukhrambam    | Counsel@2026  |
| 🤝 Counselor| counselor_yumnam        | Counsel@2026  |
| 👨‍👩‍👧 Parent  | parent_thangjam_1       | par1@2026     |
| 👨‍👩‍👧 Parent  | parent_thangjam_2       | par2@2026     |

## Report Access
Student reports are accessible to:
- ✅ **Teacher** — via 📋 Report button in student list table
- ✅ **Admin** — via 📊 Student Reports tab in Admin dashboard
- ✅ **Counselor** — via View/Report buttons in at-risk panel and all students list
- ❌ **Parent** — cannot view internal staff reports (parents see their own child's dashboard)

## Combined Features (from both versions)
- Duplicate student detection before adding (from updated version)
- Teacher can delete students (from updated version)
- Counselor email shown in navbar and reports (from updated version)
- try/except on ML init so server starts even without trained model (from updated version)
- All user credentials from updated version (Manipur names)
