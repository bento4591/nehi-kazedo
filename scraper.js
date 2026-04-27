const { chromium } = require('playwright');
const fs = require('fs');

// URL WORKER CLOUDFLARE ANDA
const WORKER_URL = "https://camel-bridge.ahmadadityaberdikari.workers.dev"; 
const targetMainDomain = "https://www.camellive.top"; 

// UA untuk proses scraping (tetap pakai Chrome desktop agar tidak dicurigai web)
const scraperUserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36';

function smartExtractMatches(json) {
    let matches = [];
    function searchNode(obj) {
        if (Array.isArray(obj)) {
            if (obj.length > 0 && typeof obj[0] === 'object' && obj[0] !== null) {
                const sampleStr = JSON.stringify(obj[0]).toLowerCase();
                if (sampleStr.includes('home') && sampleStr.includes('away')) {
                    matches = matches.concat(obj);
                }
            }
            obj.forEach(searchNode);
        } else if (typeof obj === 'object' && obj !== null) {
            Object.values(obj).forEach(searchNode);
        }
    }
    searchNode(json);
    return matches;
}

function extractTeamName(teamObj) {
    if (!teamObj) return "Unknown Team";
    if (typeof teamObj === 'string') return teamObj;
    return teamObj.name || teamObj.team_name || teamObj.teamName || teamObj.title || "Unknown Team";
}

(async () => {
    console.log("[LOG] Memulai Operasi (Multi-UA Injection: ExoPlayer, Chrome, Mozilla)...");
    const matchesMap = new Map();
    const database = {}; 

    // FASE 1: API Intelligence
    try {
        const apiResponse = await fetch('https://api.cameltv.live/camel-service/ee/sports_live/home?page=1&size=30', {
            headers: {
                'AppVersion': '20.0.0.0',
                'Device': 'WEB',
                'region': 'XM'
            }
        });
        const apiJson = await apiResponse.json();
        const rawMatches = smartExtractMatches(apiJson);
        for (const m of rawMatches) {
            let id = m.id || m.matchId || m.match_id || m.sv_id || null;
            if (!id) continue;
            let home = extractTeamName(m.homeTeamName || m.home_team);
            let away = extractTeamName(m.awayTeamName || m.away_team);
            let logo = m.home_team?.logo || m.homeLogo || "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            matchesMap.set(String(id).toLowerCase(), { title: `${home} VS ${away}`, logo: logo });
        }
    } catch (e) { console.log("[WARN] API Gagal."); }

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ userAgent: scraperUserAgent });

    let playlistContent = "#EXTM3U\n";
    let streamFoundCount = 0;

    try {
        const page = await context.newPage();
        await page.goto(targetMainDomain + '/', { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3000); 

        const liveLinks = await page.$$eval('.match-items', cards => {
            let links = [];
            for (const card of cards) {
                if (card.innerText.toUpperCase().includes('LIVE')) {
                    const aTag = card.querySelector('a.match-items-before');
                    if (aTag && aTag.href) links.push(aTag.href);
                }
            }
            return [...new Set(links)];
        });

        for (const link of liveLinks) {
            try {
                const urlParts = link.split('/');
                let urlId = urlParts[urlParts.length - 1].toLowerCase();
                if(urlId.includes('?')) urlId = urlId.split('?')[0];

                const matchData = matchesMap.get(urlId) || {
                    title: "LIVE MATCH " + urlId.toUpperCase(),
                    logo: "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
                };

                const streamPage = await context.newPage();
                let capturedM3u8 = null;
                streamPage.on('response', res => {
                    const u = res.url();
                    if (u.includes('.m3u8') && (u.includes('txSecret') || u.includes('auth='))) capturedM3u8 = u;
                });

                await streamPage.goto(link, { waitUntil: 'domcontentloaded' });
                await streamPage.waitForTimeout(8000);
                await streamPage.close(); 

                if (capturedM3u8) {
                    database[urlId] = capturedM3u8;

                    // KONFIGURASI MULTI-UA UNTUK PLAYLIST
                    playlistContent += `#EXTINF:-1 tvg-logo="${matchData.logo}" group-title="CAMEL SPORTS", ${matchData.title} [CAMEL LIVE]\n`;
                    playlistContent += `#EXTVLCOPT:http-origin=${targetMainDomain}\n`;
                    playlistContent += `#EXTVLCOPT:http-referrer=${targetMainDomain}/\n`;
                    // Menyisipkan 3 Identitas UA sekaligus (ExoPlayer, Chrome, Mozilla)
                    playlistContent += `#EXTVLCOPT:http-user-agent=ExoPlayer/2.19.1 (Linux; Android 15) Media3/1.6.0 Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36\n`;
                    playlistContent += `${WORKER_URL}/?id=${urlId}\n`;
                    
                    streamFoundCount++;
                }
            } catch (err) {}
        }

        fs.writeFileSync('database.json', JSON.stringify(database, null, 2));
        fs.writeFileSync('playlist.m3u', playlistContent);
        console.log(`[SUKSES] Selesai dengan ${streamFoundCount} stream.`);
    } catch (error) {
        console.error(error);
    } finally {
        await browser.close();
    }
})();
