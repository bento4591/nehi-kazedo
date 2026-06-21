import os
import sys
import asyncio
from functools import partial
from urllib.parse import urljoin
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 🛡️ INJEKSI JALUR AMAN: Memaksa Python mengenali file/folder utils di lingkungan GitHub Actions
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import Browser, Page, async_playwright
from utils import Cache, Time, get_logger, leagues, network

log = get_logger(__name__)

urls: dict[str, dict[str, str | float]] = {}

TAG = "EMBEDHD"
OUTPUT_FILE = "embedhd.m3u8"
DUMMY_LINK = "https://raw.githubusercontent.com/iwanfalstv/Nyetlu/refs/heads/main/njing/output.m3u8"

CACHE_FILE = Cache(TAG, exp=5_400)
API_FILE = Cache(f"{TAG}-api", exp=28_800)
BASE_URL = "https://embedhd.org"


def fix_league(s: str) -> str:
    return " ".join(x.capitalize() for x in s.split()) if len(s) > 5 else s.upper()


async def process_event(url: str, url_num: int, page: Page) -> str | None:
    captured: list[str] = []
    got_one = asyncio.Event()

    handler = partial(network.capture_req, captured=captured, got_one=got_one)
    page.on("request", handler)

    try:
        resp = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=6_000,
            referer=BASE_URL,
        )

        if not resp or resp.status != 200:
            log.warning(f"URL {url_num}) Status Code: {resp.status if resp else 'None'}")
            return

        wait_task = asyncio.create_task(got_one.wait())
        try:
            await asyncio.wait_for(wait_task, timeout=6)
        except asyncio.TimeoutError:
            log.warning(f"URL {url_num}) Timed out waiting for M3U8.")
            return
        finally:
            if not wait_task.done():
                wait_task.cancel()
                try:
                    await wait_task
                except asyncio.CancelledError:
                    pass

        if captured:
            log.info(f"URL {url_num}) Captured M3U8")
            return captured[0]

    except Exception as e:
        log.warning(f"URL {url_num}) {e}")
        return
    finally:
        page.remove_listener("request", handler)


async def get_events(cached_keys: list[str]) -> list[dict[str, str]]:
    now = Time.clean(Time.now())

    if not (api_data := API_FILE.load(per_entry=False)):
        log.info("Refreshing API cache")
        api_data = {"timestamp": now.timestamp()}
        if r := await network.request(urljoin(BASE_URL, "api-event.php"), log=log):
            api_data: dict = r.json()
            api_data["timestamp"] = now.timestamp()
        API_FILE.write(api_data)

    events = []
    start_dt = now.delta(hours=-3)
    end_dt = now.delta(minutes=30)

    for info in api_data.get("days", []):
        for event in info["items"]:
            if (event_league := event["league"]) == "channel tv":
                continue

            event_dt = Time.from_ts(event["ts_et"])
            if not start_dt <= event_dt <= end_dt:
                continue

            sport = fix_league(event_league)
            raw_event_name = event["title"]

            try:
                ts_et = int(event["ts_et"])
                dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                kickoff_wib = dt_wib.strftime("%H:%M WIB")
                
                if datetime.now(timezone.utc) >= dt_utc:
                    status_tag = "🔴 LIVE"
                else:
                    status_tag = "⏳ UPCOMING"
            except Exception:
                kickoff_wib = "UNKNOWN"
                status_tag = "🔴 LIVE"

            formatted_event_name = f"[{status_tag}] [{kickoff_wib}] {raw_event_name}"
            match_suffix = f"{raw_event_name} ({TAG})"
            
            if any(c_key.endswith(match_suffix) for c_key in cached_keys):
                continue

            if not (event_streams := event["streams"]):
                continue
            elif not (event_link := event_streams[0].get("link")):
                continue

            events.append({
                "sport": sport,
                "event": formatted_event_name,
                "link": event_link,
                "timestamp": now.timestamp(),
                "status_tag": status_tag
            })

    return events


async def scrape(browser: Browser) -> None:
    cached_urls = CACHE_FILE.load()
    valid_urls = {k: v for k, v in cached_urls.items() if v["url"]}
    valid_count = cached_count = len(valid_urls)
    urls.update(valid_urls)

    log.info(f"Loaded {cached_count} event(s) from cache")
    log.info(f'Scraping from "{BASE_URL}"')

    if events := await get_events(list(cached_urls.keys())):
        log.info(f"Processing {len(events)} new URL(s)")

        async with network.event_context(browser) as context:
            for i, ev in enumerate(events, start=1):
                link = ev["link"]
                status_tag = ev["status_tag"]
                
                if status_tag == "⏳ UPCOMING":
                    log.info(f"URL {i}) [UPCOMING] Menanamkan Dummy Link.")
                    url = DUMMY_LINK
                else:
                    async with network.event_page(context) as page:
                        handler = partial(process_event, url=link, url_num=i, page=page)
                        url = await network.safe_process(handler, url_num=i, semaphore=network.PW_S, log=log)

                sport, event, ts = ev["sport"], ev["event"], ev["timestamp"]
                tvg_id, logo = leagues.get_tvg_info(sport, event)
                key = f"[{sport}] {event} ({TAG})"

                entry = {
                    "url": url,
                    "logo": logo,
                    "base": "https://exposestrat.com",
                    "timestamp": ts,
                    "id": tvg_id or "Live.Event.us",
                    "link": link,
                }

                cached_urls[key] = entry

                if url:
                    valid_count += 1
                    urls[key] = entry

        log.info(f"Collected and cached {valid_count - cached_count} new event(s)")
    else:
        log.info("No new events found")

    CACHE_FILE.write(cached_urls)


async def main():
    print("🚀 Memulai Operasi MABES ENTERPRISE: EmbedHD Scraper...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--mute-audio"])
        await scrape(browser)
        await browser.close()
        
    print("🎯 Membangun file M3U8 EmbedHD...")
    ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
    header = ['#EXTM3U', f'# Last Updated: {ts}', '']
    
    playlist_lines = []
    for key, info in urls.items():
        if info["url"]:
            group_title = "LIVE - EmbedHD" if "🔴 LIVE" in key else "UPCOMING - EmbedHD"
            
            extinf = f'#EXTINF:-1 tvg-id="{info["id"]}" tvg-logo="{info["logo"]}" group-title="{group_title}",{key}'
            playlist_lines.append(extinf)
            
            if info["url"] == DUMMY_LINK:
                playlist_lines.append(info["url"])
            else:
                playlist_lines.append(f'{info["url"]}|Referer={BASE_URL}/')
            
            playlist_lines.append("")
            
    if playlist_lines:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + playlist_lines))
        print(f"🏁 SELESAI! Berhasil mengunci link ke {OUTPUT_FILE}")
    else:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + ["# Tidak ada siaran yang aktif saat ini."]))
        print("💀 Operasi selesai tanpa hasil buruan.")


if __name__ == "__main__":
    asyncio.run(main())
