import asyncio
import yt_dlp
import os

async def test_info():
    url = "https://www.instagram.com/reel/DVZHvpXDcCb/"
    cookies_dir = "cookies"
    
    cookie_files = [os.path.join(cookies_dir, f) for f in os.listdir(cookies_dir) if f.endswith(".txt")]
    
    for cookie_file in cookie_files:
        print(f"\n--- Testing with {cookie_file} (New Headers) ---")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookie_file,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'referer': 'https://www.instagram.com/',
            'http_headers': {
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                print(f"SUCCESS! Title: {info.get('title')}")
                return
        except Exception as e:
            print(f"Error: {str(e)[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_info())
