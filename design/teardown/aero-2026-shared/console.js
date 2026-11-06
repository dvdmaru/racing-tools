// 主動空力的控制台：固定 1600 × 900 的 CSS 版面，update(s) 依這一格的狀態重畫。
// 介面中文為主，專有名詞的英文用全形空格接在後面（站上生成頁的慣例：racinglib._en()）。
// 卡片上的每一句都來自 articles/f1-101-active-aero（同一份規章出處），不另外加文章沒有的數字。
// 規章沒有寫攻角、阻力、下壓力的數字，畫面上也一律不顯示。
import {COL} from './car.js';
import {LAP, lapAt, RULE, T_SW, ZONES} from './kin.js';

export const C = {
  ink: '#241a1c',
  soft: '#493c40',
  mute: '#786a6e',
  faint: '#a6989c',
  line: '#e6dcdc',
  panel: 'rgba(253,249,249,.94)',
  red: COL.full,
  gold: COL.partial,
  teal: COL.signal,
  grey: '#9b9092',
};
const F = `'Chakra Petch','PingFang TC','Noto Sans TC','Microsoft JhengHei',sans-serif`;
export const PARTS = ['all', 'fw', 'rw', 'act', 'ecu'];
export const VIEWS = ['solid', 'xray', 'section', 'explode'];
export const PART_LABEL = {
  all: ['全部', ''],
  fw: ['前翼', 'FW'],
  rw: ['後翼', 'RW'],
  act: ['致動器', 'Actuator'],
  ecu: ['標準 ECU', ''],
};
export const VIEW_LABEL = {solid: '實體', xray: 'X 光', section: '剖開', explode: '爆炸圖'};

const CARD = {
  all: {
    zh: '車手可調車身',
    en: 'Driver Adjustable Bodywork',
    role: '2026 年會動的車身只有兩處：前翼元件與後翼襟翼，都由 FIA 標準 ECU 控制。',
    facts: [
      ['只有兩個位置', 'Corner Mode 與 Straight Mode，沒有「開一半」（C3.10.10 t；C3.11.6 h）'],
      ['切換上限', '400 毫秒（C3.10.10 o；C3.11.6 d）'],
      ['失效時', '設計上要回到 Corner Mode（C3.10.10 v；C3.11.6 i）'],
    ],
    src: '運動規章 B7.1.1 a',
  },
  fw: {
    zh: '前翼元件',
    en: 'Front Wing',
    role: 'Straight Mode 時，主翼片與（或）副翼片的攻角變小。這個模型畫的是後面兩片在動。',
    facts: [
      ['致動器', '最多兩個，每個都配位置感測器（C3.10.10）'],
      ['幅度固定', '每次減小的攻角都一樣，用完回到 Corner Mode 的位置'],
      ['車庫裡的另一種調整', '車輛靜止、用工具；主翼片最多 30 mm、副翼片最多 60 mm，不得減小攻角'],
    ],
    src: '技術規章 C3.10.10 n',
  },
  rw: {
    zh: '後翼襟翼',
    en: 'Rear Wing Flap',
    role: 'Straight Mode 時襟翼的攻角變小。下壓力與阻力一起減少，規章沒有寫差多少。',
    facts: [
      ['致動器', '單一致動器，配位置感測器；有實體擋塊（C3.11.6）'],
      ['低抓地條件', '宣告之後，後翼襟翼不能打到 Straight Mode（B7.1.2 b）'],
    ],
    src: '技術規章 C3.11.6 c',
  },
  act: {
    zh: '致動器與位置感測器',
    en: 'Actuator',
    role: '致動器推翼片轉動，位置感測器確認到位。400 毫秒從 ECU 發出指令起算，算到感測器確認為止。',
    facts: [
      ['數量', '前翼最多兩個、後翼一個（C3.10.10；C3.11.6）'],
      ['實體擋塊', '防止翼片轉出規定範圍（圖上金色小塊）'],
      ['誰控制', '連致動器在內，都歸 FIA 標準 ECU 控制（C8.2.1）'],
    ],
    src: '技術規章 C3.10.10；C3.11.6；C8.2.1',
  },
  ecu: {
    zh: 'FIA 標準 ECU',
    en: 'Standard ECU',
    role: '決定翼片在哪個位置的是 FIA 標準 ECU，不是車隊。指令來自車手本人，規章沒有寫用哪顆按鈕。',
    facts: [
      ['已啟用', '車手要先透過控制電子系統被通知「已啟用」（B7.1.2 a）；誰決定、何時啟用，B7.1 沒有寫'],
      ['部署狀態', '從車手下指令起，到翼片回到 Corner Mode 為止'],
    ],
    src: '運動規章 B7.1.1 a、B7.1.2 a；位置是示意',
  },
};

export const MODE = {
  off: {zh: '停用', sub: '前翼 Corner・後翼 Corner', col: C.ink},
  partial: {zh: '部分啟用', sub: '前翼 Straight・後翼 Corner', col: C.gold},
  full: {zh: '完全啟用', sub: '前翼 Straight・後翼 Straight', col: C.red},
  switch: {zh: '切換中', sub: '翼片在兩個位置之間（上限 400 毫秒）', col: C.mute},
};

const CSS = `
#app{font-family:${F};color:${C.ink};-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.ui{position:absolute;inset:0;pointer-events:none}
.pn{position:absolute;background:${C.panel};border:1px solid ${C.line};border-radius:10px;box-shadow:0 1px 2px rgba(36,26,28,.05)}
.h{font-size:14px;font-weight:700;letter-spacing:.5px;white-space:nowrap}
.en{font-size:.8em;font-weight:600;letter-spacing:.6px;color:${C.mute}}
.mu{color:${C.mute}}
.sm{font-size:12.5px;line-height:1.55}
.num{font-family:'Chakra Petch',${F};font-weight:700;letter-spacing:-.5px}
.tb{position:absolute;height:30px;padding:0 10px;display:flex;align-items:center;justify-content:center;gap:2px;font-size:13.5px;font-weight:600;letter-spacing:.3px;border:1px solid ${C.line};border-radius:7px;background:#fff;color:${C.ink};white-space:nowrap}
.tb .en{font-size:11px;color:inherit;opacity:.7}
.grp{position:absolute;font-size:12px;font-weight:600;letter-spacing:1px;color:${C.mute}}
.call{position:absolute;white-space:nowrap;font-size:14.5px;font-weight:700;color:${C.ink};padding:2px 7px;border-radius:5px;background:rgba(250,246,245,.88)}
.call .en{font-size:11.5px}
.cond{position:absolute;left:52px;width:268px;display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.35}
.cond b{flex:none;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11.5px;color:#fff;margin-top:1px}
.banner{position:absolute;left:800px;transform:translateX(-50%);height:32px;padding:0 16px;display:flex;align-items:center;gap:10px;border-radius:8px;background:#fff;font-size:13.5px;font-weight:700;letter-spacing:.4px;white-space:nowrap}
.cur{position:absolute;left:0;top:0;z-index:50;filter:drop-shadow(0 1px 2px rgba(0,0,0,.3))}
.ring{position:absolute;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;border:2px solid ${C.red};opacity:0;z-index:49}
`;
const el = (h) => {
  const d = document.createElement('div');
  d.innerHTML = h.trim();
  return d.firstElementChild;
};
const zhEn = (zh, en) => (en ? `${zh}<span class="en">　${en}</span>` : zh);
const ease = (x) => {
  const u = Math.min(1, Math.max(0, x));
  return u * u * u * (u * (u * 6 - 15) + 10);
};

export function createConsole(app) {
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);
  const ui = el(`<div class="ui"></div>`);
  app.appendChild(ui);
  const add = (h) => {
    const n = el(h);
    ui.appendChild(n);
    return n;
  };

  // ------------------------------------------------------------ 標題
  add(`<div style="position:absolute;left:36px;top:30px;width:44px;height:4px;border-radius:2px;background:${C.red}"></div>`);
  add(`<div style="position:absolute;left:36px;top:44px;font-size:30px;font-weight:800;letter-spacing:.5px">2026 主動空力<span class="en" style="font-size:16px">　Active Aero</span></div>`);
  add(`<div style="position:absolute;left:37px;top:88px;font-size:14px;font-weight:600;color:${C.soft}">前翼與後翼襟翼・只有兩個位置・FIA 標準 ECU 控制</div>`);
  add(`<div style="position:absolute;left:37px;top:110px;font-size:12.5px;color:${C.mute}">依公開資料重繪的示意模型</div>`);

  // ------------------------------------------------------------ 車速與狀態
  add(`<div class="pn" style="left:36px;top:142px;width:300px;height:132px"></div>`);
  add(`<div class="grp" style="left:52px;top:154px">車速<span style="letter-spacing:0">（示意一圈）</span></div>`);
  const vBig = add(`<div class="num" style="position:absolute;left:50px;top:170px;font-size:54px;line-height:1;color:${C.ink}"></div>`);
  add(`<div style="position:absolute;left:186px;top:200px;font-size:14px;font-weight:600;color:${C.mute}">km/h</div>`);
  const mBig = add(`<div style="position:absolute;left:52px;top:230px;font-size:16px;font-weight:700"></div>`);
  const mSub = add(`<div style="position:absolute;left:52px;top:252px;font-size:12.5px;color:${C.mute};white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 翼片位置與切換時間
  add(`<div class="pn" data-g="charts" style="left:36px;top:284px;width:300px;height:226px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:296px">翼片的位置</div>`);
  add(`<div class="mu" data-g="charts" style="position:absolute;left:52px;top:317px;font-size:12px;white-space:nowrap">只有兩格，沒有中間檔（C3.10.10 t；C3.11.6 h）</div>`);
  const gauge = add(`<svg data-g="charts" style="position:absolute;left:52px;top:338px" width="268" height="96"></svg>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:440px;font-size:13px">切換時間</div>`);
  const swBar = add(`<svg data-g="charts" style="position:absolute;left:52px;top:460px" width="268" height="24"></svg>`);
  const swTxt = add(`<div data-g="charts" style="position:absolute;left:52px;top:486px;font-size:12px;white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 三道關卡
  add(`<div class="pn" data-g="charts" style="left:36px;top:520px;width:300px;height:192px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:532px">用 Straight Mode 要過三關</div>`);
  const c1 = add(`<div class="cond" data-g="charts" style="top:558px"></div>`);
  const c2 = add(`<div class="cond" data-g="charts" style="top:596px"></div>`);
  const c3 = add(`<div class="cond" data-g="charts" style="top:634px"></div>`);
  const cRes = add(`<div data-g="charts" style="position:absolute;left:52px;top:678px;width:268px;font-size:13px;font-weight:700;white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 零件卡（右上）
  const card = add(`<div class="pn" style="left:1262px;top:30px;width:302px;padding:14px 17px 14px"></div>`);
  card.style.pointerEvents = 'none';

  // ------------------------------------------------------------ 按鈕（右下）
  add(`<div class="pn" style="left:1262px;top:574px;width:302px;height:296px"></div>`);
  const btn = {};
  const row = (keys, label, x0, y, w = null) => {
    let x = x0;
    for (const k of keys) {
      const [zh, en] = label(k);
      const width = w ?? Math.round(zh.replace(/ /g, '').length * 14 + (zh.includes(' ') ? 4 : 0) + (en ? en.length * 7.4 + 18 : 0) + 22);
      btn[k] = add(`<div class="tb" style="left:${x}px;top:${y}px;width:${width}px">${zhEn(zh, en)}</div>`);
      x += width + 6;
    }
  };
  add(`<div class="grp" style="left:1278px;top:586px">零件</div>`);
  row(['all', 'fw', 'rw'], (k) => PART_LABEL[k], 1278, 606);
  row(['act', 'ecu'], (k) => PART_LABEL[k], 1278, 642);
  add(`<div class="grp" style="left:1278px;top:684px">檢視</div>`);
  row(VIEWS, (k) => [VIEW_LABEL[k], ''], 1278, 704, 64);
  add(`<div class="grp" style="left:1278px;top:746px">條件<span style="letter-spacing:0;font-weight:500">（點了會改變這一圈）</span></div>`);
  btn.enabled = add(`<div class="tb" style="left:1278px;top:766px;width:132px">已啟用通知</div>`);
  btn.lowGrip = add(`<div class="tb" style="left:1416px;top:766px;width:132px">低抓地條件</div>`);
  btn.fail = add(`<div class="tb" style="left:1278px;top:802px;width:150px">模擬系統失效</div>`);
  btn.pause = add(`<div class="tb" style="left:1434px;top:802px;width:114px">暫停</div>`);
  add(`<div class="mu" style="position:absolute;left:1278px;top:842px;font-size:11.5px;white-space:nowrap">拖曳旋轉・滾輪縮放・H 隱藏面板</div>`);

  // ------------------------------------------------------------ 一圈的條帶（下方中央）
  const LS = {x: 380, y: 768, w: 840, h: 54};
  add(`<div class="grp" style="left:${LS.x}px;top:${LS.y - 24}px">示意一圈<span style="letter-spacing:0;font-weight:500">：車速曲線、啟動區與翼片狀態（不是任何真實賽道的數據）</span></div>`);
  const lap = add(`<svg style="position:absolute;left:${LS.x}px;top:${LS.y}px" width="${LS.w + 30}" height="${LS.h + 22}"></svg>`);
  const LX = (tau) => (tau / LAP) * LS.w;
  const LY = (v) => LS.h - (v / 360) * (LS.h - 4);
  let lapPath = '';
  for (let i = 0; i <= 400; i++) {
    const tau = (i / 400) * LAP;
    lapPath += `${i ? 'L' : 'M'}${LX(tau).toFixed(1)} ${LY(lapAt(tau).v).toFixed(1)}`;
  }
  let zoneSvg = '';
  ZONES.forEach(([a, b], i) => {
    zoneSvg += `<rect x="${LX(a).toFixed(1)}" y="0" width="${(LX(b) - LX(a)).toFixed(1)}" height="${LS.h}" fill="${C.ink}" opacity=".05"/><line x1="${LX(a).toFixed(1)}" x2="${LX(a).toFixed(1)}" y1="0" y2="${LS.h}" stroke="${C.mute}" stroke-width="1"/>`;
    zoneSvg += `<text x="${(LX(a) + 4).toFixed(1)}" y="11" font-size="10.5" fill="${C.mute}">啟動區 ${i + 1}</text>`;
  });

  // ------------------------------------------------------------ 賽事訊息與失效（上方中央）
  const bLow = add(`<div class="banner" style="top:64px;border:1.5px solid ${C.gold};color:${C.ink};opacity:0"><span style="color:${C.gold}">賽事總監宣告</span>LOW GRIP CONDITIONS<span class="mu" style="font-weight:600">只准前翼部分啟用（B7.1.2 b）</span></div>`);
  const bFail = add(`<div class="banner" style="top:104px;border:1.5px solid ${C.red};color:${C.red};opacity:0">系統失效（示意）<span style="color:${C.ink};font-weight:600">翼片回到 Corner Mode（C3.10.10 v；C3.11.6 i）</span></div>`);

  // ------------------------------------------------------------ 免責聲明（最下方）
  add(`<div style="position:absolute;left:360px;right:360px;top:868px;text-align:center;font-size:11.5px;color:${C.faint};white-space:nowrap">依公開資料重繪的示意模型：比例、翼片角度與零件位置不是實物，無任何車隊塗裝或標誌。條件與 400 毫秒上限依 FIA 2026 規章；車速、啟動區與切換時間為示意。</div>`);

  // ------------------------------------------------------------ 標籤、指標
  const callSvg = add(`<svg data-callouts style="position:absolute;inset:0;overflow:visible" width="1600" height="900"></svg>`);
  const callG = add(`<div data-callouts style="position:absolute;inset:0"></div>`);
  const ring = add(`<div class="ring"></div>`);
  const cur = add(`<div class="cur"><svg width="24" height="24" viewBox="0 0 34 34"><path d="M4 3 L30 13.5 L17.5 17.5 L13.5 30 Z" fill="#111" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg></div>`);
  const centre = (n) => {
    const r = n.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  };
  const spots = Object.fromEntries(Object.entries(btn).map(([k, n]) => [k, centre(n)]));
  const pointer = (c) => {
    cur.style.display = c.x < 0 ? 'none' : 'block';
    cur.style.transform = `translate(${(c.x - 3).toFixed(2)}px, ${(c.y - 2).toFixed(2)}px) scale(${c.press ? 0.88 : 1})`;
    ring.style.left = `${c.ringX}px`;
    ring.style.top = `${c.ringY}px`;
    ring.style.opacity = String(c.ring * 0.85);
    ring.style.transform = `scale(${(0.35 + 0.9 * (1 - c.ring)).toFixed(3)})`;
  };
  const toggle = (n, on, col = C.ink) => {
    n.style.background = on ? col : '#fff';
    n.style.color = on ? '#fff' : C.ink;
    n.style.borderColor = on ? col : C.line;
  };
  const condRow = (n, ok, title, sub, warn = false) => {
    const col = ok ? C.teal : warn ? C.gold : C.grey;
    n.innerHTML = `<b style="background:${col}">${ok ? '✓' : warn ? '!' : '✕'}</b><div><div style="font-weight:700">${title}</div><div class="mu" style="font-size:11.5px;white-space:nowrap">${sub}</div></div>`;
  };

  let lastCard = '';
  return {
    btn,
    spots,
    root: ui,
    lapRect: LS,
    pointer,
    update(s) {
      const st = s.st;
      vBig.textContent = Math.round(st.v);
      const m = MODE[st.mode];
      mBig.textContent = m.zh;
      mBig.style.color = m.col;
      mSub.textContent = m.sub;

      // 兩片翼片的位置：左＝Corner、右＝Straight，只有兩個刻度
      {
        const W = 268;
        const X0 = 64;
        const X1 = W - 54;
        let h = '';
        const rowY = [22, 70];
        [
          ['前翼元件', st.pf, st.tf],
          ['後翼襟翼', st.pr, st.tr],
        ].forEach(([label, p, target], i) => {
          const y = rowY[i];
          const k = ease(p);
          const col = p > 0.999 ? (i === 0 && st.pr < 0.001 ? C.gold : C.red) : p < 0.001 ? C.ink : C.mute;
          h += `<text x="0" y="${y + 4}" font-size="12.5" font-weight="700" fill="${C.ink}">${label}</text>`;
          h += `<line x1="${X0}" x2="${X1}" y1="${y}" y2="${y}" stroke="${C.line}" stroke-width="6" stroke-linecap="round"/>`;
          h += `<line x1="${X0}" x2="${X0 + (X1 - X0) * k}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="6" stroke-linecap="round" opacity="${p > 0.001 ? 0.85 : 0}"/>`;
          for (const [x, name] of [[X0, 'Corner'], [X1, 'Straight']]) h += `<circle cx="${x}" cy="${y}" r="5.5" fill="#fff" stroke="${C.faint}" stroke-width="1.5"/><text x="${x}" y="${y + 20}" font-size="10.5" text-anchor="middle" fill="${C.mute}">${name}</text>`;
          h += `<circle cx="${X0 + (X1 - X0) * k}" cy="${y}" r="7.5" fill="${col}" stroke="#fff" stroke-width="2"/>`;
          if (target !== (p > 0.5 ? 1 : 0) || (p > 0.001 && p < 0.999)) h += `<text x="${W}" y="${y + 4}" font-size="11" text-anchor="end" fill="${C.mute}">移動中</text>`;
        });
        gauge.innerHTML = h;
      }
      // 切換時間：正在切就即時跑表，否則顯示上一次；刻度到 500 毫秒，400 是上限
      {
        const W = 268;
        const X = (ms) => (ms / 500) * W;
        const live = st.mode === 'switch';
        const ms = live ? Math.min(T_SW, Math.min(st.cmdF, st.cmdR)) * 1000 : st.lastMs;
        let h = `<rect x="0" y="4" width="${W}" height="10" rx="5" fill="#efe7e7"/>`;
        h += `<rect x="0" y="4" width="${X(ms).toFixed(1)}" height="10" rx="5" fill="${live ? C.teal : C.ink}" opacity=".8"/>`;
        h += `<line x1="${X(RULE.switchMax * 1000)}" x2="${X(RULE.switchMax * 1000)}" y1="0" y2="18" stroke="${C.red}" stroke-width="2"/>`;
        h += `<text x="${X(RULE.switchMax * 1000) + 5}" y="22" font-size="10.5" fill="${C.red}">上限 400</text>`;
        swBar.innerHTML = h;
        swTxt.innerHTML = ms > 0
          ? `${live ? '切換中' : '上一次切換'} <span class="num" style="font-size:15px">${Math.round(ms)}</span> 毫秒<span class="mu">（示意值，規章只給上限）</span>`
          : `<span class="mu">還沒切換過（上限 400 毫秒，C3.10.10 o）</span>`;
      }
      // 三道關卡
      {
        condRow(c1, st.enabled, '已被通知「已啟用」', '透過控制電子系統（B7.1.2 a）');
        condRow(c2, st.zone >= 0, st.zone >= 0 ? `完全在啟動區 ${st.zone + 1} 內` : '不在啟動區內', '部署狀態只准發生在區內（C3.10.10 w）');
        condRow(c3, !st.lowGrip, st.lowGrip ? '已宣告低抓地條件' : '沒有宣告低抓地條件', st.lowGrip ? '只准前翼部分啟用（B7.1.2 b）' : '宣告後只准前翼部分啟用（B7.1.2 b）', st.lowGrip);
        let res;
        let col;
        if (st.failed) [res, col] = ['系統失效（示意）：停在 Corner Mode', C.red];
        else if (!st.enabled) [res, col] = ['結果：不能啟用', C.grey];
        else if (st.zone < 0) [res, col] = ['結果：不在啟動區，翼片留在 Corner', C.grey];
        else if (st.lowGrip) [res, col] = ['結果：只准部分啟用（前翼）', C.gold];
        else [res, col] = ['結果：可以完全啟用', C.red];
        cRes.textContent = res;
        cRes.style.color = col;
      }

      // 零件卡
      if (s.focus !== lastCard) {
        lastCard = s.focus;
        const c = CARD[s.focus];
        const facts = c.facts
          .map(([k, v]) => `<div style="padding:8px 0;border-top:1px solid ${C.line}"><div style="font-size:12px;font-weight:700;color:${C.mute};letter-spacing:.5px">${k}</div><div class="sm" style="margin-top:2px">${v}</div></div>`)
          .join('');
        const foot = s.focus === 'all' ? `<span class="mu">點右下的零件按鈕，拆開來看</span>` : `<span class="mu">出處：${c.src}</span>`;
        // 英文長的（Driver Adjustable Bodywork）放到第二行，不擠出卡片
        const title = c.en.length > 12 ? `${c.zh}<div class="en" style="font-size:13px;margin-top:2px">${c.en}</div>` : zhEn(c.zh, c.en);
        card.innerHTML = `<div style="font-size:${c.zh.length > 7 ? 21 : 24}px;font-weight:800;white-space:nowrap">${title}</div>
          <div class="sm" style="margin:8px 0 10px;color:${C.soft}">${c.role}</div>${facts}
          <div style="padding-top:9px;border-top:1px solid ${C.line};font-size:12.5px">${foot}</div>`;
      }

      // 一圈的條帶：啟動區、車速曲線、翼片狀態色帶、這一格的游標
      {
        let h = zoneSvg;
        let prev = null;
        let x0 = 0;
        const N = 360;
        for (let i = 0; i <= N; i++) {
          const tau = (i / N) * LAP;
          const p = i < N ? s.modeAt(tau) : null;
          const k = p === 'switch' ? prev : p;
          if (k !== prev) {
            if (prev === 'full' || prev === 'partial') h += `<rect x="${x0.toFixed(1)}" y="${LS.h + 4}" width="${(LX(tau) - x0).toFixed(1)}" height="6" fill="${MODE[prev].col}" opacity=".85"/>`;
            prev = k;
            x0 = LX(tau);
          }
        }
        h += `<path d="${lapPath}" fill="none" stroke="${C.ink}" stroke-width="1.6"/>`;
        const cx = LX(st.tau);
        h += `<line x1="${cx}" x2="${cx}" y1="0" y2="${LS.h + 10}" stroke="${C.red}" stroke-width="2"/><circle cx="${cx}" cy="${LY(st.v)}" r="4.5" fill="${C.red}"/>`;
        h += `<text x="0" y="${LS.h + 22}" font-size="11" fill="${C.mute}"><tspan fill="${C.red}">■</tspan> 完全啟用　<tspan fill="${C.gold}">■</tspan> 部分啟用　灰底＝啟動區（位置與長度示意）</text>`;
        lap.innerHTML = h;
      }

      // 賽事訊息
      bLow.style.opacity = st.lowGrip ? '1' : '0';
      bFail.style.opacity = st.failed ? '1' : '0';

      // 按鈕狀態
      for (const k of PARTS) toggle(btn[k], s.focus === k);
      for (const k of VIEWS) toggle(btn[k], s.view === k);
      toggle(btn.enabled, st.enabled, C.teal);
      toggle(btn.lowGrip, st.lowGrip, C.gold);
      toggle(btn.fail, st.failed, C.red);
      btn.pause.textContent = s.paused ? '▶ 繼續' : '暫停';

      // 標籤：只在看整體時出現，從零件中心拉一條細線
      let lh = '';
      let ch = '';
      for (const c of s.callouts) {
        if (c.o < 0.02 || !c.at) continue;
        const [ax, ay] = c.at;
        const [lx, ly] = c.label;
        const left = lx < ax;
        const ex = left ? lx + c.w : lx;
        lh += `<polyline points="${ax.toFixed(1)},${ay.toFixed(1)} ${ex.toFixed(1)},${(ly + 22).toFixed(1)} ${(left ? lx : lx + c.w).toFixed(1)},${(ly + 22).toFixed(1)}" fill="none" stroke="${C.mute}" stroke-width="1" opacity="${c.o.toFixed(2)}"/><circle cx="${ax.toFixed(1)}" cy="${ay.toFixed(1)}" r="3" fill="${C.ink}" opacity="${c.o.toFixed(2)}"/>`;
        ch += `<div class="call" style="left:${lx.toFixed(1)}px;top:${ly.toFixed(1)}px;opacity:${c.o.toFixed(2)}">${c.html}</div>`;
      }
      callSvg.innerHTML = lh;
      callG.innerHTML = ch;
      pointer(s.cursor);
    },
  };
}
