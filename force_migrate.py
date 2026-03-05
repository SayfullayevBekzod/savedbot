import asyncio
from sqlalchemy import text
from bot.database.session import engine

async def migrate():
    async with engine.begin() as conn:
        print("Forcing 'invite_link' column addition...")
        try:
            await conn.execute(text("ALTER TABLE sponsor_channels ADD COLUMN invite_link VARCHAR"))
            print("Successfully added 'invite_link' column.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("'invite_link' column already exists.")
            else:
                print(f"Error adding column: {e}")

        print("Checking tables...")
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='sponsor_channels'"))
        columns = [row[0] for row in result.fetchall()]
        print(f"Current columns in 'sponsor_channels': {columns}")

if __name__ == "__main__":
    asyncio.run(migrate())
