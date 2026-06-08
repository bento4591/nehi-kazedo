import asyncio
import requests
from selectolax.parser import HTMLParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
MAIN_URL = "https://footystream.pk"
SOCCER_URL = "https://footystream.pk/soccer-streams"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
OUTPUT_FILE = "FootyStream_BoneTV.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

def convert_time_to_wib(utc_time_str):
    """Konversi waktu UTC ke WIB"""
    if not utc_time_str: return "UNKNOWN"
    try:
        start_utc = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return start_utc.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")
    except:
        return "UNKNOWN"

def check_status(start_str, end_str):
    """Menentukan status pertandingan"""
    if not start_str or not end_str: return "UNKNOWN"
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        
        if now < start_dt: return "UPCOMING"
        elif start_dt <= now <= end_dt: return "LIVE"
        else: return "ENDED"
    except:
        return "UNKNOWN"

def format_title(team1, team2):
    """SMART TITLING: Mencegah pengulangan nama event tunggal"""
    t1_lower, t2_lower = team1.lower(), team2.lower()
    if t1_lower == t2_lower or t1_lower in t2_lower or t2_lower in t1_lower:
        return team1 if len(team1) >= len(team2) else team2
    return f"{team1} vs {team2}"

def get_category(logo_url, is_soccer_page):
    """Menyuntikkan Kategori Liga/Olahraga berdasarkan logo atau URL halaman"""
    if is_soccer_page: return "[Soccer] "
    if not logo_url: return ""
    
    url_lower = logo_url.lower()
    if "f1" in url_lower or "formula" in url_lower: return "[Formula 1] "
    if "nba" in url_lower or "basketball" in url_lower: return "[NBA] "
    if "ufc" in url_lower or "mma" in url_lower: return "[UFC] "
    if "motogp" in url_lower: return "[MotoGP] "
    if "nfl" in url_lower: return "[NFL] "
    if "pga" in url_lower or "golf" in url_lower: return "[Golf] "
    if "atp" in url_lower or "tennis" in url_lower: return "[Tennis] "
    
    return ""

def parse_schedule(html_text, is_soccer_page=False):
    """Mengekstrak jadwal dari halaman HTML dengan Taktik Swap Posisi"""
    soup = HTMLParser(html_text)
    events = []
    
    for a_tag in soup.css("a[href*='/events/']"):
        countdown = a_tag.css_first(".data-countdown")
        if countdown:
            start_str = countdown.attributes.get("data-start")
            end_str = countdown.attributes.get("data-end")
            status = check_status(start_str, end_str)
            
            if status == "ENDED": continue
            if not is_soccer_page and status == "UPCOMING": continue
            
            teams = a_tag.css("img")
            
            # 🔄 TAKTIK SWAP POSISI (V2.2)
            # Web asli: [Tamu] vs [Tuan Rumah] -> Diubah ke: [Tuan Rumah] vs [Tamu]
            if len(teams) >= 2:
                team_away = teams[0].attributes.get('alt', 'Team Away')
                team_home = teams[1].attributes.get('alt', 'Team Home')
                
                raw_title = format_title(team_home, team_away)
                logo = teams[1].attributes.get("src", "") # Menggunakan logo Tuan Rumah
            else:
                raw_title = "Live Event"
                logo = teams[0].attributes.get("src", "") if teams else ""

            category_tag = get_category(logo, is_soccer_page)
            kickoff_wib = convert_time_to_wib(start_str)
            href = a_tag.attributes.get("href")
            full_url = f"{MAIN_URL}{href}" if href.startswith("/") else href
            
            events.append({
                "raw_title": raw_title,
                "kickoff": kickoff_wib,
                "category": category_tag,
                "status": status,
                "logo": logo,
                "url": full_url
            })
            
    return events

async def extract_m3u8(context, url):
    """Menyusup ke Player Video dan mengambil M3U8 + Referer"""
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://footystream.top/"

    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def handle_popup(popup):
        try: await popup.close()
        except: pass
    page.on("popup", handle_popup)

    async def handle_request(request):
        nonlocal m3u8_link, dynamic_referer
        if ".m3u8" in request.url:
            if not m3u8_link or "index" in request.url or "master" in request.url:
                m3u8_link = request.url
                if "referer" in request.headers:
                    dynamic_referer = request.headers["referer"]

    page.on("request", handle_request)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000) 
        
        for _ in range(3):
            if m3u8_link: break
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(2000)

        for _ in range(10):
            if m3u8_link: break
            await page.wait_for_timeout(1000)
    except:
        pass
    finally:
        page.remove_listener("request", handle_request)
        page.remove_listener("popup", handle_popup)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Operasi FootyStream (V2.2 - Swap Posisi & Dummy Link)...")
    all_streams = []
    raw_events = []

    try:
        print("\n🔍 Memindai Halaman Utama...")
        res_main = requests.get(MAIN_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        raw_events.extend(parse_schedule(res_main.text, is_soccer_page=False))

        print("🔍 Memindai Halaman Soccer-Streams...")
        res_soc = requests.get(SOCCER_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        raw_events.extend(parse_schedule(res_soc.text, is_soccer_page=True))
        
    except Exception as e:
        print(f"❌ Gagal memindai web: {e}")
        return

    # PEMBERSIHAN DUPLIKAT (Berdasarkan Judul + Waktu + URL)
    unique_events_dict = {}
    for ev in raw_events:
        unique_key = f"{ev['raw_title']}_{ev['kickoff']}_{ev['url']}"
        if unique_key not in unique_events_dict:
            unique_events_dict[unique_key] = ev

    unique_events = list(unique_events_dict.values())
    print(f"🎯 Ditemukan Total {len(unique_events)} Pertandingan Unik.")

    if unique_events:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
            
            for ev in unique_events:
                status_icon = "🔴 LIVE" if ev['status'] == "LIVE" else "⏳ UPCOMING"
                base_title = f"[{status_icon}] [{ev['kickoff']}] {ev['category']}{ev['raw_title']} [Ft]"
                
                if ev['status'] == "UPCOMING":
                    print(f"  ⏳ {base_title} -> Menanam Link Dummy")
                    all_streams.append([
                        f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",{base_title}',
                        DUMMY_LINK,
                        ''
                    ])
                
                elif ev['status'] == "LIVE":
                    print(f"\n⚡ Mengeksekusi LIVE: {base_title}")
                    try:
                        match_res = requests.get(ev['url'], headers={"User-Agent": USER_AGENT}, timeout=15)
                        match_soup = HTMLParser(match_res.text)
                        
                        watch_links = []
                        for a in match_soup.css("a"):
                            if a.text(strip=True) == "Watch":
                                href = a.attributes.get("href")
                                if href and "footystream.top" in href:
                                    watch_links.append(href)
                        
                        # Batasi maksimal 2 server
                        watch_links = watch_links[:2] 
                        
                        if watch_links:
                            for idx, link in enumerate(watch_links):
                                server_num = idx + 1
                                print(f"    📡 Menyadap Server {server_num}...")
                                
                                m3u8_url, referer = await extract_m3u8(context, link)
                                
                                if m3u8_url:
                                    print(f"      ✅ Berhasil: {m3u8_url[:40]}...")
                                    pipe_headers = f"|Referer={referer}&User-Agent={USER_AGENT}"
                                    server_label = f" (Server {server_num})" if len(watch_links) > 1 else ""
                                    
                                    all_streams.append([
                                        f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="LIVE - FootyStream",{base_title}{server_label}',
                                        f'{m3u8_url}{pipe_headers}',
                                        ''
                                    ])
                                else:
                                    print(f"      ⚠️ Server {server_num} gagal diekstrak.")
                        else:
                            print("    ⚠️ Tidak ada tombol 'Watch' yang tersedia.")
                    except Exception as e:
                        print(f"    ❌ Gagal memproses event: {e}")

            await browser.close()

    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    if all_streams:
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link berhasil dikunci ke {OUTPUT_FILE}.")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada stream yang berhasil diekstrak saat ini."]))
        print("\n💀 Operasi selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
