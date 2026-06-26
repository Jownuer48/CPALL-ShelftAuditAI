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
8. Check YOLO-style annotated image in backend\annotated\

## 7. Reference Images

Put reference images here:

```text
backend\reference\model_a.jpg หรือ backend\reference\model_a.png
backend\reference\model_b.jpg หรือ backend\reference\model_b.png
backend\reference\model_c.jpg หรือ backend\reference\model_c.png
```

Do not push real CPALL images to GitHub unless allowed.

## 8. Planogram Files

Planogram templates are here:

```text
backend\planograms\model_a.json
backend\planograms\model_b.json
backend\planograms\model_c.json
```

ช่วงแรก slots สามารถว่างได้ เพราะจะเริ่มจากแยก MODEL_A / MODEL_B / MODEL_C ก่อน
ถ้ามี backend\planograms\model_d.json อยู่เดิม สามารถเก็บไว้ได้ แต่ระบบไม่ require MODEL_D แล้ว

## 9. AI Visual Audit Result

หลัง worker วิเคราะห์รูปเสร็จ ระบบจะสร้างภาพผลตรวจแบบ YOLO-style ไว้ที่:

```text
backend\annotated\
```

Dashboard จะแสดงภาพ annotated ก่อน ถ้ายังไม่มีจะ fallback ไปแสดงรูป upload เดิม

หมายเหตุ: กล่องสีเขียว/แดง/เหลืองมาจาก planogram JSON + OpenCV drawing ไม่ใช่ YOLO ที่ train แล้ว
