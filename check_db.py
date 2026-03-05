import asyncio
from sqlalchemy import text
from bot.database.session import engine

async def check():
    async with engine.connect() as conn:
        print("Checking 'sponsor_channels' table...")
        try:
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='sponsor_channels'
            """))
            columns = [row[0] for row in result.fetchall()]
            print(f"Columns in 'sponsor_channels': {columns}")
        except Exception as e:
            print(f"Error checking table: {e}")

if __name__ == "__main__":
    asyncio.run(check())
