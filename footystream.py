import asyncio
# 🛠️ PERBAIKAN FATAL: Menggunakan LexborHTMLParser sesuai aturan selectolax 1.0+
from selectolax.lexbor import LexborHTMLParser 
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# --- KONFIGURASI MABES ENTERPRISE: FOOTYSTREAM V5 (ANTI-AD & SMART RADAR) ---
MAIN_URL = "https://pogo.pk"
SOCCER_URL = "https://pogo.pk/soccer-streams"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
OUTPUT_FILE = "FootyStream_BoneTV.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

def convert_time_to_wib(utc_time_str):
    if not utc_time_str: return "UNKNOWN"
    try:
        start_utc = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return start_utc.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")
    except:
        return "UNKNOWN"

def format_title(team1, team2):
    t1_lower, t2_lower = team1.lower(), team2.lower()
    if t1_lower == t2_lower or t1_lower in t2_lower or t2_lower in t1_lower:
        return team1 if len(team1) >= len(team2) else team2
    return f"{team1} vs {team2}"

def parse_schedule(html_text):
    soup = LexborHTMLParser(html_text)
    events = []
    
    for a_tag in soup.css("a[href*='/events/']"):
        countdown = a_tag.css_first(".data-countdown")
        if countdown:
            start_str = countdown.attributes.get("data-start")
            end_str = countdown.attributes.get("data-end")
            
            teams = a_tag.css("img")
            if len(teams) >= 2:
                team1 = teams[0].attributes.get('alt', 'Team 1')
                team2 = teams[1].attributes.get('alt', 'Team 2')
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

# 🛡️ Fungsi pemblokir iklan & sampah
def route_interceptor(route):
    bad_types = ["image", "stylesheet", "font", "media"]
    url = route.request.url.lower()
    if route.request.resource_type in bad_types or any(bad in url for bad in ["pop", "ads", "tracker", "analytics", "banner"]):
        return route.abort()
    return route.continue_()

async def extract_m3u8(context, url):
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://pogo.pk/"
    m3u8_found_event = asyncio.Event()

    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # Cegah popup baru muncul ke permukaan
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
                m3u8_found_event.set() # Set trigger secepatnya

    page.on("request", handle_request)

    try:
        # Aktifkan tameng Ad-Blocker
        await page.route("**/*", route_interceptor)
        
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        # Eksekusi Trigger Play (Cari iframe atau elemen video dan klik langsung)
        try:
            # Berikan waktu 2 detik agar iframe player termuat
            await asyncio.sleep(2)
            frames = page.frames
            if len(frames) > 1:
                # Mengetuk frame pemutar langsung
                await page.mouse.click(640, 360) 
                await page.keyboard.press("Space")
        except:
            pass
            
        # Tunggu sampai event ditangkap, max 10 detik agar tidak buang waktu
        try:
            await asyncio.wait_for(m3u8_found_event.wait(), timeout=10.0)
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            pass

    except PlaywrightTimeout:
        pass
    except Exception:
        pass
    finally:
        page.remove_listener("request", handle_request)
        page.remove_listener("popup", handle_popup)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Operasi FootyStream (V5 Anti-Ad & Smart Radar)...")
    all_streams = []
    raw_events = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
        
        try:
            print("\n🔍 Memindai Halaman Utama (Bypass Cloudflare)...")
            scanner_page = await context.new_page()
            await scanner_page.route("**/*", route_interceptor)
            await scanner_page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=20000)
            html_main = await scanner_page.content()
            raw_events.extend(parse_schedule(html_main))

            print("🔍 Memindai Halaman Soccer-Streams...")
            await scanner_page.goto(SOCCER_URL, wait_until="domcontentloaded", timeout=20000)
            html_soc = await scanner_page.content()
            raw_events.extend(parse_schedule(html_soc))
            await scanner_page.close()
            
        except Exception as e:
            print(f"❌ Gagal memindai web pogo.pk: {e}")
            ts_fail = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(f"#EXTM3U\n# Last Updated: {ts_fail}\n#EXTINF:-1, [ERROR] Cloudflare Menahan Pogo.pk\n{DUMMY_LINK}\n")
            await browser.close()
            return

        unique_events_dict = {}
        for ev in raw_events:
            unique_key = f"{ev['raw_title']}_{ev['kickoff']}_{ev['url']}"
            if unique_key not in unique_events_dict:
                unique_events_dict[unique_key] = ev

        unique_events = list(unique_events_dict.values())
        print(f"🎯 Ditemukan Total {len(unique_events)} Pertandingan Unik.")

        if unique_events:
            for ev in unique_events:
                try:
                    now = datetime.now(timezone.utc)
                    start_dt = datetime.strptime(ev['start_str'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    end_dt = datetime.strptime(ev['end_str'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    
                    if now > end_dt:
                        continue
                        
                    time_to_kickoff = (start_dt - now).total_seconds()
                    
                    detail_page = await context.new_page()
                    await detail_page.route("**/*", route_interceptor)
                    await detail_page.goto(ev['url'], wait_until="domcontentloaded", timeout=15000)
                    detail_html = await detail_page.content()
                    await detail_page.close()
                    
                    match_soup = LexborHTMLParser(detail_html)
                    
                    tour_elem = match_soup.css_first("div.text-white.font-semibold.text-sm")
                    category_tag = f"[{tour_elem.text(strip=True).upper()}] " if tour_elem else ""
                    core_title = f"[{ev['kickoff']}] {category_tag}{ev['raw_title']}"
                    
                    if time_to_kickoff <= 3600:
                        watch_links = []
                        
                        # 📡 SMART RADAR TAHAP 1: Cari iframe yang mencurigakan secara langsung
                        for iframe in match_soup.css("iframe"):
                            src = iframe.attributes.get("src")
                            if src and ("pogo.pk" in src or "embed" in src or "stream" in src or "live" in src):
                                watch_links.append(src)
                                
                        # 📡 SMART RADAR TAHAP 2: Jika iframe tidak ada, sapu semua link a href
                        if not watch_links:
                            for a in match_soup.css("a"):
                                href = a.attributes.get("href")
                                text = a.text(strip=True).lower()
                                if href and (
                                    "watch" in text or "stream" in text or "play" in text or
                                    "/alpha/" in href or "/embed/" in href or "footystream" in href or "/live/" in href
                                ):
                                    full_watch_link = f"{MAIN_URL}{href}" if href.startswith("/") else href
                                    if full_watch_link not in watch_links:
                                        watch_links.append(full_watch_link)
                        
                        extracted_any = False
                        if watch_links:
                            print(f"\n⚡ Mengeksekusi (Sisa {int(time_to_kickoff // 60)} menit): {core_title}")
                            for idx, link in enumerate(watch_links):
                                server_num = idx + 1
                                print(f"    📡 Menyadap Tautan {server_num}...")
                                m3u8_url, referer = await extract_m3u8(context, link)
                                
                                if m3u8_url:
                                    print(f"      ✅ Sukses: {m3u8_url[:40]}...")
                                    pipe_headers = f"|Referer={referer}&User-Agent={USER_AGENT}"
                                    server_label = f" [CH {server_num}]" if len(watch_links) > 1 else ""
                                    
                                    all_streams.append([
                                        f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="LIVE - FootyStream",[🔴 LIVE] {core_title}{server_label}',
                                        f'{m3u8_url}{pipe_headers}',
                                        ''
                                    ])
                                    extracted_any = True
                                else:
                                    print(f"      ⚠️ Tautan {server_num} gagal dipenetrasi.")
                        
                        if not extracted_any:
                            print(f"  ⏳ {core_title} -> Link diblokir/belum tayang, menanam Dummy.")
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                                DUMMY_LINK,
                                ''
                            ])
                    else:
                        print(f"  ⏳ {core_title} -> Jadwal masih jauh (> 1 Jam), tanam Dummy.")
                        all_streams.append([
                            f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                            DUMMY_LINK,
                            ''
                        ])

                except Exception as e:
                    print(f"  ❌ Melewati pertandingan {ev['raw_title']}: {e}")

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
