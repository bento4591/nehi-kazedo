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
    "soccer": "https://images.seeklogo.com/logo-png/48/1/soccer-ball-logo-png_seeklogo-480250.png",
    "mlb": "https://images.seeklogo.com/logo-png/28/1/mlb-com-logo-png_seeklogo-288672.png",
    "nba": "https://images.seeklogo.com/logo-png/24/1/nba-logo-png_seeklogo-247736.png",
    "nfl": "https://images.seeklogo.com/logo-png/37/1/nfl-logo-png_seeklogo-375127.png",
    "nhl": "https://images.seeklogo.com/logo-png/18/1/nhl-logo-png_seeklogo-183814.png",
    "ufc": "https://images.seeklogo.com/logo-png/27/1/ufc-logo-png_seeklogo-272931.png",
    "box": "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png",
    "f1": "https://images.seeklogo.com/logo-png/33/1/formula-1-logo-png_seeklogo-330361.png",
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
    "atlanta hawks": "https://a.espncdn.com/i/teamlogos/nba/500/atl.png",
    "boston celtics": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    "brooklyn nets": "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png",
    "charlotte hornets": "https://a.espncdn.com/i/teamlogos/nba/500/cha.png",
    "chicago bulls": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png",
    "cleveland cavaliers": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png",
    "dallas mavericks": "https://a.espncdn.com/i/teamlogos/nba/500/dal.png",
    "denver nuggets": "https://a.espncdn.com/i/teamlogos/nba/500/den.png",
    "detroit pistons": "https://a.espncdn.com/i/teamlogos/nba/500/det.png",
    "golden state warriors": "https://a.espncdn.com/i/teamlogos/nba/500/gs.png",
    "houston rockets": "https://a.espncdn.com/i/teamlogos/nba/500/hou.png",
    "indiana pacers": "https://a.espncdn.com/i/teamlogos/nba/500/ind.png",
    "la clippers": "https://a.espncdn.com/i/teamlogos/nba/500/lac.png",
    "los angeles lakers": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png",
    "memphis grizzlies": "https://a.espncdn.com/i/teamlogos/nba/500/mem.png",
    "miami heat": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png",
    "milwaukee bucks": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png",
    "minnesota timberwolves": "https://a.espncdn.com/i/teamlogos/nba/500/min.png",
    "new orleans pelicans": "https://a.espncdn.com/i/teamlogos/nba/500/no.png",
    "new york knicks": "https://a.espncdn.com/i/teamlogos/nba/500/ny.png",
    "oklahoma city thunder": "https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
    "orlando magic": "https://a.espncdn.com/i/teamlogos/nba/500/orl.png",
    "philadelphia 76ers": "https://a.espncdn.com/i/teamlogos/nba/500/phi.png",
    "phoenix suns": "https://a.espncdn.com/i/teamlogos/nba/500/phx.png",
    "portland trail blazers": "https://a.espncdn.com/i/teamlogos/nba/500/por.png",
    "sacramento kings": "https://a.espncdn.com/i/teamlogos/nba/500/sac.png",
    "san antonio spurs": "https://a.espncdn.com/i/teamlogos/nba/500/sa.png",
    "toronto raptors": "https://a.espncdn.com/i/teamlogos/nba/500/tor.png",
    "utah jazz": "https://a.espncdn.com/i/teamlogos/nba/500/uta.png",
    "washington wizards": "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png",
    # Soccer - EPL
    "arsenal": "https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
    "chelsea": "https://a.espncdn.com/i/teamlogos/soccer/500/363.png",
    "aston villa": "https://a.espncdn.com/i/teamlogos/soccer/500/362.png",
    "bournemouth": "https://a.espncdn.com/i/teamlogos/soccer/500/349.png",
    "brentford": "https://a.espncdn.com/i/teamlogos/soccer/500/337.png",
    "brighton & hove albion": "https://a.espncdn.com/i/teamlogos/soccer/500/331.png",
    "crystal palace": "https://a.espncdn.com/i/teamlogos/soccer/500/384.png",
    "everton": "https://a.espncdn.com/i/teamlogos/soccer/500/368.png",
    "fulham": "https://a.espncdn.com/i/teamlogos/soccer/500/370.png",
    "ipswich town": "https://a.espncdn.com/i/teamlogos/soccer/500/394.png",
    "leicester city": "https://a.espncdn.com/i/teamlogos/soccer/500/375.png",
    "liverpool": "https://a.espncdn.com/i/teamlogos/soccer/500/364.png",
    "manchester city": "https://a.espncdn.com/i/teamlogos/soccer/500/382.png",
    "manchester united": "https://a.espncdn.com/i/teamlogos/soccer/500/360.png",
    "newcastle united": "https://a.espncdn.com/i/teamlogos/soccer/500/361.png",
    "nottingham forest": "https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
    "southampton": "https://a.espncdn.com/i/teamlogos/soccer/500/376.png",
    "tottenham hotspur": "https://a.espncdn.com/i/teamlogos/soccer/500/367.png",
    "west ham united": "https://a.espncdn.com/i/teamlogos/soccer/500/371.png",
    "wolverhampton wanderers": "https://a.espncdn.com/i/teamlogos/soccer/500/380.png",
    
    # Soccer - La Liga
    "alaves": "https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
    "athletic club": "https://a.espncdn.com/i/teamlogos/soccer/500/93.png",
    "atletico madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/1068.png",
    "barcelona": "https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
    "celta vigo": "https://a.espncdn.com/i/teamlogos/soccer/500/85.png",
    "elche": "https://a.espncdn.com/i/teamlogos/soccer/500/3751.png",
    "espanyol": "https://a.espncdn.com/i/teamlogos/soccer/500/88.png",
    "getafe": "https://a.espncdn.com/i/teamlogos/soccer/500/2922.png",
    "girona": "https://a.espncdn.com/i/teamlogos/soccer/500/9812.png",
    "levante": "https://a.espncdn.com/i/teamlogos/soccer/500/3142.png",
    "mallorca": "https://a.espncdn.com/i/teamlogos/soccer/500/84.png",
    "osasuna": "https://a.espncdn.com/i/teamlogos/soccer/500/97.png",
    "rayo vallecano": "https://a.espncdn.com/i/teamlogos/soccer/500/101.png",
    "real betis": "https://a.espncdn.com/i/teamlogos/soccer/500/244.png",
    "real madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/86.png",
    "real oviedo": "https://a.espncdn.com/i/teamlogos/soccer/500/3146.png",
    "real sociedad": "https://a.espncdn.com/i/teamlogos/soccer/500/89.png",
    "sevilla": "https://a.espncdn.com/i/teamlogos/soccer/500/243.png",
    "valencia": "https://a.espncdn.com/i/teamlogos/soccer/500/94.png",
    "villarreal": "https://a.espncdn.com/i/teamlogos/soccer/500/102.png",

    "ac milan": "https://a.espncdn.com/i/teamlogos/soccer/500/115.png",
    "atalanta": "https://a.espncdn.com/i/teamlogos/soccer/500/103.png",
    "bologna": "https://a.espncdn.com/i/teamlogos/soccer/500/105.png",
    "cagliari": "https://a.espncdn.com/i/teamlogos/soccer/500/106.png",
    "como": "https://a.espncdn.com/i/teamlogos/soccer/500/3514.png",
    "cremonese": "https://a.espncdn.com/i/teamlogos/soccer/500/3341.png",
    "fiorentina": "https://a.espncdn.com/i/teamlogos/soccer/500/108.png",
    "genoa": "https://a.espncdn.com/i/teamlogos/soccer/500/109.png",
    "hellas verona": "https://a.espncdn.com/i/teamlogos/soccer/500/110.png",
    "inter milan": "https://a.espncdn.com/i/teamlogos/soccer/500/111.png",
    "juventus": "https://a.espncdn.com/i/teamlogos/soccer/500/112.png",
    "lazio": "https://a.espncdn.com/i/teamlogos/soccer/500/113.png",
    "lecce": "https://a.espncdn.com/i/teamlogos/soccer/500/114.png",
    "napoli": "https://a.espncdn.com/i/teamlogos/soccer/500/116.png",
    "parma": "https://a.espncdn.com/i/teamlogos/soccer/500/117.png",
    "pisa": "https://a.espncdn.com/i/teamlogos/soccer/500/3345.png",
    "roma": "https://a.espncdn.com/i/teamlogos/soccer/500/118.png",
    "sassuolo": "https://a.espncdn.com/i/teamlogos/soccer/500/2886.png",
    "torino": "https://a.espncdn.com/i/teamlogos/soccer/500/119.png",
    "udinese": "https://a.espncdn.com/i/teamlogos/soccer/500/120.png",
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
