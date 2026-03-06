# 🚀 Cookies Tizimini Qo'llash - Tez Boshlash

## Asosiy 3 Qadam

### 1️⃣ Cookies Files Qo'shish

Quyidagi yo'llardan birini tanlang:

**A) Bitta asosiy cookies (tavsiya etilgan):**
```
d:\Work\savedbot\cookies.txt
```

**B) Bir necha cookies (fallback uchun):**
```
d:\Work\savedbot\cookies\
├── cookies.txt
├── cookies1.txt
└── cookies2.txt
```

### 2️⃣ Code Avtomatik Ishlaydi ✓

Hech narsa o'zgarmasin! Kod avtomatik:
- ✅ cookies.txt va cookies/*.txt fayllarni topib
- ✅ Har bir download da shu cookies'larni ishlatadir
- ✅ Agar bitta eskirsa, ikkinchisini ishlatadir
- ✅ 3ta urinib o'rnatadi

### 3️⃣ Monitor Qiling (Optional)

```python
from bot.services.antiban import antiban_service

# Cookies status koʻring
status = antiban_service.get_cookie_status()
print(f"Working cookies: {status['working_cookies']}")
print(f"Failed cookies: {status['failed_cookies']}")
```

---

## Download Logs

Loglarni koʻrish uchun:

```
Terminal'da:
Bot ishlaganda automat log chiqadi:

"Cookie marked as working: cookies.txt"
"Download attempt 1 with cookie: cookies.txt"
"Cookie marked as failed: cookies1.txt (fails: 1) - 403 Forbidden"
"Download attempt 2 with cookie: cookies2.txt"
```

---

## Netscape Format Cookies

Chrome-dan cookies export qilish:

1. **Chrome Developer Tools** → **Application** → **Cookies**
2. **Netscape HTTPCookieJar format** ga export qiling
3. **cookies.txt** ga saqlang

**Format misol:**
```
# Netscape HTTP Cookie File
.instagram.com	TRUE	/	TRUE	1700000000	sessionid	abc123xyz
.instagram.com	TRUE	/	TRUE	1700000000	mid	xyz789abc
```

---

## Tez Masalalar Hal Qilish

### "Cookies faylini topa olmayapti" ❌
```python
# Log chiqadi:
# "Cookie_path" doesn't exist
# Qaytadan koʻring:
# d:\Work\savedbot\cookies.txt yoki cookies\*.txt
```

### "Hammasida proxy/ban xatosi" ❌
```python
# Yangi cookies qo'shing yoki 
# Koʻlgan cookies'larni refresh qiling:
antiban_service.cookie_manager.reset_failed_cookies()
```

### "3 ta cookie ham fail boʻlyapti" ❌
```python
# Yangi/aktual cookies qo'shing:
# 1. Chrome-dan yangi session ol
# 2. cookies.txt'ga yoz
# 3. Bot avtomatik ishlatadir
```

---

## Xulosa: Ishlashi

```
📥 Cookies qo'shish → 
🤖 Bot avtomatik yuklab oladi → 
⚡ Download fail bo'lsa → 
🔄 Keyingi cookie bilan auto-retry → 
✅ Success!
```

**To'liq avtomatik! Hech narsa o'zgarmasin** ✨

---

## Advanced: Code Integration

Agar o'z commandingiz bor bo'lsa:

```python
from bot.services.downloader import downloader

# Avtomatik retry bilan:
result = await downloader.download("https://...")
# Ichida automatic cookie rotation

result = await downloader.fast_download("https://...")
# Ichida automatic cookie rotation

result = await downloader.get_info("https://...")
# Ichida automatic cookie rotation
```

Barcha download methodlari **avtomatik cookie retry** bilan ishlaydi! 🎉

---

## Qoʻshimcha Havolalar

- [Full Documentation](./COOKIE_MANAGEMENT.md)
- [Antiban Service Code](./bot/services/antiban.py)
- [Downloader Service Code](./bot/services/downloader.py)
