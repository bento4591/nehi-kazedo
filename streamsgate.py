"""
streamsgate.py (V2 - Playwright Edition)
─────────────────────────────────────────────────────────────────────────────
MABES ENTERPRISE - StreamsGate Scraper

PERUBAHAN DARI V1:
- API /data/{sport}.json sudah 404. Data sekarang di-render dinamis via JS.
- Menggunakan Playwright untuk membuka homepage dan mengambil semua link game.
- Mengunjungi setiap halaman game dan menangkap URL m3u8 dari network request.
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import re
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─── KONFIGURASI ─────────────────────────────────────────────────────────────

BASE_URL    = "https://streamsgates.io"
OUTPUT_FILE = Path("streamsgate.m3u8")
USER_AGENT  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Regex untuk menangkap URL m3u8 yang valid dari network
M3U8_REGEX  = re.compile(r'https?://[^\s"\']+\.m3u8[^\s"\']*')

# Timeout per halaman game (detik)
PAGE_TIMEOUT_MS = 20000

# Berapa banyak halaman game dibuka secara paralel
CONCURRENCY = 3

# ─── KAMUS LOGO ──────────────────────────────────────────────────────────────

SPORT_FALLBACK_LOGOS = {
    "soccer": "https://images.seeklogo.com/logo-png/48/1/soccer-ball-logo-png_seeklogo-480250.png",
    "mlb":    "https://images.seeklogo.com/logo-png/28/1/mlb-com-logo-png_seeklogo-288672.png",
    "nba":    "https://images.seeklogo.com/logo-png/24/1/nba-logo-png_seeklogo-247736.png",
    "nfl":    "https://images.seeklogo.com/logo-png/37/1/nfl-logo-png_seeklogo-375127.png",
    "nhl":    "https://images.seeklogo.com/logo-png/18/1/nhl-logo-png_seeklogo-183814.png",
    "ufc":    "https://images.seeklogo.com/logo-png/27/1/ufc-logo-png_seeklogo-272931.png",
    "box":    "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png",
    "f1":     "https://images.seeklogo.com/logo-png/33/1/formula-1-logo-png_seeklogo-330361.png",
    "misc":   "https://i.postimg.cc/qMm0rc3L/247.png",
}

TEAM_LOGOS = {
    # NBA
    "los angeles lakers": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png",
    "boston celtics": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    "golden state warriors": "https://a.espncdn.com/i/teamlogos/nba/500/gs.png",
    "miami heat": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png",
    "chicago bulls": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png",
    "atlanta hawks": "https://a.espncdn.com/i/teamlogos/nba/500/atl.png",
    "brooklyn nets": "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png",
    "charlotte hornets": "https://a.espncdn.com/i/teamlogos/nba/500/cha.png",
    "cleveland cavaliers": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png",
    "dallas mavericks": "https://a.espncdn.com/i/teamlogos/nba/500/dal.png",
    "denver nuggets": "https://a.espncdn.com/i/teamlogos/nba/500/den.png",
    "detroit pistons": "https://a.espncdn.com/i/teamlogos/nba/500/det.png",
    "houston rockets": "https://a.espncdn.com/i/teamlogos/nba/500/hou.png",
    "indiana pacers": "https://a.espncdn.com/i/teamlogos/nba/500/ind.png",
    "la clippers": "https://a.espncdn.com/i/teamlogos/nba/500/lac.png",
    "memphis grizzlies": "https://a.espncdn.com/i/teamlogos/nba/500/mem.png",
    "milwaukee bucks": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png",
    "minnesota timberwolves": "https://a.espncdn.com/i/teamlogos/nba/500/min.png",
    "new orleans pelicans": "https://a.espncdn.com/i/teamlogos/nba/500/no.png",
    "new york knicks": "https://a.espncdn.com/i/teamlogos/nba/500/ny.png",
    "oklahoma city thunder": "https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
    "orlando magic": "https://a.espncdn.com/i/teamlogos/nba/500/orl.png",
    "philadelphia 76ers": "https://a.espncdn.com/i/teamlogos/nba/500/phi.png",
    "phoenix suns": "https://a.espncdn.com/i/teamlogos/nba/500/phx.png",
    "portland trail blazers": "https://a.espncdn.com/i/teamlogos/nba/500/por.png",
    "sacramento kings": "https://a.espncdn.com/i/teamlogos/nba/500/sac.png",
    "san antonio spurs": "https://a.espncdn.com/i/teamlogos/nba/500/sa.png",
    "toronto raptors": "https://a.espncdn.com/i/teamlogos/nba/500/tor.png",
    "utah jazz": "https://a.espncdn.com/i/teamlogos/nba/500/uta.png",
    "washington wizards": "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png",
    # NHL
    "anaheim ducks": "https://a.espncdn.com/i/teamlogos/nhl/500/ana.png",
    "boston bruins": "https://a.espncdn.com/i/teamlogos/nhl/500/bos.png",
    "buffalo sabres": "https://a.espncdn.com/i/teamlogos/nhl/500/buf.png",
    "calgary flames": "https://a.espncdn.com/i/teamlogos/nhl/500/cgy.png",
    "carolina hurricanes": "https://a.espncdn.com/i/teamlogos/nhl/500/car.png",
    "chicago blackhawks": "https://a.espncdn.com/i/teamlogos/nhl/500/chi.png",
    "colorado avalanche": "https://a.espncdn.com/i/teamlogos/nhl/500/col.png",
    "columbus blue jackets": "https://a.espncdn.com/i/teamlogos/nhl/500/cbj.png",
    "dallas stars": "https://a.espncdn.com/i/teamlogos/nhl/500/dal.png",
    "detroit red wings": "https://a.espncdn.com/i/teamlogos/nhl/500/det.png",
    "edmonton oilers": "https://a.espncdn.com/i/teamlogos/nhl/500/edm.png",
    "florida panthers": "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png",
    "los angeles kings": "https://a.espncdn.com/i/teamlogos/nhl/500/la.png",
    "minnesota wild": "https://a.espncdn.com/i/teamlogos/nhl/500/min.png",
    "montreal canadiens": "https://a.espncdn.com/i/teamlogos/nhl/500/mtl.png",
    "nashville predators": "https://a.espncdn.com/i/teamlogos/nhl/500/nsh.png",
    "new jersey devils": "https://a.espncdn.com/i/teamlogos/nhl/500/nj.png",
    "new york islanders": "https://a.espncdn.com/i/teamlogos/nhl/500/nyi.png",
    "new york rangers": "https://a.espncdn.com/i/teamlogos/nhl/500/nyr.png",
    "ottawa senators": "https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
    "philadelphia flyers": "https://a.espncdn.com/i/teamlogos/nhl/500/phi.png",
    "pittsburgh penguins": "https://a.espncdn.com/i/teamlogos/nhl/500/pit.png",
    "san jose sharks": "https://a.espncdn.com/i/teamlogos/nhl/500/sj.png",
    "seattle kraken": "https://a.espncdn.com/i/teamlogos/nhl/500/sea.png",
    "st. louis blues": "https://a.espncdn.com/i/teamlogos/nhl/500/stl.png",
    "tampa bay lightning": "https://a.espncdn.com/i/teamlogos/nhl/500/tb.png",
    "toronto maple leafs": "https://a.espncdn.com/i/teamlogos/nhl/500/tor.png",
    "utah hockey club": "https://a.espncdn.com/i/teamlogos/nhl/500/utah.png",
    "vancouver canucks": "https://a.espncdn.com/i/teamlogos/nhl/500/van.png",
    "vegas golden knights": "https://a.espncdn.com/i/teamlogos/nhl/500/vgk.png",
    "washington capitals": "https://a.espncdn.com/i/teamlogos/nhl/500/wsh.png",
    "winnipeg jets": "https://a.espncdn.com/i/teamlogos/nhl/500/wpg.png",
    # MLB
    "arizona diamondbacks": "https://a.espncdn.com/i/teamlogos/mlb/500/ari.png",
    "atlanta braves": "https://a.espncdn.com/i/teamlogos/mlb/500/atl.png",
    "baltimore orioles": "https://a.espncdn.com/i/teamlogos/mlb/500/bal.png",
    "boston red sox": "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png",
    "chicago cubs": "https://a.espncdn.com/i/teamlogos/mlb/500/chc.png",
    "chicago white sox": "https://a.espncdn.com/i/teamlogos/mlb/500/chw.png",
    "cincinnati reds": "https://a.espncdn.com/i/teamlogos/mlb/500/cin.png",
    "cleveland guardians": "https://a.espncdn.com/i/teamlogos/mlb/500/cle.png",
    "colorado rockies": "https://a.espncdn.com/i/teamlogos/mlb/500/col.png",
    "detroit tigers": "https://a.espncdn.com/i/teamlogos/mlb/500/det.png",
    "houston astros": "https://a.espncdn.com/i/teamlogos/mlb/500/hou.png",
    "kansas city royals": "https://a.espncdn.com/i/teamlogos/mlb/500/kc.png",
    "los angeles angels": "https://a.espncdn.com/i/teamlogos/mlb/500/laa.png",
    "los angeles dodgers": "https://a.espncdn.com/i/teamlogos/mlb/500/lad.png",
    "miami marlins": "https://a.espncdn.com/i/teamlogos/mlb/500/mia.png",
    "milwaukee brewers": "https://a.espncdn.com/i/teamlogos/mlb/500/mil.png",
    "minnesota twins": "https://a.espncdn.com/i/teamlogos/mlb/500/min.png",
    "new york mets": "https://a.espncdn.com/i/teamlogos/mlb/500/nym.png",
    "new york yankees": "https://a.espncdn.com/i/teamlogos/mlb/500/nyy.png",
    "oakland athletics": "https://a.espncdn.com/i/teamlogos/mlb/500/oak.png",
    "philadelphia phillies": "https://a.espncdn.com/i/teamlogos/mlb/500/phi.png",
    "pittsburgh pirates": "https://a.espncdn.com/i/teamlogos/mlb/500/pit.png",
    "san diego padres": "https://a.espncdn.com/i/teamlogos/mlb/500/sd.png",
    "san francisco giants": "https://a.espncdn.com/i/teamlogos/mlb/500/sf.png",
    "seattle mariners": "https://a.espncdn.com/i/teamlogos/mlb/500/sea.png",
    "st. louis cardinals": "https://a.espncdn.com/i/teamlogos/mlb/500/stl.png",
    "tampa bay rays": "https://a.espncdn.com/i/teamlogos/mlb/500/tb.png",
    "texas rangers": "https://a.espncdn.com/i/teamlogos/mlb/500/tex.png",
    "toronto blue jays": "https://a.espncdn.com/i/teamlogos/mlb/500/tor.png",
    "washington nationals": "https://a.espncdn.com/i/teamlogos/mlb/500/wsh.png",
    # Soccer - EPL
    "arsenal": "https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
    "chelsea": "https://a.espncdn.com/i/teamlogos/soccer/500/363.png",
    "aston villa": "https://a.espncdn.com/i/teamlogos/soccer/500/362.png",
    "bournemouth": "https://a.espncdn.com/i/teamlogos/soccer/500/349.png",
    "brentford": "https://a.espncdn.com/i/teamlogos/soccer/500/337.png",
    "brighton & hove albion": "https://a.espncdn.com/i/teamlogos/soccer/500/331.png",
    "crystal palace": "https://a.espncdn.com/i/teamlogos/soccer/500/384.png",
    "everton": "https://a.espncdn.com/i/teamlogos/soccer/500/368.png",
    "fulham": "https://a.espncdn.com/i/teamlogos/soccer/500/370.png",
    "ipswich town": "https://a.espncdn.com/i/teamlogos/soccer/500/394.png",
    "leicester city": "https://a.espncdn.com/i/teamlogos/soccer/500/375.png",
    "liverpool": "https://a.espncdn.com/i/teamlogos/soccer/500/364.png",
    "manchester city": "https://a.espncdn.com/i/teamlogos/soccer/500/382.png",
    "manchester united": "https://a.espncdn.com/i/teamlogos/soccer/500/360.png",
    "newcastle united": "https://a.espncdn.com/i/teamlogos/soccer/500/361.png",
    "nottingham forest": "https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
    "southampton": "https://a.espncdn.com/i/teamlogos/soccer/500/376.png",
    "tottenham hotspur": "https://a.espncdn.com/i/teamlogos/soccer/500/367.png",
    "west ham united": "https://a.espncdn.com/i/teamlogos/soccer/500/371.png",
    "wolverhampton wanderers": "https://a.espncdn.com/i/teamlogos/soccer/500/380.png",
    # Soccer - La Liga
    "atletico madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/1068.png",
    "barcelona": "https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
    "real madrid": "https://a.espncdn.com/i/teamlogos/soccer/500/86.png",
    "real betis": "https://a.espncdn.com/i/teamlogos/soccer/500/244.png",
    "real sociedad": "https://a.espncdn.com/i/teamlogos/soccer/500/89.png",
    "sevilla": "https://a.espncdn.com/i/teamlogos/soccer/500/243.png",
    "valencia": "https://a.espncdn.com/i/teamlogos/soccer/500/94.png",
    "villarreal": "https://a.espncdn.com/i/teamlogos/soccer/500/102.png",
    # Soccer - Serie A
    "ac milan": "https://a.espncdn.com/i/teamlogos/soccer/500/115.png",
    "atalanta": "https://a.espncdn.com/i/teamlogos/soccer/500/103.png",
    "fiorentina": "https://a.espncdn.com/i/teamlogos/soccer/500/108.png",
    "inter milan": "https://a.espncdn.com/i/teamlogos/soccer/500/111.png",
    "juventus": "https://a.espncdn.com/i/teamlogos/soccer/500/112.png",
    "lazio": "https://a.espncdn.com/i/teamlogos/soccer/500/113.png",
    "napoli": "https://a.espncdn.com/i/teamlogos/soccer/500/116.png",
    "roma": "https://a.espncdn.com/i/teamlogos/soccer/500/118.png",
    # Others
    "bayern munich": "https://a.espncdn.com/i/teamlogos/soccer/500/132.png",
    "paris saint-germain": "https://a.espncdn.com/i/teamlogos/soccer/500/160.png",
}

def get_logo(team_name: str, sport: str) -> str:
    clean = str(team_name).lower().strip()
    return TEAM_LOGOS.get(clean, SPORT_FALLBACK_LOGOS.get(sport, SPORT_FALLBACK_LOGOS["misc"]))

def detect_sport_from_url(url: str) -> str:
    """Deteksi jenis olahraga dari slug URL game."""
    url_lower = url.lower()
    if any(k in url_lower for k in ["-nhl-", "-hockey-", "kraken", "canucks", "knights", "flames", "rangers-", "bruins", "ducks", "panthers-nhl"]):
        return "nhl"
    if any(k in url_lower for k in ["-nba-", "-basketball-", "lakers", "celtics", "warriors-", "nuggets", "clippers", "raptors"]):
        return "nba"
    if any(k in url_lower for k in ["-mlb-", "-baseball-", "dodgers", "yankees", "braves", "astros", "padres"]):
        return "mlb"
    if any(k in url_lower for k in ["-nfl-", "-football-", "patriots", "cowboys", "chiefs", "eagles-", "lions-", "panthers-nfl"]):
        return "nfl"
    if any(k in url_lower for k in ["-ufc-", "-mma-"]):
        return "ufc"
    if any(k in url_lower for k in ["-f1-", "-formula"]):
        return "f1"
    if any(k in url_lower for k in ["-boxing-", "-box-"]):
        return "box"
    return "soccer"

# ─── TAHAP 1: Ambil Semua Link Game dari Homepage ─────────────────────────────

async def get_game_links(browser) -> list[dict]:
    """
    Membuka homepage streamsgates.io menggunakan Playwright.
    Menunggu semua kartu game ter-render, lalu mengambil semua link /watch.php?game=
    beserta judul pertandingan dan status LIVE.
    """
    page = await browser.new_page()
    games = []
    try:
        await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        # Tunggu kartu game muncul
        await page.wait_for_selector("a.game-tile", timeout=15000)

        # Ambil semua link kartu game
        cards = await page.query_selector_all("a.game-tile")
        for card in cards:
            href  = await card.get_attribute("href") or ""
            title = await card.inner_text()
            # Cek apakah statusnya LIVE
            is_live = "LIVE" in (title.upper())

            if "/watch.php?game=" in href:
                full_url  = BASE_URL + href if href.startswith("/") else href
                game_slug = href.split("game=")[-1]
                # Ambil nama tim dari judul kartu (biasanya "Tim A vs Tim B")
                clean_title = re.sub(r'[\n\r]+', ' ', title).strip()
                games.append({
                    "url":    full_url,
                    "slug":   game_slug,
                    "title":  clean_title,
                    "is_live": is_live,
                })
        print(f"  📋 Ditemukan {len(games)} game di homepage ({sum(1 for g in games if g['is_live'])} LIVE)")
    except Exception as e:
        print(f"  ⚠️  Gagal membuka homepage: {e}")
    finally:
        await page.close()
    return games

# ─── TAHAP 2: Buka Tiap Halaman Game & Tangkap M3U8 ─────────────────────────

async def extract_m3u8_from_game(browser, game: dict) -> list[str]:
    """
    Membuka halaman watch game menggunakan Playwright.
    Menangkap semua URL m3u8 dari network request.
    Mengembalikan list URL m3u8 unik yang berhasil ditangkap.
    """
    page = await browser.new_page()
    captured = []
    seen     = set()

    async def on_request(request):
        url = request.url
        if ".m3u8" in url and url not in seen:
            seen.add(url)
            captured.append(url)

    page.on("request", on_request)

    try:
        # Blokir iklan dan tracker agar loading lebih cepat
        await page.route(
            "**/*",
            lambda route: route.abort()
            if any(x in route.request.url for x in [
                "histats.com", "aclib.net", "popunder", "adnxs", "doubleclick",
                "googlesyndication", "adsystem", ".woff", ".woff2", ".ttf",
            ])
            else route.continue_()
        )

        await page.goto(game["url"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)

        # Tunggu m3u8 muncul (max 15 detik)
        for _ in range(15):
            if captured:
                break
            await asyncio.sleep(1)

    except PlaywrightTimeout:
        print(f"  ⏱️  Timeout: {game['title'][:50]}")
    except Exception as e:
        print(f"  ⚠️  Error [{game['title'][:40]}]: {e}")
    finally:
        await page.close()

    # Deduplikasi: buang token dari URL untuk perbandingan
    unique = []
    seen_base = set()
    for url in captured:
        base = url.split("?")[0]
        if base not in seen_base:
            seen_base.add(base)
            unique.append(url)

    return unique

# ─── PEMROSESAN PARALEL ───────────────────────────────────────────────────────

async def process_games_parallel(browser, games: list[dict]) -> list[dict]:
    """Proses semua game secara paralel dengan batas CONCURRENCY."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results   = []

    async def process_one(game):
        async with semaphore:
            m3u8_list = await extract_m3u8_from_game(browser, game)
            return game, m3u8_list

    tasks    = [process_one(g) for g in games]
    settled  = await asyncio.gather(*tasks, return_exceptions=True)

    for result in settled:
        if isinstance(result, Exception):
            continue
        game, m3u8_list = result
        if m3u8_list:
            results.append({"game": game, "m3u8_list": m3u8_list})
            print(f"  ✅ {len(m3u8_list)} URL | {game['title'][:60]}")
        else:
            print(f"  ❌ Nihil | {game['title'][:60]}")

    return results

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    print("🚀 StreamsGate Scraper V2 (Playwright) starting...")
    now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
    ts_str  = now_wib.strftime("%Y-%m-%d %H:%M WIB")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio",
            ]
        )

        # ── TAHAP 1: Ambil daftar game dari homepage ──────────────────────────
        print("\n📡 TAHAP 1: Membaca daftar game dari homepage...")
        games = await get_game_links(browser)

        if not games:
            print("💀 Tidak ada game yang ditemukan di homepage.")
            await browser.close()
            return

        # Prioritaskan game yang LIVE
        live_games     = [g for g in games if g["is_live"]]
        upcoming_games = [g for g in games if not g["is_live"]]
        ordered_games  = live_games + upcoming_games

        print(f"\n🎯 TAHAP 2: Mengekstrak M3U8 dari {len(ordered_games)} game...")

        # ── TAHAP 2: Buka tiap halaman & tangkap M3U8 ─────────────────────────
        results = await process_games_parallel(browser, ordered_games)
        await browser.close()

    # ── TAHAP 3: Tulis M3U8 ───────────────────────────────────────────────────
    if not results:
        print("\n❌ Tidak ada M3U8 yang berhasil ditangkap.")
        return

    playlist_lines = [
        "#EXTM3U",
        f"# StreamsGate - MABES ENTERPRISE V2",
        f"# Last Updated: {ts_str}",
        "",
    ]

    seen_m3u8      = set()
    server_counts  = defaultdict(int)
    total_channels = 0

    for item in results:
        game       = item["game"]
        m3u8_list  = item["m3u8_list"]
        title      = game["title"]
        sport      = detect_sport_from_url(game["url"])

        # Cari nama tim dari judul (format: "Tim A VS Tim B [LIVE]")
        team_match = re.search(r'^(.+?)\s+(?:vs|VS|v)\s+(.+?)(?:\s+\[|\s*$)', title, re.IGNORECASE)
        home_team  = team_match.group(1).strip() if team_match else title
        logo       = get_logo(home_team, sport)
        status_tag = "[🔴 LIVE]" if game["is_live"] else "[⏰ UPCOMING]"
        group      = sport.upper()

        for i, m3u8_url in enumerate(m3u8_list, start=1):
            base_url = m3u8_url.split("?")[0]
            if base_url in seen_m3u8:
                continue
            seen_m3u8.add(base_url)

            server_counts[title] += 1
            count = server_counts[title]
            server_label = f" [S{count}]" if count > 1 else ""
            channel_name = f"{status_tag} [{group}] {title}{server_label}"

            # Ambil origin dari URL m3u8 (untuk Referer)
            try:
                from urllib.parse import urlparse
                parsed   = urlparse(m3u8_url)
                origin   = f"{parsed.scheme}://{parsed.netloc}"
                referer  = origin + "/"
            except Exception:
                origin  = BASE_URL
                referer = BASE_URL + "/"

            playlist_lines.extend([
                f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{sport.upper()}.sg.tv" group-title="BONE TV - StreamsGate",{channel_name}',
                f'#EXTVLCOPT:http-referrer={referer}',
                f'#EXTVLCOPT:http-origin={origin}',
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                m3u8_url,
                "",
            ])
            total_channels += 1

    OUTPUT_FILE.write_text("\n".join(playlist_lines), encoding="utf-8")
    print(f"\n🏁 SELESAI! {total_channels} channel unik disimpan ke {OUTPUT_FILE}")
    print(f"   ({len(results)} game berhasil | {len(games) - len(results)} game nihil)")

if __name__ == "__main__":
    asyncio.run(main())
