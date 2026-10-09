import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # 🛡️ PASANG JUBAH GAIB DI HALAMAN INI
        await stealth_async(page)
        
        print("[TEST] Membuka playerdee.top dengan Jubah Gaib (playwright-stealth)...")
        m3u8_found = []
        page.on("request", lambda r: m3u8_found.append(r.url) if ".m3u8" in r.url else None)
        
        try:
            await page.goto(
                "https://playerdee.top/alpha/shanghai-rolex-masters/2614",
                wait_until="domcontentloaded",
                timeout=30000
            )
        except Exception as e:
            print(f"[ERROR] Halaman gagal dimuat: {e}")
            
        title = await page.title()
        print(f"[TITLE]: {title}")
        
        await asyncio.sleep(12) # Tunggu 12 detik membiarkan Cloudflare memproses
        
        if m3u8_found:
            print(f"\n[✅ SUKSES] Tembus! Cloudflare berhasil ditipu! M3U8: {m3u8_found[0]}")
        else:
            print(f"\n[❌ GAGAL] Masih tertahan. Judul halaman: {title}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
