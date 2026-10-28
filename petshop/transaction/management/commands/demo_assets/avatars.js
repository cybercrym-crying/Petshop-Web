// Foto profil ilustrasi (DiceBear "notionists", lisensi CC0) untuk akun demo.
const { createAvatar } = require('@dicebear/core');
const { notionists } = require('@dicebear/collection');
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const OUT = process.argv[2]; fs.mkdirSync(OUT, { recursive: true });
const BG = ['ffd5dc', 'c0aede', 'b6e3f4', 'd1d4f9', 'ffdfbf', 'c7f0d8', 'fde68a', 'fbcfe8'];
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 320, height: 320 } });
  for (let i = 1; i <= 48; i++) {
    const svg = createAvatar(notionists, { seed: 'seelly-' + i * 7, backgroundColor: [BG[i % BG.length]], gestureProbability: 0, size: 320 }).toString();
    await pg.setContent(`<html><body style="margin:0">${svg}</body></html>`);
    await pg.locator('svg').screenshot({ path: path.join(OUT, `orang-${String(i).padStart(2, '0')}.jpg`), type: 'jpeg', quality: 88 });
  }
  await b.close();
})();
