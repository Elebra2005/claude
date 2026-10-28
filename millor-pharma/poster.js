'use strict';
// Праздничный постер для задания «Разбитый постер» (600×600, делится на 9 плиток 3×3).
function posterSvg() {
  const stars = [[60, 40], [140, 90], [240, 30], [330, 70], [430, 36], [520, 96], [570, 40], [90, 150], [480, 160]]
    .map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="${1.5 + (i % 3)}" fill="#f6d68a" opacity=".8"/>`).join('');
  const flask = (x, y, c, s = 1) => `<g transform="translate(${x} ${y}) scale(${s})"><rect x="-8" y="-60" width="16" height="30" rx="3" fill="#9fb3b8" opacity=".4"/><path d="M-8 -32 L-34 22 Q-36 34 -22 34 H22 Q36 34 34 22 L8 -32 Z" fill="#9fb3b8" opacity=".3"/><path d="M-22 0 L-34 22 Q-36 34 -22 34 H22 Q36 34 34 22 L22 0 Z" fill="${c}"/><circle cx="-8" cy="14" r="4" fill="#fff" opacity=".5"/><circle cx="10" cy="22" r="3" fill="#fff" opacity=".4"/></g>`;
  const box = (x, y, c, t) => `<g transform="translate(${x} ${y})"><rect width="92" height="64" rx="4" fill="${c}"/><rect y="22" width="92" height="20" fill="#f4ede6"/><text x="46" y="36" font-size="11" text-anchor="middle" font-family="Arial" font-weight="700" fill="#2a1d20">${t}</text><rect x="8" y="6" width="14" height="14" fill="#f4ede6" opacity=".8"/></g>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a0f18"/><stop offset=".55" stop-color="#2a1420"/><stop offset="1" stop-color="#140e12"/></linearGradient>
<radialGradient id="glow" cx="300" cy="320" r="260" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#a3192b" stop-opacity=".55"/><stop offset="1" stop-color="#a3192b" stop-opacity="0"/></radialGradient>
<radialGradient id="moon" cx=".4" cy=".4"><stop offset="0" stop-color="#fff6dc"/><stop offset="1" stop-color="#e9c97b"/></radialGradient>
</defs>
<rect width="600" height="600" fill="url(#bg)"/><rect width="600" height="600" fill="url(#glow)"/>${stars}
<circle cx="90" cy="95" r="52" fill="url(#moon)"/><circle cx="72" cy="82" r="9" fill="#d9b768" opacity=".55"/><circle cx="108" cy="110" r="6" fill="#d9b768" opacity=".55"/>
<g fill="#0b0709"><path d="M470 80 q18 -18 32 0 q8 -10 14 0 q14 -18 32 0 q-18 0 -24 14 q-8 -8 -14 0 q-8 -8 -14 0 q-6 -14 -26 -14z"/><path d="M380 130 q10 -10 18 0 q4 -6 8 0 q8 -10 18 0 q-10 0 -14 8 q-4 -4 -8 0 q-4 -4 -8 0 q-4 -8 -14 -8z"/></g>
<text x="300" y="180" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="58" fill="#f7f2ee" letter-spacing="3">МИЛЛОР ФАРМА</text>
<text x="300" y="214" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="22" fill="#f29f3d" letter-spacing="9">HALLOWEEN BINGO</text>
<rect x="30" y="268" width="170" height="8" fill="#4a3a3e"/><rect x="30" y="360" width="170" height="8" fill="#4a3a3e"/>
${flask(66, 268, '#a3192b', .9)}${flask(118, 268, '#f28c28', .75)}${flask(170, 268, '#5bbf8a', .9)}${flask(66, 360, '#f2b33d', .75)}${flask(118, 360, '#6d4ba8')}${flask(170, 360, '#a3192b', .8)}
<g transform="translate(300 340)"><path d="M-62 60 V-14 a62 62 0 0 1 124 0 V60 l-20 -18 -21 18 -21 -18 -21 18 -21 -18 z" fill="#f4efe6"/><circle cx="-22" cy="-10" r="9" fill="#1a1416"/><circle cx="22" cy="-10" r="9" fill="#1a1416"/><ellipse cx="0" cy="22" rx="11" ry="15" fill="#1a1416"/><circle cx="-34" cy="8" r="9" fill="#ffb3bd" opacity=".5"/><circle cx="34" cy="8" r="9" fill="#ffb3bd" opacity=".5"/></g>
<g transform="translate(500 345)"><path d="M-62 -34 Q-70 52 0 58 Q70 52 62 -34 Z" fill="#141012"/><ellipse cx="0" cy="-34" rx="66" ry="14" fill="#2a1f22"/><ellipse cx="0" cy="-34" rx="54" ry="9" fill="#5bbf8a"/><circle cx="-16" cy="-52" r="8" fill="#5bbf8a" opacity=".6"/><circle cx="14" cy="-66" r="11" fill="#5bbf8a" opacity=".45"/><circle cx="32" cy="-48" r="5" fill="#5bbf8a" opacity=".6"/></g>
<g transform="translate(95 505)"><ellipse rx="62" ry="46" fill="#e0731d"/><ellipse cx="-22" rx="22" ry="45" fill="#f28c28"/><ellipse cx="22" rx="22" ry="45" fill="#f28c28"/><rect x="-6" y="-60" width="12" height="18" rx="3" fill="#4c6b2f"/><path d="M-34 -10 l12 -14 12 14z M10 -10 l12 -14 12 14z M-30 14 q30 24 60 0 l-10 10 -10 -6 -10 6 -10 -6 -10 6z" fill="#3a1606"/></g>
<text x="300" y="470" text-anchor="middle" font-family="Georgia,serif" font-style="italic" font-size="25" fill="#f6d68a">Секретная лаборатория:</text>
<text x="300" y="506" text-anchor="middle" font-family="Georgia,serif" font-style="italic" font-weight="700" font-size="31" fill="#f7f2ee">спаси пятницу!</text>
<text x="300" y="560" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#b8acb0" letter-spacing="4">30 ОКТЯБРЯ · 10:00–17:00 МСК</text>
${box(440, 470, '#a3192b', 'ФЛАМИН')}${box(512, 508, '#5a2a7a', 'РЕГЛИСАМ')}${box(430, 540, '#f28c28', 'РЕАКТАКТИВ')}
<g stroke="#a3192b" stroke-width="2" fill="none" opacity=".5"><circle cx="540" cy="240" r="30"/><path d="M540 210 L566 255 H514 Z"/></g>
</svg>`;
}
module.exports = { posterSvg };
