# Avtomatik Cookies Boshqarish Tizimi

## Tavsifi

Cookies fayllarni avtomatik boshqaradigan yangi tizim yaratildi. Bu tizim:

✅ **Avtomatik cookies.txt faylini yuklab oladi**
✅ **Eski/eskirgan cookies avtomatik o'zgartiriladi**
✅ **To'liq avtomatlashtirish - hech qanday userdan input kerak emas**
✅ **Bir vaqtning o'zida 3 ta cookie faylini sinab ko'radi**
✅ **Ishlovchi cookieslarni prioritet bilan ishlatadi**

---

## Ishlash Prinsipi

### 1. Cookie Yuklash Tartibi (Prioritet)

1. **cookies.txt** - Eng yuqori prioritet (agar mavjud bo'lsa)
2. **cookies/ papkadagi .txt fayllar** - Ikkinchi prioritet
3. Hech biri yo'q bo'lsa - **without cookies** (proxy bilan harakat qiladi)

### 2. Avtomatik Rotation Mekanizmi

```
📝 Download boʻlanayotgan vaqtda:
   ↓
1️⃣ Cookie-1 bilan urinish
   ├─ SUCCESS ✅ → Cookie-1 ishchi deb belgilash, yuklab olish
   └─ FAILED ❌ → Cookie-1 eskirgan deb belgilash, Cookie-2 bilan urinish
   ↓
2️⃣ Cookie-2 bilan urinish
   ├─ SUCCESS ✅ → Cookie-2 ishchi deb belgilash, yuklab olish
   └─ FAILED ❌ → Cookie-2 eskirgan deb belgilash, Cookie-3 bilan urinish
   ↓
3️⃣ Cookie-3 bilan urinish
   ├─ SUCCESS ✅ → Cookie-3 ishchi deb belgilash, yuklab olish
   └─ FAILED ❌ → Barcha cookies reset qilish, yana boshdan urinish
```

### 3. Cookie Holati (Status Tracking)

Har bir cookie uchun quyidagi ma'lumotlar saqlanadi:

```python
{
    'failed': bool,           # Eskirgan yoki ishchi
    'fail_count': int,        # Necha marta xato bergan
    'last_used': timestamp,   # Oxirgi o'rnatilgan vaqt
    'last_error': str         # Oxirgi xato xabari
}
```

---

## Fayllar Tavsifi

### **bot/services/antiban.py** (Yangi CookieManager klassy)

```python
class CookieManager:
    - get_next_cookie()              # Keyingi ishchi cookie olish
    - mark_cookie_failed(path, err)  # Cookie eskirgan deb belgilash
    - mark_cookie_working(path)      # Cookie ishchi deb belgilash
    - get_status()                   # Barcha cookies statusini olish
```

### **bot/services/downloader.py** (Yangi retry logic)

```python
async def _download_with_cookie_retry(...)
    # Avtomatik cookie rotation bilan download
    # Max 3 ta cookie sinab ko'radi
    # Bitta fail uchun keyingisiga o'tadi
```

---

## Cookies Fayllarini Qo'shish

### Variant 1: **Asosiy cookies.txt** (Eng yaxshi)
```
d:\Work\savedbot\
    ├── cookies.txt  ← Put Netscape format cookies here
    └── cookies/
```

### Variant 2: **Cookies papkasida bir nechtasi** 
```
d:\Work\savedbot\
    └── cookies/
        ├── cookies1.txt
        ├── cookies2.txt
        └── cookies3.txt
```

### Variant 3: **Ikkalasi ham**
```
d:\Work\savedbot\
    ├── cookies.txt      ← Shu birinchi ishlatilinadi
    └── cookies/
        ├── cookies1.txt ← Fallback
        ├── cookies2.txt ← Fallback
        └── cookies3.txt ← Fallback
```

---

## Netscape Format Cookies

Chrome-dan cookies olish:

```python
# Cookie format: Netscape format
# Domain | Flag | Path | Secure | Expiration | Name | Value
.instagram.com	TRUE	/	TRUE	1700000000	sessionid	abc123xyz456
```

---

## Monitoring va Debug

### Status Koʻrish
```python
from bot.services.antiban import antiban_service

# Barcha cookies status
status = antiban_service.get_cookie_status()
print(status)
# Output:
# {
#     'total_cookies': 3,
#     'working_cookies': 2,
#     'failed_cookies': 1,
#     'cookies': {...}
# }
```

### Logs
```
Logger: bot.services.downloader
Logger: bot.services.antiban

# Yangi fayllar ichidagi INFO/WARNING logs:
"Cookie marked as working: cookies.txt"
"Cookie marked as failed: cookies1.txt (fails: 1) - Connection error"
```

---

## Ishlash Xususiyatlari

| Feature | Tafsifi |
|---------|---------|
| **Avtomatik yuklab olish** | cookies.txt qo'shilsa, avtomatik yuklab olinadi |
| **Fault tolerance** | 1 cookie eskirsa, keyingisini ishlatadir |
| **Max retries** | Har download uchun 3 ta cookie sinab ko'radi |
| **Smart rotation** | Ishchi cookies avval sinab ko'radi, eskirganlarni keyinroq |
| **Status tracking** | Barcha cookies holatini kuzatadi |
| **Auto-reset** | 5 marta failed bo'lgan cookies reset qilinadi |

---

## Misol: Real Download Jarayoni

```
User: /download https://instagram.com/reel/xyz123

1. get_next_cookie() → "cookies.txt" qaytaradi
2. Download boʻlanayotgan vaqtda:
   - Try: cookies.txt
     ✅ Success! "Reel_title.mp4" saved
     
   - If failed:
     ❌ cookies.txt fails
     - Mark: cookies.txt → failed
     - Try: cookies1.txt
       ✅ Success! "Reel_title.mp4" saved

   - If still failed:
     ❌ cookies1.txt fails too
     - Mark: cookies1.txt → failed  
     - Try: cookies2.txt
       ✅ Success! "Reel_title.mp4" saved

   - If all failed:
     ❌ All cookies failed
     - Reset all failed cookies (let them be tried again later)
     - Return error to user with next retry hint
```

---

## Configuration Variables

```python
# antiban.py
CookieManager.max_retries = 3  # Default
# Change: cookie_manager.reset_failed_cookies() uchun:
fail_threshold = 5  # 5 ta xato keyin auto-reset
```

---

## API Changes

### Eski (Old):
```python
antiban_service.get_random_cookie_file()  # Simple random
```

### Yangi (New):
```python
antiban_service.get_random_cookie_file()  # Smart rotation + retry
antiban_service.mark_cookie_failed(path, error)
antiban_service.mark_cookie_working(path)
antiban_service.get_cookie_status()
```

---

## Troubleshooting

### "Barcha cookies eskirgan/failed" ✗

```python
# Reset manually:
from bot.services.antiban import antiban_service
antiban_service.cookie_manager.reset_failed_cookies()
```

### Cookies faylini yangilash ✓

```python
# Avtomatik _refresh_cookies() chaqiriladi
# Yangi fayllar avtomatik yuklab olinadi
cookie = antiban_service.get_random_cookie_file()
```

### Debug mode ✓

```python
# Log level o'zgartirib:
import logging
logging.getLogger('bot.services').setLevel(logging.DEBUG)
```

---

## Xulosa

✅ **Barcha cookies avtomatik boshqaraladi**
✅ **Eskirgan cookie avtomatik o'zgartiriladi**  
✅ **3 marta urinib ko'riladi**
✅ **Hech qanday manual input kerak emas**
✅ **Ishchi cookies prioritet bilan ishlatilinadi**

**Nanoq o'xshash masalalar yo'q!** 🎉
