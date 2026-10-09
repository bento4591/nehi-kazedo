# debug_footy.py - JALANKAN DI GITHUB ACTIONS DULU, LAPOR HASILNYA
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        
        # Injeksi stealth
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        
        print("[TEST] Membuka playerdee.top...")
        m3u8_found = []
        page.on("request", lambda r: m3u8_found.append(r.url) if ".m3u8" in r.url else None)
        
        await page.goto(
            "https://playerdee.top/alpha/shanghai-rolex-masters/2614",
            wait_until="domcontentloaded",
            timeout=30000
        )
        
        title = await page.title()
        print(f"[TITLE]: {title}")
        
        # Tunggu 10 detik
        await asyncio.sleep(10)
        
        if m3u8_found:
            print(f"[✅ SUKSES] M3U8 tertangkap: {m3u8_found[0]}")
        else:
            print(f"[❌ GAGAL] Tidak ada M3U8. Judul halaman: {title}")
            # Dump 300 char pertama
            body = await page.evaluate("document.body.innerText.substring(0, 300)")
            print(f"[KONTEN]: {body}")
        
        await browser.close()

asyncio.run(main())
