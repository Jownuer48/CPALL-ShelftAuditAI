# Shelf Audit AI Demo Runbook

## 1. Start Backend

เปิด Terminal 1:

```powershell
cd C:\Users\ASUS\ShelfAuditAI\backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend local:

http://localhost:8000/docs

## 2. Start ngrok

เปิด Terminal 2:

```powershell
ngrok http --url=mutilator-trifocals-grueling.ngrok-free.dev 8000
```

Public API:

https://mutilator-trifocals-grueling.ngrok-free.dev/docs

## 3. Start Dashboard

เปิด Terminal 3:

```powershell
cd C:\Users\ASUS\ShelfAuditAI\dashboard
..\backend\.venv\Scripts\activate
streamlit run app.py
```

Dashboard:

http://localhost:8501

## 4. Run Flutter on Chrome

ใช้สำหรับทดสอบ UI / Upload / Backend / Dashboard:

```powershell
cd C:\Users\ASUS\ShelfAuditAI\mobile\shelf_audit_app
flutter run -d chrome --dart-define=API_BASE_URL=https://mutilator-trifocals-grueling.ngrok-free.dev
```

## 5. Build Android APK

ใช้สำหรับทดสอบกล้องจริงและกรอบ Overlay บนมือถือ:

```powershell
cd C:\Users\ASUS\ShelfAuditAI\mobile\shelf_audit_app
flutter clean
flutter pub get
flutter build apk --release --dart-define=API_BASE_URL=https://mutilator-trifocals-grueling.ngrok-free.dev
```

APK path:

```text
mobile\shelf_audit_app\build\app\outputs\flutter-apk\app-release.apk
```

## 6. Test Flow

1. Open Android app
2. Enter branch code เช่น 0001
3. Take shelf photo
4. Preview image
5. Upload to AI
6. Check /results
7. Check Dashboard

## 7. Reference Images

Put reference images here:

```text
backend\reference\model_a.jpg
backend\reference\model_b.jpg
backend\reference\model_c.jpg
backend\reference\model_d.jpg
```

Do not push real CPALL images to GitHub unless allowed.

## 8. Planogram Files

Planogram templates are here:

```text
backend\planograms\model_a.json
backend\planograms\model_b.json
backend\planograms\model_c.json
backend\planograms\model_d.json
```

ช่วงแรก slots สามารถว่างได้ เพราะจะเริ่มจากแยก MODEL_A / MODEL_B / MODEL_C / MODEL_D ก่อน
