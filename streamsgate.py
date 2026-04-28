import asyncio
import re
import httpx
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# --- KONFIGURASI DASAR ---
TAG = "STRMSGATE"
BASE_URL = "https://streamsgates.io"
OUTPUT_FILE = Path("streamsgate.m3u8")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Daftar Olahraga yang akan dirampok
SPORTS_TO_SCRAPE = ["mlb", "nba", "nhl", "soccer", "ufc"]

# Kamus Logo BONE TV
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

async def process_event(client: httpx.AsyncClient, url: str, url_num: int):
    """Fungsi untuk mengekstrak link M3U8 dari halaman pertandingan."""
    try:
        # 1. Buka halaman utama pertandingan
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        ifr = soup.find("iframe")
        
        if not ifr or not ifr.get("src"):
            print(f"⚠️ [{url_num}] Iframe video tidak ditemukan.")
            return None, None
            
        ifr_src = ifr["src"]
        if ifr_src.startswith("//"):
            ifr_src = f"https:{ifr_src}"
            
        # 2. Buka isi iframe dengan header Referer
        ifr_resp = await client.get(ifr_src, headers={"Referer": url}, timeout=15)
        ifr_resp.raise_for_status()
        
        # 3. Cari link M3U8 di dalam kode sumber iframe menggunakan Regex
        valid_m3u8 = re.compile(r"(file|source):\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
        match = valid_m3u8.search(ifr_resp.text)
        
        if match:
            m3u8_link = match.group(2)
            print(f"✅ [{url_num}] M3U8 Tertangkap: {m3u8_link.split('?')[0]}")
            return m3u8_link, ifr_src
        else:
            print(f"❌ [{url_num}] Gagal menemukan link .m3u8 di dalam iframe.")
            return None, None
            
    except Exception as e:
        print(f"❌ [{url_num}] Error saat memproses: {e}")
        return None, None

async def scrape():
    print(f"🚀 Memulai Scraper StreamsGate...")
    now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    
    all_streams = []
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # TAHAP 1: Merampok jadwal JSON
        for sport in SPORTS_TO_SCRAPE:
            api_url = f"{BASE_URL}/data/{sport}.json"
            print(f"\n📂 Memeriksa API: {sport.upper()}...")
            
            try:
                resp = await client.get(api_url, timeout=10)
                if resp.status_code != 200: continue
                
                events_data = resp.json()
            except Exception:
                continue
                
            for item in events_data:
                date_str = item.get("time")
                league = item.get("league")
                t1 = item.get("away")
                t2 = item.get("home")
                streams = item.get("streams")
                
                if not all([date_str, league, t1, t2, streams]):
                    continue
                    
                match_url = streams[0].get("url")
                if not match_url: continue
                
                # --- LOGIKA WAKTU WIB ---
                try:
                    # Streamsgate menggunakan format UTC
                    clean_date = date_str.replace("T", " ").replace("Z", "")
                    dt_utc = datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
                    dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                except Exception:
                    continue
                
                # Hanya ambil pertandingan hari ini atau ke depan
                if dt_wib.date() < now_wib.date() - timedelta(days=1):
                    continue
                    
                # Cek status LIVE (Window 4 Jam)
                diff_sec = (now_wib - dt_wib).total_seconds()
                is_live = (0 <= diff_sec <= 14400)
                
                time_tag = f"[{dt_wib.strftime('%H:%M WIB')}]"
                if is_live:
                    time_tag = f"[🔴 LIVE] {time_tag}"
                    
                event_name = format_event_name(t1, t2)
                
                # Format Nama Eksklusif MABES ENTERPRISE dengan akhiran (Gate)
                full_title = f"{time_tag} [{league.upper()}] {event_name} (Gate)"
                
                all_streams.append({
                    "sport": sport,
                    "title": full_title,
                    "url": match_url
                })

        if not all_streams:
            print("💀 Tidak ada jadwal pertandingan hari ini.")
            return

        print(f"\n🎯 Menemukan {len(all_streams)} kandidat jadwal. Memulai ekstraksi Iframe...")
        
        # TAHAP 2: Mengekstrak M3U8 secara berurutan
        playlist_entries = []
        
        for i, ev in enumerate(all_streams, start=1):
            m3u8_link, iframe_src = await process_event(client, ev["url"], i)
            
            if m3u8_link and iframe_src:
                clean_m3u8 = m3u8_link.split("?st")[0]
                
                # Ambil origin dari URL Iframe
                origin_match = re.search(r'(https?://[^/]+)', iframe_src)
                origin = origin_match.group(1) if origin_match else BASE_URL
                
                tvg_id, logo, group_name = get_tv_data(ev["sport"])
                
                entry = [
                    f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="BONE TV",LIVE {ev["sport"].upper()} - Bone TV | {ev["title"]}',
                    f'#EXTVLCOPT:http-referrer={iframe_src}',
                    f'#EXTVLCOPT:http-origin={origin}',
                    f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                    clean_m3u8,
                    ''
                ]
                playlist_entries.extend(entry)
                
        # TAHAP 3: Simpan ke File
        if playlist_entries:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M WIB")
            header = [
                '#EXTM3U',
                f'# Last Updated: {ts}',
                ''
            ]
            
            OUTPUT_FILE.write_text("\n".join(header + playlist_entries), encoding="utf-8")
            print(f"\n🏁 SELESAI! Berhasil menyusun file {OUTPUT_FILE} untuk BONE TV.")
        else:
            print("\n❌ Gagal total, tidak ada M3U8 yang berhasil diekstrak.")

if __name__ == "__main__":
    asyncio.run(scrape())
