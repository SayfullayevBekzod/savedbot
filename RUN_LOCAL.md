# 🚀 Local Server Qollanmasi (Non-Docker)

Ushbu botni Docker-siz, to'g'ridan-to'g'ri serveringizda yoki kompyuteringizda ishga tushirish uchun quyidagi qadamlarni bajaring.

## 📋 Talablar
1. **Python 3.10+** o'rnatilgan bo'lishi kerak.
2. **FFmpeg** o'rnatilgan va PATH'ga qo'shilgan bo'lishi kerak.
3. **Redis**: `6379` portida ishlab turgan bo'lishi kerak.
   - *Variant*: Redis'ni Docker orqali ishga tushirishingiz mumkin: `docker compose up -d redis`.
4. **Git** (ixtiyoriy, kodni yangilab turish uchun).

## 🛠 O'rnatish

### 1. Virtual Muhitni Yaratish
Dastlab loyiha papkasida virtual muhitni yarating va faollashtiring:
```bash
python -m venv venv

# Windows uchun:
.\venv\Scripts\activate

# Linux/macOS uchun:
source venv/bin/activate
```

### 2. Kutubxonalarni O'rnatish
```bash
pip install -r requirements.txt
```

### 3. Konfiguratsiya
`.env` faylida barcha ma'lumotlar to'g'riligini tekshiring:
- `BOT_TOKEN`: Telegram botingiz tokeni.
- `REDIS_URL`: `redis://localhost:6379/0` (Local Redis ishlatayotgan bo'lsangiz).
- `DATABASE_URL`: PostgreSQL bazangiz manzili.

## 🚀 Ishga Tushirish

Botni va Fon vazifalarini (worker) alohida terminal oynalarida ishga tushiring:

### A. Botni ishga tushirish:
```bash
python -m bot.main
```

### B. Worker (Fon vazifalari)ni ishga tushirish:
```bash
# Virtual muhit faol bo'lgan terminalda:
arq bot.services.worker.WorkerSettings
```

## 🧹 Tozalash
Vaqti-vaqti bilan `downloads/` papkasini tozalab turing (bot buni kunlik avtomatik bajaradi, lekin qo'lda ham tekshirish mumkin).
