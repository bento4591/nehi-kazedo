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
    """Fungsi intelijen Brutal-Force untuk masuk ke halaman dan menekan Play"""
    page = await context.new_page()
    m3u8_link = None

    # Pasang Radar Network untuk menangkap m3u8 dari sportnobar.xyz dll
    def handle_request(request):
        nonlocal m3u8_link
        if ".m3u8" in request.url and "ad" not in request.url.lower() and not m3u8_link:
            m3u8_link = request.url

    page.on("request", handle_request)

    try:
        print(f"  🔍 Mengendus: {match_title}")
        await page.goto(match_url, wait_until="domcontentloaded", timeout=25000)
        
        # Tunggu loading player Next.js
        await page.wait_for_timeout(4000) 
        
        print("  ▶️ Menembakkan klik ke tombol Play Kuning...")
        # Taktik Brutal: Klik tepat di tengah layar (koordinat 640x360 dari resolusi 1280x720)
        await page.mouse.click(640, 360)
        await page.wait_for_timeout(1000)
        
        # Jaga-jaga jika tombolnya butuh klik dua kali atau berada di dalam iframe
        await page.mouse.click(640, 360)
        
        # Jika player berupa Iframe, kita sapu semua iframe dan klik di tengahnya
        for frame in page.frames:
            try:
                # Klik area player dalam iframe
                await frame.locator("body").click(position={"x": 300, "y": 200}, force=True, timeout=2000)
            except: pass

        # Tunggu 5 detik agar video merender dan M3U8 tertangkap radar
        await page.wait_for_timeout(5000) 

    except Exception as e:
        print(f"  ❌ Gagal memuat halaman: {e}")
    finally:
        page.remove_listener("request", handle_request)
        await page.close()

    return m3u8_link

async def main():
    print("🚀 Memulai Radar LivenobarSeru MABES ENTERPRISE (Mode Brutal)...")
    all_streams = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        # Kunci resolusi layar agar klik koordinat tengah (640,360) selalu akurat
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
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
            await main_page.wait_for_timeout(5000) # Biarkan Next.js merender seluruh blok
            
            print("Menyapu bersih link pertandingan LIVE (Status 'Tonton')...")
            
            # TAKTIK BARU: Evaluasi Javascript Murni di Browser (Kebal dari bug locator)
            matches = await main_page.evaluate("""() => {
                let results = [];
                // Sapu semua tag link di halaman
                document.querySelectorAll('a').forEach(a => {
                    // Jika teks di dalamnya mengandung kata "Tonton"
                    if (a.innerText && a.innerText.includes('Tonton')) {
                        results.push({
                            url: a.href,
                            raw_title: a.innerText
                        });
                    }
                });
                return results;
            }""")

            target_links = []
            for m in matches:
                full_url = m['url']
                
                # Pembersih Judul Tempur:
                # Menghapus spasi berlebih, enter, kata Tonton, dan mengganti skor jadi 'vs'
                clean_title = re.sub(r'\s+', ' ', m['raw_title']).replace('Tonton', '').strip()
                clean_title = re.sub(r'\s\d+\s', ' vs ', clean_title) 
                
                target_links.append({"url": full_url, "title": clean_title})

            # Hapus duplikat link
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
                    print("  ⚠️ M3U8 tidak terdeteksi (Tombol kuning meleset atau enkripsi kuat).")

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
