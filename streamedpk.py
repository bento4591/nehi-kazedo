import asyncio
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
JSON_URL = "https://raw.githubusercontent.com/srhady/data/refs/heads/main/live_sports_playlist.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = "StreamedPK_BoneTV.m3u8"

async def extract_m3u8(context, url, match_title):
    page = await context.new_page()
    m3u8_link = None

    # RADAR PENYADAP NETWORK
    async def handle_request(request):
        nonlocal m3u8_link
        # Tangkap link M3U8 yang mengandung kata kunci 'secure' atau 'm3u8'
        if ".m3u8" in request.url and ("secure" in request.url or "modifiles" in request.url):
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        print(f"  🔍 Menyusup ke: {match_title}")
        await page.goto(url, wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Tembakan Pancingan: Klik Brutal di tengah layar untuk memicu tombol Play
        # Lakukan 2-3 kali untuk menembus lapisan iklan popup jika ada
        for _ in range(3):
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(1500)

        # Pantau radar selama maksimal 10 detik setelah klik
        for _ in range(10):
            if m3u8_link:
                break
            await page.wait_for_timeout(1000)

    except Exception as e:
        print(f"  ❌ Gagal menembus pertahanan: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()

    return m3u8_link

async def main():
    print("🚀 Memulai Tank Berat MABES ENTERPRISE (Streamed.pk Edition)...")
    all_streams = []

    # 1. BACA DATA JSON DARI GITHUB KAPTEN
    try:
        print("Membaca Peta Satelit (JSON)...")
        response = requests.get(JSON_URL, timeout=15)
        response.raise_for_status()
        matches = response.json()
    except Exception as e:
        print(f"❌ Gagal membaca JSON: {e}")
        return

    # 2. FILTER HANYA YANG BERSTATUS LIVE
    live_matches = [m for m in matches if "Live" in m.get("Match Status", "")]
    print(f"🎯 Ditemukan {len(live_matches)} pertandingan yang sedang LIVE.")

    if not live_matches:
        print("💀 Tidak ada pertandingan live saat ini.")
    else:
        # 3. TERJUNKAN PLAYWRIGHT
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=USER_AGENT
            )
            
            for match in live_matches:
                league = match.get("League", "Sports")
                title = match.get("Match Title", "Live Match")
                poster = match.get("Match Poster", "")
                
                # Rakit Judul
                display_title = f"[🔴 LIVE] [{league}] {title} [Seru]"
                
                streams = match.get("Streams", [])
                # Ambil maksimal 2 stream pertama saja per pertandingan agar tidak kelamaan
                for stream in streams[:2]:
                    embed_url = stream.get("Embed_URL")
                    quality = stream.get("Quality", "HD")
                    lang = stream.get("Language", "")
                    
                    if embed_url:
                        tag_title = f"{display_title} - {quality} {lang}".strip()
                        m3u8_url = await extract_m3u8(context, embed_url, tag_title[:60])
                        
                        if m3u8_url:
                            print(f"  ✅ HARTA DIDAPAT: {m3u8_url[:60]}...")
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{poster}" group-title="BONE TV - StreamedPK",{tag_title}',
                                f'#EXTVLCOPT:http-referrer=https://embedsports.top/',
                                f'#EXTVLCOPT:http-origin=https://embedsports.top',
                                f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                                m3u8_url,
                                ''
                            ])
                        else:
                            print("  ⚠️ Gagal mendapatkan M3U8 (Video mati atau klik meleset).")

            await browser.close()

    # 4. MENYIMPAN HASIL
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
