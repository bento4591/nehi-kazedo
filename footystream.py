import asyncio
import requests
from selectolax.parser import HTMLParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
BASE_URL = "https://footystream.pk"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
OUTPUT_FILE = "FootyStream_BoneTV.m3u8"

def is_live(start_str, end_str):
    """Fungsi mendeteksi apakah pertandingan sedang LIVE berdasarkan waktu UTC di HTML"""
    if not start_str or not end_str: 
        return False
    try:
        # Format waktu dari HTML: "2026-06-06T22:00:00.000Z"
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return start_dt <= now <= end_dt
    except:
        return False

async def extract_m3u8(context, url, match_title):
    """Fungsi Playwright untuk menembus pemutar video dan merampas M3U8"""
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = "https://footystream.top/"

    # SUNTIKAN ANTI-DETEKSI
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # ALGORITMA TAB KILLER (Membunuh iklan pop-up liar)
    async def handle_popup(popup):
        try:
            await popup.close()
            print("    [!] Iklan Pop-up liar berhasil dihancurkan.")
        except:
            pass
    page.on("popup", handle_popup)

    # RADAR PENYADAP NETWORK
    async def handle_request(request):
        nonlocal m3u8_link, dynamic_referer
        if ".m3u8" in request.url:
            print(f"    📡 [Radar]: Menangkap sinyal M3U8...") 
            if not m3u8_link or "index" in request.url or "master" in request.url:
                m3u8_link = request.url
                # Curi Referer Asli (seperti bhalocast.pro)
                if "referer" in request.headers:
                    dynamic_referer = request.headers["referer"]

    page.on("request", handle_request)

    try:
        print(f"  🔍 Menyusup ke Pemutar: {match_title}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000) 
        
        # KLIK GANDA BRUTAL TEPAT SASARAN
        for _ in range(3):
            if m3u8_link: 
                break
            await page.mouse.click(640, 360)
            await page.wait_for_timeout(2000)

        # Tunggu hasil maksimal 10 detik
        for _ in range(10):
            if m3u8_link: 
                break
            await page.wait_for_timeout(1000)

    except Exception as e:
        print(f"  ❌ Terkena Ranjau/Timeout: {e}")
    finally:
        page.remove_listener("request", handle_request)
        page.remove_listener("popup", handle_popup)
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Operasi FootyStream (Hybrid Scraper Mode)...")
    all_streams = []

    # 1. BACA HALAMAN DEPAN FOOTYSTREAM (CEPAT)
    try:
        print("Membaca Peta Jadwal FootyStream...")
        res = requests.get(BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        res.raise_for_status()
        soup = HTMLParser(res.text)
    except Exception as e:
        print(f"❌ Gagal membaca web induk: {e}")
        return

    # 2. FILTER PERTANDINGAN LIVE
    live_events = []
    for a_tag in soup.css("a[href*='/events/']"):
        countdown = a_tag.css_first(".data-countdown")
        if countdown:
            start = countdown.attributes.get("data-start")
            end = countdown.attributes.get("data-end")
            
            # Jika jam saat ini masuk dalam rentang waktu pertandingan
            if is_live(start, end):
                teams = a_tag.css("img")
                title = f"{teams[0].attributes.get('alt', 'Team 1')} vs {teams[1].attributes.get('alt', 'Team 2')}" if len(teams) >= 2 else "Live Match"
                logo = teams[0].attributes.get("src", "") if teams else ""
                href = a_tag.attributes.get("href")
                
                # Gunakan URL absolut
                full_url = f"{BASE_URL}{href}" if href.startswith("/") else href
                live_events.append({"title": title, "logo": logo, "url": full_url})

    # Hapus duplikat
    unique_events = {e['url']: e for e in live_events}.values()
    print(f"🎯 Ditemukan {len(unique_events)} pertandingan sedang LIVE.")

    if unique_events:
        # 3. TERJUNKAN PLAYWRIGHT UNTUK MENGAMBIL VIDEO
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=USER_AGENT)
            
            for ev in unique_events:
                print(f"\nMenganalisis: {ev['title']}")
                try:
                    # Buka halaman event untuk mencari link "Watch"
                    match_res = requests.get(ev['url'], headers={"User-Agent": USER_AGENT}, timeout=15)
                    match_soup = HTMLParser(match_res.text)
                    
                    watch_links = []
                    for a in match_soup.css("a"):
                        if a.text(strip=True) == "Watch":
                            href = a.attributes.get("href")
                            if href and "footystream.top" in href:
                                watch_links.append(href)
                    
                    if watch_links:
                        # Ambil stream pertama saja untuk efisiensi
                        tag_title = f"[🔴 LIVE] {ev['title']} [Ft]"
                        m3u8_url, referer = await extract_m3u8(context, watch_links[0], tag_title[:60])
                        
                        if m3u8_url:
                            print(f"  ✅ HARTA DIDAPAT: {m3u8_url[:50]}...")
                            print(f"  🔑 Menggunakan Referer: {referer}")
                            
                            # Format Pipe (|) khusus TiviMate/ExoPlayer
                            pipe_headers = f"|Referer={referer}&User-Agent={USER_AGENT}"
                            all_streams.append([
                                f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="BONE TV - FootyStream",{tag_title}',
                                f'{m3u8_url}{pipe_headers}',
                                ''
                            ])
                        else:
                            print("  ⚠️ Gagal menembus video player.")
                    else:
                        print("  ⚠️ Link 'Watch' tidak ditemukan di halaman event.")
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
