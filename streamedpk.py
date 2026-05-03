import asyncio
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
JSON_URL = "https://raw.githubusercontent.com/srhady/data/refs/heads/main/live_sports_playlist.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
OUTPUT_FILE = "StreamedPK_BoneTV.m3u8"

async def extract_m3u8(context, url, match_title):
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://embedsports.top/"

    # SUNTIKAN ANTI-DETEKSI
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # ALGORITMA TAB KILLER (DIPERBAIKI)
    # Sekarang hanya menembak mati "popup" liar, bukan halaman utama kita!
    async def handle_popup(popup):
        try:
            await popup.close()
            print("    [!] Iklan Pop-up liar berhasil dihancurkan.")
        except:
            pass
    page.on("popup", handle_popup)

    # RADAR PENYADAP NETWORK
    async def handle_request(request):
        nonlocal m3u8_link, dynamic_referer
        if ".m3u8" in request.url:
            print(f"    📡 [Radar M3U8]: {request.url[:80]}...") 
            if not m3u8_link or "index" in request.url or "master" in request.url:
                m3u8_link = request.url
                if "referer" in request.headers:
                    dynamic_referer = request.headers["referer"]

    page.on("request", handle_request)

    try:
        print(f"  🔍 Menyusup ke: {url}")
        
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000) 
        
        # CEK JUDUL HALAMAN 
        title = await page.title()
        print(f"    [Status] Judul Halaman: {title}")
        
        # KLIK GANDA BERJEDA TEPAT SASARAN
        for _ in range(3):
            if m3u8_link: 
                break
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(2000)

        # Tunggu hasil maksimal 10 detik
        for _ in range(10):
            if m3u8_link and "index" in m3u8_link: 
                break
            await page.wait_for_timeout(1000)

    except Exception as e:
        print(f"  ❌ Terkena Ranjau/Timeout: {e}")
    finally:
        page.remove_listener("request", handle_request)
        page.remove_listener("popup", handle_popup)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Tank Berat MABES ENTERPRISE (Xvfb GUI Mode V16.1)...")
    all_streams = []

    try:
        print("Membaca Peta Satelit (JSON)...")
        response = requests.get(JSON_URL, timeout=15)
        response.raise_for_status()
        matches = response.json()
    except Exception as e:
        print(f"❌ Gagal membaca JSON: {e}")
        return

    live_matches = [m for m in matches if "Live" in m.get("Match Status", "")]
    print(f"🎯 Ditemukan {len(live_matches)} pertandingan yang sedang LIVE.")

    if not live_matches:
        print("💀 Tidak ada pertandingan live saat ini.")
    else:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
            
            for match in live_matches:
                league = match.get("League", "Sports")
                title = match.get("Match Title", "Live Match")
                poster = match.get("Match Poster", "")
                
                display_title = f"[🔴 LIVE] [{league}] {title} [Seru]"
                streams = match.get("Streams", [])
                
                hd_streams = [s for s in streams if str(s.get("Quality", "")).upper() == "HD"]
                
                # Eksekusi maksimal 1 stream HD pertama per jadwal
                for stream in hd_streams[:1]:
                    embed_url = stream.get("Embed_URL")
                    source_name = stream.get("Source", "unknown").upper()
                    lang = stream.get("Language", "")
                    
                    if embed_url:
                        tag_title = f"{display_title} - HD {lang} ({source_name})".strip()
                        m3u8_url, dynamic_referer = await extract_m3u8(context, embed_url, tag_title[:65])
                        
                        if m3u8_url:
                            print(f"  ✅ HARTA DIDAPAT: {m3u8_url[:60]}...")
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{poster}" group-title="BONE TV - StreamedPK",{tag_title}',
                                f'#EXTVLCOPT:http-referrer={dynamic_referer}',
                                f'#EXTVLCOPT:http-origin={dynamic_referer.strip("/")}',
                                f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                                m3u8_url,
                                ''
                            ])
                        else:
                            print("  ⚠️ Gagal mendapatkan M3U8.")

            await browser.close()

    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    if all_streams:
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link berhasil dikunci ke {OUTPUT_FILE}.")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada stream yang berhasil diekstrak saat ini."]))
        print("\n💀 Operasi selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
