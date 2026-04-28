import asyncio
import re
import httpx
from urllib.parse import urljoin
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from collections import defaultdict

# --- KONFIGURASI DASAR ---
TAG = "STRMSGATE"
BASE_URL = "https://streamsgates.io"
OUTPUT_FILE = Path("streamsgate.m3u8")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

SPORTS_TO_SCRAPE = ["mlb", "nba", "nhl", "soccer", "ufc"]

TV_INFO = {
    "soccer": ("Soccer.Dummy.us", "https://i.postimg.cc/HsWHFvV0/Soccer.png", "Soccer"),
    "mlb": ("MLB.Baseball.Dummy.us", "https://i.postimg.cc/FsFmwC7K/Baseball3.png", "MLB"),
    "nba": ("NBA.Basketball.Dummy.us", "https://i.postimg.cc/jdqKB3LW/Basketball-2.png", "NBA"),
    "nfl": ("Football.Dummy.us", "https://i.postimg.cc/tRNpSGCq/Maxx.png", "NFL"),
    "nhl": ("NHL.Hockey.Dummy.us", "https://i.postimg.cc/mgMRQ7FR/nhl-logo-png-seeklogo-534236.png", "NHL"),
    "ufc": ("UFC.Fight.Pass.Dummy.us", "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png", "UFC"),
    "misc": ("Sports.Dummy.us", "https://i.postimg.cc/qMm0rc3L/247.png", "Random Events")
}

def get_tv_data(sport_name):
    key = sport_name.lower().strip()
    return TV_INFO.get(key, TV_INFO["misc"])

def format_event_name(t1: str, t2: str) -> str:
    if t1 == "RED ZONE": return "NFL RedZone"
    if t1 == "TBD": return "TBD"
    return f"{t1.strip()} vs {t2.strip()}"

def parse_universal_time(time_val):
    """Mesin penerjemah berbagai format waktu kacau dari API menjadi format UTC yang solid"""
    try:
        # Jika formatnya angka UNIX (contoh: 1714291200)
        if isinstance(time_val, (int, float)):
            return datetime.fromtimestamp(time_val, tz=ZoneInfo("UTC"))
        if isinstance(time_val, str) and time_val.isdigit():
            return datetime.fromtimestamp(int(time_val), tz=ZoneInfo("UTC"))
        
        # Jika formatnya teks ISO (contoh: 2024-04-28T15:30:00Z)
        clean = str(time_val).replace("Z", "+00:00").replace("T", " ")
        try:
            dt_utc = datetime.fromisoformat(clean)
            if dt_utc.tzinfo is None: 
                dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
            return dt_utc
        except ValueError:
            return datetime.strptime(clean[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
    except Exception:
        return None

async def process_event(client: httpx.AsyncClient, url: str, url_num: int):
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        ifr = soup.find("iframe")
        
        if not ifr or not ifr.get("src"):
            return None, None
            
        ifr_src = urljoin(url, ifr.get("src"))
        
        ifr_resp = await client.get(ifr_src, headers={"Referer": url}, timeout=15)
        ifr_resp.raise_for_status()
        
        valid_m3u8 = re.compile(r"(?:file|source)\s*:\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
        match = valid_m3u8.search(ifr_resp.text)
        
        if match:
            m3u8_link = match.group(1)
            return m3u8_link, ifr_src
        else:
            return None, None
            
    except Exception:
        return None, None

async def scrape():
    print("🚀 Memulai Scraper StreamsGate MABES ENTERPRISE...")
    now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
    
    # Menentukan Jendela Waktu (-3 Jam sampai +4 Jam)
    window_start = now_wib - timedelta(hours=3)
    window_end = now_wib + timedelta(hours=4)
    print(f"🕒 Acuan Server: {now_wib.strftime('%H:%M WIB')}")
    print(f"🎯 Filter Jendela Tayang: {window_start.strftime('%H:%M WIB')} s/d {window_end.strftime('%H:%M WIB')}")

    headers = { "User-Agent": USER_AGENT, "Accept": "application/json" }
    all_streams = []
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # TAHAP 1: Merampok & Memfilter API
        for sport in SPORTS_TO_SCRAPE:
            api_url = f"{BASE_URL}/data/{sport}.json"
            
            try:
                resp = await client.get(api_url, timeout=10)
                if resp.status_code != 200: continue
                events_data = resp.json()
            except Exception:
                continue
                
            if not events_data: continue

            for item in events_data:
                date_str = item.get("time")
                league = item.get("league")
                t1 = item.get("away")
                t2 = item.get("home")
                streams = item.get("streams")
                
                if not all([date_str, league, t1, t2, streams]): continue
                
                dt_utc = parse_universal_time(date_str)
                if not dt_utc: continue # Abaikan jika waktu benar-benar rusak
                
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                
                # EKSEKUSI FILTER JENDELA WAKTU KETAT
                if dt_wib < window_start or dt_wib > window_end:
                    continue
                
                # Tentukan Status LIVE (Jika waktu tayang sudah terlewati/sekarang)
                if dt_wib <= now_wib:
                    time_tag = f"[🔴 LIVE] [{dt_wib.strftime('%H:%M WIB')}]"
                else:
                    time_tag = f"[{dt_wib.strftime('%H:%M WIB')}]"
                    
                event_name = format_event_name(t1, t2)
                base_title = f"{time_tag} [{league.upper()}] {event_name}"
                
                # Ambil SEMUA server cadangan dari API jika ada
                for stream_item in streams:
                    match_url = stream_item.get("url")
                    if match_url:
                        all_streams.append({
                            "sport": sport,
                            "base_title": base_title,
                            "url": match_url
                        })

        if not all_streams:
            print("\n💀 Tidak ada pertandingan di dalam Jendela Waktu 7 Jam.")
            return

        print(f"\n🎯 Terkumpul {len(all_streams)} link potensial. Memulai ekstraksi M3U8...")
        
        # TAHAP 2: Ekstrak M3U8 & Gerbang Anti-Duplikat
        playlist_entries = []
        seen_m3u8 = set()
        server_counts = defaultdict(int)
        
        for i, ev in enumerate(all_streams, start=1):
            m3u8_link, iframe_src = await process_event(client, ev["url"], i)
            
            if m3u8_link and iframe_src:
                clean_m3u8 = m3u8_link.split("?st")[0].strip()
                
                # LOGIKA ANTI-DUPLIKAT SPAM
                if clean_m3u8 in seen_m3u8:
                    print(f"🗑️ [SKIP] M3U8 Duplikat ditemukan untuk {ev['base_title']}")
                    continue
                
                seen_m3u8.add(clean_m3u8)
                
                # LOGIKA PENAMAAN SERVER CADANGAN
                base_title = ev["base_title"]
                server_counts[base_title] += 1
                count = server_counts[base_title]
                
                final_title = f"{base_title} (Gate)"
                if count > 1:
                    final_title += f" [S{count}]"
                    
                print(f"✅ Harta diamankan: {final_title}")
                
                origin_match = re.search(r'(https?://[^/]+)', iframe_src)
                origin = origin_match.group(1) if origin_match else BASE_URL
                tvg_id, logo, group_name = get_tv_data(ev["sport"])
                
                entry = [
                    f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="BONE TV",LIVE {ev["sport"].upper()} - Bone TV | {final_title}',
                    f'#EXTVLCOPT:http-referrer={iframe_src}',
                    f'#EXTVLCOPT:http-origin={origin}',
                    f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                    clean_m3u8,
                    ''
                ]
                playlist_entries.extend(entry)
                
        # TAHAP 3: Tulis File
        if playlist_entries:
            ts = now_wib.strftime("%Y-%m-%d %H:%M WIB")
            header = ['#EXTM3U', f'# Last Updated: {ts}', '']
            OUTPUT_FILE.write_text("\n".join(header + playlist_entries), encoding="utf-8")
            print(f"\n🏁 SELESAI! {len(seen_m3u8)} tayangan unik (beserta server cadangan) berhasil disimpan ke {OUTPUT_FILE}.")
        else:
            print("\n❌ Ekstraksi selesai, tapi nihil. Semua link mungkin diblokir server.")

if __name__ == "__main__":
    asyncio.run(scrape())
