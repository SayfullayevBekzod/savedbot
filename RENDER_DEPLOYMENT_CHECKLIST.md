# Render.com Complete Deployment Checklist

## 🚀 Render.com Web Service Setup

### 📋 Basic Information
- **Name**: `savedbot`
- **Environment**: `Python 3`
- **Region**: Eng yaqin region (masalan: Oregon)
- **Branch**: `main`
- **Root Directory**: `.` (leave empty)

### 📦 Build Settings
- **Build Command**: `pip install -r requirements.txt`
- **Runtime**: `Docker` (agar Docker ishlatsa) yoki `Python`
- **Instance Type**: `Free` (boshlang'ich uchun)

### 🚀 Start Settings
- **Start Command**: `python main.py`
- **Health Check Path**: `/health` (agar health check bo'lsa)

## 🔧 Environment Variables (To'liq ro'yxat)

### 🤖 Zarur Variables
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```
- @BotFather dan olingan token

### 🗄️ Database Variables
```
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
REDIS_URL=rediss://default:password@host:6379/0
ARQ_REDIS_URL=rediss://default:password@host:6379/1
```
- Render PostgreSQL va Redis service URL lari

### 🌐 Webhook Variables
```
WEBHOOK_HOST=https://savedbot.onrender.com
WEBHOOK_PATH=/webhook
BACKEND_PORT=8000
```
- WEBHOOK_HOST: Deploy qilingandan so'ng app URL

### ⚡ Performance Variables (Ultra-fast)
```
DOWNLOAD_DIR=downloads
MAX_VIDEO_SIZE_MB=50
AUTO_VIDEO_MAX_HEIGHT=480
UPLOAD_CHUNK_SIZE_KB=4096
DOWNLOAD_CONCURRENT_FRAGMENTS=256
MAX_CONCURRENT_DOWNLOADS=8
COOLDOWN_SECONDS=0
```

### 👑 Admin Variables
```
ADMIN_IDS=[123456789]
SPONSOR_CHANNELS=["@Bekcode"]
ENABLE_SUBSCRIPTION_CHECK=false
```

## 📋 Deploy Qilish Tartibi

### 1️⃣ Services Yaratish (Avval)
1. **PostgreSQL**:
   - Render Dashboard → New → PostgreSQL
   - Name: `savedbot-db`
   - Region: Tanlang
   - Plan: Free
   - Database URL ni copy qiling

2. **Redis**:
   - Render Dashboard → New → Redis
   - Name: `savedbot-redis`
   - Region: PostgreSQL bilan bir xil
   - Plan: Free
   - Redis URL ni copy qiling

### 2️⃣ Web Service Yaratish
1. **GitHub Repository**:
   - Connect GitHub repository
   - Repository: `SayfullayevBekzod/savedbot`
   - Branch: `main`

2. **Environment**:
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`

3. **Environment Variables**:
   - Yuqoridagi barcha variables qo'shing
   - DATABASE_URL va REDIS_URL ni services dan oling

4. **Deploy**:
   - "Create Web Service" tugmasini bosing
   - Build jarayonini kuting (5-10 daqiqa)

### 3️⃣ Post-Deploy Setup
1. **Webhook URL olish**:
   - Deploy tugagandan so'ng app URL ni copy qiling
   - Masalan: `https://savedbot.onrender.com`

2. **WEBHOOK_HOST yangilash**:
   - Environment variables ga qayta kiring
   - WEBHOOK_HOST ni to'g'ri URL bilan yangilang
   - Redeploy qiling

## 🔍 Troubleshooting

### ❌ Agar Build Xatolik Bersa:
- Requirements.txt ni tekshiring
- Python version mosligini tekshiring
- Dependencies ni tekshiring

### ❌ Agar Bot Ishlamasa:
- BOT_TOKEN to'g'riligini tekshiring
- Database ulanishini tekshiring
- Redis ulanishini tekshiring
- Log larni ko'ring

### ❌ Agar Webhook Ishlamasa:
- WEBHOOK_HOST to'g'ri URL ekanligini tekshiring
- Port ochiq ekanligini tekshiring
- HTTPS ishlayotganini tekshiring

## ✅ Success Indicators
- ✅ Build muvaffaqiyatli tugaydi
- ✅ Bot ishga tushadi
- ✅ Webhook ulanadi
- ✅ Database ulanadi
- ✅ Redis ulanadi
- ✅ Botga yozish mumkin bo'ladi

## 🎯 Final URL Format
```
WEBHOOK_HOST=https://your-app-name.onrender.com
```

## 📞 Support
- Render logs: Dashboard → Logs
- GitHub: Code qayta deploy qilish
- Environment: Variables qayta sozlash
