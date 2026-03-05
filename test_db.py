import asyncio
from sqlalchemy import text
from bot.database.session import engine

async def test_db():
    print("Connecting to DB...")
    try:
        async with engine.connect() as conn:
            print("Connected! Running simple query...")
            result = await conn.execute(text("SELECT 1"))
            print(f"Query result: {result.scalar()}")
            
            print("Checking schema metadata...")
            # This is what create_all does internally but safer to run separately
            from bot.database.models import Base
            # We don't run create_all here, just check if we can access models
            print("Metadata check ok.")
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_db())
