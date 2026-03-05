# 🚀 Production Deployment & Scaling Guide

Ushbu qollanma botni 500,000+ foydalanuvchi uchun professional darajada ishga tushirish va boshqarishga yordam beradi.

## 🏗 Arxitektura: Webhook mode
Polling'dan farqli o'laroq, Webhook rejimida Telegram serveri botga xabarlarni o'zi yuboradi (push). Bu yuqori yuklamalar uchun eng barqaror va samarali usuldir.

### 1. Webhook sozlamalari
Webhook ishlashi uchun SSL (HTTPS) sertifikati bo'lgan domen kerak.

`.env` fayliga quyidagilarni qo'shing:
- `WEBHOOK_HOST=https://sizning-domeningiz.com`
- `BACKEND_PORT=8000` (Default bot porti)

### 2. Monitoring (Healthcheck)
Botning holatini tekshirish uchun `/health` endpointi mavjud. 
Downtime monitoring xizmatlari (UptimeRobot, etc.) orqali ushbu manzilni tekshirib turing: `https://sizning-domeningiz.com/health`

### 3. Graceful Shutdown
Bot to'xtatilganda (SIGTERM), u avtomatik ravishda Webhook'ni o'chiradi va sessiyalarni yopadi. Bu `TelegramConflictError` xatolarining oldini oladi.

## 📈 Scaling for Viral Growth
- **Worker Scaling**: Fon vazifalarini ko'paytirish uchun: 
  `docker compose up -d --scale worker=4`
- **Reverse Proxy**: Nginx yoki Traefik orqali Webhook'ga kelayotgan so'rovlarni boshqaring.
- **Worker Isolation**: Agar yuklama juda oshsa, worker'larni alohida VPS'larga ko'chirishingiz mumkin.

## 🛡️ Security & Anti-Ban
- **Rotating Proxies**: Instagram scraping uchun kamida 10-20 ta sifatli proxy va account'lardan foydalaning.
- **Redis Caching**: Tizim barcha og'ir yuklamalarni Redis orqali atomic holatda keshlaydi.

---
**Antigravity Senior Architect tomonidan tayyorlandi**
