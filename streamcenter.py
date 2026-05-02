import asyncio
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
API_URL = "https://backend.streamcenter.live/api/Parties?pageNumber=1&pageSize=500"
ORIGIN = "https://streamcenter.live"
REFERER = "https://streamcenter.live/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = "Streamcenter_BoneTV.m3u8"

async def extract_m3u8(context, url, match_title):
    """Taktik Baru: Menyadap Respons dari decrypt.php tanpa menunggu video berputar"""
    page = await context.new_page()
    m3u8_link = None

    # RADAR PENYADAP RESPONS
    async def handle_response(response):
        nonlocal m3u8_link
        # Jika musuh memanggil decrypt.php, kita baca isi balasannya!
        if "decrypt.php" in response.url:
            try:
                text = await response.text()
                if "mainstreams.pro" in text and ".m3u8" in text:
                    m3u8_link = text.strip()
            except:
                pass
        # Jaga-jaga jika m3u8 dipanggil langsung tanpa decrypt
        elif "mainstreams.pro/hls" in response.url and ".m3u8" in response.url and not m3u8_link:
            m3u8_link = response.url

    page.on("response", handle_response)

    try:
        print(f"  🔍 Menerjunkan pasukan ke: {match_title}")
        # Masuk ke halaman dan biarkan Javascript musuh meracik kuncinya
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Pantau terus selama 10 detik, jika radar menangkap M3U8, langsung hentikan pencarian (Efisien)
        for _ in range(10):
            if m3u8_link:
                break
            await page.wait_for_timeout(1000)
            
        # Tembakan Pancingan (jika dalam 10 detik belum muncul)
        if not m3u8_link:
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(3000)

    except Exception as e:
        print(f"  ❌ Gagal memuat halaman: {e}")
    finally:
        page.remove_listener("response", handle_response)
        await page.close()

    return m3u8_link

async def main():
    print("🚀 Memulai Tank Berat MABES ENTERPRISE (Streamcenter Edition)...")
    all_streams = []

    # 1. AMBIL JADWAL DARI API
    try:
        headers = {"User-Agent": USER_AGENT, "Origin": ORIGIN, "Referer": REFERER}
        print("Membaca Radar API Streamcenter...")
        response = requests.get(API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ Gagal membaca API: {e}")
        return

    now_utc = datetime.now(timezone.utc)
    target_matches = []
    
    if isinstance(data, list):
        for item in data:
            try:
                begin_dt = datetime.strptime(item.get("beginPartie"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                end_dt = datetime.strptime(item.get("endPartie"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                
                # Toleransi Waktu Diperlebar: -6 Jam sebelum main, sampai +2 Jam setelah selesai
                if (begin_dt - timedelta(hours=6)) <= now_utc <= (end_dt + timedelta(hours=2)):
                    target_matches.append((item, begin_dt))
            except Exception:
                continue

    print(f"🎯 Ditemukan {len(target_matches)} target potensial (LIVE & UPCOMING dekat).")

    if not target_matches:
        print("💀 Tidak ada pertandingan dalam jangkauan radar waktu.")
    else:
        # 2. TERJUNKAN PLAYWRIGHT UNTUK EKSTRAKSI
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=USER_AGENT,
                extra_http_headers={"Origin": ORIGIN, "Referer": REFERER}
            )
            
            for item, begin_dt in target_matches:
                league_text = ""
                if item.get("description") and " - " in item.get("description"):
                    league_text = f"[{item['description'].split(' - ')[0]}] "
                
                jkt_time = begin_dt.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")
                display_title = f"[🔴 LIVE {jkt_time}] {league_text}{item.get('name', 'Live Match')} [Seru]"
                
                logo = item.get("logoTeam1", "")
                raw_url = item.get("videoUrl", "")
                clean_url = raw_url.split("<")[0] if raw_url else None
                
                # Hanya buru link embed
                if clean_url and "embed" in clean_url:
                    m3u8_url = await extract_m3u8(context, clean_url, display_title[:60])
                    
                    if m3u8_url:
                        print(f"  ✅ HARTA DIDAPAT: {m3u8_url[:60]}...")
                        all_streams.append([
                            f'#EXTINF:-1 tvg-logo="{logo}" group-title="BONE TV - Streamcenter",{display_title}',
                            f'#EXTVLCOPT:http-referrer={REFERER}',
                            f'#EXTVLCOPT:http-origin={ORIGIN}',
                            f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                            m3u8_url,
                            ''
                        ])
                    else:
                        print("  ⚠️ Gagal menyadap M3U8.")

            await browser.close()

    # 3. MENYIMPAN HASIL
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    if all_streams:
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link Streamcenter berhasil dikunci ke {OUTPUT_FILE}.")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada stream yang berhasil diekstrak saat ini."]))
        print("\n💀 Operasi selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
