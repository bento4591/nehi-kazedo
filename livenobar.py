import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

# --- KONFIGURASI MABES ENTERPRISE ---
BASE_URL = "https://stream.livenobarseru.com/id"
ORIGIN = "https://stream.livenobarseru.com"
REFERER = "https://stream.livenobarseru.com/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
OUTPUT_FILE = "Livenobar_BoneTV.m3u8"

async def extract_m3u8(context, match_url, match_title):
    """Fungsi intelijen untuk masuk ke halaman pertandingan dan mengendus M3U8"""
    page = await context.new_page()
    m3u8_link = None

    # Pasang Radar Network
    def handle_request(request):
        nonlocal m3u8_link
        # Cari file .m3u8, abaikan iklan atau master playlist palsu jika ada
        if ".m3u8" in request.url and "ad" not in request.url.lower() and not m3u8_link:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        print(f"  🔍 Mengendus: {match_title}")
        await page.goto(match_url, wait_until="domcontentloaded", timeout=25000)
        
        # Tunggu sebentar agar player video merender dan memanggil M3U8
        await page.wait_for_timeout(5000) 
        
        # Pancing video agar berputar jika belum
        try:
            play_btn = page.locator("button.vjs-big-play-button, .play-wrapper").first
            if await play_btn.count() > 0:
                await play_btn.click(timeout=2000)
                await page.wait_for_timeout(3000)
        except:
            pass

    except Exception as e:
        print(f"  ❌ Gagal memuat halaman: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()

    return m3u8_link

async def main():
    print("🚀 Memulai Radar LivenobarSeru MABES ENTERPRISE...")
    all_streams = []

    async with async_playwright() as p:
        # Jalankan Chromium dengan penyamaran penuh
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers={
                "Origin": ORIGIN,
                "Referer": REFERER,
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        )
        
        main_page = await context.new_page()
        
        try:
            print("Membuka halaman utama...")
            await main_page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            await main_page.wait_for_timeout(4000) # Biarkan list pertandingan termuat sempurna
            
            print("Mencari pertandingan LIVE (Status 'Tonton')...")
            
            # TAKTIK BARU: Mencari tag <a> yang membungkus span berteks "Tonton"
            # Berdasarkan inspeksi elemen Kapten yang sangat akurat
            match_elements = await main_page.locator("a").filter(has=main_page.locator("span", has_text="Tonton")).all()

            target_links = []
            for el in match_elements:
                href = await el.get_attribute("href")
                if href:
                    # Gabungkan URL jika path-nya relatif
                    full_url = href if href.startswith("http") else f"{ORIGIN}{href}"
                    
                    # Ambil semua teks di dalam kotak tersebut
                    raw_text = await el.inner_text()
                    
                    # Pembersih Judul Tempur:
                    # Mengubah newline menjadi spasi, menghapus kata 'Tonton', dan merapikan spasi ganda
                    clean_title = re.sub(r'\s+', ' ', raw_text).replace('Tonton', '').strip()
                    # Menghapus angka skor jika menempel (opsional, tapi membuat judul lebih rapi)
                    clean_title = re.sub(r'\s\d+\s', ' vs ', clean_title) 
                    
                    target_links.append({"url": full_url, "title": clean_title})

            # Hapus duplikat link (jika web meload dua elemen yang sama)
            unique_targets = {v['url']:v for v in target_links}.values()
            
            print(f"🎯 Ditemukan {len(unique_targets)} pertandingan LIVE (Tonton).")

            # Eksekusi masuk ke masing-masing halaman pertandingan
            for target in unique_targets:
                m3u8_url = await extract_m3u8(context, target['url'], target['title'][:50])
                
                if m3u8_url:
                    print(f"  ✅ Harta didapat: {m3u8_url}")
                    
                    # Format ke Playlist M3U8
                    all_streams.append([
                        f'#EXTINF:-1 group-title="BONE TV - Livenobar",[🔴 LIVE] {target["title"][:45]}',
                        f'#EXTVLCOPT:http-referrer={REFERER}',
                        f'#EXTVLCOPT:http-origin={ORIGIN}',
                        f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                        m3u8_url,
                        ''
                    ])
                else:
                    print("  ⚠️ M3U8 tidak terdeteksi.")

        except Exception as e:
            print(f"Terjadi kesalahan utama: {e}")
        finally:
            await browser.close()

    # --- MENULIS HASIL KE FILE M3U8 ---
    if all_streams:
        ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        header = ['#EXTM3U', f'# Last Updated: {ts}', '']
        
        flat_list = [item for sublist in all_streams for item in sublist]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(header + flat_list))
        print(f"\n🏁 SELESAI! {len(all_streams)} link berhasil disimpan ke {OUTPUT_FILE}.")
    else:
        print("\n💀 Operasi selesai, namun tidak ada M3U8 yang berhasil diekstrak (Mungkin enkripsi kuat atau sedang tidak ada live).")

if __name__ == "__main__":
    asyncio.run(main())
