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
        if ".m3u8" in request.url and not m3u8_link:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        print(f"  🔍 Mengendus: {match_title} ({match_url})")
        await page.goto(match_url, wait_until="domcontentloaded", timeout=20000)
        
        # Tunggu sebentar agar player video merender dan memanggil M3U8
        await page.wait_for_timeout(4000) 
        
        # Jika ada tombol play di tengah video, coba di-klik (opsional, tergantung web)
        try:
            play_btn = page.locator("button.vjs-big-play-button, .play-wrapper").first
            if await play_btn.count() > 0:
                await play_btn.click(timeout=2000)
                await page.wait_for_timeout(2000)
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
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
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
            await main_page.wait_for_timeout(3000) # Biarkan list pertandingan termuat
            
            # MENCARI TARGET SPESIFIK: Hanya yang ada tulisan "Tonton"
            # Asumsi: Tombol "Tonton" berada di dalam tag <a> (link) atau elemen yang bisa diklik
            print("Menyaring pertandingan dengan status 'Tonton'...")
            
            # Kita cari elemen yang mengandung teks "Tonton" dan cari tahu link (href) nya
            match_elements = await main_page.locator("xpath=//a[.//text()[contains(., 'Tonton')]]").all()
            
            # Jika struktur web tidak menggunakan tag <a> untuk tombol, kita bisa cari div pelindungnya
            if not match_elements:
                print("Mencari menggunakan elemen pembungkus...")
                # Mencari kontainer pertandingan yang memiliki kata "Tonton"
                match_elements = await main_page.locator("xpath=//*[contains(@class, 'match-card') or contains(@class, 'item')]//a[contains(text(), 'Tonton')]").all()

            target_links = []
            for el in match_elements:
                href = await el.get_attribute("href")
                if href:
                    # Gabungkan URL jika path-nya relatif (misal: /id/match/123)
                    full_url = href if href.startswith("http") else f"https://stream.livenobarseru.com{href}"
                    
                    # Coba ambil nama tim dari elemen di sekitarnya (Bisa disesuaikan dengan struktur web)
                    # Ini mengambil seluruh teks dalam kotak pertandingan
                    raw_text = await el.evaluate("node => node.closest('div').innerText")
                    clean_title = raw_text.replace('\n', ' ').strip() if raw_text else "Live Match"
                    
                    target_links.append({"url": full_url, "title": clean_title})

            # Hapus duplikat link
            unique_targets = {v['url']:v for v in target_links}.values()
            
            print(f"🎯 Ditemukan {len(unique_targets)} pertandingan LIVE (Tonton).")

            # Eksekusi satu per satu
            for target in unique_targets:
                m3u8_url = await extract_m3u8(context, target['url'], target['title'][:50] + "...")
                
                if m3u8_url:
                    print(f"  ✅ Harta didapat: {m3u8_url}")
                    
                    # Format ke Playlist M3U8
                    all_streams.append([
                        f'#EXTINF:-1 group-title="BONE TV - Livenobar",[🔴 LIVE] {target["title"][:40]}',
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
        print("\n💀 Operasi selesai, namun tidak ada M3U8 yang berhasil diekstrak.")

if __name__ == "__main__":
    asyncio.run(main())

