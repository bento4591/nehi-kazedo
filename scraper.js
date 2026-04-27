const { chromium } = require('playwright');
const fs = require('fs');

// URL Worker Jembatan Anda
const WORKER_URL = "https://camel-bridge.ahmadadityaberdikari.workers.dev"; 

function extractTeamName(teamObj) {
    if (!teamObj) return "Unknown Team";
    if (typeof teamObj === 'string') return teamObj;
    return teamObj.name || teamObj.team_name || teamObj.teamName || teamObj.title || "Unknown Team";
}

(async () => {
    console.log("[LOG] Memulai Scraper V12.1 (Masking M3U8 & Clean Playlist)...");
    const matchesMap = new Map();
    const database = {}; 

    // FASE 1: Ambil Data dari API (Untuk Nama & Logo Asli)
    try {
        const apiResponse = await fetch('https://api.cameltv.live/camel-service/ee/sports_live/home?page=1&size=30', {
            headers: {
                'AppVersion': '20.0.0.0',
                'Device': 'WEB',
                'region': 'XM'
            }
        });
        const apiJson = await apiResponse.json();
        
        // Logika pencarian data pertandingan di dalam JSON API
        const rows = apiJson.data?.rows || [];
        rows.forEach(m => {
            const id = String(m.id || m.matchId).toLowerCase();
            const home = extractTeamName(m.homeTeamName || m.home_team);
            const away = extractTeamName(m.awayTeamName || m.away_team);
            const logo = m.home_team?.logo || m.homeLogo || "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            
            matchesMap.set(id, { title: `${home} VS ${away}`, logo: logo });
        });
    } catch (e) { console.log("[WARN] Gagal akses API, mengandalkan data Web."); }

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    });

    let playlistContent = "#EXTM3U\n";
    let found = 0;

    try {
        const page = await context.newPage();
        await page.goto("https://www.camellive.top/", { waitUntil: 'networkidle', timeout: 60000 });

        // AMBIL DATA LANGSUNG DARI HALAMAN WEB (DOM)
        const liveElements = await page.$$eval('.match-items', cards => {
            return cards.filter(c => c.innerText.includes('LIVE')).map(c => {
                const a = c.querySelector('a');
                const img = c.querySelector('img');
                const teams = c.querySelectorAll('.team-name'); 
                
                return {
                    url: a ? a.href : null,
                    webTitle: teams.length >= 2 ? `${teams[0].innerText} VS ${teams[1].innerText}` : null,
                    webLogo: img ? img.src : null
                };
            }).filter(item => item.url !== null);
        });

        for (const item of liveElements) {
            const urlParts = item.url.split('/');
            const rawId = urlParts[urlParts.length - 1].split('?')[0];
            const id = rawId.toLowerCase();

            // SINKRONISASI: Cek API dulu, kalau tidak ada pakai data Web
            const info = matchesMap.get(id) || {
                title: item.webTitle || "LIVE MATCH " + id.toUpperCase(),
                logo: item.webLogo || "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
            };

            const streamPage = await context.newPage();
            let m3u8 = null;

            streamPage.on('response', res => {
                const u = res.url();
                if (u.includes('.m3u8') && (u.includes('txSecret') || u.includes('auth'))) m3u8 = u;
            });

            await streamPage.goto(item.url, { waitUntil: 'domcontentloaded' });
            await streamPage.waitForTimeout(5000); // Tunggu token muncul

            if (m3u8) {
                database[id] = m3u8;
                
                // Format output yang SUPER BERSIH: Logo, Judul, dan URL Masking .m3u8 (Tanpa Header Tambahan)
                playlistContent += `#EXTINF:-1 tvg-logo="${info.logo}" group-title="CAMEL SPORTS", ${info.title} [CAMEL LIVE]\n`;
                playlistContent += `${WORKER_URL}/${id}.m3u8\n`;
                
                found++;
                console.log(`[OK] Berhasil: ${info.title}`);
            }
            await streamPage.close();
        }

        fs.writeFileSync('database.json', JSON.stringify(database, null, 2));
        fs.writeFileSync('playlist.m3u', playlistContent);
        console.log(`[FINISH] Berhasil mengupdate ${found} siaran.`);

    } catch (err) {
        console.error("[ERROR]", err);
    } finally {
        await browser.close();
    }
})();
