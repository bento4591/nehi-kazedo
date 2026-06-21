import os
import json
import time
import asyncio
import requests
from urllib.parse import urljoin
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE: EMBEDHD ---
TAG = "EMBEDHD"
OUTPUT_FILE = "embedhd.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"
BASE_URL = "https://embedhd.org"

# Sistem Cache Mandiri (Pengganti modul 'utils')
API_CACHE_FILE = f"{TAG}_api_cache.json"
EVENT_CACHE_FILE = f"{TAG}_event_cache.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"

def fix_league(s: str) -> str:
    return " ".join(x.capitalize() for x in s.split()) if len(s) > 5 else s.upper()

def load_api_cache():
    if os.path.exists(API_CACHE_FILE):
        if time.time() - os.path.getmtime(API_CACHE_FILE) < 28800: # Valid 8 Jam
            try:
                with open(API_CACHE_FILE, "r") as f:
                    return json.load(f)
            except: pass
    return None

def save_api_cache(data):
    with open(API_CACHE_FILE, "w") as f:
        json.dump(data, f)

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
    
    # Bypass deteksi bot
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def handle_request(request):
        nonlocal m3u8_link
        if ".m3u8" in request.url:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000, referer=BASE_URL)
        
        # Taktik menunggu M3U8 (Maksimal 10 detik)
        for _ in range(10):
            if m3u8_link: break
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"    ⚠️ URL {index_num} error: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()
        
    return m3u8_link

async def get_events(cached_keys):
    now_ts = time.time()
    api_data = load_api_cache()
    
    if not api_data:
        print("🔄 Mengunduh data API baru dari server...")
        try:
            r = requests.get(urljoin(BASE_URL, "api-event.php"), timeout=15)
            api_data = r.json()
            api_data["timestamp"] = now_ts
            save_api_cache(api_data)
        except Exception as e:
            print(f"❌ Gagal mengambil API EmbedHD: {e}")
            return []

    events = []
    
    for info in api_data.get("days", []):
        for event in info.get("items", []):
            event_league = event.get("league", "")
            if event_league == "channel tv":
                continue

            ts_et = int(event.get("ts_et", 0))
            
            # Filter jadwal (-3 Jam ke belakang sampai +30 Menit ke depan)
            if not ((now_ts - 10800) <= ts_et <= (now_ts + 1800)):
                continue

            sport = fix_league(event_league)
            raw_event_name = event.get("title", "Unknown Event")

            # Konversi Zona Waktu & Penetapan Status
            dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
            dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
            kickoff_wib = dt_wib.strftime("%H:%M WIB")
            
            if datetime.now(timezone.utc) >= dt_utc:
                status_tag = "🔴 LIVE"
            else:
                status_tag = "⏳ UPCOMING"

            formatted_event_name = f"[{status_tag}] [{kickoff_wib}] {raw_event_name}"
            
            # Anti-Duplikat Cache
            match_suffix = f"{raw_event_name} ({TAG})"
            if any(c_key.endswith(match_suffix) for c_key in cached_keys):
                continue
                
            event_streams = event.get("streams", [])
            if not event_streams: continue
            
            event_link = event_streams[0].get("link")
            if not event_link: continue
                
            events.append({
                "sport": sport,
                "event": formatted_event_name,
                "link": event_link,
                "timestamp": now_ts,
                "status_tag": status_tag
            })
            
    return events

async def scrape(browser):
    cached_urls = load_event_cache()
    urls = {k: v for k, v in cached_urls.items() if v.get("url")}
    
    print(f"📦 Memuat {len(urls)} event dari Cache lokal.")
    
    events = await get_events(list(cached_urls.keys()))
    
    if events:
        print(f"🎯 Memproses {len(events)} URL baru...")
        context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
        
        for i, ev in enumerate(events, start=1):
            link = ev["link"]
            status_tag = ev["status_tag"]
            
            # TAKTIK PARKING: Hemat Server, Bypass Playwright jika Upcoming
            if status_tag == "⏳ UPCOMING":
                print(f"  ⏳ {ev['event']} -> Menanam Link Dummy")
                url = DUMMY_LINK
            else:
                print(f"\n⚡ Mengeksekusi LIVE: {ev['event']}")
                print(f"    📡 Menyadap Player...")
                url = await extract_m3u8(context, link, i)
                if url:
                    print(f"      ✅ Berhasil: {url[:40]}...")
                
            sport = ev["sport"]
            event_name = ev["event"]
            key = f"[{sport}] {event_name} ({TAG})"
            
            entry = {
                "url": url,
                "logo": "", 
                "id": "Live.Event.us",
                "link": link
            }
            
            cached_urls[key] = entry
            if url:
                urls[key] = entry
                
        save_event_cache(cached_urls)
    else:
        print("✅ Tidak ada jadwal baru yang perlu disadap.")
        
    return urls

async def main():
    print("🚀 Memulai Operasi MABES ENTERPRISE: EmbedHD Standalone Scraper...")
    
    # Mulai Operasi Scraper
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
        urls = await scrape(browser)
        await browser.close()
        
    # Perakitan File M3U8
    print("\n🎯 Membangun file M3U8 EmbedHD...")
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
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
                # Tambahkan Referer agar anti-blokir
                playlist_lines.append(f'{info["url"]}|Referer={BASE_URL}/')
            
            playlist_lines.append("")
            
    if playlist_lines:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + playlist_lines))
        print(f"🏁 SELESAI! Berhasil mengunci {len(playlist_lines)//3} link ke {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada siaran yang aktif saat ini."]))
        print("💀 Operasi selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
