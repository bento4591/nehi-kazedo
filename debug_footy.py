import asyncio
from playwright.async_api import async_playwright

# 🛡️ INJEKSI JUBAH GAIB MABES
STEALTH_SCRIPTS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""

async def main():
    async with async_playwright() as p:
        # ⚠️ KUNCI UTAMA: HEADLESS = FALSE (Browser Berwujud)
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        await context.add_init_script(STEALTH_SCRIPTS)
        page = await context.new_page()
        
        print("[TEST] Membuka playerdee.top dengan Chrome Berwujud (Headed) + Layar Virtual...")
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
        
        # Cloudflare butuh waktu memproses puzzle keamanan di latar belakang
        await asyncio.sleep(15) 
        
        if m3u8_found:
            print(f"\n[✅ SUKSES BESAR] Tembus! Cloudflare berhasil dihancurkan! M3U8: {m3u8_found[0]}")
        else:
            print(f"\n[❌ GAGAL] Masih tertahan. Judul halaman: {title}")
            body = await page.evaluate("document.body.innerText.substring(0, 500)")
            print(f"[KONTEN HTML]:\n{body}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
