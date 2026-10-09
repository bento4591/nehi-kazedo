import asyncio
from playwright.async_api import async_playwright

# 🛡️ INJEKSI JUBAH GAIB MABES (Pengganti playwright-stealth)
STEALTH_SCRIPTS = """
    // 1. Sembunyikan identitas Webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    
    // 2. Palsukan keberadaan Chrome
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };
    
    // 3. Palsukan Plugin & Bahasa layaknya browser manusia
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    
    // 4. Bobol sistem deteksi Permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled", # Hapus tanda bot
                "--disable-web-security"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        
        # 🛡️ PASANG JUBAH GAIB DI TINGKAT BROWSER
        await context.add_init_script(STEALTH_SCRIPTS)
        
        page = await context.new_page()
        
        print("[TEST] Membuka playerdee.top dengan Jubah Gaib MABES (Inline Stealth)...")
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
        
        # Tunggu 12 detik membiarkan Cloudflare memproses simulasi browser
        await asyncio.sleep(12) 
        
        if m3u8_found:
            print(f"\n[✅ SUKSES] Tembus! Cloudflare berhasil ditipu! M3U8: {m3u8_found[0]}")
        else:
            print(f"\n[❌ GAGAL] Masih tertahan. Judul halaman: {title}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
