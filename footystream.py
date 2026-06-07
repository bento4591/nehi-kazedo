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

def convert_time_to_wib(utc_time_str):
    """Konversi waktu UTC ke WIB"""
    if not utc_time_str: return "UNKNOWN"
    try:
        start_utc = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return start_utc.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")
    except:
        return "UNKNOWN"

def check_status(start_str, end_str):
    """Menentukan status pertandingan (LIVE / UPCOMING / ENDED)"""
    if not start_str or not end_str: return "UNKNOWN"
    try:
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        
        if now < start_dt: return "UPCOMING ⏳"
        elif start_dt <= now <= end_dt: return "LIVE 🔴"
        else: return "ENDED 🏁"
    except:
        return "UNKNOWN"

def format_title(team1, team2):
    """SMART TITLING: Mencegah penulisan 'Formula 1 vs Formula 1'"""
    t1_lower, t2_lower = team1.lower(), team2.lower()
    
    # Jika namanya sama atau salah satunya ada di dalam nama yang lain
    if t1_lower == t2_lower or t1_lower in t2_lower or t2_lower in t1_lower:
        # Pilih nama yang paling panjang (biasanya lebih detail)
        return team1 if len(team1) >= len(team2) else team2
    else:
        return f"{team1} vs {team2}"

def parse_schedule(html_text, is_soccer_page=False):
    """Mengekstrak jadwal dari halaman HTML"""
    soup = HTMLParser(html_text)
    events = []
    
    for a_tag in soup.css("a[href*='/events/']"):
        countdown = a_tag.css_first(".data-countdown")
        if countdown:
            start_str = countdown.attributes.get("data-start")
            end_str = countdown.attributes.get("data-end")
            status = check_status(start_str, end_str)
            
            # ATURAN FILTERING:
            # - Halaman Utama: Hanya ambil yang LIVE
            # - Halaman Soccer: Ambil semua (Live & Upcoming), abaikan yang Ended
            if status == "ENDED 🏁":
                continue
            if not is_soccer_page and status == "UPCOMING ⏳":
                continue
            
            teams = a_tag.css("img")
            logo = teams[0].attributes.get("src", "") if teams else ""
            
            if len(teams) >= 2:
                team1 = teams[0].attributes.get('alt', 'Team 1')
                team2 = teams[1].attributes.get('alt', 'Team 2')
                match_title = format_title(team1, team2)
            else:
                match_title = "Live Event"

            kickoff_wib = convert_time_to_wib(start_str)
            href = a_tag.attributes.get("href")
            full_url = f"{MAIN_URL}{href}" if href.startswith("/") else href
            
            # Format label status
            status_label = "[🔴 LIVE]" if status == "LIVE 🔴" else "[⏳ UPCOMING]"
            display_title = f"{status_label} [{kickoff_wib}] {match_title} [Seru]"
            
            events.append({"title": display_title, "logo": logo, "url": full_url})
            
    return events

async def extract_m3u8(context, url, match_title):
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://footystream.top/"

    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    async def handle_popup(popup):
        try:
            await popup.close()
        except:
            pass
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
        
        # Double Tap
        for _ in range(3):
            if m3u8_link: break
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(2000)

        for _ in range(10):
            if m3u8_link: break
            await page.wait_for_timeout(1000)

    except Exception as e:
        print(f"    ❌ Error memuat player: {e}")
    finally:
        page.remove_listener("request", handle_request)
        page.remove_listener("popup", handle_popup)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Operasi FootyStream (Multi-Page & Multi-Link Scraper)...")
    all_streams = []
    target_events = []

    try:
        # 1. Pindai Halaman Utama (Hanya LIVE)
        print("\n🔍 Memindai Halaman Utama...")
        res_main = requests.get(MAIN_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        main_events = parse_schedule(res_main.text, is_soccer_page=False)
        target_events.extend(main_events)
        print(f"  -> Ditemukan {len(main_events)} pertandingan LIVE.")

        # 2. Pindai Halaman Soccer (Semua jadwal belum selesai)
        print("\n🔍 Memindai Halaman Soccer-Streams...")
        res_soc = requests.get(SOCCER_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        soc_events = parse_schedule(res_soc.text, is_soccer_page=True)
        target_events.extend(soc_events)
        print(f"  -> Ditemukan {len(soc_events)} pertandingan (Live & Upcoming).")
        
    except Exception as e:
        print(f"❌ Gagal memindai web: {e}")
        return

    # Hapus duplikat berdasarkan URL
    unique_events = {e['url']: e for e in target_events}.values()
    print(f"\n🎯 Total Target Unik: {len(unique_events)} pertandingan.")

    if unique_events:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
            
            for ev in unique_events:
                print(f"\n⚡ Mengeksekusi: {ev['title']}")
                try:
                    match_res = requests.get(ev['url'], headers={"User-Agent": USER_AGENT}, timeout=15)
                    match_soup = HTMLParser(match_res.text)
                    
                    # Mencari semua link "Watch"
                    watch_links = []
                    for a in match_soup.css("a"):
                        if a.text(strip=True) == "Watch":
                            href = a.attributes.get("href")
                            if href and "footystream.top" in href:
                                watch_links.append(href)
                    
                    # Batasi maksimal 3 server per pertandingan
                    watch_links = watch_links[:3] 
                    
                    if watch_links:
                        for idx, link in enumerate(watch_links):
                            server_num = idx + 1
                            print(f"  ⏳ Mengekstrak Server {server_num}...")
                            
                            m3u8_url, referer = await extract_m3u8(context, link, ev['title'])
                            
                            if m3u8_url:
                                print(f"    ✅ Server {server_num} BERHASIL!")
                                pipe_headers = f"|Referer={referer}&User-Agent={USER_AGENT}"
                                server_label = f" (Server {server_num})" if len(watch_links) > 1 else ""
                                
                                all_streams.append([
                                    f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="BONE TV - FootyStream",{ev["title"]}{server_label}',
                                    f'{m3u8_url}{pipe_headers}',
                                    ''
                                ])
                            else:
                                print(f"    ⚠️ Server {server_num} Gagal.")
                    else:
                        print("  ⚠️ Tidak ada tombol 'Watch' yang tersedia (Mungkin pertandingan terlalu lama).")
                except Exception as e:
                    print(f"  ❌ Gagal memproses event: {e}")

            await browser.close()

    # 4. SIMPAN HASIL KE M3U8
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
