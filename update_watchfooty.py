#!/usr/bin/env python3

import asyncio
import json
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
# Terowongan Proxy Cloudflare Kapten
PROXY_URL = "https://watchfooty99.iwansandra1974.workers.dev/?url="

BASE_DOMAIN = "watchfooty.st"
API_URL = f"https://api.{BASE_DOMAIN}"
BASE_URL = f"https://www.{BASE_DOMAIN}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Referer": BASE_URL + "/"}
OUTPUT_FILE = "Watchfooty_BoneTV.m3u8"

TV_INFO = {
    "soccer": ("Soccer.Dummy.us", "https://i.postimg.cc/HsWHFvV0/Soccer.png", "Soccer"),
    "mlb": ("MLB.Baseball.Dummy.us", "https://i.postimg.cc/FsFmwC7K/Baseball3.png", "MLB"),
    "nba": ("NBA.Basketball.Dummy.us", "https://i.postimg.cc/jdqKB3LW/Basketball-2.png", "NBA"),
    "nfl": ("Football.Dummy.us", "https://i.postimg.cc/tRNpSGCq/Maxx.png", "NFL"),
    "nhl": ("NHL.Hockey.Dummy.us", "https://i.postimg.cc/mgMRQ7FR/nhl-logo-png-seeklogo-534236.png", "NHL"),
    "ufc": ("UFC.Fight.Pass.Dummy.us", "https://i.postimg.cc/59Sb7W9D/Combat-Sports2.png", "UFC"),
    "misc": ("Sports.Dummy.us", "https://i.postimg.cc/qMm0rc3L/247.png", "Random Events"),
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_tv_data(sport_name):
    key = sport_name.lower().strip()
    for k, v in TV_INFO.items():
        if k in key: return v
    return TV_INFO["misc"]

def get_wfty_live_events():
    print(f"Mencari jadwal LIVE di API {BASE_DOMAIN}...")
    url = f"{API_URL}/_internal/trpc/sports.getPopularLiveMatches"
    params = {"batch": "1", "input": '{"0":{"json":null,"meta":{"values":["undefined"]}}}'}
    try:
        r = SESSION.get(url, params=params, timeout=15)
        api_data = r.json()[0].get("result", {}).get("data", {}).get("json", [])
        return api_data
    except Exception as e:
        print(f"Gagal akses API WFTY: {e}")
        return []

def get_embed_data(event_id):
    url = f"{API_URL}/_internal/trpc/sports.getMatchById"
    input_data = {"0": {"json": {"id": event_id, "withoutAdditionalInfo": True, "withoutLinks": False}}}
    params = {"batch": "1", "input": json.dumps(input_data)}
    try:
        r = SESSION.get(url, params=params, timeout=10)
        api_data = r.json()[0].get("result", {}).get("data", {}).get("json", {})
        links = api_data.get("fixtureData", {}).get("links", [])
        valid_links = [l for l in links if l.get("wld") and "e" not in l.get("wld")]
        if not valid_links: return None
        best = sorted(valid_links, key=lambda x: x.get("viewerCount", -1), reverse=True)[0]
        gi, t = best.get("gi"), best.get("t")
        cn, sn = best.get("wld", {}).get("cn"), best.get("wld", {}).get("sn")
        return f"https://sportsembed.su/embed/{gi}/{t}/{cn}/{sn}?player=clappr&autoplay=true"
    except: return None

# PASUKAN PENEMBUS JS OBFUSCATOR (Playwright)
async def extract_m3u8_playwright(page, url):
    stream_url = None
    def handle_request(request):
        nonlocal stream_url
        if ".m3u8" in request.url and "ad" not in request.url.lower():
            if not stream_url: stream_url = request.url

    page.on("request", handle_request)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000) # Tunggu JS decrypt berjalan
        
        # Coba klik tombol play jika ada
        try:
            btn = page.locator("button.streambutton").first
            if await btn.count() > 0: await btn.dblclick(force=True, timeout=2000)
        except: pass

        # Cek source dari player
        try:
            src = await page.evaluate("() => clapprPlayer.options.source")
            if src and ".m3u8" in src: stream_url = src
        except: pass
    except: pass

    page.remove_listener("request", handle_request)
    return stream_url

async def main():
    events = get_wfty_live_events()
    if not events:
        print("Tidak ada jadwal LIVE.")
        return

    all_streams = []
    print(f"Menemukan {len(events)} jadwal. Menyiapkan Mesin Playwright...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        for ev in events:
            title = ev.get("title", "Unknown Event")
            league = ev.get("league") or "Misc"
            print(f"Memproses: {title}")
            
            embed_url = get_embed_data(ev.get("id"))
            if not embed_url: continue
            
            # Ekstrak M3U8 Murni
            raw_m3u8 = await extract_m3u8_playwright(page, embed_url)
            
            if raw_m3u8:
                # BUNGKUS DENGAN PROXY CLOUDFLARE
                proxied_url = f"{PROXY_URL}{quote(raw_m3u8)}"
                
                tvg_id, logo, group_name = get_tv_data(league)
                full_title = f"[🔴 LIVE] [{league.upper()}] {title} - WFTY"
                
                all_streams.append([
                    f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="BONE TV - Watchfooty",{full_title}',
                    f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                    proxied_url,
                    ''
                ])
                print(f"  ✅ Sukses di-proxy!")
            else:
                print(f"  ❌ Gagal menembus enkripsi.")

        await browser.close()

    if all_streams:
        ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        header = ['#EXTM3U', f'# Last Updated: {ts}', '']
        
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link siap tempur.")

if __name__ == "__main__":
    asyncio.run(main())
