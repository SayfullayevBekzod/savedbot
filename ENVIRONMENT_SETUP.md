# Render.com Environment Variables Setup

## 🚀 Zarur Environment Variables

### 🤖 Bot Asosiy Sozlamalari
```
BOT_TOKEN=your_bot_token_here
```
- Telegram Bot Token (BotFather dan oling)

### 🗄️ Database Sozlamalari
```
DATABASE_URL=postgresql+asyncpg://bot_user:bot_password@db:5432/bot_db
```
- Render PostgreSQL database URL
- Render da PostgreSQL service yarating va URL ni copy qiling

### 📡 Redis Sozlamalari
```
REDIS_URL=redis://localhost:6379/0
ARQ_REDIS_URL=redis://localhost:6379/1
```
- Render Redis service URL
- Render da Redis service yarating va URL ni copy qiling

### 🌐 Webhook Sozlamalari
```
WEBHOOK_HOST=your-app-name.onrender.com
WEBHOOK_PATH=/webhook
BACKEND_PORT=8000
```
- WEBHOOK_HOST: Render app URL (masalan: savedbot.onrender.com)
- BACKEND_PORT: 8000 (default)

### 🎥 Performance Sozlamalari (Ultra-fast)
```
DOWNLOAD_DIR=downloads
MAX_VIDEO_SIZE_MB=50
AUTO_VIDEO_MAX_HEIGHT=480
UPLOAD_CHUNK_SIZE_KB=4096
DOWNLOAD_CONCURRENT_FRAGMENTS=256
MAX_CONCURRENT_DOWNLOADS=8
COOLDOWN_SECONDS=0
```

### 👑 Admin Sozlamalari
```
ADMIN_IDS=[123456789]
SPONSOR_CHANNELS=["@Bekcode"]
ENABLE_SUBSCRIPTION_CHECK=false
```
- ADMIN_IDS: Sizning Telegram ID raqamingiz
- SPONSOR_CHANNELS: Sponsor kanallar ro'yxati
- ENABLE_SUBSCRIPTION_CHECK: Obuna tekshirish (true/false)

## 📋 Render.com da Qo'shish Tartibi

### 1️⃣ Database Yaratish
- Render Dashboard → New → PostgreSQL
- Name: `savedbot-db`
- Region: Eng yaqin region
- Plan: Free
- Database URL ni copy qiling

### 2️⃣ Redis Yaratish
- Render Dashboard → New → Redis
- Name: `savedbot-redis`
- Region: Database bilan bir xil
- Plan: Free
- Redis URL ni copy qiling

### 3️⃣ Web Service Yaratish
- GitHub repository ulang
- Environment variables qo'shing
- Deploy qiling

## ⚡ Tezkor Setup

### Bot Token Olish:
1. @BotFather ga yozing
2. `/newbot` command
3. Token ni copy qiling

### Telegram ID Olish:
1. @userinfobot ga yozing
2. ID raqamni copy qiling

### Render URL Olish:
1. Deploy qilingandan so'ng
2. App URL ni copy qiling (masalan: savedbot.onrender.com)

## 🎯 Final Environment Variables List:
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
ARQ_REDIS_URL=redis://host:6379/1
WEBHOOK_HOST=savedbot.onrender.com
WEBHOOK_PATH=/webhook
BACKEND_PORT=8000
ADMIN_IDS=[123456789]
SPONSOR_CHANNELS=["@Bekcode"]
ENABLE_SUBSCRIPTION_CHECK=false
DOWNLOAD_DIR=downloads
MAX_VIDEO_SIZE_MB=50
AUTO_VIDEO_MAX_HEIGHT=480
UPLOAD_CHUNK_SIZE_KB=4096
DOWNLOAD_CONCURRENT_FRAGMENTS=256
MAX_CONCURRENT_DOWNLOADS=8
COOLDOWN_SECONDS=0
```
