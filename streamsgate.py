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

# Kategori Olahraga yang dirampok
SPORTS_TO_SCRAPE = ["soccer", "nfl", "nba", "mlb", "nhl", "ufc", "box", "f1"]

# --- KAMUS LOGO BONE TV ---
# Logo Bawaan Olahraga (Jika tim tidak ada di database)
SPORT_FALLBACK_LOGOS = {
    "soccer": "https://i.postimg.cc/HsWHFvV0/Soccer.png",
    "mlb": "https://i.postimg.cc/FsFmwC7K/Baseball3.png",
    "nba": "https://i.postimg.cc/jdqKB3LW/Basketball-2.png",
    "nfl": "https://i.postimg.cc/tRNpSGCq/Maxx.png",
    "nhl": "https://i.postimg.cc/mgMRQ7FR/nhl-logo-png-seeklogo-534236.png",
    "ufc": "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png",
    "box": "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png",
    "f1": "https://i.postimg.cc/Vv8M1Q30/F1.png",
    "misc": "https://i.postimg.cc/qMm0rc3L/247.png"
}

# Kamus Logo Tim Raksasa (Silakan Kapten tambahkan sendiri ke depannya)
TEAM_LOGOS = {
    # NBA
    "los angeles lakers": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png",
    "boston celtics": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    "golden state warriors": "https://a.espncdn.com/i/teamlogos/nba/500/gs.png",
    "miami heat": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png",
    "chicago bulls": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png",
    # Soccer - EPL
    "manchester united": "https://a.espncdn.com/i/teamlogos/soccer/500/360.png",
    "arsenal": "https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
    "chelsea": "https://a.espncdn.com/i/teamlogos/soccer/500/363.png",
    "liverpool": "https://a.espncdn.com/i/teamlogos/soccer/500/364.png",
    "manchester city": "https://a.espncdn.com/i/teamlogos/soccer/500/382.png",
    "tottenham hotspur": "https://a.espncdn.com/i/teamlogos/soccer/500/367.png",
    # Soccer - La Liga
    "real madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/86.png",
    "barcelona": "https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
    "atlético madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/1068.png",
    # Soccer - Serie A
    "juventus": "https://a.espncdn.com/i/teamlogos/soccer/500/111.png",
    "ac milan": "https://a.espncdn.com/i/teamlogos/soccer/500/103.png",
    "internazionale": "https://a.espncdn.com/i/teamlogos/soccer/500/110.png",
    # Soccer - Others
    "bayern munich": "https://a.espncdn.com/i/teamlogos/soccer/500/132.png",
    "paris saint-germain": "https://a.espncdn.com/i/teamlogos/soccer/500/160.png"
}

def get_logo(team_name, sport):
    """Pencari Logo Otomatis: Cek kamus tim dulu, jika tidak ada pakai logo default olahraga"""
    clean_name = str(team_name).lower().strip()
    return TEAM_LOGOS.get(clean_name, SPORT_FALLBACK_LOGOS.get(sport, SPORT_FALLBACK_LOGOS["misc"]))

def format_event_name(t1: str, t2: str) -> str:
    if t1 == "RED ZONE": return "NFL RedZone"
    if t1 == "TBD": return "TBD"
    return f"{t1.strip()} vs {t2.strip()}"

async def process_event(client: httpx.AsyncClient, url: str, url_num: int):
    """Mengekstrak iframe dan M3U8"""
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        ifr = soup.find("iframe")
        
        if not ifr or not ifr.get("src"): return None, None
            
        ifr_src = urljoin(url, ifr.get("src"))
        
        ifr_resp = await client.get(ifr_src, headers={"Referer": url}, timeout=15)
        ifr_resp.raise_for_status()
        
        valid_m3u8 = re.compile(r"(?:file|source)\s*:\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
        match = valid_m3u8.search(ifr_resp.text)
        
        if match:
            return match.group(1), ifr_src
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
        # TAHAP 1: Bongkar JSON dengan Acuan UNIX Timestamp
        for sport in SPORTS_TO_SCRAPE:
            # Gunakan timestamp cache-busting agar tidak mendapat data usang
            cache_buster = int(datetime.now().timestamp() * 1000)
            api_url = f"{BASE_URL}/data/{sport}.json?_={cache_buster}"
            
            try:
                resp = await client.get(api_url, timeout=10)
                if resp.status_code != 200: continue
                events_data = resp.json()
            except Exception:
                continue
                
            if not events_data: continue

            for item in events_data:
                ts_unix = item.get("timestamp")
                t1_home = item.get("home")
                t2_away = item.get("away")
                streams = item.get("streams")
                
                if not all([ts_unix, t1_home, t2_away, streams]): continue
                
                # --- MESIN WAKTU UNIX ---
                try:
                    dt_utc = datetime.fromtimestamp(int(ts_unix), tz=ZoneInfo("UTC"))
                    dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                except Exception:
                    continue # Lewati jika gagal konversi angka
                
                # --- FILTER JENDELA WAKTU KETAT (7 JAM) ---
                if dt_wib < window_start or dt_wib > window_end:
                    continue
                
                # --- STATUS LIVE ---
                if dt_wib <= now_wib:
                    time_tag = f"[🔴 LIVE] [{dt_wib.strftime('%H:%M WIB')}]"
                else:
                    time_tag = f"[{dt_wib.strftime('%H:%M WIB')}]"
                    
                event_name = format_event_name(t1_home, t2_away)
                
                # FORMAT BARU YANG LEBIH RAMPING DAN ELEGAN
                base_title = f"{time_tag} [{sport.upper()}] {event_name}"
                
                # Cari Logo Tuan Rumah
                team_logo = get_logo(t1_home, sport)
                
                # Ambil SEMUA URL dari array "streams"
                for stream_item in streams:
                    match_url = stream_item.get("url")
                    if match_url:
                        all_streams.append({
                            "sport": sport,
                            "base_title": base_title,
                            "url": match_url,
                            "logo": team_logo,
                            "tvg_id": f"{sport.upper()}.Dummy.us"
                        })

        if not all_streams:
            print("\n💀 Tidak ada pertandingan di dalam Jendela Waktu 7 Jam saat ini.")
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
                
                # BUANG LINK SPAM (SAMA PERSIS)
                if clean_m3u8 in seen_m3u8:
                    continue
                
                seen_m3u8.add(clean_m3u8)
                
                # LOGIKA PENAMAAN SERVER CADANGAN [S2], [S3]
                base_title = ev["base_title"]
                server_counts[base_title] += 1
                count = server_counts[base_title]
                
                final_title = f"{base_title} (Gate)"
                if count > 1:
                    final_title += f" [S{count}]"
                    
                print(f"✅ Harta diamankan: {final_title}")
                
                origin_match = re.search(r'(https?://[^/]+)', iframe_src)
                origin = origin_match.group(1) if origin_match else BASE_URL
                
                # FORMAT OUTPUT BARU (TANPA EMBEL-EMBEL BERLEBIHAN)
                entry = [
                    f'#EXTINF:-1 tvg-logo="{ev["logo"]}" tvg-id="{ev["tvg_id"]}" group-title="BONE TV",{final_title}',
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
            print(f"\n🏁 SELESAI! {len(seen_m3u8)} tayangan unik berhasil disimpan ke {OUTPUT_FILE}.")
        else:
            print("\n❌ Ekstraksi selesai, tapi nihil. M3U8 mungkin diblokir oleh server web.")

if __name__ == "__main__":
    asyncio.run(scrape())
