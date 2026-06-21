import os
import json
import time
import asyncio
import requests
import re
from urllib.parse import urljoin
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE: EMBEDHD V3.5 (HDS BYPASS & 1-HR PRE-MATCH) ---
TAG = "EMBEDHD"
OUTPUT_FILE = "embedhd.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"
BASE_URL = "https://embedhd.org"

# Properti Penyamaran (Spoofing) Ekstrem
SPOOF_REFERER = "https://exposestrat.com"
SPOOF_ORIGIN = "https://exposestrat.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"

# File database cache lokal 
API_CACHE_FILE = f"{TAG}_api_v3.json"
EVENT_CACHE_FILE = f"{TAG}_event_v3.json"

def fix_league(s: str) -> str:
    return " ".join(x.capitalize() for x in s.split()) if len(s) > 5 else s.upper()

def load_api_cache():
    if os.path.exists(API_CACHE_FILE):
        if time.time() - os.path.getmtime(API_CACHE_FILE) < 1800: # Refresh API setiap 30 menit
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
    
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def handle_request(request):
        nonlocal m3u8_link
        if ".m3u8" in request.url:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        # Meluncur langsung ke url bypass iframe atau halaman watch
        await page.goto(url, wait_until="domcontentloaded", timeout=15000, referer=BASE_URL)
        
        for _ in range(10):
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
    api_data = load_api_cache()
    
    if not api_data:
        print("🔄 Menghubungi server pusat EmbedHD untuk memuat jadwal segar...")
        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Referer": BASE_URL,
                "Accept": "application/json"
            }
            r = requests.get(urljoin(BASE_URL, "api-event.php"), headers=headers, timeout=15)
            r.raise_for_status()
            api_data = r.json()
            save_api_cache(api_data)
        except Exception as e:
            print(f"❌ Gagal menembus API EmbedHD: {e}")
            return []

    events = []
    
    kategori_panjang = ["FIGHT", "WWE", "UFC", "MOTOR", "TENNIS", "BADMINTON", "VOLLEYBALL"]
    
    for info in api_data.get("days", []):
        for event in info.get("items", []):
            event_league = event.get("league", "")
            if event_league == "channel tv":
                continue

            ts_et = int(event.get("ts_et", 0))
            sport = fix_league(event_league)
            sport_upper = sport.upper()
            
            # Tentukan batas waktu kedaluwarsa secara dinamis
            if any(k in sport_upper for k in kategori_panjang):
                batas_waktu = 28800  # 8 Jam
            else:
                batas_waktu = 14400  # 4 Jam

            # 🛡️ FILTER KEDALUWARSA & MASA DEPAN
            if now_ts > (ts_et + batas_waktu):
                continue
            if ts_et > (now_ts + 129600):
                continue

            raw_event_name = event.get("title", "Unknown Event")

            try:
                dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                kickoff_tag = dt_wib.strftime("%H:%M WIB %d/%m/%Y")
            except Exception:
                kickoff_tag = "UNKNOWN"
                
            # 🛡️ PENDETEKSI LINK STANDAR
            event_streams = event.get("streams", [])
            event_link = event_streams[0].get("link") if event_streams else ""

            # 🛡️ TAKTIK "BYPASS GENERATOR" (Untuk laga besar/World Cup yang pakai modal iframe)
            if not event_link:
                hds_data = event.get("hds")
                if hds_data:
                    # Kadang berbentuk list [71, 85], kadang string "71,85" atau "[71]"
                    if isinstance(hds_data, list) and len(hds_data) > 0:
                        event_link = f"https://embedhd.org/source/fetch.php?hd={hds_data[0]}"
                    elif isinstance(hds_data, str):
                        match = re.search(r'\d+', hds_data) # Cari angka pertama saja
                        if match:
                            event_link = f"https://embedhd.org/source/fetch.php?hd={match.group()}"

            # 🛡️ LOGIKA PRE-MATCH (1 Jam Sebelum Kickoff langsung tancap LIVE)
            waktu_ke_kickoff = ts_et - now_ts
            if waktu_ke_kickoff <= 3600:
                status_tag = "🔴 LIVE"
            else:
                status_tag = "⏳ UPCOMING"

            try:
                home_team = raw_event_name.split(" - ")[0].strip()
                home_logo = f"https://embedhd.org/images/team-logos/{home_team}.png".replace(" ", "%20")
            except Exception:
                home_logo = ""
                
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
                print(f"  ⏳ {key} -> Menanam Link Dummy (Bandar belum mengaktifkan stream/HDS)")
                url = DUMMY_LINK
            else:
                if status_tag == "⏳ UPCOMING":
                    print(f"  ⏳ {key} -> Link/HDS ada, tapi kickoff masih > 1 Jam. Pasang Dummy.")
                    url = DUMMY_LINK
                else:
                    print(f"\n⚡ Meluncurkan operasi penyadapan LIVE / PRE-MATCH: {key}")
                    url = await extract_m3u8(context, link, i)
                    if url:
                        print(f"      ✅ Sukses mengunci M3U8: {url[:50]}...")
                    else:
                        print("      ⚠️ Gagal menyadap M3U8, memasang Link Dummy sebagai cadangan.")
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
                
        # Membersihkan cache dari siaran yang sudah usang
        active_keys = current_playlist_urls.keys()
        cleaned_cache = {k: v for k, v in cached_urls.items() if k in active_keys}
        save_event_cache(cleaned_cache)
        
    else:
        print("✅ Tidak ditemukan siaran baru dalam radar.")
        
    return current_playlist_urls

async def main():
    print("🚀 Memulai Operasi MABES ENTERPRISE: EmbedHD Engine V3.5 (HDS Bypass & Pre-Match)...")
    
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
                # 🛡️ INJEKSI SPOOFING KELAS BERAT (EXTVLCOPT)
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
