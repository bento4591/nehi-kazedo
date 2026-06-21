import asyncio
from functools import partial
from urllib.parse import urljoin
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.async_api import Browser, Page

from .utils import Cache, Time, get_logger, leagues, network

log = get_logger(__name__)

urls: dict[str, dict[str, str | float]] = {}

TAG = "EMBEDHD"

CACHE_FILE = Cache(TAG, exp=5_400)

API_FILE = Cache(f"{TAG}-api", exp=28_800)

BASE_URL = "https://embedhd.org"


def fix_league(s: str) -> str:
    return " ".join(x.capitalize() for x in s.split()) if len(s) > 5 else s.upper()


async def process_event(
    url: str,
    url_num: int,
    page: Page,
) -> str | None:

    captured: list[str] = []

    got_one = asyncio.Event()

    handler = partial(
        network.capture_req,
        captured=captured,
        got_one=got_one,
    )

    page.on("request", handler)

    try:
        resp = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=6_000,
            referer=BASE_URL,
        )

        if not resp or resp.status != 200:
            log.warning(
                f"URL {url_num}) Status Code: {resp.status if resp else 'None'}"
            )
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

            # --- TAKTIK BARU: Konversi Waktu WIB & Penentuan Status ---
            try:
                ts_et = int(event["ts_et"])
                dt_utc = datetime.fromtimestamp(ts_et, tz=timezone.utc)
                dt_wib = dt_utc.astimezone(ZoneInfo("Asia/Jakarta"))
                kickoff_wib = dt_wib.strftime("%H:%M WIB")
                
                # Tentukan Status berdasarkan waktu server saat ini
                if datetime.now(timezone.utc) >= dt_utc:
                    status_tag = "🔴 LIVE"
                else:
                    status_tag = "⏳ UPCOMING"
            except Exception:
                kickoff_wib = "UNKNOWN"
                status_tag = "🔴 LIVE"

            # Sisipkan Tag dan Jam ke dalam Nama Event
            formatted_event_name = f"[{status_tag}] [{kickoff_wib}] {raw_event_name}"

            # Pengecekan Cache Fleksibel
            match_suffix = f"{raw_event_name} ({TAG})"
            if any(c_key.endswith(match_suffix) for c_key in cached_keys):
                continue

            if not (event_streams := event["streams"]):
                continue

            elif not (event_link := event_streams[0].get("link")):
                continue

            events.append(
                {
                    "sport": sport,
                    "event": formatted_event_name,
                    "link": event_link,
                    "timestamp": now.timestamp(),
                }
            )

    return events


async def scrape(browser: Browser) -> None:
    cached_urls = CACHE_FILE.load()

    valid_urls = {k: v for k, v in cached_urls.items() if v["url"]}

    valid_count = cached_count = len(valid_urls)

    urls.update(valid_urls)

    log.info(f"Loaded {cached_count} event(s) from cache")

    log.info(f'Scraping from "{BASE_URL}"')

    if events := await get_events(cached_urls.keys()):
        log.info(f"Processing {len(events)} new URL(s)")

        async with network.event_context(browser) as context:
            for i, ev in enumerate(events, start=1):
                async with network.event_page(context) as page:
                    handler = partial(
                        process_event,
                        url=(link := ev["link"]),
                        url_num=i,
                        page=page,
                    )

                    url = await network.safe_process(
                        handler,
                        url_num=i,
                        semaphore=network.PW_S,
                        log=log,
                    )

                    sport, event, ts = (
                        ev["sport"],
                        ev["event"],
                        ev["timestamp"],
                    )

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
