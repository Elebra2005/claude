'use strict';
// Иллюстрация ночной лаборатории для задания «Охотник за привидениями» (viewBox 800×500).
// Отдаётся сервером только авторизованному игроку; клики проверяются на сервере.

const ghost = (x, y, s, rot, op) => `
  <g transform="translate(${x} ${y}) rotate(${rot}) scale(${s})" opacity="${op}">
    <path d="M-13 12 V-2 a13 13 0 0 1 26 0 V12 l-4.3 -4 -4.4 4 -4.3 -4 -4.3 4 -4.4 -4 z" fill="#f4efe6"/>
    <circle cx="-4.5" cy="-2" r="2.1" fill="#1a1416"/><circle cx="4.5" cy="-2" r="2.1" fill="#1a1416"/>
    <ellipse cx="0" cy="4" rx="2.2" ry="2.8" fill="#1a1416"/>
  </g>`;

const flask = (x, y, color, h = 46) => `
  <g transform="translate(${x} ${y})">
    <rect x="-5" y="${-h}" width="10" height="${h * 0.45}" rx="2" fill="#9fb3b8" opacity=".35"/>
    <path d="M-5 ${-h * 0.56} L-18 0 Q-18 6 -12 6 H12 Q18 6 18 0 L5 ${-h * 0.56} Z" fill="#9fb3b8" opacity=".28"/>
    <path d="M-11 -10 L-17 0 Q-17 5 -12 5 H12 Q17 5 17 0 L11 -10 Z" fill="${color}" opacity=".85"/>
    <circle cx="-4" cy="-5" r="1.6" fill="#fff" opacity=".6"/><circle cx="5" cy="-2" r="1" fill="#fff" opacity=".5"/>
  </g>`;

const box = (x, y, w, h, c, label) => `
  <g transform="translate(${x} ${y})">
    <rect width="${w}" height="${h}" rx="2" fill="${c}"/>
    <rect y="${h * 0.35}" width="${w}" height="${h * 0.22}" fill="#fff" opacity=".8"/>
    <text x="${w / 2}" y="${h * 0.52}" font-size="${Math.min(9, h * 0.18)}" text-anchor="middle" fill="#2a1d20" font-family="Arial" font-weight="700">${label}</text>
    <rect x="${w * 0.1}" y="${h * 0.1}" width="${w * 0.18}" height="${w * 0.18}" fill="#fff" opacity=".7"/>
  </g>`;

function ghostScene(spots) {
  const [g1, g2, g3, g4, g5] = spots;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="800" height="500">
  <defs>
    <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b1619"/><stop offset="1" stop-color="#2a1f22"/></linearGradient>
    <radialGradient id="lamp" cx="300" cy="60" r="260" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#f29f3d" stop-opacity=".28"/><stop offset="1" stop-color="#f29f3d" stop-opacity="0"/></radialGradient>
    <radialGradient id="moon" cx="0.4" cy="0.4"><stop offset="0" stop-color="#fff6dc"/><stop offset="1" stop-color="#e9c97b"/></radialGradient>
    <pattern id="tiles" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="#231b1d"/><path d="M0 0H40V40" fill="none" stroke="#2f2427" stroke-width="2"/></pattern>
  </defs>
  <rect width="800" height="500" fill="url(#wall)"/>
  <rect y="400" width="800" height="100" fill="url(#tiles)"/>
  <rect y="398" width="800" height="4" fill="#3a2b2f"/>

  <!-- окно с луной -->
  <rect x="610" y="30" width="150" height="120" rx="6" fill="#0e1424" stroke="#4a3a3e" stroke-width="8"/>
  <circle cx="710" cy="70" r="26" fill="url(#moon)"/>
  <circle cx="700" cy="62" r="4" fill="#d9b768" opacity=".6"/><circle cx="719" cy="80" r="3" fill="#d9b768" opacity=".6"/>
  <path d="M685 32 V148 M612 90 H758" stroke="#4a3a3e" stroke-width="6"/>
  <path d="M630 120 q8 -10 16 0 q8 -10 16 0" fill="none" stroke="#1b1619" stroke-width="3"/>
  ${ghost(g2.x, g2.y, 0.62, -12, 0.5)}
  <rect x="612" y="88" width="72" height="4" fill="#4a3a3e"/>

  <!-- лампа -->
  <rect width="800" height="500" fill="url(#lamp)"/>
  <path d="M300 0 V22" stroke="#4a3a3e" stroke-width="3"/>
  <path d="M276 46 L288 22 H312 L324 46 Z" fill="#3a2b2f"/>
  <ellipse cx="300" cy="48" rx="12" ry="5" fill="#f6c46b"/>
  ${ghost(g5.x, g5.y, 0.62, 18, 0.42)}

  <!-- полки с колбами -->
  <rect x="40" y="176" width="210" height="10" fill="#4a3a3e"/>
  <rect x="40" y="268" width="210" height="10" fill="#4a3a3e"/>
  ${ghost(g1.x, g1.y, 0.62, 8, 0.6)}
  ${flask(80, 176, '#9b1d2a')}${flask(150, 176, '#f28c28', 40)}${flask(205, 176, '#5bbf8a', 52)}
  ${flask(70, 268, '#f2b33d', 36)}${flask(125, 268, '#6d4ba8')}${flask(190, 268, '#9b1d2a', 42)}
  <path d="M60 300 q10 18 0 36 M60 300 q-10 18 0 36" stroke="#3a2b2f" stroke-width="1.5" fill="none" opacity=".7"/>


  <!-- отвлекающие предметы: белое, но не привидения -->
  <g transform="translate(228 266)" opacity=".75"><ellipse cx="0" cy="-9" rx="9" ry="8" fill="#e6dfd0"/><rect x="-5" y="-3" width="10" height="5" rx="1" fill="#e6dfd0"/><circle cx="-3.4" cy="-9" r="2" fill="#1a1416"/><circle cx="3.4" cy="-9" r="2" fill="#1a1416"/></g>
  <g transform="translate(385 118)" opacity=".7"><path d="M-16 -6 L-8 -12 H8 L16 -6 L22 24 H-22 Z" fill="#d9d2c4"/><path d="M-2 -12 L0 4 L2 -12" stroke="#a9a090" fill="none"/><rect x="-1" y="-24" width="2" height="12" fill="#6b5a4a"/></g>
  <g transform="translate(540 372)" opacity=".8"><rect x="-4" y="-18" width="8" height="18" rx="2" fill="#e9e1d0"/><path d="M0 -26 q4 5 0 8 q-4 -3 0 -8z" fill="#f6c46b"/></g>

  <!-- паутина -->
  <g stroke="#6b5b5f" stroke-width="1" fill="none" opacity=".6">
    <path d="M0 0 L90 0 M0 0 L0 90 M0 0 L70 60 M0 0 L35 80 M0 0 L80 30"/>
    <path d="M30 0 Q22 22 0 30 M55 0 Q42 42 0 55 M80 0 Q62 62 0 80"/>
  </g>

  <!-- шкаф с аптечными упаковками -->
  <rect x="470" y="190" width="230" height="208" rx="4" fill="#2f2326" stroke="#4a3a3e" stroke-width="5"/>
  <rect x="478" y="262" width="214" height="6" fill="#4a3a3e"/><rect x="478" y="334" width="214" height="6" fill="#4a3a3e"/>
  ${box(486, 214, 52, 48, '#9b1d2a', 'ФЛАМИН')}${box(546, 222, 60, 40, '#f28c28', 'РЕГЛИСАМ')}${box(614, 206, 70, 56, '#5a2a7a', 'КАРДИОВАЛЕН')}
  ${box(490, 290, 48, 44, '#f2b33d', 'МИЛЛОР')}
  ${ghost(g4.x, g4.y, 0.62, -6, 0.42)}
  ${box(612, 286, 66, 48, '#9b1d2a', 'ФЛАМИН')}
  ${box(486, 356, 70, 42, '#5a2a7a', 'РЕГЛИСАМ')}${box(566, 362, 50, 36, '#f28c28', 'АПТЕКА')}${box(626, 352, 60, 46, '#2f6b5a', 'ЛАБ-13')}

  <!-- лабораторный стол -->
  <rect x="300" y="378" width="270" height="16" rx="3" fill="#4a3a3e"/>
  <rect x="314" y="394" width="12" height="76" fill="#3a2b2f"/><rect x="544" y="394" width="12" height="76" fill="#3a2b2f"/>
  ${ghost(g3.x, g3.y, 0.62, 4, 0.55)}
  ${flask(350, 378, '#5bbf8a', 34)}${flask(410, 378, '#f28c28', 48)}
  <g transform="translate(470 378)"><rect x="-4" y="-56" width="8" height="56" fill="#9fb3b8" opacity=".35"/><rect x="-4" y="-22" width="8" height="22" fill="#9b1d2a"/></g>
  <g transform="translate(510 378)"><rect x="-6" y="-30" width="30" height="30" rx="4" fill="#2a1f22" stroke="#6b5b5f"/><circle cx="9" cy="-15" r="8" fill="#f28c28" opacity=".8"/></g>

  <!-- тыква и котёл -->
  <g transform="translate(150 430)">
    <ellipse cx="0" cy="0" rx="40" ry="30" fill="#e0731d"/><ellipse cx="-14" cy="0" rx="14" ry="29" fill="#f28c28"/><ellipse cx="14" cy="0" rx="14" ry="29" fill="#f28c28"/>
    <rect x="-4" y="-38" width="8" height="12" rx="2" fill="#4c6b2f"/>
    <path d="M-20 -8 l8 -8 l8 8 z M4 -8 l8 -8 l8 8 z M-18 10 q18 14 36 0 l-6 6 l-6 -4 l-6 4 l-6 -4 l-6 4 z" fill="#3a1606"/>
  </g>
  <g transform="translate(720 450)">
    <path d="M-44 -24 Q-50 30 0 34 Q50 30 44 -24 Z" fill="#141012"/><ellipse cx="0" cy="-24" rx="46" ry="10" fill="#2a1f22"/>
    <ellipse cx="0" cy="-24" rx="38" ry="6" fill="#5bbf8a" opacity=".85"/>
    <circle cx="-10" cy="-34" r="5" fill="#5bbf8a" opacity=".5"/><circle cx="8" cy="-44" r="7" fill="#5bbf8a" opacity=".35"/><circle cx="20" cy="-30" r="3" fill="#5bbf8a" opacity=".55"/>
  </g>

  <!-- летучие мыши и символы -->
  <g fill="#0d0a0b">
    <path d="M420 90 q10 -10 18 0 q4 -6 8 0 q8 -10 18 0 q-10 0 -14 8 q-4 -4 -8 0 q-4 -4 -8 0 q-4 -8 -14 -8 z"/>
    <path d="M520 130 q7 -7 13 0 q3 -4 6 0 q6 -7 13 0 q-7 0 -10 6 q-3 -3 -6 0 q-3 -3 -6 0 q-3 -6 -10 -6 z"/>
  </g>
  <g stroke="#9b1d2a" stroke-width="2" fill="none" opacity=".55">
    <circle cx="380" cy="230" r="34"/><path d="M380 196 L409 247 H351 Z"/><circle cx="380" cy="230" r="6"/>
  </g>
  <text x="380" y="292" font-family="Georgia,serif" font-size="13" fill="#c9a26b" text-anchor="middle" opacity=".7">ЛАБОРАТОРИЯ № 13</text>
</svg>`;
}

module.exports = { ghostScene };
