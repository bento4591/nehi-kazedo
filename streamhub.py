import os
import json
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, parse_qsl, urlsplit
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# --- KONFIGURASI MABES ENTERPRISE: STREAMHUB ENGINE ---
TAG = "STRMHUB"
OUTPUT_FILE = "streamhub.m3u8"
BASE_URL = "https://streamhub.pro"
M3U8_DOMAIN = "https://obstreamx.click/live/" # Sengaja ditaruh di luar agar mudah diganti jika bandar ganti domain
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

# Properti Spoofing MABES
SPOOF_REFERER = "https://streamhub.pro/"
SPOOF_ORIGIN = "https://streamhub.pro"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

# Sistem Cache Lokal Mandiri
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
        # Lapis 1: Buka halaman pertandingan
        resp1 = await client.get(url, timeout=15.0)
        if resp1.status_code != 200: return None
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        
        ifr_1 = soup1.find('iframe', id='playerIframe')
        if not ifr_1 or not ifr_1.get('src'): return None
        ifr_1_src = ifr_1['src']
        
        # Lapis 2: Buka Iframe pertama
        resp2 = await client.get(ifr_1_src, headers={"Referer": BASE_URL}, timeout=15.0)
        if resp2.status_code != 200: return None
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        
        ifr_2 = soup2.find('iframe')
        if not ifr_2 or not ifr_2.get('src'): return None
        ifr_2_src = ifr_2['src']
        
        # Lapis 3: Rampas stream key dari parameter
        params = dict(parse_qsl(urlsplit(ifr_2_src).query))
        stream_key = params.get("stream")
        
        if stream_key:
            return f"{M3U8_DOMAIN}{stream_key}.m3u8"
            
    except Exception as e:
        print(f"    ⚠️ URL {url_num} Gagal ditembus: {e}")
        
    return None

async def get_events(client):
    """Menyapu bersih jadwal dari halaman depan Streamhub"""
    print("🔄 Memindai radar utama Streamhub...")
    events = []
    
    try:
        resp = await client.get(BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=15.0)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Cari semua blok kategori olahraga
        blocks = soup.find_all('div', class_='upcoming-date-block')
        
        for block in blocks:
            # Dapatkan nama olahraga
            sport_elem = block.find('div', class_='upcoming-sport-head')
            if not sport_elem: continue
            
            # Mengambil teks pertama saja (mengabaikan "3 games" dll)
            sport = sport_elem.contents[0].strip().upper()
            
            # Cari semua baris pertandingan dalam blok olahraga ini
            rows = block.find_all('div', class_='match-row')
            for row in rows:
                countdown = row.find('span', class_='countdown')
                if not countdown: continue
                
                # 🗑️ TENDANG SAMPAH: Lewati pertandingan yang sudah berakhir
                if "Live window ended" in countdown.text:
                    continue
                    
                ts_et = int(countdown.get('data-start', 0))
                if ts_et == 0: continue
                
                # Ekstrak Teks Tim dan Logo
                teams = row.find_all('span', class_='team-name')
                if len(teams) < 2: continue
                
                home_team = teams[0].text.strip()
                away_team = teams[1].text.strip()
                raw_event_name = f"{home_team} - {away_team}"
                
                logos = row.find_all('img', class_='small-logo')
                home_logo = logos[0].get('src', '') if logos else ""
                
                link_elem = row.find('a', class_='watch-live')
                if not link_elem: continue
                event_link = urljoin(BASE_URL, link_elem.get('href'))
                
                # Konversi Zona Waktu & Penetapan Status
                dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                kickoff_tag = dt_wib.strftime("%H:%M WIB %d/%m/%Y")
                
                if datetime.now(timezone.utc) >= dt_utc:
                    status_tag = "🔴 LIVE"
                else:
                    status_tag = "⏳ UPCOMING"
                    
                events.append({
                    "sport": sport,
                    "raw_title": raw_event_name,
                    "kickoff_tag": kickoff_tag,
                    "link": event_link,
                    "status_tag": status_tag,
                    "logo": home_logo,
                    "ts_et": ts_et
                })
                
    except Exception as e:
        print(f"❌ Gagal memindai halaman Streamhub: {e}")
        
    return events

async def scrape():
    cached_urls = load_event_cache()
    current_playlist_urls = {}
    now_ts = time.time()
    
    # Gunakan httpx AsyncClient agar operasi jaringan berjalan paralel dan kencang
    async with httpx.AsyncClient(verify=False) as client:
        events = await get_events(client)
        
        if events:
            print(f"🎯 Ditemukan {len(events)} siaran di beranda Streamhub.")
            
            # Kita batasi concurrency agar server Streamhub tidak mendeteksi serangan DDoS
            semaphore = asyncio.Semaphore(5) 
            
            async def process_single_event(i, ev):
                sport = ev["sport"]
                raw_name = ev["raw_title"]
                status_tag = ev["status_tag"]
                kickoff_tag = ev["kickoff_tag"]
                link = ev["link"]
                home_logo = ev["logo"]
                
                key = f"[{sport}] [{status_tag}] [{kickoff_tag}] {raw_name} ({TAG})"
                
                # Pakai cache jika link aktif sudah tersimpan (Hemat waktu)
                cached_entry = cached_urls.get(key)
                if cached_entry and cached_entry.get("url") and cached_entry["url"] != DUMMY_LINK:
                    print(f"  ℹ️ {key} -> Menggunakan link dari database cache.")
                    current_playlist_urls[key] = cached_entry
                    return
                
                # Taktik Siap Tempur: Selama ada link di halaman web, kita gasak!
                async with semaphore:
                    if status_tag == "⏳ UPCOMING":
                        print(f"\n⚡ Mencoba operasi PRA-PERTANDINGAN: {key}")
                    else:
                        print(f"\n⚡ Meluncurkan operasi penyadapan LIVE: {key}")
                        
                    url = await extract_m3u8(client, link, i)
                    
                    if url:
                        print(f"      ✅ Sukses mengunci M3U8: {url[:50]}...")
                    else:
                        print("      ⚠️ Iframe belum memuat stream_key, memasang Link Dummy sebagai cadangan.")
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

            # Jalankan semua proses secara konkuren
            tasks = [process_single_event(i, ev) for i, ev in enumerate(events, start=1)]
            await asyncio.gather(*tasks)
            
            # Bersihkan cache dari acara yang sudah usang
            active_keys = current_playlist_urls.keys()
            cleaned_cache = {k: v for k, v in cached_urls.items() if k in active_keys}
            save_event_cache(cleaned_cache)
            
        else:
            print("✅ Tidak ada siaran aktif yang terdeteksi.")
            
    return current_playlist_urls

async def main():
    print("🚀 Memulai Operasi MABES ENTERPRISE: Streamhub Engine (Fast Async HTTP)...")
    
    urls = await scrape()
        
    print("\n🎯 Membangun berkas fisik M3U8 Streamhub...")
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    playlist_lines = []
    for key, info in urls.items():
        if info.get("url"):
            group_title = "LIVE - Streamhub" if "🔴 LIVE" in key else "UPCOMING - Streamhub"
            
            extinf = f'#EXTINF:-1 tvg-id="{info["id"]}" tvg-logo="{info["logo"]}" group-title="{group_title}",{key}'
            playlist_lines.append(extinf)
            
            if info["url"] == DUMMY_LINK:
                playlist_lines.append(info["url"])
            else:
                # 🛡️ INJEKSI SPOOFING STREAMHUB
                playlist_lines.append(f'#EXTVLCOPT:http-referrer={SPOOF_REFERER}')
                playlist_lines.append(f'#EXTVLCOPT:http-origin={SPOOF_ORIGIN}')
                playlist_lines.append(f'#EXTVLCOPT:http-user-agent={USER_AGENT}')
                playlist_lines.append(info["url"])
            
            playlist_lines.append("")
            
    if playlist_lines:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + playlist_lines))
        print(f"🏁 BERHASIL! {len(playlist_lines)//6} Channel Streamhub dikunci ke {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada siaran aktif dalam radar saat ini."]))
        print("💀 Selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
