import asyncio
import requests
from selectolax.parser import HTMLParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE: FOOTYSTREAM V4.3 ---
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

def format_title(team1, team2):
    """SMART TITLING: Mencegah pengulangan nama event tunggal"""
    t1_lower, t2_lower = team1.lower(), team2.lower()
    if t1_lower == t2_lower or t1_lower in t2_lower or t2_lower in t1_lower:
        return team1 if len(team1) >= len(team2) else team2
    return f"{team1} - {team2}"

def parse_schedule(html_text):
    """Mengekstrak jadwal dasar dari halaman depan/kategori"""
    soup = HTMLParser(html_text)
    events = []
    
    for a_tag in soup.css("a[href*='/events/']"):
        countdown = a_tag.css_first(".data-countdown")
        if countdown:
            start_str = countdown.attributes.get("data-start")
            end_str = countdown.attributes.get("data-end")
            
            teams = a_tag.css("img")
            if len(teams) >= 2:
                team1 = teams[0].attributes.get('alt', 'Team 1') # Tuan Rumah
                team2 = teams[1].attributes.get('alt', 'Team 2') # Tamu
                raw_title = format_title(team1, team2)
                logo = teams[0].attributes.get("src", "")
            else:
                raw_title = "Live Event"
                logo = teams[0].attributes.get("src", "") if teams else ""

            kickoff_wib = convert_time_to_wib(start_str)
            href = a_tag.attributes.get("href")
            full_url = f"{MAIN_URL}{href}" if href.startswith("/") else href
            
            events.append({
                "raw_title": raw_title,
                "kickoff": kickoff_wib,
                "start_str": start_str,
                "end_str": end_str,
                "logo": logo,
                "url": full_url
            })
            
    return events

async def extract_m3u8(context, url):
    """Menyusup ke Player Video dan mengambil M3U8 + Referer"""
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://footystream.pk/"

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
    print("🚀 Memulai Operasi FootyStream (Content-Based Titling V4.3)...")
    all_streams = []
    raw_events = []

    try:
        print("\n🔍 Memindai Halaman Utama...")
        res_main = requests.get(MAIN_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        raw_events.extend(parse_schedule(res_main.text))

        print("🔍 Memindai Halaman Soccer-Streams...")
        res_soc = requests.get(SOCCER_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        raw_events.extend(parse_schedule(res_soc.text))
    except Exception as e:
        print(f"❌ Gagal memindai web: {e}")
        return

    # PEMBERSIHAN DUPLIKAT JADWAL
    unique_events_dict = {}
    for ev in raw_events:
        unique_key = f"{ev['raw_title']}_{ev['kickoff']}_{ev['url']}"
        if unique_key not in unique_events_dict:
            unique_events_dict[unique_key] = ev

    unique_events = list(unique_events_dict.values())
    print(f"🎯 Ditemukan Total {len(unique_events)} Pertandingan Unik dalam Radar.")

    if unique_events:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
            
            for ev in unique_events:
                try:
                    now = datetime.now(timezone.utc)
                    start_dt = datetime.strptime(ev['start_str'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    end_dt = datetime.strptime(ev['end_str'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    
                    # Abaikan pertandingan yang sudah selesai lewat dari durasi target
                    if now > end_dt:
                        continue
                        
                    time_to_kickoff = (start_dt - now).total_seconds()
                    
                    # Ambil informasi turnamen detail halaman dalam
                    match_res = requests.get(ev['url'], headers={"User-Agent": USER_AGENT}, timeout=10)
                    match_soup = HTMLParser(match_res.text)
                    
                    tour_elem = match_soup.css_first("div.text-white.font-semibold.text-sm")
                    if tour_elem:
                        tournament_name = tour_elem.text(strip=True)
                        category_tag = f"[{tournament_name.upper()}] "
                    else:
                        category_tag = ""

                    # 🛡️ FORMAT BERSIH: Hapus [Ft] dan siapkan nama inti
                    core_title = f"[{ev['kickoff']}] {category_tag}{ev['raw_title']}"
                    
                    # 🛡️ LOGIKA RADAR PENYADAPAN (Batas 60 Menit)
                    if time_to_kickoff <= 3600:
                        watch_links = []
                        for a in match_soup.css("a"):
                            if a.text(strip=True) == "Watch":
                                href = a.attributes.get("href")
                                if href and ("/alpha/" in href or "footystream" in href):
                                    full_watch_link = f"{MAIN_URL}{href}" if href.startswith("/") else href
                                    if full_watch_link not in watch_links:
                                        watch_links.append(full_watch_link)
                        
                        extracted_any = False
                        if watch_links:
                            print(f"\n⚡ Mencari link asli (Waktu sisa: {int(time_to_kickoff // 60)} menit): {core_title}")
                            for idx, link in enumerate(watch_links):
                                server_num = idx + 1
                                print(f"    📡 Menyadap Server {server_num}...")
                                m3u8_url, referer = await extract_m3u8(context, link)
                                
                                if m3u8_url:
                                    print(f"      ✅ Sukses merampas link asli: {m3u8_url[:40]}...")
                                    pipe_headers = f"|Referer={referer}&User-Agent={USER_AGENT}"
                                    server_label = f" [CH {server_num}]" if len(watch_links) > 1 else ""
                                    
                                    # 🔴 JIKA LINK ASLI DAPAT -> MUTLAK LIVE
                                    all_streams.append([
                                        f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="LIVE - FootyStream",[🔴 LIVE] {core_title}{server_label}',
                                        f'{m3u8_url}{pipe_headers}',
                                        ''
                                    ])
                                    extracted_any = True
                                else:
                                    print(f"      ⚠️ Server {server_num} gagal diekstrak.")
                        
                        # Jika bandar belum rilis link atau Playwright gagal menembus
                        if not extracted_any:
                            print(f"  ⏳ {core_title} -> Link asli belum tayang, menanam Dummy.")
                            # ⏳ JIKA HANYA DUMMY -> MUTLAK UPCOMING
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                                DUMMY_LINK,
                                ''
                            ])
                    else:
                        # Di luar batas 1 jam, langsung pasang dummy untuk efisiensi resource
                        print(f"  ⏳ {core_title} -> Jadwal masih jauh (> 1 Jam), tanam Dummy.")
                        all_streams.append([
                            f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                            DUMMY_LINK,
                            ''
                        ])

                except Exception as e:
                    print(f"  ❌ Gagal memproses detail pertandingan {ev['raw_title']}: {e}")

            await browser.close()

    # SIMPAN DAN BANGUN BERKAS M3U8
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    if all_streams:
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 BERHASIL! {len(all_streams)} opsi stream berhasil dikunci ke {OUTPUT_FILE}.")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada stream yang berhasil diekstrak saat ini."]))
        print("\n💀 Operasi selesai tanpa hasil buruan.")

if __name__ == "__main__":
    asyncio.run(main())
