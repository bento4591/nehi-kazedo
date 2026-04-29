import asyncio
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

# --- KONFIGURASI UTAMA ---
# GANTI INI dengan URL Cloudflare Worker Anda nanti
WORKER_RESOLVER_URL = "https://watchfooty99.iwansandra1974.workers.dev/"

BASE_DOMAIN = "watchfooty.st"
API_URL = f"https://api.{BASE_DOMAIN}"
BASE_URL = f"https://www.{BASE_DOMAIN}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

def get_tv_data(sport_name):
    key = sport_name.lower().strip()
    for k, v in TV_INFO.items():
        if k in key: return v
    return TV_INFO["misc"]

def get_live_events():
    print(f"🚀 [GitHub] Menyapu API {BASE_DOMAIN}...")
    url = f"{API_URL}/_internal/trpc/sports.getPopularLiveMatches"
    params = {"batch": "1", "input": '{"0":{"json":None,"meta":{"values":["undefined"]}}}'}
    
    try:
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
        api_data = r.json()[0].get("result", {}).get("data", {}).get("json", [])
        return api_data
    except: return []

def get_embed_url(event_id):
    url = f"{API_URL}/_internal/trpc/sports.getMatchById"
    input_data = {"0": {"json": {"id": event_id, "withoutAdditionalInfo": True, "withoutLinks": False}}}
    params = {"batch": "1", "input": json.dumps(input_data)}
    
    try:
        r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
        api_data = r.json()[0].get("result", {}).get("data", {}).get("json", {})
        links = api_data.get("fixtureData", {}).get("links", [])
        if not links: return None
        
        # Ambil link terbaik (viewer terbanyak)
        best = sorted(links, key=lambda x: x.get("viewerCount", 0), reverse=True)[0]
        gi, t = best.get("gi"), best.get("t")
        cn, sn = best.get("wld", {}).get("cn"), best.get("wld", {}).get("sn")
        return f"https://sportsembed.su/embed/{gi}/{t}/{cn}/{sn}?player=clappr&autoplay=true"
    except: return None

def main():
    events = get_live_events()
    if not events:
        print("💀 Tidak ada pertandingan LIVE.")
        return

    playlist = ["#EXTM3U", f"# Last Updated: {datetime.now(ZoneInfo('Asia/Jakarta')).strftime('%Y-%m-%d %H:%M WIB')}\n"]

    for ev in events:
        title = ev.get("title", "Unknown Event")
        league = ev.get("league") or "Misc"
        embed_url = get_embed_url(ev.get("id"))
        
        if embed_url:
            # KONSTRUKSI LINK RESOLVER CLOUDFLARE
            resolver_link = f"{WORKER_RESOLVER_URL}/?url={quote(embed_url)}"
            
            tvg_id, logo, group = get_tv_data(league)
            full_title = f"[🔴 LIVE] [{league}] {title} - WFTY"
            
            playlist.extend([
                f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tvg_id}" group-title="BONE TV - Watchfooty",{full_title}',
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                resolver_link,
                ''
            ])
            print(f"✅ Terjaring: {title}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    print(f"🏁 Selesai! File {OUTPUT_FILE} siap digunakan.")

if __name__ == "__main__":
    main()

