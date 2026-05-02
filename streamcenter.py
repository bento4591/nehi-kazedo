import asyncio
import json
import requests
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
API_URL = "https://backend.streamcenter.live/api/Parties?pageNumber=1&pageSize=50"
ORIGIN = "https://streamcenter.live"
REFERER = "https://streamcenter.live/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = "Streamcenter_BoneTV.m3u8"

async def extract_m3u8(context, url, match_title):
    """Fungsi Tank Berat: Mendobrak halaman PHP dan menyadap M3U8 dari mainstreams.pro"""
    page = await context.new_page()
    m3u8_link = None

    # Pasang Radar Network Khusus Streamcenter
    def handle_request(request):
        nonlocal m3u8_link
        # Tangkap jika ada request ke mainstreams.pro yang berakhiran .m3u8 beserta tokennya
        if "mainstreams.pro/hls" in request.url and ".m3u8" in request.url and not m3u8_link:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        print(f"  🔍 Menerjunkan pasukan ke: {match_title}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Tunggu loading Javascript musuh untuk memanggil decrypt.php
        await page.wait_for_timeout(5000) 
        
        # Tembakan Brutal: Klik di tengah layar jaga-jaga jika butuh interaksi Play
        await page.mouse.click(640, 360)
        await page.wait_for_timeout(3000)
        await page.mouse.click(640, 360) # Klik kedua untuk menembus overlay iklan jika ada
        
        # Tunggu sejenak agar M3U8 keluar dari sarangnya
        await page.wait_for_timeout(5000) 

    except Exception as e:
        print(f"  ❌ Gagal memuat halaman: {e}")
    finally:
        page.remove_listener("request", handle_request)
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

    # Waktu saat ini dalam UTC (Karena API Streamcenter menggunakan UTC)
    now_utc = datetime.now(timezone.utc)
    
    target_matches = []
    
    if isinstance(data, list):
        for item in data:
            try:
                # Parsing string waktu dari API "2026-05-02T15:00:00"
                begin_dt = datetime.strptime(item.get("beginPartie"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                end_dt = datetime.strptime(item.get("endPartie"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                
                # Toleransi: Mulai menyadap 30 menit sebelum Kick-off sampai pertandingan selesai
                if (begin_dt - timedelta(minutes=30)) <= now_utc <= end_dt:
                    target_matches.append((item, begin_dt))
            except Exception:
                continue

    print(f"🎯 Ditemukan {len(target_matches)} target potensial (LIVE & Segera Main).")

    if not target_matches:
        print("💀 Tidak ada pertandingan live saat ini.")
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
                # Format Judul
                league_text = ""
                if item.get("description") and " - " in item.get("description"):
                    league_text = f"[{item['description'].split(' - ')[0]}] "
                
                # Konversi jam Kick-off ke WIB
                jkt_time = begin_dt.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")
                display_title = f"[🔴 LIVE {jkt_time}] {league_text}{item.get('name', 'Live Match')} [Seru]"
                
                logo = item.get("logoTeam1", "")
                raw_url = item.get("videoUrl", "")
                
                # Bersihkan URL dari tag <English
                clean_url = raw_url.split("<")[0] if raw_url else None
                
                if clean_url:
                    m3u8_url = await extract_m3u8(context, clean_url, display_title[:50])
                    
                    if m3u8_url:
                        print(f"  ✅ HARTA DIDAPAT: {m3u8_url}")
                        all_streams.append([
                            f'#EXTINF:-1 tvg-logo="{logo}" group-title="BONE TV - Streamcenter",{display_title}',
                            f'#EXTVLCOPT:http-referrer={REFERER}',
                            f'#EXTVLCOPT:http-origin={ORIGIN}',
                            f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                            m3u8_url,
                            ''
                        ])
                    else:
                        print("  ⚠️ M3U8 tidak tertembus (Mungkin enkripsi gagal atau stream mati).")

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
