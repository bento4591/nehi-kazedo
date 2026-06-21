import os
import json
import time
import asyncio
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE: EMBEDHD V4.0 (DIRECT BREACH & HDS BYPASS) ---
TAG = "EMBEDHD"
OUTPUT_FILE = "embedhd.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"
BASE_URL = "https://embedhd.org"

# Properti Penyamaran (Spoofing) Ekstrem
SPOOF_REFERER = "https://exposestrat.com"
SPOOF_ORIGIN = "https://exposestrat.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"

EVENT_CACHE_FILE = f"{TAG}_event_v4.json"

def load_event_cache():
    if os.path.exists(EVENT_CACHE_FILE):
        try:
            with open(EVENT_CACHE_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {}

def save_event_cache(data):
    with open(EVENT_CACHE_FILE, "w") as f:
        json.dump(data, f)

async def extract_m3u8(context, url, index_num):
    page = await context.new_page()
    m3u8_link = None
    
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def handle_request(request):
        nonlocal m3u8_link
        if ".m3u8" in request.url:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        # Pendaratan udara langsung ke URL iframe rahasia (fetch.php)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000, referer=BASE_URL)
        
        for _ in range(15): # Waktu tunggu Playwright diperpanjang menjadi 15 detik
            if m3u8_link: break
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"    ⚠️ URL {index_num} kendala Playwright: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()
        
    return m3u8_link

async def get_events():
    now_ts = time.time()
    
    print("🔄 Menggempur pertahanan depan HTML EmbedHD...")
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": BASE_URL,
            "Accept": "text/html"
        }
        r = requests.get(BASE_URL, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f"❌ Gagal memindai HTML EmbedHD: {e}")
        return []

    events = []
    kategori_panjang = ["FIGHT", "WWE", "UFC", "MOTOR", "TENNIS", "BADMINTON", "VOLLEYBALL"]
    
    # Memburu kotak jadwal (score-row) secara langsung
    rows = soup.find_all('div', class_='score-row event-row')
    
    for row in rows:
        sport = row.get('data-cat', 'SPORT').upper()
        if sport == 'TV': continue
            
        ts_et = int(row.get('data-start', 0))
        if ts_et == 0: continue
        
        # Tentukan batas kedaluwarsa secara dinamis
        batas_waktu = 28800 if any(k in sport for k in kategori_panjang) else 14400

        # Filter masa lalu dan masa depan
        if now_ts > (ts_et + batas_waktu): continue
        if ts_et > (now_ts + 129600): continue
            
        home_team = row.get('data-home', '')
        away_team = row.get('data-away', '')
        raw_event_name = f"{home_team} - {away_team}" if home_team and away_team else row.get('data-title', 'Unknown Event')
        
        home_logo = row.get('data-home-logo', '')
        
        # Deteksi nama liga
        league_div = row.find('div', class_='league-cell')
        league_name = league_div.get('title', '').strip() if league_div else ""
        if league_name:
            raw_event_name = f"[{league_name}] {raw_event_name}"

        # 🛡️ TAKTIK "DIRECT BREACH" (Pencurian Kunci HDS dari HTML)
        event_link = ""
        hds_data = row.get('data-hds', '')
        if hds_data:
            match = re.search(r'\d+', hds_data)
            if match:
                # Rakit URL langsung ke jantung pemutar video
                event_link = f"https://embedhd.org/source/fetch.php?hd={match.group()}"
        else:
            # Fallback jika tidak ada data HDS
            onclick_attr = row.get('onclick', '')
            if 'location.href=' in onclick_attr:
                extracted = onclick_attr.split("location.href='")[1].split("'")[0]
                event_link = urljoin(BASE_URL, extracted)

        # Logika 1 Jam Pre-Match = LIVE
        waktu_ke_kickoff = ts_et - now_ts
        status_tag = "🔴 LIVE" if waktu_ke_kickoff <= 3600 else "⏳ UPCOMING"

        try:
            dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
            dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
            kickoff_tag = dt_wib.strftime("%H:%M WIB %d/%m/%Y")
        except Exception:
            kickoff_tag = "UNKNOWN"
            
        events.append({
            "sport": sport,
            "raw_title": raw_event_name,
            "kickoff_tag": kickoff_tag,
            "link": event_link,
            "status_tag": status_tag,
            "logo": home_logo
        })
            
    return events

async def scrape(browser):
    cached_urls = load_event_cache()
    current_playlist_urls = {}
    
    events = await get_events()
    
    if events:
        print(f"🎯 Ditemukan {len(events)} siaran dalam radar operasi.")
        context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
        
        for i, ev in enumerate(events, start=1):
            sport = ev["sport"]
            raw_name = ev["raw_title"]
            status_tag = ev["status_tag"]
            kickoff_tag = ev["kickoff_tag"]
            link = ev["link"]
            home_logo = ev["logo"]
            
            key = f"[{sport}] [{status_tag}] [{kickoff_tag}] {raw_name} ({TAG})"
            
            cached_entry = cached_urls.get(key)
            if cached_entry and cached_entry.get("url") and cached_entry["url"] != DUMMY_LINK:
                print(f"  ℹ️ {key} -> Menggunakan link dari database cache.")
                current_playlist_urls[key] = cached_entry
                continue
                
            if not link:
                print(f"  ⏳ {key} -> Link HDS belum tersedia (Bandar belum mengaktifkan)")
                url = DUMMY_LINK
            else:
                if status_tag == "⏳ UPCOMING":
                    print(f"  ⏳ {key} -> Link HDS terdeteksi, tapi jadwal masih > 1 Jam. (Menahan sadapan)")
                    url = DUMMY_LINK
                else:
                    print(f"\n⚡ Meluncurkan operasi penyadapan jalur udara: {key}")
                    url = await extract_m3u8(context, link, i)
                    if url:
                        print(f"      ✅ Sukses merampas M3U8: {url[:50]}...")
                    else:
                        print("      ⚠️ Gagal menembus pertahanan iframe, menggunakan cadangan.")
                        url = DUMMY_LINK
            
            entry = {
                "url": url,
                "logo": home_logo, 
                "id": "Live.Event.us",
                "link": link
            }
            
            cached_urls[key] = entry
            if url:
                current_playlist_urls[key] = entry
                
        active_keys = current_playlist_urls.keys()
        cleaned_cache = {k: v for k, v in cached_urls.items() if k in active_keys}
        save_event_cache(cleaned_cache)
        
    else:
        print("✅ Tidak ditemukan siaran baru dalam radar.")
        
    return current_playlist_urls

async def main():
    print("🚀 Memulai Operasi MABES ENTERPRISE: EmbedHD Engine V4.0 (Direct Breach & HDS Bypass)...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
        urls = await scrape(browser)
        await browser.close()
        
    print("\n🎯 Membangun berkas fisik M3U8 EmbedHD...")
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    playlist_lines = []
    for key, info in urls.items():
        if info.get("url"):
            group_title = "LIVE - EmbedHD" if "🔴 LIVE" in key else "UPCOMING - EmbedHD"
            
            extinf = f'#EXTINF:-1 tvg-id="{info["id"]}" tvg-logo="{info["logo"]}" group-title="{group_title}",{key}'
            playlist_lines.append(extinf)
            
            if info["url"] == DUMMY_LINK:
                playlist_lines.append(info["url"])
            else:
                playlist_lines.append(f'#EXTVLCOPT:http-referrer={SPOOF_REFERER}')
                playlist_lines.append(f'#EXTVLCOPT:http-origin={SPOOF_ORIGIN}')
                playlist_lines.append(f'#EXTVLCOPT:http-user-agent={USER_AGENT}')
                playlist_lines.append(info["url"])
            
            playlist_lines.append("")
            
    if playlist_lines:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + playlist_lines))
        print(f"🏁 BERHASIL! {len(playlist_lines)//6} Channel lintas olahraga dikunci ke {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada siaran aktif dalam radar saat ini."]))
        print("💀 Selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
