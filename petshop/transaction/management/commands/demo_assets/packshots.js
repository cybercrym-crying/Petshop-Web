// Render foto produk bergaya katalog (latar terang, bayangan lantai) untuk data demo.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = process.argv[2] || path.join(__dirname, 'out/products');
fs.mkdirSync(OUT, { recursive: true });

// --- util -------------------------------------------------------------
let gid = 0;
const id = (p) => `${p}${++gid}`;
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) + amt, g = ((n >> 8) & 255) + amt, b = (n & 255) + amt;
  r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); b = Math.max(0, Math.min(255, b));
  return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
function lines(text, max) {
  const out = []; let cur = '';
  for (const w of text.split(' ')) {
    if ((cur + ' ' + w).trim().length > max && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim();
  }
  if (cur) out.push(cur);
  return out;
}
function textBlock(x, y, text, { size = 26, max = 16, weight = 800, color = '#222', lh = 1.15, anchor = 'middle' } = {}) {
  return lines(text, max).map((t, i) =>
    `<text x="${x}" y="${y + i * size * lh}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}">${esc(t)}</text>`).join('');
}
function vgrad(c1, c2) { const g = id('v'); return [g, `<linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient>`]; }
function hgrad(stops) { const g = id('h'); return [g, `<linearGradient id="${g}" x1="0" y1="0" x2="1" y2="0">${stops.map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join('')}</linearGradient>`]; }
function rgrad(c1, c2, cx = 0.35, cy = 0.3) { const g = id('r'); return [g, `<radialGradient id="${g}" cx="${cx}" cy="${cy}" r="0.75"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></radialGradient>`]; }
// Kilau silinder: terang di kiri, gelap di kanan.
function sheen() { return hgrad([[0, '#fff', 0.0], [0.12, '#fff', 0.32], [0.3, '#fff', 0.05], [0.75, '#000', 0.0], [1, '#000', 0.22]]); }
// Teks merek dipersempit bila terlalu lebar untuk kemasannya.
function brandText(x, y, text, size, maxW, color) {
  const est = text.length * size * 0.66;
  const fit = est > maxW ? ` textLength="${maxW}" lengthAdjust="spacingAndGlyphs"` : '';
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="900" fill="${color}" text-anchor="middle"${fit}>${esc(text)}</text>`;
}
const PAW = (x, y, s, c) => `<g transform="translate(${x},${y}) scale(${s})" fill="${c}"><ellipse cx="0" cy="12" rx="14" ry="11"/><ellipse cx="-15" cy="-6" rx="6" ry="8"/><ellipse cx="-5" cy="-14" rx="6" ry="8"/><ellipse cx="6" cy="-14" rx="6" ry="8"/><ellipse cx="16" cy="-6" rx="6" ry="8"/></g>`;

// --- bentuk kemasan ---------------------------------------------------
function bag(p) {
  const [g1, d1] = vgrad(shade(p.color, 18), shade(p.color, -22));
  const [sh, d2] = sheen();
  const body = 'M235 190 Q232 420 222 640 Q400 668 578 640 Q568 420 565 190 Z';
  return `<defs>${d1}${d2}</defs>
  <path d="${body}" fill="url(#${g1})"/>
  <rect x="228" y="150" width="344" height="48" rx="6" fill="${shade(p.color, -30)}"/>
  ${Array.from({ length: 30 }, (_, i) => `<line x1="${236 + i * 11}" y1="154" x2="${236 + i * 11}" y2="194" stroke="#000" stroke-opacity=".12" stroke-width="3"/>`).join('')}
  <circle cx="540" cy="174" r="7" fill="#fff" fill-opacity=".7"/>
  ${brandText(400, 262, p.brand, p.brandSize || 44, 290, p.brandColor || '#fff')}
  <rect x="262" y="292" width="276" height="250" rx="22" fill="#fff" fill-opacity=".95"/>
  <circle cx="400" cy="352" r="38" fill="${p.accent}"/>${PAW(400, 352, 1.15, '#fff')}
  ${textBlock(400, 422, p.title, { size: 25, max: 18, color: '#1f1f1f' })}
  <rect x="330" y="560" width="140" height="44" rx="22" fill="${p.accent}"/>
  <text x="400" y="590" font-size="23" font-weight="800" fill="#fff" text-anchor="middle">${esc(p.size)}</text>
  <path d="${body}" fill="url(#${sh})"/>`;
}
function pouch(p) {
  const [g1, d1] = vgrad(shade(p.color, 20), shade(p.color, -18));
  const [sh, d2] = sheen();
  const zig = (y, dir) => Array.from({ length: 24 }, (_, i) => `${300 + i * 8.33},${y + (i % 2 ? dir * 7 : 0)}`).join(' ');
  return `<defs>${d1}${d2}</defs>
  <polygon points="300,215 ${zig(208, -1)} 500,215 500,625 ${zig(632, 1).split(' ').reverse().join(' ')} 300,625" fill="url(#${g1})"/>
  ${brandText(400, 290, p.brand, 38, 170, '#fff')}
  <ellipse cx="400" cy="420" rx="78" ry="62" fill="#fff" fill-opacity=".93"/>
  ${PAW(400, 420, 1.3, p.accent)}
  ${textBlock(400, 522, p.title, { size: 21, max: 12, color: '#fff' })}
  <text x="400" y="600" font-size="22" font-weight="800" fill="#fff" fill-opacity=".9" text-anchor="middle">${esc(p.size)}</text>
  <rect x="300" y="215" width="200" height="410" fill="url(#${sh})"/>`;
}
function can(p) {
  const [m, d1] = hgrad([[0, '#9aa3ad'], [0.2, '#eef1f4'], [0.55, '#b9c0c8'], [1, '#6f7780']]);
  const [lab, d2] = hgrad([[0, shade(p.color, -25)], [0.25, shade(p.color, 20)], [0.6, p.color], [1, shade(p.color, -40)]]);
  return `<defs>${d1}${d2}</defs>
  <rect x="290" y="300" width="220" height="330" fill="url(#${m})"/>
  <ellipse cx="400" cy="630" rx="110" ry="26" fill="#7d858e"/>
  <rect x="290" y="330" width="220" height="270" fill="url(#${lab})"/>
  <ellipse cx="400" cy="300" rx="110" ry="26" fill="#c9cfd5" stroke="#8d959e" stroke-width="5"/>
  <ellipse cx="400" cy="300" rx="88" ry="18" fill="#dfe3e7" stroke="#a7aeb6" stroke-width="3"/>
  <rect x="372" y="290" width="56" height="12" rx="6" fill="#9aa3ad"/>
  <text x="400" y="395" font-size="46" font-weight="900" fill="#fff" text-anchor="middle">${esc(p.brand)}</text>
  ${textBlock(400, 450, p.title, { size: 24, max: 14, color: '#fff' })}
  <text x="400" y="575" font-size="22" font-weight="800" fill="#fff" text-anchor="middle">${esc(p.size)}</text>`;
}
function box(p) {
  const [g1, d1] = vgrad('#ffffff', '#eceff3');
  return `<defs>${d1}</defs>
  <polygon points="300,290 360,250 560,250 500,290" fill="${shade(p.color, 30)}"/>
  <polygon points="500,290 560,250 560,590 500,630" fill="${shade(p.color, -35)}"/>
  <rect x="300" y="290" width="200" height="340" fill="url(#${g1})"/>
  <rect x="300" y="290" width="200" height="88" fill="${p.color}"/>
  ${brandText(400, 345, p.brand, 30, 180, '#fff')}
  ${textBlock(400, 420, p.title, { size: 23, max: 13, color: '#222' })}
  <circle cx="400" cy="540" r="30" fill="${p.accent}"/>${PAW(400, 540, 0.9, '#fff')}
  <rect x="300" y="596" width="200" height="34" fill="${p.color}"/>
  <text x="400" y="620" font-size="19" font-weight="800" fill="#fff" text-anchor="middle">${esc(p.size)}</text>`;
}
function bottle(p) {
  const [b, d1] = hgrad([[0, shade(p.color, -20)], [0.18, shade(p.color, 35)], [0.5, p.color], [1, shade(p.color, -45)]]);
  const body = 'M318 340 Q318 290 360 280 L360 238 L440 238 L440 280 Q482 290 482 340 L482 620 Q482 645 456 645 L344 645 Q318 645 318 620 Z';
  return `<defs>${d1}</defs>
  <path d="${body}" fill="url(#${b})"/>
  <rect x="352" y="186" width="96" height="60" rx="10" fill="${p.cap || '#2b2b2b'}"/>
  ${Array.from({ length: 8 }, (_, i) => `<line x1="${360 + i * 11}" y1="192" x2="${360 + i * 11}" y2="240" stroke="#fff" stroke-opacity=".15" stroke-width="3"/>`).join('')}
  <rect x="330" y="380" width="140" height="220" rx="12" fill="#fff" fill-opacity=".94"/>
  ${brandText(400, 420, p.brand, 24, 128, p.accent)}
  ${textBlock(400, 460, p.title, { size: 18, max: 11, color: '#222' })}
  <text x="400" y="584" font-size="19" font-weight="800" fill="${p.accent}" text-anchor="middle">${esc(p.size)}</text>`;
}
function dropper(p) {
  const [b, d1] = hgrad([[0, '#5a2d0c'], [0.22, '#c0712c'], [0.55, '#8a4a16'], [1, '#3e1f08']]);
  return `<defs>${d1}</defs>
  <g transform="translate(110,0)">${box(p)}</g>
  <path d="M250 420 Q250 380 290 372 L290 340 L350 340 L350 372 Q390 380 390 420 L390 630 Q390 650 370 650 L270 650 Q250 650 250 630 Z" fill="url(#${b})"/>
  <rect x="286" y="270" width="68" height="74" rx="8" fill="#222"/>
  <path d="M298 270 L298 210 Q320 180 342 210 L342 270 Z" fill="#333"/>
  <rect x="262" y="470" width="116" height="110" rx="8" fill="#fff" fill-opacity=".92"/>
  ${textBlock(320, 515, 'Tetes kutu', { size: 19, max: 10, color: '#333' })}`;
}
function tube(p) {
  const [b, d1] = vgrad('#ffffff', '#e5e8ec');
  return `<defs>${d1}</defs>
  <g transform="rotate(-18 400 430)">
  <path d="M300 250 L500 250 L470 600 L330 600 Z" fill="url(#${b})" stroke="#d3d7dc" stroke-width="3"/>
  <rect x="296" y="236" width="208" height="22" fill="#c9ced4"/>
  ${Array.from({ length: 12 }, (_, i) => `<line x1="${304 + i * 17}" y1="238" x2="${304 + i * 17}" y2="256" stroke="#9aa1a9" stroke-width="2"/>`).join('')}
  <rect x="352" y="600" width="96" height="70" rx="10" fill="${p.color}"/>
  <rect x="318" y="300" width="164" height="70" fill="${p.color}"/>
  ${brandText(400, 347, p.brand, 30, 150, '#fff')}
  ${textBlock(400, 420, p.title, { size: 22, max: 12, color: '#333' })}
  <text x="400" y="560" font-size="20" font-weight="800" fill="${p.color}" text-anchor="middle">${esc(p.size)}</text>
  </g>`;
}
function jar(p) {
  const [b, d1] = hgrad([[0, '#d9dde2'], [0.2, '#ffffff'], [0.6, '#eef0f3'], [1, '#b8bec5']]);
  return `<defs>${d1}</defs>
  <rect x="300" y="300" width="200" height="330" rx="26" fill="url(#${b})"/>
  <rect x="312" y="240" width="176" height="74" rx="12" fill="${p.color}"/>
  ${Array.from({ length: 14 }, (_, i) => `<line x1="${320 + i * 12}" y1="246" x2="${320 + i * 12}" y2="308" stroke="#000" stroke-opacity=".12" stroke-width="3"/>`).join('')}
  <rect x="300" y="360" width="200" height="210" fill="${p.color}"/>
  ${brandText(400, 408, p.brand, 32, 180, '#fff')}
  ${textBlock(400, 450, p.title, { size: 21, max: 13, color: '#fff' })}
  <text x="400" y="552" font-size="20" font-weight="800" fill="#fff" text-anchor="middle">${esc(p.size)}</text>`;
}

// --- barang non-kemasan ------------------------------------------------
function cage(p) {
  const tiers = p.tiers || 1; const top = tiers === 2 ? 220 : 300;
  const bars = Array.from({ length: 17 }, (_, i) => `<line x1="${230 + i * 21.25}" y1="${top}" x2="${230 + i * 21.25}" y2="560" stroke="${p.wire || '#cfd4da'}" stroke-width="5"/>`).join('');
  const shelf = tiers === 2 ? `<rect x="230" y="390" width="200" height="14" fill="${shade(p.color, -10)}"/><path d="M430 404 L560 520" stroke="${shade(p.color, -10)}" stroke-width="12"/>` : '';
  return `${bars}
  <rect x="222" y="${top - 10}" width="356" height="16" rx="6" fill="${p.wire || '#cfd4da'}"/>
  <rect x="222" y="${(top + 560) / 2}" width="356" height="8" fill="${p.wire || '#cfd4da'}"/>
  <path d="M360 ${top - 12} Q400 ${top - 60} 440 ${top - 12}" stroke="${p.wire || '#bfc5cc'}" stroke-width="10" fill="none"/>
  ${shelf}
  <rect x="210" y="555" width="380" height="80" rx="14" fill="${p.color}"/>
  <rect x="210" y="555" width="380" height="18" rx="9" fill="#fff" fill-opacity=".25"/>
  ${p.door ? `<rect x="330" y="${top + 60}" width="140" height="150" fill="none" stroke="${shade(p.wire || '#cfd4da', -40)}" stroke-width="7"/>` : ''}`;
}
function birdcage(p) {
  const bars = Array.from({ length: 15 }, (_, i) => { const x = 250 + i * 21.4; return `<path d="M${x} 600 L${x} 330 Q${x} ${330 - 140 * Math.sin(Math.PI * i / 14)} 400 190" stroke="#d6b45a" stroke-width="4" fill="none"/>`; }).join('');
  return `${bars}
  <ellipse cx="400" cy="330" rx="152" ry="16" fill="none" stroke="#c9a347" stroke-width="7"/>
  <circle cx="400" cy="172" r="22" fill="none" stroke="#c9a347" stroke-width="8"/>
  <line x1="290" y1="470" x2="510" y2="470" stroke="#8b5a2b" stroke-width="10" stroke-linecap="round"/>
  <rect x="236" y="590" width="328" height="56" rx="12" fill="${p.color}"/>
  <rect x="300" y="520" width="44" height="34" rx="6" fill="#e9eef3"/>`;
}
function aquarium() {
  const [w, d1] = vgrad('#bfe9ff', '#3a9bd8');
  const fish = (x, y, c, s = 1, f = 1) => `<g transform="translate(${x},${y}) scale(${s * f},${s})"><ellipse cx="0" cy="0" rx="26" ry="14" fill="${c}"/><polygon points="22,0 44,-14 44,14" fill="${c}"/><circle cx="-12" cy="-3" r="3" fill="#222"/></g>`;
  return `<defs>${d1}</defs>
  <rect x="200" y="290" width="400" height="320" rx="8" fill="url(#${w})" fill-opacity=".9"/>
  <rect x="200" y="290" width="400" height="34" fill="#e6f6ff" fill-opacity=".8"/>
  <path d="M200 575 Q260 555 320 570 T440 565 T600 572 L600 610 L200 610 Z" fill="#d9c49a"/>
  <path d="M260 575 Q250 470 280 410 M275 575 Q300 480 270 430 M520 575 Q540 470 510 400 M535 575 Q520 500 560 450" stroke="#2f9e44" stroke-width="10" fill="none" stroke-linecap="round"/>
  ${fish(380, 410, '#ff7a1a', 1.2)}${fish(470, 480, '#ffd43b', 0.9, -1)}${fish(330, 500, '#ff4d6d', 0.8, -1)}
  <rect x="200" y="290" width="400" height="320" rx="8" fill="none" stroke="#1f2933" stroke-width="10"/>
  <rect x="190" y="270" width="420" height="26" rx="6" fill="#1f2933"/>
  <rect x="220" y="300" width="40" height="300" fill="#fff" fill-opacity=".22"/>`;
}
function bowl(p) {
  const [b, d1] = hgrad([[0, shade(p.color, -30)], [0.25, shade(p.color, 30)], [0.6, p.color], [1, shade(p.color, -45)]]);
  const kib = Array.from({ length: 26 }, (_, i) => `<ellipse cx="${300 + (i * 37) % 200}" cy="${408 + (i * 13) % 26}" rx="13" ry="9" fill="${['#a5682a', '#8a5321', '#c07a33'][i % 3]}"/>`).join('');
  return `<defs>${d1}</defs>
  <path d="M220 420 Q240 600 300 610 L500 610 Q560 600 580 420 Z" fill="url(#${b})"/>
  <ellipse cx="400" cy="420" rx="180" ry="44" fill="${shade(p.color, 25)}"/>
  <ellipse cx="400" cy="424" rx="150" ry="32" fill="${shade(p.color, -45)}"/>
  ${kib}
  <rect x="280" y="604" width="240" height="22" rx="10" fill="#333" fill-opacity=".8"/>`;
}
function litterbox(p) {
  return `<path d="M200 420 L240 610 L560 610 L600 420 Z" fill="${p.color}"/>
  <rect x="186" y="404" width="428" height="30" rx="12" fill="${shade(p.color, 25)}"/>
  <path d="M230 432 Q400 470 570 432 L566 450 Q400 486 234 450 Z" fill="#e8dcc6"/>
  <g transform="rotate(-25 560 360)"><rect x="520" y="230" width="22" height="140" rx="11" fill="${shade(p.accent, -10)}"/>
  <path d="M480 370 L582 370 L572 470 L490 470 Z" fill="${p.accent}"/>
  ${Array.from({ length: 5 }, (_, i) => `<line x1="${500 + i * 16}" y1="385" x2="${500 + i * 16}" y2="455" stroke="#fff" stroke-width="5"/>`).join('')}</g>`;
}
function bed(p) {
  const [b, d1] = rgrad(shade(p.color, 30), shade(p.color, -25), 0.5, 0.3);
  return `<defs>${d1}</defs>
  <ellipse cx="400" cy="470" rx="250" ry="140" fill="url(#${b})"/>
  <ellipse cx="400" cy="480" rx="175" ry="88" fill="${shade(p.color, -35)}"/>
  <ellipse cx="400" cy="492" rx="160" ry="74" fill="${p.accent}"/>
  <path d="M260 470 Q400 420 540 470" stroke="#fff" stroke-opacity=".3" stroke-width="6" fill="none"/>`;
}
function comb(p) {
  return `<g transform="rotate(-30 400 420)"><rect x="370" y="430" width="60" height="230" rx="28" fill="${p.color}"/>
  <rect x="250" y="270" width="300" height="170" rx="40" fill="${shade(p.color, 15)}"/>
  <rect x="268" y="288" width="264" height="134" rx="30" fill="#2b2b2b"/>
  ${Array.from({ length: 12 }, (_, r) => Array.from({ length: 6 }, (_, c) => `<circle cx="${288 + r * 21.5}" cy="${305 + c * 20}" r="4" fill="#d9d9d9"/>`).join('')).join('')}</g>`;
}
function hamsterbottle() {
  return `<rect x="350" y="200" width="100" height="330" rx="40" fill="#cfe9ff" fill-opacity=".85" stroke="#7fb4dd" stroke-width="5"/>
  <rect x="350" y="330" width="100" height="200" rx="0" fill="#66b3ff" fill-opacity=".5"/>
  <rect x="345" y="520" width="110" height="40" rx="10" fill="#2e7d32"/>
  <path d="M400 560 L430 680" stroke="#b0b7bf" stroke-width="16" stroke-linecap="round"/>
  <circle cx="433" cy="690" r="10" fill="#8d959e"/>
  <rect x="330" y="300" width="140" height="18" rx="9" fill="#2e7d32"/>
  <rect x="362" y="220" width="18" height="290" rx="9" fill="#fff" fill-opacity=".35"/>`;
}
function ball(p) {
  const [b, d1] = rgrad(shade(p.color, 70), shade(p.color, -30));
  return `<defs>${d1}</defs><circle cx="400" cy="440" r="160" fill="url(#${b})"/>
  <path d="M260 380 Q400 470 540 380 M260 500 Q400 410 540 500" stroke="#fff" stroke-opacity=".55" stroke-width="10" fill="none"/>
  ${Array.from({ length: 9 }, (_, i) => `<circle cx="${320 + (i % 3) * 80}" cy="${370 + Math.floor(i / 3) * 70}" r="9" fill="${shade(p.color, -40)}" fill-opacity=".5"/>`).join('')}`;
}
function bone(p) {
  const [b, d1] = vgrad(shade(p.color, 40), shade(p.color, -20));
  return `<defs>${d1}</defs><g transform="rotate(-20 400 440)" fill="url(#${b})">
  <rect x="270" y="400" width="260" height="80" rx="30"/>
  <circle cx="265" cy="395" r="58"/><circle cx="265" cy="485" r="58"/><circle cx="535" cy="395" r="58"/><circle cx="535" cy="485" r="58"/></g>
  <path d="M300 420 L500 360" stroke="#fff" stroke-opacity=".35" stroke-width="10" stroke-linecap="round"/>`;
}
function mouse() {
  return `<path d="M520 520 Q640 520 650 420 Q655 360 610 330" stroke="#c48a5a" stroke-width="10" fill="none" stroke-linecap="round"/>
  <ellipse cx="400" cy="480" rx="160" ry="100" fill="#9aa1a8"/>
  <path d="M250 470 Q240 430 300 400" fill="none"/>
  <circle cx="300" cy="390" r="44" fill="#9aa1a8"/><circle cx="300" cy="390" r="26" fill="#f2b8c6"/>
  <circle cx="380" cy="372" r="44" fill="#9aa1a8"/><circle cx="380" cy="372" r="26" fill="#f2b8c6"/>
  <circle cx="262" cy="470" r="9" fill="#222"/><circle cx="238" cy="500" r="11" fill="#f28da5"/>
  <path d="M236 505 L190 495 M236 508 L190 515 M236 511 L196 532" stroke="#555" stroke-width="3"/>
  ${Array.from({ length: 8 }, (_, i) => `<path d="M${330 + i * 30} 420 l10 120" stroke="#8a9197" stroke-width="3" opacity=".5"/>`).join('')}`;
}
function wand() {
  const feather = (a, c) => `<g transform="rotate(${a} 520 260)"><path d="M520 260 Q560 160 520 80 Q480 160 520 260 Z" fill="${c}"/><line x1="520" y1="260" x2="520" y2="90" stroke="#fff" stroke-width="3"/></g>`;
  return `<line x1="230" y1="660" x2="510" y2="280" stroke="#a0703c" stroke-width="16" stroke-linecap="round"/>
  <rect x="210" y="600" width="50" height="80" rx="14" transform="rotate(37 235 640)" fill="#e64980"/>
  ${feather(-30, '#4dabf7')}${feather(0, '#ff922b')}${feather(30, '#e64980')}${feather(60, '#ffd43b')}
  <circle cx="515" cy="270" r="20" fill="#7048e8"/>`;
}
function feltfish() {
  return `<g transform="rotate(-12 400 440)"><ellipse cx="380" cy="440" rx="170" ry="100" fill="#ff8787"/>
  <polygon points="530,440 640,350 640,530" fill="#ffa8a8"/>
  <circle cx="290" cy="420" r="18" fill="#fff"/><circle cx="292" cy="422" r="9" fill="#222"/>
  <path d="M380 360 Q420 440 380 520 M440 370 Q470 440 440 510" stroke="#fff" stroke-width="6" stroke-dasharray="10 9" fill="none"/>
  <path d="M220 445 Q240 470 260 460" stroke="#c92a2a" stroke-width="5" fill="none"/>
  <rect x="300" y="300" width="150" height="24" rx="8" fill="#fff" fill-opacity=".0"/></g>`;
}
function wheel(p) {
  return `<path d="M400 440 L300 640 M400 440 L500 640" stroke="${shade(p.color, -30)}" stroke-width="18" stroke-linecap="round"/>
  <rect x="260" y="628" width="280" height="22" rx="10" fill="${shade(p.color, -30)}"/>
  <circle cx="400" cy="400" r="190" fill="${p.color}"/>
  <circle cx="400" cy="400" r="160" fill="${shade(p.color, 45)}"/>
  ${Array.from({ length: 24 }, (_, i) => { const a = i * Math.PI / 12; return `<line x1="${400 + 160 * Math.cos(a)}" y1="${400 + 160 * Math.sin(a)}" x2="${400 + 140 * Math.cos(a)}" y2="${400 + 140 * Math.sin(a)}" stroke="${p.color}" stroke-width="6"/>`; }).join('')}
  <circle cx="400" cy="400" r="34" fill="${shade(p.color, -30)}"/>`;
}
function swing() {
  const beads = Array.from({ length: 8 }, (_, i) => `<circle cx="${285 + i * 33}" cy="${300 + Math.sin(i) * 6}" r="13" fill="${['#ff6b6b', '#ffd43b', '#4dabf7', '#51cf66'][i % 4]}"/>`).join('');
  return `<path d="M400 140 L260 300 L260 540 M400 140 L540 300 L540 540" stroke="#d6b45a" stroke-width="7" fill="none"/>
  <circle cx="400" cy="130" r="18" fill="none" stroke="#d6b45a" stroke-width="7"/>
  ${beads}
  <rect x="240" y="530" width="320" height="22" rx="11" fill="#8b5a2b"/>
  ${Array.from({ length: 5 }, (_, i) => `<circle cx="${270 + i * 65}" cy="420" r="15" fill="${['#ff922b', '#7048e8', '#20c997', '#f06595', '#fab005'][i]}"/>`).join('')}
  <line x1="260" y1="420" x2="540" y2="420" stroke="#d6b45a" stroke-width="4"/>`;
}
function collar(p) {
  return `<ellipse cx="400" cy="430" rx="200" ry="130" fill="none" stroke="${shade(p.color, -30)}" stroke-width="58"/>
  <ellipse cx="400" cy="430" rx="200" ry="130" fill="none" stroke="${p.color}" stroke-width="46"/>
  <ellipse cx="400" cy="430" rx="200" ry="130" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="6" stroke-dasharray="14 10"/>
  <rect x="360" y="530" width="80" height="58" rx="8" fill="none" stroke="#d4a72c" stroke-width="12"/>
  <line x1="400" y1="530" x2="400" y2="588" stroke="#d4a72c" stroke-width="8"/>
  ${p.bell ? `<circle cx="400" cy="640" r="42" fill="#f2c94c"/><path d="M370 640 L430 640" stroke="#a37b12" stroke-width="5"/><circle cx="400" cy="660" r="7" fill="#7a5a08"/>` : `<circle cx="470" cy="300" r="10" fill="#d4a72c"/><circle cx="520" cy="320" r="10" fill="#d4a72c"/><circle cx="560" cy="350" r="10" fill="#d4a72c"/>`}`;
}
function harness(p) {
  return `<ellipse cx="400" cy="300" rx="110" ry="60" fill="none" stroke="${p.color}" stroke-width="30"/>
  <path d="M300 330 Q290 470 330 560 L470 560 Q510 470 500 330" fill="none" stroke="${p.color}" stroke-width="30"/>
  <rect x="320" y="430" width="160" height="110" rx="26" fill="${shade(p.color, 15)}"/>
  <rect x="340" y="450" width="120" height="70" rx="18" fill="${shade(p.color, -20)}"/>
  <rect x="372" y="545" width="56" height="42" rx="8" fill="#222"/>
  <circle cx="400" cy="250" r="20" fill="none" stroke="#b0b7bf" stroke-width="8"/>`;
}
function leash(p) {
  const coil = Array.from({ length: 5 }, (_, i) => `<ellipse cx="${400 + i * 6}" cy="${440 + i * 10}" rx="${170 - i * 8}" ry="${90 - i * 5}" fill="none" stroke="${i % 2 ? shade(p.color, -15) : p.color}" stroke-width="20"/>`).join('');
  return `${coil}
  <path d="M250 300 Q220 200 300 180 Q380 170 360 260" fill="none" stroke="${p.color}" stroke-width="24" stroke-linecap="round"/>
  <path d="M560 480 L600 600" stroke="${p.color}" stroke-width="18"/>
  <rect x="585" y="590" width="34" height="60" rx="10" fill="#b0b7bf"/>
  <circle cx="602" cy="666" r="16" fill="none" stroke="#b0b7bf" stroke-width="8"/>`;
}
function shirt(p) {
  const pat = id('pt');
  return `<defs><pattern id="${pat}" width="60" height="60" patternUnits="userSpaceOnUse">
  <rect width="60" height="60" fill="${p.color}"/><path d="M30 6 L54 30 L30 54 L6 30 Z" fill="none" stroke="${p.accent}" stroke-width="5"/>
  <circle cx="30" cy="30" r="7" fill="${p.accent}"/><circle cx="0" cy="0" r="6" fill="#fff" fill-opacity=".7"/><circle cx="60" cy="60" r="6" fill="#fff" fill-opacity=".7"/></pattern></defs>
  <path d="M310 230 Q400 290 490 230 L600 300 L560 400 L510 380 L520 620 Q400 650 280 620 L290 380 L240 400 L200 300 Z" fill="url(#${pat})"/>
  <path d="M310 230 Q400 290 490 230" stroke="${shade(p.color, -40)}" stroke-width="14" fill="none"/>`;
}
function hoodie(p) {
  return `<path d="M320 250 Q400 160 480 250 L600 320 L560 420 L510 400 L515 620 Q400 650 285 620 L290 400 L240 420 L200 320 Z" fill="${p.color}"/>
  <path d="M330 250 Q400 330 470 250 Q470 200 400 190 Q330 200 330 250 Z" fill="${shade(p.color, -30)}"/>
  <rect x="330" y="470" width="140" height="80" rx="16" fill="${shade(p.color, -15)}"/>
  <line x1="380" y1="290" x2="376" y2="370" stroke="#fff" stroke-width="5"/><line x1="420" y1="290" x2="424" y2="370" stroke="#fff" stroke-width="5"/>
  ${PAW(400, 420, 1.1, '#fff')}`;
}

const SHAPES = { bag, pouch, can, box, bottle, dropper, tube, jar, cage, birdcage, aquarium, bowl, litterbox, bed, comb, hamsterbottle, ball, bone, mouse, wand, feltfish, wheel, swing, collar, harness, leash, shirt, hoodie };

function page(item) {
  gid = 0;
  const draw = SHAPES[item.shape](item);
  return `<!doctype html><html><head><style>html,body{margin:0}svg{display:block;font-family:'DejaVu Sans',Arial,sans-serif}</style></head><body>
  <svg id="s" width="800" height="800" viewBox="0 0 800 800" xmlns="http://www.w3.org/2000/svg">
  <defs><radialGradient id="bg" cx=".5" cy=".42" r=".75"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="${item.bg || '#efece7'}"/></radialGradient>
  <filter id="blur"><feGaussianBlur stdDeviation="14"/></filter><filter id="ds"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-opacity=".18"/></filter></defs>
  <rect width="800" height="800" fill="url(#bg)"/>
  <ellipse cx="400" cy="672" rx="230" ry="26" fill="#000" opacity=".16" filter="url(#blur)"/>
  <g filter="url(#ds)">${draw}</g>
  </svg></body></html>`;
}

(async () => {
  const items = JSON.parse(fs.readFileSync(path.join(__dirname, 'products.json'), 'utf8'));
  const browser = await chromium.launch();
  const pg = await browser.newPage({ viewport: { width: 800, height: 800 } });
  for (const item of items) {
    await pg.setContent(page(item));
    await pg.locator('#s').screenshot({ path: path.join(OUT, item.file + '.jpg'), type: 'jpeg', quality: 86 });
  }
  await browser.close();
  console.log(items.length, 'gambar ->', OUT);
})();
