import asyncio
import yt_dlp
import os

async def test_info():
    url = "https://www.instagram.com/reel/DVZHvpXDcCb/"
    
    print(f"--- Testing with cookiesfrombrowser(chrome) ---")
    ydl_opts = {
        'quiet': False,
        'no_warnings': False,
        'cookiesfrombrowser': ('chrome', )
    }
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"SUCCESS! Title: {info.get('title')}")
            return
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_info())
