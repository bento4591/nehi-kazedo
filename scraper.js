const { chromium } = require('playwright');
const fs = require('fs');

const WORKER_URL = "https://camel-bridge.ahmadadityaberdikari.workers.dev"; 
const targetMainDomain = "https://www.camellive.top"; 
const globalUserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36';

// Fungsi Pengekstrak API Tangguh (Kembali ke versi terbaik Anda)
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
    console.log("[LOG] Memulai Scraper (Restore Header + Format Worker .m3u8)...");
    const matchesMap = new Map();
    const database = {}; 

    // Ambil Data dari API dengan kuota yang diperbesar
    try {
        const apiResponse = await fetch('https://api.cameltv.live/camel-service/ee/sports_live/home?page=1&size=50', {
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'AppVersion': '20.0.0.0',
                'Device': 'WEB',
                'region': 'XM',
                'node': 'camel1_g2'
            }
        });

        const apiJson = await apiResponse.json();
        const rawMatches = smartExtractMatches(apiJson);

        for (const m of rawMatches) {
            let id = m.id || m.matchId || m.match_id || m.sv_id || null;
            if (!id) continue;

            let homeName = extractTeamName(m.homeTeamName || m.home_team || m.homeName || m.home);
            let awayName = extractTeamName(m.awayTeamName || m.away_team || m.awayName || m.away);
            
            let logoUrl = "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png";
            if (m.home_team && m.home_team.logo) logoUrl = m.home_team.logo;
            else if (m.homeLogo) logoUrl = m.homeLogo;
            
            matchesMap.set(String(id).toLowerCase(), {
                title: `${homeName} VS ${awayName}`,
                logo: logoUrl
            });
        }
    } catch (error) {
        console.error(`[ERROR] API: ${error.message}`);
    }

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        userAgent: globalUserAgent,
        viewport: { width: 1280, height: 720 },
        extraHTTPHeaders: { 'Origin': targetMainDomain, 'Referer': targetMainDomain + '/' }
    });

    let playlistContent = "#EXTM3U\n";
    let streamFoundCount = 0;

    try {
        const page = await context.newPage();
        await page.goto(targetMainDomain + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
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
                    title: `CAMEL LIVE EVENT ${streamFoundCount + 1}`,
                    logo: "https://raw.githubusercontent.com/tsender57-dotcom/offline/refs/heads/main/logo/Logo%20OGI%20Bone.png"
                };

                const streamPage = await context.newPage();
                let capturedM3u8 = null;

                streamPage.on('response', async (response) => {
                    const resUrl = response.url();
                    if (resUrl.includes('.m3u8') && (resUrl.includes('txSecret') || resUrl.includes('auth='))) {
                        capturedM3u8 = resUrl;
                    }
                });

                await streamPage.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
                
                const playBtn = streamPage.locator('[class*="play"], video').first();
                if (await playBtn.isVisible()) await playBtn.click().catch(() => {});

                await streamPage.waitForTimeout(10000);
                await streamPage.close(); 

                if (capturedM3u8) {
                    database[urlId] = capturedM3u8;

                    // MENGEMBALIKAN SEMUA HEADER & MENGGUNAKAN URL MASKING
                    playlistContent += `#EXTINF:-1 tvg-logo="${matchData.logo}" group-title="CAMEL SPORTS", ${matchData.title} [CAMEL LIVE]\n`;
                    playlistContent += `#EXTVLCOPT:http-origin=${targetMainDomain}\n`;
                    playlistContent += `#EXTVLCOPT:http-referrer=${targetMainDomain}/\n`;
                    playlistContent += `#EXTVLCOPT:http-user-agent=${globalUserAgent}\n`;
                    playlistContent += `${WORKER_URL}/${urlId}.m3u8\n`;
                    
                    streamFoundCount++;
                }
            } catch (err) {
                console.log(`[SKIP] Timeout.`);
            }
        }

        fs.writeFileSync('database.json', JSON.stringify(database, null, 2));
        if (streamFoundCount > 0) {
            fs.writeFileSync('playlist.m3u', playlistContent);
        } else {
            fs.writeFileSync('playlist.m3u', "#EXTM3U\n#EXTINF:-1,Tidak Ada Siaran Langsung\nhttp://offline.local");
        }

    } catch (error) {
        console.error(`[ERROR FATAL] ${error.message}`);
    } finally {
        await browser.close();
    }
})();
