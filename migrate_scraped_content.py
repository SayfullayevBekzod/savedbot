import asyncio
import logging
from bot.database.session import engine, Base
from bot.database.models import ScrapedContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate():
    logger.info("Yangi 'scraped_content' jadvalini yaratish boshlanmoqda...")
    try:
        async with engine.begin() as conn:
            # Faqat yangi jadvalni yaratish (create_all mavjud jadvallarga tegmaydi)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Jadval muvaffaqiyatli yaratildi! ✅")
    except Exception as e:
        logger.error(f"Migratsiyada xatolik: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
