// 煞車頁的控制台：固定 1600 × 900 的 CSS 版面，update(s) 依這一格的狀態重畫。
// 介面中文為主，專有名詞的英文用全形空格接在後面。卡片上的每一句都來自 articles/f1-101-brakes。
// 壓力只畫相對值（規章沒有比賽中的壓力數字）；溫度是示意熱模型的輸出，標「示意」。
import {COL} from './car.js';
import {LAP, lapAt, RULE} from './kin.js';

export const C = {
  ink: '#241a1c',
  soft: '#493c40',
  mute: '#786a6e',
  faint: '#a6989c',
  line: '#e6dcdc',
  panel: 'rgba(253,249,249,.94)',
  red: COL.press,
  teal: COL.harvest,
  hot: '#e0661c',
  gold: '#c8971f',
  grey: '#9b9092',
};
const F = `'Chakra Petch','PingFang TC','Noto Sans TC','Microsoft JhengHei',sans-serif`;
export const PARTS = ['all', 'pedal', 'fbrake', 'rbrake', 'bbw', 'mguk'];
export const VIEWS = ['solid', 'xray', 'section', 'explode'];
export const PART_LABEL = {
  all: ['全部', ''],
  pedal: ['踏板', 'Pedal'],
  fbrake: ['前輪煞車', ''],
  rbrake: ['後輪煞車', ''],
  bbw: ['電控', 'BBW'],
  mguk: ['馬達', 'MGU-K'],
};
export const VIEW_LABEL = {solid: '實體', xray: 'X 光', section: '剖開', explode: '爆炸圖'};

const CARD = {
  all: {
    zh: '煞車系統',
    en: 'Brake System',
    role: '一輛車只准一套煞車系統：一根踏板推兩個主缸，前後兩條油路各自獨立，任一條失效，另一條仍能煞車。',
    facts: [
      ['沒有 ABS', '明文禁止防止車輪鎖死的煞車系統（C11.4.1）'],
      ['碳碳盤', '規章允許碳碳複合材料當摩擦材料（C15.4.c）；Brembo 說 2026 年仍是碳碳'],
      ['溫度管理', '禁止用液體冷卻（C11.5），也禁止另外加熱或保溫（C10.8.3.d）'],
    ],
    src: '技術規章 C11.1.1',
  },
  pedal: {
    zh: '踏板與主缸',
    en: 'Master Cylinders',
    role: '腳下只有一根踏板，推動兩個主缸：一個管前輪、一個管後輪。主缸把腳力轉成油壓。',
    facts: [
      ['煞車平衡', '前後分配的比例，車手開車途中就能調（F1 官方詞彙表）'],
      ['調整的規矩', '賽道上的變更要由車手直接操作，或由後輪煞車控制系統完成，不得預先設定（C11.1.4）'],
      ['Brembo 模擬', '蒙札 1 號彎：318 降到 87 km/h、3.22 秒、踏板 111 公斤、3.8 g'],
    ],
    src: '技術規章 C11.1.1、C11.1.4',
  },
  fbrake: {
    zh: '前輪煞車',
    en: 'Front Brake',
    role: '前輪只有液壓：踏板推前主缸，油壓直接送到卡鉗，卡鉗把來令片夾在碳碳盤上。',
    facts: [
      ['碟盤尺寸', '直徑 325 到 345 mm、厚度最多 34 mm、冷卻孔最小直徑 2.5 mm（C11.3）'],
      ['溫度', 'Brembo：工作窗口通常攝氏 350 到 550 度，重煞可超過 1,000 度'],
      ['2026 年', 'Brembo：前盤最大直徑放大 15 mm'],
    ],
    src: '技術規章 C11.3',
  },
  rbrake: {
    zh: '後輪煞車',
    en: 'Rear Brake',
    role: '2026 年後輪煞車沒有被馬達取代：馬達幫不上忙時，機械煞車也要夠用。',
    facts: [
      ['不靠動力單元', '每個後輪至少 2500 牛頓米，卡鉗壓力不超過 150 barG（C11.1.1）'],
      ['碟盤尺寸', '直徑 260 到 280 mm、厚度最多 34 mm（C11.3）'],
      ['2026 年', 'Brembo：後盤厚度上限從 32 mm 加到 34 mm'],
    ],
    src: '技術規章 C11.1.1、C11.3',
  },
  bbw: {
    zh: '後輪電控',
    en: 'Brake-by-Wire',
    role: '後輪的油壓可以由電動控制系統給：馬達回收得多，就少給油壓，讓後輪總減速仍照車手的平衡設定。',
    facts: [
      ['上限', '不能超過車手同時在後主缸產生壓力的 1.2 倍（C11.6）'],
      ['停用時', '連著踏板的液壓主缸仍把壓力送到後輪（C11.6）'],
      ['唯一例外', '其他煞車都不得讓卡鉗壓力高於車手踩出的壓力（C11.4.2）'],
    ],
    src: '技術規章 C11.6、C11.4.2；位置是示意',
  },
  mguk: {
    zh: '電動馬達回收',
    en: 'MGU-K',
    role: '煞車時 MGU-K 反過來當發電機，把後輪減速的動能收回電池。這頁的回收量沿用動力單元頁的同一圈。',
    facts: [
      ['2026 年', 'Brembo：功率從 120 kW 提高到 350 kW，回收能力近三倍'],
      ['不是新做法', 'F1 官方 2014 年的技術解說就在講這套後輪分工'],
    ],
    src: 'Brembo 2026 規則頁；F1 官方 2014',
  },
};

export const PHASE = {
  brake: {zh: '煞車・前後分擔', sub: '前輪：液壓　後輪：液壓＋馬達回收', col: C.red},
  brakeNoK: {zh: '煞車・馬達沒有回收', sub: '後輪全靠液壓', col: C.red},
  brakeNoBbw: {zh: '煞車・後輪電控停用', sub: '後輪壓力＝後主缸壓力（C11.6）', col: C.red},
  lift: {zh: '收油・馬達回收', sub: '沒踩煞車，MGU-K 讓後輪減速', col: C.teal},
  full: {zh: '全油門', sub: '沒有煞車，碟盤降溫', col: C.ink},
  part: {zh: '部分油門', sub: '沒有煞車，碟盤降溫', col: C.ink},
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
.tb{position:absolute;height:30px;padding:0 8px;display:flex;align-items:center;justify-content:center;gap:2px;font-size:13.5px;font-weight:600;letter-spacing:.3px;border:1px solid ${C.line};border-radius:7px;background:#fff;color:${C.ink};white-space:nowrap}
.tb .en{font-size:11px;color:inherit;opacity:.7}
.grp{position:absolute;font-size:12px;font-weight:600;letter-spacing:1px;color:${C.mute}}
.call{position:absolute;white-space:nowrap;font-size:14.5px;font-weight:700;color:${C.ink};padding:2px 7px;border-radius:5px;background:rgba(250,246,245,.88)}
.call .en{font-size:11.5px}
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
  add(`<div style="position:absolute;left:36px;top:44px;font-size:30px;font-weight:800;letter-spacing:.5px">2026 煞車系統<span class="en" style="font-size:16px">　Brakes</span></div>`);
  add(`<div style="position:absolute;left:37px;top:88px;font-size:14px;font-weight:600;color:${C.soft}">一根踏板・兩條油路・後輪馬達分擔減速</div>`);
  add(`<div style="position:absolute;left:37px;top:110px;font-size:12.5px;color:${C.mute}">依公開資料重繪的示意模型</div>`);

  // ------------------------------------------------------------ 車速與狀態
  add(`<div class="pn" style="left:36px;top:142px;width:300px;height:132px"></div>`);
  add(`<div class="grp" style="left:52px;top:154px">車速<span style="letter-spacing:0">（示意一圈）</span></div>`);
  const vBig = add(`<div class="num" style="position:absolute;left:50px;top:170px;font-size:54px;line-height:1;color:${C.ink}"></div>`);
  add(`<div style="position:absolute;left:186px;top:200px;font-size:14px;font-weight:600;color:${C.mute}">km/h</div>`);
  const phBig = add(`<div style="position:absolute;left:52px;top:230px;font-size:16px;font-weight:700"></div>`);
  const phSub = add(`<div style="position:absolute;left:52px;top:252px;font-size:12.5px;color:${C.mute};white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 壓力（相對值）
  add(`<div class="pn" data-g="charts" style="left:36px;top:284px;width:300px;height:170px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:296px">煞車壓力<span class="mu" style="font-weight:600;font-size:12px">（相對值，踏板踩到底＝100%）</span></div>`);
  const pres = add(`<svg data-g="charts" style="position:absolute;left:52px;top:318px;overflow:visible" width="268" height="112"></svg>`);
  add(`<div class="mu" data-g="charts" style="position:absolute;left:52px;top:432px;font-size:12px;white-space:nowrap">紅線＝後主缸的 1.2 倍，後卡鉗的上限（C11.6）</div>`);

  // ------------------------------------------------------------ 後輪減速分工
  add(`<div class="pn" data-g="charts" style="left:36px;top:464px;width:300px;height:96px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:476px">後輪減速分工<span class="mu" style="font-weight:600;font-size:12px">（示意）</span></div>`);
  const split = add(`<svg data-g="charts" style="position:absolute;left:52px;top:498px" width="268" height="18"></svg>`);
  const splitTxt = add(`<div data-g="charts" style="position:absolute;left:52px;top:520px;font-size:12.5px;white-space:nowrap"></div>`);
  const balTxt = add(`<div data-g="charts" class="mu" style="position:absolute;left:52px;top:538px;font-size:12px;white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 碟盤溫度
  add(`<div class="pn" data-g="charts" style="left:36px;top:570px;width:300px;height:142px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:582px">碟盤溫度<span class="mu" style="font-weight:600;font-size:12px">（示意熱模型，不是實測）</span></div>`);
  const temp = add(`<svg data-g="charts" style="position:absolute;left:52px;top:604px" width="268" height="84"></svg>`);
  add(`<div class="mu" data-g="charts" style="position:absolute;left:52px;top:690px;font-size:12px;white-space:nowrap">灰帶＝Brembo 說的工作窗口 350–550°C</div>`);

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
      const width = w ?? Math.round(zh.replace(/ /g, '').length * 14 + (en ? en.length * 7.2 + 16 : 0) + 18);
      btn[k] = add(`<div class="tb" style="left:${x}px;top:${y}px;width:${width}px">${zhEn(zh, en)}</div>`);
      x += width + 6;
    }
  };
  add(`<div class="grp" style="left:1278px;top:586px">零件</div>`);
  row(['all', 'pedal', 'fbrake'], (k) => PART_LABEL[k], 1278, 606);
  row(['rbrake', 'bbw', 'mguk'], (k) => PART_LABEL[k], 1278, 642);
  add(`<div class="grp" style="left:1278px;top:684px">檢視</div>`);
  row(VIEWS, (k) => [VIEW_LABEL[k], ''], 1278, 704, 64);
  add(`<div class="grp" style="left:1278px;top:746px">條件<span style="letter-spacing:0;font-weight:500">（點了會改變這一圈）</span></div>`);
  btn.balF = add(`<div class="tb" style="left:1278px;top:766px;width:132px">平衡往前 ▲</div>`);
  btn.balR = add(`<div class="tb" style="left:1416px;top:766px;width:132px">平衡往後 ▼</div>`);
  // ☠️ 鍵名不能跟零件按鈕撞（零件也有 bbw）：撞了會把零件按鈕蓋掉，點了沒反應、導覽游標也會按錯顆
  btn.bbwOff = add(`<div class="tb" style="left:1278px;top:802px;width:104px">後輪電控停用</div>`);
  btn.noK = add(`<div class="tb" style="left:1388px;top:802px;width:96px">MGU-K 不回收</div>`);
  btn.pause = add(`<div class="tb" style="left:1490px;top:802px;width:58px">暫停</div>`);
  add(`<div class="mu" style="position:absolute;left:1278px;top:842px;font-size:11.5px;white-space:nowrap">拖曳旋轉・滾輪縮放・H 隱藏面板</div>`);

  // ------------------------------------------------------------ 一圈的條帶（下方中央）
  const LS = {x: 380, y: 768, w: 840, h: 54};
  add(`<div class="grp" style="left:${LS.x}px;top:${LS.y - 24}px">示意一圈<span style="letter-spacing:0;font-weight:500">：車速曲線、煞車段與前盤溫度（不是任何真實賽道的數據）</span></div>`);
  const lap = add(`<svg style="position:absolute;left:${LS.x}px;top:${LS.y}px;overflow:visible" width="${LS.w}" height="${LS.h + 22}"></svg>`);
  const LX = (tau) => (tau / LAP) * LS.w;
  const LY = (v) => LS.h - (v / 360) * (LS.h - 4);
  const TY = (T) => LS.h - (Math.min(1200, T) / 1200) * (LS.h - 4);
  let lapPath = '';
  for (let i = 0; i <= 400; i++) {
    const tau = (i / 400) * LAP;
    lapPath += `${i ? 'L' : 'M'}${LX(tau).toFixed(1)} ${LY(lapAt(tau).v).toFixed(1)}`;
  }

  // ------------------------------------------------------------ 條件訊息（上方中央）
  const bNoBbw = add(`<div class="banner" style="top:64px;border:1.5px solid ${C.red};color:${C.red};display:none">後輪電控停用<span style="color:${C.ink};font-weight:600">液壓主缸直接把壓力送到後輪（C11.6）</span></div>`);
  const bNoK = add(`<div class="banner" style="top:104px;border:1.5px solid ${C.gold};color:${C.ink};display:none"><span style="color:${C.gold}">MGU-K 不回收（示意）</span>後輪減速全靠卡鉗，後盤更燙</div>`);

  // ------------------------------------------------------------ 免責聲明
  add(`<div style="position:absolute;left:360px;right:360px;top:868px;text-align:center;font-size:11.5px;color:${C.faint};white-space:nowrap">依公開資料重繪的示意模型：比例與零件位置不是實物，無任何車隊塗裝或標誌。條文依 FIA 2026 技術規章 C11；車速、回收量、壓力與溫度為示意。</div>`);

  // ------------------------------------------------------------ 標籤、指標
  const callSvg = add(`<svg data-callouts style="position:absolute;inset:0;overflow:visible" width="1600" height="900"></svg>`);
  const callG = add(`<div data-callouts style="position:absolute;inset:0"></div>`);
  const ring = add(`<div class="ring"></div>`);
  const cur = add(`<div class="cur"><svg width="24" height="24" viewBox="0 0 34 34"><path d="M4 3 L30 13.5 L17.5 17.5 L13.5 30 Z" fill="#111" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg></div>`);
  const centre = (n) => {
    const r = n.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  };
  // 每顆按鈕的鍵名必須唯一：零件、檢視、條件的鍵名若重複，後建的會蓋掉先建的
  if (Object.keys(btn).length !== PARTS.length + VIEWS.length + 5) console.error('[brake-2026] 按鈕鍵名重複', Object.keys(btn));
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
  const flash = (n, t) => {
    // 平衡按鈕是一次一次按的：按下後 0.4 秒內反白
    toggle(n, t < 0.4, C.ink);
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
      const cond = st.cond;
      vBig.textContent = Math.round(st.v);
      const ph = PHASE[st.phase];
      phBig.textContent = ph.zh;
      phBig.style.color = ph.col;
      phSub.textContent = ph.sub;

      // 壓力：四條橫條；後卡鉗那條畫出 1.2 倍上限
      {
        const W = 268;
        const X0 = 84;
        const BW = W - X0 - 46;
        const rows = [
          ['踏板', st.pedal, C.ink],
          ['前主缸', st.pFM, C.red],
          ['後主缸', st.pRM, C.red],
          ['後卡鉗', st.pRC, cond.bbw ? C.teal : C.red],
        ];
        let h = '';
        rows.forEach(([label, v, col], i) => {
          const y = 8 + i * 25;
          h += `<text x="0" y="${y + 9}" font-size="12.5" font-weight="700" fill="${C.ink}">${label}</text>`;
          h += `<rect x="${X0}" y="${y}" width="${BW}" height="11" rx="5" fill="#efe7e7"/>`;
          h += `<rect x="${X0}" y="${y}" width="${(BW * Math.min(1.2, v) / 1.2).toFixed(1)}" height="11" rx="5" fill="${col}" opacity=".85"/>`;
          h += `<text x="${W}" y="${y + 10}" font-size="12" text-anchor="end" font-weight="700" fill="${C.ink}">${Math.round(v * 100)}%</text>`;
          if (i === 3) {
            const cap = X0 + (BW * Math.min(1.2, RULE.bbwMax * st.pRM)) / 1.2;
            if (st.pRM > 0.02) h += `<line x1="${cap.toFixed(1)}" x2="${cap.toFixed(1)}" y1="${y - 3}" y2="${y + 14}" stroke="${C.red}" stroke-width="2"/>`;
          }
        });
        // 100% 的參考線（橫條畫到 120%，留位置給 1.2 倍上限）
        const x100 = X0 + BW / 1.2;
        h += `<line x1="${x100}" x2="${x100}" y1="4" y2="${8 + 3 * 25 + 14}" stroke="${C.faint}" stroke-dasharray="2 3"/>`;
        pres.innerHTML = h;
      }
      // 後輪減速分工
      {
        const W = 268;
        const tot = st.Fk + st.Frc;
        let h = `<rect x="0" y="2" width="${W}" height="14" rx="5" fill="#efe7e7"/>`;
        if (tot > 1) {
          const kW = (W * st.Fk) / tot;
          h += `<rect x="0" y="2" width="${kW.toFixed(1)}" height="14" rx="5" fill="${C.teal}" opacity=".85"/>`;
          h += `<rect x="${kW.toFixed(1)}" y="2" width="${(W - kW).toFixed(1)}" height="14" rx="5" fill="${C.red}" opacity=".85"/>`;
          splitTxt.innerHTML = `<span style="color:${C.teal}">■</span> 馬達回收 <span class="num">${Math.round((100 * st.Fk) / tot)}</span>%　<span style="color:${C.red}">■</span> 卡鉗 <span class="num">${Math.round((100 * st.Frc) / tot)}</span>%`;
        } else splitTxt.innerHTML = `<span class="mu">沒有減速</span>`;
        split.innerHTML = h;
        balTxt.textContent = `煞車平衡：前 ${Math.round(cond.bal * 100)}%・後 ${Math.round((1 - cond.bal) * 100)}%（示意）`;
      }
      // 碟盤溫度：0–1200°C，灰帶是工作窗口，1000 標出來
      {
        const W = 268;
        const X0 = 40;
        const BW = W - X0 - 66;
        const X = (T) => X0 + (BW * Math.min(1200, Math.max(0, T))) / 1200;
        let h = '';
        [['前盤', st.Tf], ['後盤', st.Tr]].forEach(([label, T], i) => {
          const y = 10 + i * 34;
          h += `<text x="0" y="${y + 10}" font-size="12.5" font-weight="700" fill="${C.ink}">${label}</text>`;
          h += `<rect x="${X0}" y="${y}" width="${BW}" height="13" rx="5" fill="#efe7e7"/>`;
          h += `<rect x="${X(RULE.winLo)}" y="${y - 2}" width="${X(RULE.winHi) - X(RULE.winLo)}" height="17" fill="${C.ink}" opacity=".12"/>`;
          const col = T > RULE.winHi + 150 ? C.hot : T >= RULE.winLo ? C.gold : C.grey;
          h += `<rect x="${X0}" y="${y}" width="${(X(T) - X0).toFixed(1)}" height="13" rx="5" fill="${col}" opacity=".85"/>`;
          h += `<line x1="${X(RULE.peak)}" x2="${X(RULE.peak)}" y1="${y - 3}" y2="${y + 16}" stroke="${C.red}" stroke-width="1.5" stroke-dasharray="2 2"/>`;
          h += `<text x="${W}" y="${y + 11}" font-size="13" text-anchor="end" font-weight="700" fill="${C.ink}">約 ${Math.round(T / 10) * 10}°C</text>`;
        });
        h += `<text x="${X(RULE.peak)}" y="82" font-size="10" text-anchor="middle" fill="${C.red}">1,000</text><text x="${X(RULE.winLo)}" y="82" font-size="10" text-anchor="middle" fill="${C.mute}">350</text><text x="${X(RULE.winHi)}" y="82" font-size="10" text-anchor="middle" fill="${C.mute}">550</text>`;
        temp.innerHTML = h;
      }

      // 零件卡
      if (s.focus !== lastCard) {
        lastCard = s.focus;
        const c = CARD[s.focus];
        const facts = c.facts
          .map(([k, v]) => `<div style="padding:8px 0;border-top:1px solid ${C.line}"><div style="font-size:12px;font-weight:700;color:${C.mute};letter-spacing:.5px">${k}</div><div class="sm" style="margin-top:2px">${v}</div></div>`)
          .join('');
        const foot = s.focus === 'all' ? `<span class="mu">點右下的零件按鈕，拆開來看</span>` : `<span class="mu">出處：${c.src}</span>`;
        // 英文長的（Master Cylinders、Brake-by-Wire）放到第二行，不擠出卡片
        const title = c.en.length > 12 ? `${c.zh}<div class="en" style="font-size:13px;margin-top:2px">${c.en}</div>` : zhEn(c.zh, c.en);
        card.innerHTML = `<div style="font-size:24px;font-weight:800;white-space:nowrap">${title}</div>
          <div class="sm" style="margin:8px 0 10px;color:${C.soft}">${c.role}</div>${facts}
          <div style="padding-top:9px;border-top:1px solid ${C.line};font-size:12.5px">${foot}</div>`;
      }

      // 一圈的條帶：煞車段（紅）、收油回收段（青）、車速曲線、前盤溫度曲線、這一格的游標
      {
        let h = `<rect x="0" y="${TY(RULE.winHi)}" width="${LS.w}" height="${TY(RULE.winLo) - TY(RULE.winHi)}" fill="${C.ink}" opacity=".06"/>`;
        let prev = null;
        let x0 = 0;
        const N = 360;
        let tPath = '';
        for (let i = 0; i <= N; i++) {
          const tau = (i / N) * LAP;
          const a = s.stripAt(Math.min(tau, LAP - 1e-3));
          tPath += `${i ? 'L' : 'M'}${LX(tau).toFixed(1)} ${TY(a.Tf).toFixed(1)}`;
          const p = i < N ? (a.phase.startsWith('brake') ? 'brake' : a.phase === 'lift' ? 'lift' : null) : 'end';
          if (p !== prev) {
            if (prev === 'brake' || prev === 'lift') h += `<rect x="${x0.toFixed(1)}" y="${LS.h + 4}" width="${(LX(tau) - x0).toFixed(1)}" height="6" fill="${prev === 'brake' ? C.red : C.teal}" opacity=".85"/>`;
            prev = p;
            x0 = LX(tau);
          }
        }
        h += `<path d="${lapPath}" fill="none" stroke="${C.ink}" stroke-width="1.6"/>`;
        h += `<path d="${tPath}" fill="none" stroke="${C.hot}" stroke-width="1.4" opacity=".9"/>`;
        const cx = LX(st.tau);
        h += `<line x1="${cx}" x2="${cx}" y1="0" y2="${LS.h + 10}" stroke="${C.red}" stroke-width="2"/><circle cx="${cx}" cy="${LY(st.v)}" r="4.5" fill="${C.red}"/>`;
        h += `<text x="0" y="${LS.h + 22}" font-size="11" fill="${C.mute}"><tspan fill="${C.red}">■</tspan> 踩煞車　<tspan fill="${C.teal}">■</tspan> 收油・馬達回收　<tspan fill="${C.hot}">━</tspan> 前盤溫度（示意，灰帶＝工作窗口）</text>`;
        lap.innerHTML = h;
      }

      bNoBbw.style.display = cond.bbw ? 'none' : 'flex';
      bNoK.style.display = cond.harvest ? 'none' : 'flex';

      for (const k of PARTS) toggle(btn[k], s.focus === k);
      for (const k of VIEWS) toggle(btn[k], s.view === k);
      toggle(btn.bbwOff, !cond.bbw, C.red);
      toggle(btn.noK, !cond.harvest, C.gold);
      flash(btn.balF, s.balAge?.f ?? 9);
      flash(btn.balR, s.balAge?.r ?? 9);
      btn.pause.textContent = s.paused ? '▶' : '暫停';

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
