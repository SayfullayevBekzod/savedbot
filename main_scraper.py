import asyncio
import json
from scraper import InstagramScraper
from bot.database.session import async_session, Database, init_db

# API kalitingiz (RapidAPI dan olingan)
API_KEY = "f9b2ddbbe6msh514d28889a9db79p1ba6eajsnc03895443b3a"

async def main():
    # 1. Ma'lumotlar bazasini initsializatsiya qilish
    print("Bazaga ulanilmoqda...")
    await init_db()
    
    # Scraperni initsializatsiya qilish
    scraper = InstagramScraper(API_KEY)
    
    # DB sessiyasini ochish
    async with async_session() as session:
        db = Database(session)
        
        # Namuna foydalanuvchi nomi va hashtag
        username = "cristiano" # Ommaviy mahhur profil
        hashtag = "uzbekistan"
        
        print("\n--- 1. Reels olish va bazaga saqlash ---")
        reels = await scraper.get_user_reels(username, max_pages=1, db=db)
        print(f"Olingan Reels soni: {len(reels)}")
        
        print("\n--- 2. Hashtag postlarini olish va bazaga saqlash ---")
        hashtag_posts = await scraper.get_hashtag_posts(hashtag, max_pages=1, db=db)
        print(f"Olingan postlar soni: {len(hashtag_posts)}")

        print("\n--- 3. Stories olish va bazaga saqlash ---")
        stories = await scraper.get_user_stories(username, db=db)
        print(f"Olingan Stories soni: {len(stories)}")

        print("\n--- 4. Foydalanuvchi barcha postlarini olish va bazaga saqlash ---")
        posts = await scraper.get_user_posts(username, max_pages=1, db=db)
        print(f"Olingan barcha postlar soni: {len(posts)}")
        
    print("\nBarcha ma'lumotlar muvaffaqiyatli bazaga yuklandi! ✅")

if __name__ == "__main__":
    asyncio.run(main())
