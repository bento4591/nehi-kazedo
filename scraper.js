const { chromium } = require('playwright');
const fs = require('fs');

// Logika Pro: Ekstraksi data API cerdas
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
    console.log("[LOG] Memulai Operasi Database (DYNAMICS MODE)...");
    const matchesMap = new Map();
    const database = {}; // Objek untuk menyimpan link murni

    // ==========================================
    // FASE 1: API INTELLIGENCE
    // ==========================================
    try {
        const apiResponse = await fetch('https://api.cameltv.live/camel-service/ee/sports_live/home?page=1&size=20', {
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'AppVersion': '20.0.0.0',
                'Device': 'WEB',
                'region': 'XM',
                'node': 'camel1_g2',
                'deviceId': '07fc8207-5b16-4b3f-b46e-e1f7e986a2aa'
            }
        });
        const apiJson = await apiResponse.json();
        const rawMatches = smartExtractMatches(apiJson);

        for (const m of rawMatches) {
            let id = m.id || m.matchId || m.match_id || m.sv_id || null;
            if (!id) continue;
            let homeName = extractTeamName(m.homeTeamName || m.home_team);
            let awayName = extractTeamName(m.awayTeamName || m.away_team);
            matchesMap.set(String(id).toLowerCase(), `${homeName} VS ${awayName}`);
        }
    } catch (error) { console.error(`[ERROR] API: ${error.message}`); }

    // ==========================================
    // FASE 2: PLAYWRIGHT TURBO SNIFFER
    // ==========================================
    const browser = await chromium.launch({ headless: true });
    const targetMainDomain = "https://www.camellive.top"; 
    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    });

    try {
        const page = await context.newPage();
        await page.route('**/*', r => ['image', 'stylesheet', 'font'].includes(r.request().resourceType()) ? r.abort() : r.continue());
        await page.goto(targetMainDomain + '/', { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(3000);

        const liveLinks = await page.$$eval('a', as => [...new Set(as.map(a => a.href).filter(h => h.includes('/live/') || h.includes('/football/')))]);

        for (const link of liveLinks) {
            try {
                const urlParts = link.split('/');
                let urlId = urlParts[urlParts.length - 1].toLowerCase().split('?')[0];
                const streamPage = await context.newPage();
                let capturedM3u8 = null;

                const m3u8Promise = new Promise((resolve) => {
                    streamPage.on('response', async (response) => {
                        const resUrl = response.url();
                        // LOGIKA PRO: Hanya tangkap jika mengandung "auth=" (Langkah 2)
                        if (resUrl.includes('.m3u8') && resUrl.includes('auth=')) {
                            capturedM3u8 = resUrl;
                            resolve(true);
                        }
                    });
                });

                await streamPage.goto(link, { waitUntil: 'domcontentloaded' });
                const playBtn = streamPage.locator('[class*="play"], video').first();
                if (await playBtn.isVisible()) await playBtn.click().catch(() => {});

                // Balapan: Tunggu sampai auth ditemukan atau timeout 10 detik
                await Promise.race([m3u8Promise, streamPage.waitForTimeout(10000)]);
                await streamPage.close();

                if (capturedM3u8) {
                    // Simpan ke database dengan ID sebagai kunci
                    database[urlId] = capturedM3u8;
                    console.log(`[SUCCESS] Captured Auth: ${urlId}`);
                }
            } catch (err) {}
        }

        // Simpan hasil ke database.json
        fs.writeFileSync('database.json', JSON.stringify(database, null, 2));
        console.log("[LOG] database.json Updated!");

    } finally { await browser.close(); }
})();
