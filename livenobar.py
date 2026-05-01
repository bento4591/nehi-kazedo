import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# --- KONFIGURASI MABES ENTERPRISE ---
API_URL = "https://apiy.cdnsport.xyz/api/v1/fixtures/live"
ORIGIN = "https://stream.livenobarseru.com"
REFERER = "https://stream.livenobarseru.com/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = "Livenobar_BoneTV.m3u8"

def main():
    print("🚀 Memulai Radar API LivenobarSeru MABES ENTERPRISE (Jalur VIP)...")
    all_streams = []

    headers = {
        "User-Agent": USER_AGENT,
        "Origin": ORIGIN,
        "Referer": REFERER,
        "Accept": "application/json"
    }

    try:
        print(f"Menyadap data dari: {API_URL}")
        response = requests.get(API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data_json = response.json()

        if data_json.get("success") and data_json.get("data"):
            sports = data_json["data"]
            
            # Membongkar brankas JSON
            for sport in sports:
                for league in sport.get("leagues", []):
                    for match in league.get("matches", []):
                        # 1. Merapikan Judul
                        title = match.get("title", "Live Match").replace(" VS ", " vs ")
                        
                        # 2. Mengambil Logo Tim Kandang (Home)
                        home_logo = match.get("home_team", {}).get("logo", "")
                        
                        # 3. Mengkonversi Timestamp menjadi Jam Kick-Off (WIB)
                        match_ts = match.get("match_timestamp")
                        kick_off_time = ""
                        if match_ts:
                            # Ubah timestamp server ke waktu Asia/Jakarta (WIB)
                            dt_obj = datetime.fromtimestamp(match_ts, tz=ZoneInfo("Asia/Jakarta"))
                            kick_off_time = dt_obj.strftime("%H:%M WIB")
                        else:
                            # Jika timestamp gagal, pakai waktu teks bawaan API
                            kick_off_time = match.get("match_time", "LIVE")

                        # Merakit Judul Tampilan Akhir
                        display_title = f"[🔴 LIVE {kick_off_time}] {title}"

                        # 4. Mengekstrak Link M3U8
                        live_sources = match.get("live_sources", [])
                        for source in live_sources:
                            m3u8_url = source.get("source")
                            
                            if m3u8_url and ".m3u8" in m3u8_url:
                                # Bersihkan URL jika ada escape character
                                m3u8_url = m3u8_url.replace("\\/", "/")
                                
                                print(f"  ✅ {display_title} -> {m3u8_url}")
                                
                                # Merakit Playlist dengan Logo dan Jam
                                all_streams.append([
                                    f'#EXTINF:-1 tvg-logo="{home_logo}" group-title="BONE TV - Livenobar",{display_title[:70]}',
                                    f'#EXTVLCOPT:http-referrer={REFERER}',
                                    f'#EXTVLCOPT:http-origin={ORIGIN}',
                                    f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                                    m3u8_url,
                                    ''
                                ])

        print(f"🎯 Ditemukan {len(all_streams)} link M3U8 murni dengan logo dan jadwal.")

    except Exception as e:
        print(f"❌ Terjadi kesalahan fatal saat menyadap API: {e}")

    # --- MENULIS HASIL KE FILE M3U8 ---
    if all_streams:
        ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        header = ['#EXTM3U', f'# Last Updated: {ts}', '']
        
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link berhasil disimpan ke {OUTPUT_FILE}.")
    else:
        print("\n💀 Operasi selesai. Tidak ada M3U8 (Mungkin tidak ada pertandingan live saat ini).")

if __name__ == "__main__":
    main()
