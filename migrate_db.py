import asyncio
from sqlalchemy import text
from bot.database.session import engine

async def migrate():
    async with engine.begin() as conn:
        print("Checking for missing columns in 'users' table...")
        # Check users table
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users'
        """))
        existing_columns = [row[0] for row in result.fetchall()]
        
        if 'referral_count' not in existing_columns:
            print("Adding referral_count column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0"))
        
        if 'referral_code' not in existing_columns:
            print("Adding referral_code column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR UNIQUE"))
            
        if 'referred_by' not in existing_columns:
            print("Adding referred_by column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN referred_by BIGINT REFERENCES users(id)"))

        if 'joined_at' not in existing_columns:
            print("Adding joined_at column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))

        if 'language' not in existing_columns:
            print("Adding language column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR DEFAULT 'uz'"))

        if 'is_blocked' not in existing_columns:
            print("Adding is_blocked column...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE"))

        # Sponsor channels table migration
        print("Ensuring 'sponsor_channels' table exists...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sponsor_channels (
                id SERIAL PRIMARY KEY,
                channel_id VARCHAR UNIQUE NOT NULL,
                title VARCHAR NOT NULL,
                username VARCHAR,
                invite_link VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Check sponsor_channels columns
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='sponsor_channels'
        """))
        sponsor_columns = [row[0] for row in result.fetchall()]
        
        if 'invite_link' not in sponsor_columns:
            print("Adding invite_link column to sponsor_channels...")
            await conn.execute(text("ALTER TABLE sponsor_channels ADD COLUMN invite_link VARCHAR"))

        print("Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
