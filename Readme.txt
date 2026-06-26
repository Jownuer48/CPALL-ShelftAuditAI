STEP 1: Build APK หลังแก้ MyApp

เข้าโฟลเดอร์ Flutter:

cd C:\Users\ASUS\ShelfAuditAI\mobile\shelf_audit_app
flutter clean
flutter pub get
flutter build apk --release --dart-define=API_BASE_URL=https://mutilator-trifocals-grueling.ngrok-free.dev

ถ้า build ผ่าน ไฟล์ APK อยู่ที่:

C:\Users\ASUS\ShelfAuditAI\mobile\shelf_audit_app\build\app\outputs\flutter-apk\app-release.apk

ให้ลบแอปเก่าในมือถือก่อน แล้วติดตั้งตัวนี้ใหม่

STEP 2: เปิด Backend + ngrok + Dashboard

เปิด Terminal 1:

cd C:\Users\ASUS\ShelfAuditAI\backend
.venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

เปิด Terminal 2:

ngrok http --url=mutilator-trifocals-grueling.ngrok-free.dev 8000

เปิด Terminal 3:

cd C:\Users\ASUS\ShelfAuditAI\dashboard
..\backend\.venv\Scripts\activate
streamlit run app.py

เช็ก API:

https://mutilator-trifocals-grueling.ngrok-free.dev/docs

เช็ก Dashboard:

http://localhost:8501
ถ้าต้องการให้มันขึ้นให้เลือกแบบนี้ ให้รันคำสั่ง ไม่ต้องใส่ -d chrome

ใช้คำสั่งนี้รันถ้าจะใช้chrome:

cd C:\Users\ASUS\ShelfAuditAI\mobile\shelf_audit_app
flutter run --dart-define=API_BASE_URL=https://mutilator-trifocals-grueling.ngrok-free.dev