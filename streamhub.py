import os
import json
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, parse_qsl, urlsplit
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# --- KONFIGURASI MABES ENTERPRISE: STREAMHUB ENGINE V1.4 ---
TAG = "STRMHUB"
OUTPUT_FILE = "streamhub.m3u8"
BASE_URL = "https://streamhub.pro"
M3U8_DOMAIN = "https://obstreamx.click/live/" 
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

# Properti Spoofing MABES
SPOOF_REFERER = "https://streamhub.pro/"
SPOOF_ORIGIN = "https://streamhub.pro"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

EVENT_CACHE_FILE = f"{TAG}_event_cache.json"

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

async def extract_m3u8(client, url, url_num):
    """Taktik Penyadapan Double-Iframe Streamhub"""
    try:
        resp1 = await client.get(url, headers={"User-Agent": USER_AGENT, "Referer": BASE_URL}, timeout=15.0)
        if resp1.status_code != 200: return None
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        
        ifr_1 = soup1.find('iframe', id='playerIframe')
        if not ifr_1 or not ifr_1.get('src'): return None
        
        ifr_1_src = ifr_1['src']
        if ifr_1_src.startswith('//'):
            ifr_1_src = 'https:' + ifr_1_src
            
        resp2 = await client.get(ifr_1_src, headers={"User-Agent": USER_AGENT, "Referer": url}, timeout=15.0)
        if resp2.status_code != 200: return None
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        
        ifr_2 = soup2.find('iframe')
        if not ifr_2 or not ifr_2.get('src'): return None
        ifr_2_src = ifr_2['src']
        
        params = dict(parse_qsl(urlsplit(ifr_2_src).query))
        stream_key = params.get("stream")
        
        if stream_key:
            return f"{M3U8_DOMAIN}{stream_key}.m3u8"
            
    except Exception as e:
        print(f"    ⚠️ URL {url_num} Gagal ditembus: {e}")
        
    return None

async def fetch_page_events(client, target_url, now_ts):
    """Mata Sensor Ganda (Live Card & Match Row)"""
    page_events = []
    try:
        resp = await client.get(target_url, headers={"User-Agent": USER_AGENT}, timeout=15.0)
        if resp.status_code != 200: 
            print(f"❌ Diblokir saat akses {target_url} (Status: {resp.status_code})")
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # ==========================================
        # 1. SENSOR UTAMA: Tangkap "🔴 LIVE NOW"
        # ==========================================
        live_cards = soup.find_all('a', class_='live-card')
        for card in live_cards:
            event_link = urljoin(BASE_URL, card.get('href', ''))
            
            teams = card.find_all('div', class_='live-team-name')
            if len(teams) < 2: continue
            home_team = teams[0].text.strip()
            away_team = teams[1].text.strip()
            
            league_div = card.find('div', class_='live-league')
            league_name = league_div.text.replace('🏆', '').strip() if league_div else "SPORT"
            sport_kategori = "FOOTBALL" # Default Live Now biasanya bola/sport umum
            
            logos = card.find_all('img', class_='small-logo')
            home_logo = logos[0].get('src', '') if logos else ""
            
            raw_event_name = f"[{league_name}] {home_team} - {away_team}"
            
            # Buat jam simulasi untuk Live Now (karena di web tidak ada jamnya)
            dt_wib_now = datetime.now(ZoneInfo("Asia/Jakarta"))
            kickoff_tag = dt_wib_now.strftime("LIVE %H:%M WIB %d/%m/%Y")
            
            unique_key = f"[LIVE_NOW] {raw_event_name}"
            
            page_events.append({
                "unique_key": unique_key,
                "sport": sport_kategori,
                "raw_title": raw_event_name,
                "kickoff_tag": kickoff_tag,
                "link": event_link,
                "status_tag": "🔴 LIVE",
                "logo": home_logo,
                "ts_et": now_ts - 3600 # Taruh di urutan teratas
            })

        # ==========================================
        # 2. SENSOR KEDUA: Tangkap "UPCOMING / PRE-MATCH"
        # ==========================================
        rows = soup.find_all('div', class_='match-row')
        for row in rows:
            # Lewati jika row ini ternyata bagian dari Live Now (untuk hindari duplikat)
            if row.find_parent('section', id='liveNowAjax'): continue
            
            countdown = row.find('span', class_='countdown')
            if not countdown: continue
            
            if "Live window ended" in countdown.text: continue
                
            ts_et = int(countdown.get('data-start', 0))
            if ts_et == 0: continue
            
            # Filter jadwal yang terlalu jauh (> 36 Jam)
            if ts_et > (now_ts + 129600): continue
            
            teams = row.find_all('span', class_='team-name')
            if len(teams) < 2: continue
            home_team = teams[0].text.strip()
            away_team = teams[1].text.strip()
            
            league_name = ""
            league_div = row.find('div', class_='league-name')
            if league_div:
                league_name = league_div.text.strip()
            else:
                meta_div = row.find('div', class_='match-meta')
                if meta_div:
                    spans = meta_div.find_all('span')
                    if spans: league_name = spans[0].text.strip()
            
            raw_event_name = f"[{league_name}] {home_team} - {away_team}" if league_name and league_name != "•" else f"{home_team} - {away_team}"
            
            logos = row.find_all('img', class_='small-logo')
            home_logo = logos[0].get('src', '') if logos else ""
            
            link_elem = row.find('a', class_='watch-live')
            if not link_elem:
                # Coba ambil href dari div.match-row jika a.watch-live tidak ada
                if row.has_attr('onclick'):
                    onclick_txt = row['onclick']
                    if "location.href='" in onclick_txt:
                        extracted_link = onclick_txt.split("location.href='")[1].split("'")[0]
                        link_elem = {'href': extracted_link}
                        
            if not link_elem: continue
            event_link = urljoin(BASE_URL, link_elem.get('href', ''))
            
            dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
            dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
            kickoff_tag = dt_wib.strftime("%H:%M WIB %d/%m/%Y")
            
            # Deteksi Kategori Olahraga dari blok atasnya
            sport = "SPORT"
            parent_block = row.find_previous('div', class_='upcoming-sport-head')
            if parent_block:
                sport = parent_block.contents[0].strip().upper()
            
            waktu_ke_kickoff = ts_et - now_ts
            status_tag = "🔴 LIVE" if waktu_ke_kickoff <= 3600 else "⏳ UPCOMING"
                
            unique_key = f"[{sport}] {raw_event_name} {ts_et}"
            
            page_events.append({
                "unique_key": unique_key,
                "sport": sport,
                "raw_title": raw_event_name,
                "kickoff_tag": kickoff_tag,
                "link": event_link,
                "status_tag": status_tag,
                "logo": home_logo,
                "ts_et": ts_et
            })
            
    except Exception as e:
        print(f"❌ Error ekstrak dari {target_url}: {e}")
        
    return page_events

async def get_all_events(client):
    print("🔄 Mengaktifkan Mode Stealth Crawler...")
    now_ts = time.time()
    now_utc = datetime.now(timezone.utc)
    
    # URL 3 Hari
    urls = [
        f"{BASE_URL}/?date={now_utc.strftime('%Y-%m-%d')}",
        f"{BASE_URL}/?date={(now_utc + timedelta(days=1)).strftime('%Y-%m-%d')}",
        f"{BASE_URL}/?date={(now_utc + timedelta(days=2)).strftime('%Y-%m-%d')}"
    ]
    
    all_events = []
    seen_keys = set()
    
    # Taktik Mengendap: Ambil satu per satu dengan jeda istirahat untuk menipu Cloudflare
    for i, url in enumerate(urls):
        print(f"📡 Menyapu Tab Tanggal: {url}")
        page_events = await fetch_page_events(client, url, now_ts)
        
        for ev in page_events:
            if ev["unique_key"] not in seen_keys:
                seen_keys.add(ev["unique_key"])
                all_events.append(ev)
                
        if i < len(urls) - 1:
            print("   ⏳ Menyamar sebagai manusia... (Jeda 2 detik)")
            await asyncio.sleep(2)
                
    all_events.sort(key=lambda x: x["ts_et"])
    return all_events

async def scrape():
    cached_urls = load_event_cache()
    current_playlist_urls = {}
    
    async with httpx.AsyncClient(verify=False) as client:
        events = await get_all_events(client)
        
        if events:
            print(f"\n🎯 Ditemukan total {len(events)} siaran dari radar.")
            semaphore = asyncio.Semaphore(3) # Kurangi kecepatan serbu iframe jadi 3 agar aman
            
            async def process_single_event(i, ev):
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
                    return
                
                async with semaphore:
                    if status_tag == "⏳ UPCOMING":
                        print(f"  ⏳ UPCOMING -> {raw_name}")
                        url = DUMMY_LINK
                    else:
                        print(f"  ⚡ SADAP LIVE -> {raw_name}")
                        url = await extract_m3u8(client, link, i)
                        if not url: url = DUMMY_LINK
                            
                entry = {
                    "url": url,
                    "logo": home_logo,
                    "id": "Live.Event.us",
                    "link": link
                }
                
                cached_urls[key] = entry
                current_playlist_urls[key] = entry

            tasks = [process_single_event(i, ev) for i, ev in enumerate(events, start=1)]
            await asyncio.gather(*tasks)
            
            active_keys = current_playlist_urls.keys()
            cleaned_cache = {k: v for k, v in cached_urls.items() if k in active_keys}
            save_event_cache(cleaned_cache)
        else:
            print("✅ Tidak ada siaran aktif yang terdeteksi.")
            
    return current_playlist_urls

async def main():
    print("🚀 MABES ENTERPRISE: Streamhub Stealth Engine V1.4 (Live Catcher)")
    urls = await scrape()
        
    print("\n🎯 Membangun berkas M3U8...")
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    playlist_lines = []
    for key, info in urls.items():
        if info.get("url"):
            group_title = "LIVE - Streamhub" if "🔴 LIVE" in key else "UPCOMING - Streamhub"
            extinf = f'#EXTINF:-1 tvg-id="{info["id"]}" tvg-logo="{info["logo"]}" group-title="{group_title}",{key}'
            
            playlist_lines.append(extinf)
            if info["url"] != DUMMY_LINK:
                playlist_lines.append(f'#EXTVLCOPT:http-referrer={SPOOF_REFERER}')
                playlist_lines.append(f'#EXTVLCOPT:http-origin={SPOOF_ORIGIN}')
                playlist_lines.append(f'#EXTVLCOPT:http-user-agent={USER_AGENT}')
            playlist_lines.append(info["url"])
            playlist_lines.append("")
            
    if playlist_lines:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + playlist_lines))
        print(f"🏁 BERHASIL! {len(playlist_lines)//6} Channel (termasuk Live Now) dikunci ke {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada siaran aktif dalam radar saat ini."]))
        print("💀 Selesai tanpa hasil.")

if __name__ == "__main__":
    asyncio.run(main())
