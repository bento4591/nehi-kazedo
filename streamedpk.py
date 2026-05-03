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
    dynamic_referer = "https://embedsports.top/" # Default referer

    # RADAR PENYADAP NETWORK KHUSUS M3U8 & REFERER
    async def handle_request(request):
        nonlocal m3u8_link, dynamic_referer
        
        # Incar link dari modifiles / secure yang berakhiran m3u8
        if ".m3u8" in request.url and ("secure" in request.url or "modifiles" in request.url):
            # Prioritaskan index.m3u8 (Master playlist) daripada mono.ts (Audio)
            if "index" in request.url or "master" in request.url or not m3u8_link:
                m3u8_link = request.url
                
                # CURI REFERER ASLI DARI HEADER MUSUH (Contoh: https://pooembed.eu/)
                req_headers = request.headers
                if "referer" in req_headers:
                    dynamic_referer = req_headers["referer"]

    page.on("request", handle_request)

    try:
        print(f"  🔍 Menyusup ke: {match_title}")
        # Tunggu sampai Iframe pihak ketiga (pooembed) selesai dimuat
        await page.goto(url, wait_until="load", timeout=35000)
        await page.wait_for_timeout(3000)
        
        # TAKTIK KLIK BRUTAL TEMBUS IFRAME
        # 1. Klik koordinat layar (menembus iklan popup dasar)
        for _ in range(2):
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(1000)
            
        # 2. Paksa klik di dalam setiap Iframe yang ditemukan
        for frame in page.frames:
            try:
                # Cari tombol play atau klik seluruh area body iframe
                await frame.locator("body").click(force=True, timeout=1000)
            except:
                pass

        # Pantau radar selama maksimal 15 detik setelah klik
        for _ in range(15):
            if m3u8_link and "index" in m3u8_link:
                break # Jika sudah dapat index.m3u8, langsung tarik mundur pasukan (Efisien)
            await page.wait_for_timeout(1000)

    except Exception as e:
        print(f"  ❌ Gagal menembus pertahanan: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Tank Berat MABES ENTERPRISE (StreamedPK / PooEmbed Edition)...")
    all_streams = []

    # 1. BACA DATA JSON
    try:
        print("Membaca Peta Satelit (JSON)...")
        response = requests.get(JSON_URL, timeout=15)
        response.raise_for_status()
        matches = response.json()
    except Exception as e:
        print(f"❌ Gagal membaca JSON: {e}")
        return

    # 2. FILTER HANYA LIVE
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
                
                display_title = f"[🔴 LIVE] [{league}] {title} [Seru]"
                streams = match.get("Streams", [])
                
                # Ambil maksimal 2 stream pertama
                for stream in streams[:2]:
                    embed_url = stream.get("Embed_URL")
                    quality = stream.get("Quality", "HD")
                    lang = stream.get("Language", "")
                    
                    if embed_url:
                        tag_title = f"{display_title} - {quality} {lang}".strip()
                        
                        # Ekstraksi mengembalikan 2 nilai (Link M3U8 & Referer Asli)
                        m3u8_url, dynamic_referer = await extract_m3u8(context, embed_url, tag_title[:60])
                        
                        if m3u8_url:
                            print(f"  ✅ HARTA DIDAPAT: {m3u8_url[:60]}...")
                            print(f"  🔑 Menggunakan Referer Rahasia: {dynamic_referer}")
                            
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{poster}" group-title="BONE TV - StreamedPK",{tag_title}',
                                f'#EXTVLCOPT:http-referrer={dynamic_referer}', # <--- Referer Dinamis!
                                f'#EXTVLCOPT:http-origin={dynamic_referer.strip("/")}',
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
