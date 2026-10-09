import asyncio
from urllib.parse import urlparse
from selectolax.lexbor import LexborHTMLParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# --- KONFIGURASI FOOTYSTREAM ULTIMATE V8 (CLOUDFLARE-AWARE + HEADED STEALTH) ---
MAIN_URL = "https://pogo.pk"
SOCCER_URL = "https://pogo.pk/soccer-streams"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
OUTPUT_FILE = "FootyStream_BoneTV.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

DEBUG = False
EXTRACT_WINDOW_SEC = 3600      
POST_END_GRACE_SEC = 14400     

NAV_ALLOW_HOSTS = ("pogo.pk", "playerdee.top", "cloudflare.com")
AD_KEYWORDS = ("pop", "ads", "tracker", "analytics", "banner", "bet", "casino")
CF_MARKERS = ("just a moment", "verify you are human", "verifikasi bahwa anda adalah manusia",
              "attention required", "challenge-platform", "cf-challenge")

CF_BLOCKED = "CF_BLOCKED"

TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
)

# 🛡️ INJEKSI JUBAH GAIB MABES (Ditambahkan dari V8)
STEALTH_SCRIPTS = """
    window.open = function() { return null; };
    window.alert = function() { return null; };
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""

def parse_utc(s):
    if not s:
        return None
    for fmt in TIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None

def convert_time_to_wib(utc_time_str):
    dt = parse_utc(utc_time_str)
    if not dt:
        return "UNKNOWN"
    return dt.astimezone(ZoneInfo("Asia/Jakarta")).strftime("%H:%M WIB")

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
        if not countdown:
            continue
        start_str = countdown.attributes.get("data-start")
        end_str = countdown.attributes.get("data-end")
        teams = a_tag.css("img")
        if len(teams) >= 2:
            team1 = teams[0].attributes.get("alt", "Team 1")
            team2 = teams[1].attributes.get("alt", "Team 2")
            raw_title = format_title(team1, team2)
            logo = teams[0].attributes.get("src", "")
        else:
            raw_title = "Live Event"
            logo = teams[0].attributes.get("src", "") if teams else ""
        href = a_tag.attributes.get("href")
        if not href:
            continue
        full_url = f"{MAIN_URL}{href}" if href.startswith("/") else href
        events.append({
            "raw_title": raw_title,
            "kickoff": convert_time_to_wib(start_str),
            "start_str": start_str,
            "end_str": end_str,
            "logo": logo,
            "url": full_url,
        })
    return events

def find_watch_links(html_text):
    soup = LexborHTMLParser(html_text)
    primary, fallback = [], []
    for a in soup.css("a"):
        href = a.attributes.get("href")
        if not href:
            continue
        href_l = href.lower()
        text = a.text(strip=True).lower()
        full = f"{MAIN_URL}{href}" if href.startswith("/") else href
        if "playerdee.top" in href_l or "/alpha/" in href_l:
            if full not in primary:
                primary.append(full)
        elif text == "watch":
            if full not in fallback:
                fallback.append(full)
    return primary or fallback

async def extract_m3u8(context, url):
    page = await context.new_page()
    m3u8_link = None
    dynamic_referer = url
    m3u8_found_event = asyncio.Event()

    # 🛡️ Pasang Jubah Gaib MABES
    await page.add_init_script(STEALTH_SCRIPTS)
    page.on("popup", lambda p: asyncio.create_task(p.close()))

    async def route_interceptor(route):
        req = route.request
        if req.is_navigation_request() and req.frame == page.main_frame:
            host = urlparse(req.url).hostname or ""
            if not any(host == h or host.endswith("." + h) for h in NAV_ALLOW_HOSTS):
                if DEBUG: print(f"    🛑 navigasi diblokir -> {req.url[:90]}")
                return await route.abort()
        if req.resource_type in ("image", "stylesheet", "font"):
            return await route.abort()
        url_lower = req.url.lower()
        if any(bad in url_lower for bad in AD_KEYWORDS):
            if DEBUG: print(f"    🛑 keyword diblokir -> {req.url[:90]}")
            return await route.abort()
        return await route.continue_()

    async def handle_request(request):
        nonlocal m3u8_link, dynamic_referer
        if ".m3u8" in request.url:
            if not m3u8_link or "index" in request.url or "master" in request.url:
                m3u8_link = request.url
                if "referer" in request.headers:
                    dynamic_referer = request.headers["referer"]
                m3u8_found_event.set()

    page.on("request", handle_request)

    try:
        await page.route("**/*", route_interceptor)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        # Beri waktu lebih lama agar Cloudflare (Headed Mode) bisa memproses verifikasi
        await page.wait_for_timeout(8000)

        # --- Deteksi tantangan Cloudflare (Logika Asisten) ---
        try:
            probe = (await page.content())[:8000].lower()
        except Exception:
            probe = ""
        if any(m in probe for m in CF_MARKERS):
            return CF_BLOCKED, dynamic_referer

        try:
            await asyncio.wait_for(m3u8_found_event.wait(), timeout=8.0)
        except asyncio.TimeoutError:
            try:
                await page.evaluate("var vids=document.getElementsByTagName('video');if(vids.length>0){vids[0].play();}")
                await asyncio.wait_for(m3u8_found_event.wait(), timeout=4.0)
            except Exception:
                pass
    except PlaywrightTimeout:
        pass
    except Exception:
        pass
    finally:
        try:
            page.remove_listener("request", handle_request)
        except Exception:
            pass
        await page.close()

    return m3u8_link, dynamic_referer

async def main():
    print("🚀 Memulai Operasi FootyStream (V8 ULTIMATE - HEADED STEALTH)...")
    all_streams = []
    raw_events = []
    stats = {"live": 0, "upcoming": 0, "extracted": 0, "cf_blocked": 0, "failed": 0}

    async with async_playwright() as p:
        # ⚠️ PERUBAHAN V8: headless=False agar berjalan dengan wujud fisik di dalam Xvfb!
        browser = await p.chromium.launch(
            headless=False, 
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage", 
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security"
            ]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720}, user_agent=USER_AGENT)

        try:
            print("\n🔍 Memindai Halaman Utama...")
            scanner_page = await context.new_page()
            await scanner_page.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "stylesheet", "font") else route.continue_())
            await scanner_page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=20000)
            raw_events.extend(parse_schedule(await scanner_page.content()))
            
            print("🔍 Memindai Halaman Soccer-Streams...")
            await scanner_page.goto(SOCCER_URL, wait_until="domcontentloaded", timeout=20000)
            raw_events.extend(parse_schedule(await scanner_page.content()))
            await scanner_page.close()
        except Exception as e:
            print(f"❌ Gagal memindai pogo.pk: {e}")
            ts_fail = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(f"#EXTM3U\n# Last Updated: {ts_fail}\n#EXTINF:-1, [ERROR] Gagal memindai pogo.pk\n{DUMMY_LINK}\n")
            await browser.close()
            return

        unique_events = list({f"{ev['raw_title']}_{ev['kickoff']}_{ev['url']}": ev for ev in raw_events}.values())
        print(f"🎯 Ditemukan Total {len(unique_events)} Pertandingan Unik.")

        now = datetime.now(timezone.utc)
        for ev in unique_events:
            try:
                start_dt = parse_utc(ev["start_str"])
                end_dt = parse_utc(ev["end_str"])
                if not start_dt or not end_dt:
                    print(f"  ⚠️ {ev['raw_title']}: format waktu tak dikenal, lewati.")
                    stats["failed"] += 1
                    continue
                if (now - end_dt).total_seconds() > POST_END_GRACE_SEC:
                    continue

                detail_page = await context.new_page()
                try:
                    await detail_page.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "stylesheet", "font") else route.continue_())
                    await detail_page.goto(ev["url"], wait_until="domcontentloaded", timeout=15000)
                    detail_html = await detail_page.content()
                finally:
                    await detail_page.close()

                match_soup = LexborHTMLParser(detail_html)
                tour_elem = match_soup.css_first("div.text-white.font-semibold.text-sm")
                category_tag = f"[{tour_elem.text(strip=True).upper()}] " if tour_elem else ""
                core_title = f"[{ev['kickoff']}] {category_tag}{ev['raw_title']}"
                time_to_kickoff = (start_dt - now).total_seconds()

                if time_to_kickoff <= EXTRACT_WINDOW_SEC:
                    stats["live"] += 1
                    watch_links = find_watch_links(detail_html)
                    extracted_any = False
                    if watch_links:
                        mins = int(time_to_kickoff // 60)
                        status = "LIVE" if mins <= 0 else f"sisa {mins} mnt"
                        print(f"\n⚡ Mengeksekusi ({status}): {core_title}")
                        for idx, link in enumerate(watch_links):
                            print(f"    📡 Menyadap Server {idx + 1}...")
                            m3u8_url, referer = await extract_m3u8(context, link)
                            if m3u8_url == CF_BLOCKED:
                                stats["cf_blocked"] += 1
                                print("      🛡️ Server masih menampilkan tantangan Cloudflare (pertahanan terlalu kuat) — lewati.")
                            elif m3u8_url:
                                print(f"      ✅ Sukses: {m3u8_url[:50]}...")
                                pipe = f"|Referer={referer}&User-Agent={USER_AGENT}"
                                label = f" [CH {idx + 1}]" if len(watch_links) > 1 else ""
                                all_streams.append([
                                    f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="LIVE - FootyStream",[🔴 LIVE] {core_title}{label}',
                                    f"{m3u8_url}{pipe}",
                                    "",
                                ])
                                extracted_any = True
                                stats["extracted"] += 1
                            else:
                                print("      ⚠️ Server tidak mengeluarkan .m3u8.")
                    if not extracted_any:
                        print(f"  ⏳ {core_title} -> tanam Dummy.")
                        all_streams.append([
                            f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                            DUMMY_LINK,
                            "",
                        ])
                else:
                    stats["upcoming"] += 1
                    print(f"  ⏳ {core_title} -> Jadwal masih jauh (> 1 Jam), tanam Dummy.")
                    all_streams.append([
                        f'#EXTINF:-1 tvg-logo="{ev["logo"]}" group-title="UPCOMING - FootyStream",[⏳ UPCOMING] {core_title}',
                        DUMMY_LINK,
                        "",
                    ])
            except Exception as e:
                stats["failed"] += 1
                print(f"  ❌ Melewati {ev['raw_title']}: {e}")

        await browser.close()

    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d/%m/%Y %H:%M WIB")
    header = ["#EXTM3U", f"# Last Updated: {ts}", ""]
    if all_streams:
        flat = [item for sub in all_streams for item in sub]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat))
        print(f"\n🏁 SELESAI: {len(all_streams)} entri -> {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada stream yang berhasil diekstrak saat ini."]))
        print("\n💀 Operasi selesai tanpa hasil buruan.")
    print(f"📊 Statistik: live/dieksekusi={stats['live']}, upcoming={stats['upcoming']}, "
          f"stream sukses={stats['extracted']}, cf_blocked={stats['cf_blocked']}, gagal={stats['failed']}")

if __name__ == "__main__":
    asyncio.run(main())
