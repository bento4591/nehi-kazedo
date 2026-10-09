import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Meluncurkan browser dengan argumen siluman
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled", # Hapus tanda bot Playwright
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        
        # Injeksi JS Stealth Tingkat Lanjut
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        
        print("[TEST] Membuka playerdee.top...")
        m3u8_found = []
        page.on("request", lambda r: m3u8_found.append(r.url) if ".m3u8" in r.url else None)
        
        try:
            # Gunakan pertandingan Live yang Kapten berikan (Shanghai Rolex Masters)
            await page.goto(
                "https://playerdee.top/alpha/shanghai-rolex-masters/2614",
                wait_until="domcontentloaded",
                timeout=30000
            )
        except Exception as e:
            print(f"[ERROR] Gagal memuat halaman: {e}")
        
        title = await page.title()
        print(f"[TITLE]: {title}")
        
        # Tunggu 10 detik membiarkan JS berjalan
        await asyncio.sleep(10)
        
        if m3u8_found:
            print(f"\n[✅ SUKSES] Cloudflare berhasil ditembus! M3U8 tertangkap: {m3u8_found[0]}")
        else:
            print(f"\n[❌ GAGAL] Tidak ada M3U8 yang lewat. Judul halaman: {title}")
            # Dump HTML sedikit untuk melihat apa yang memblokir
            body = await page.evaluate("document.body.innerText.substring(0, 300)")
            print(f"[KONTEN HTML]:\n{body}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
