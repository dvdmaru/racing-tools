// 動力單元的控制台：固定 1600 × 900 的 CSS 版面，update(s) 依這一格的狀態重畫。
// 介面中文為主，專有名詞的英文用全形空格接在後面（站上生成頁的慣例：racinglib._en()）。
// 卡片上的每一句都來自 articles/f1-101-power-unit（同一份規章出處），不另外加文章沒有的數字。
import {COL} from './pu.js';
import {kLimit, LAP, lapAt, RULE} from './kin.js';

export const C = {
  ink: '#241a1c',
  soft: '#493c40',
  mute: '#786a6e',
  faint: '#a6989c',
  line: '#e6dcdc',
  panel: 'rgba(253,249,249,.94)',
  red: COL.deploy,
  teal: COL.harvest,
  gold: COL.fuel,
  grey: '#9b9092',
};
const F = `'Chakra Petch','PingFang TC','Noto Sans TC','Microsoft JhengHei',sans-serif`;
export const PARTS = ['all', 'ice', 'tc', 'exh', 'mguk', 'es', 'pce'];
export const VIEWS = ['solid', 'xray', 'section', 'explode'];
export const PART_LABEL = {
  all: ['全部', ''],
  ice: ['內燃機', 'ICE'],
  tc: ['渦輪', 'TC'],
  exh: ['排氣', 'EXH'],
  mguk: ['電動馬達', 'MGU-K'],
  es: ['電池組', 'ES'],
  pce: ['控制電子', 'PU-CE'],
};
export const VIEW_LABEL = {solid: '實體', xray: 'X 光', section: '剖開', explode: '爆炸圖'};

// 零件卡：title（中文、英文）、一句話角色、規章重點、一季可用數量（2026 年，運動規章 B8.2.2＋B8.2.3）
const CARD = {
  all: {
    zh: '動力單元',
    en: 'Power Unit',
    role: '規章管的不是一顆引擎，而是一整套：內燃機、渦輪、排氣、電動馬達、電池與控制電子，共六類受管制的元件。',
    facts: [
      ['能推車的只有兩處', '內燃機與 MGU-K（C5.2.1）'],
      ['2026 年取消', 'MGU-H：排氣的能量不再回收進電池'],
      ['官方口語', '大約一半來自電、一半來自內燃機（設計目標，不是規章條文）'],
    ],
    count: null,
  },
  ice: {
    zh: '內燃機',
    en: 'ICE',
    role: '燒燃料、推動後輪。部分油門時，也能帶動 MGU-K 發電。',
    facts: [
      ['規格', '四行程、1600cc、六缸排成 90 度 V 型'],
      ['渦輪', '只准用一顆'],
      ['燃料', '先進永續燃料（Advanced Sustainable fuel）'],
    ],
    count: 4,
  },
  tc: {
    zh: '渦輪增壓器',
    en: 'TC',
    role: '排氣推動渦輪，同軸的壓縮機把空氣壓進進氣室。',
    facts: [
      ['數量', '一具動力單元只准一顆'],
      ['2026 年', '沒有 MGU-H，排氣的能量不再回收進電池'],
    ],
    count: 4,
  },
  exh: {
    zh: '排氣',
    en: 'EXH',
    role: '左右兩排各三缸的廢氣匯進渦輪，再從尾管排出。',
    facts: [['規章', '六類受管制元件之一，有自己的數量限制']],
    count: 4,
  },
  mguk: {
    zh: '電動馬達',
    en: 'MGU-K',
    role: 'K 是 Kinetic（動能）。加速時當馬達推車，煞車時把減速的動能收回來發電。',
    facts: [
      ['功率上限', '直流電 350 kW（C5.2.7）'],
      ['車速越快', '可用功率越低，未啟用 Overtake 時 345 km/h 歸零（C5.2.8）'],
      ['起跑', '從發車格靜止起跑，車速到 50 km/h 才可以用'],
    ],
    count: 3,
  },
  es: {
    zh: '電池組',
    en: 'ES',
    role: '只負責存電，自己不推車。',
    facts: [
      ['可動用的電', '最高與最低電量差不可超過 4 MJ（C5.2.9）'],
      ['每圈回充上限', '8.5 MJ（C5.2.10），FIA 可依賽道調降'],
    ],
    count: 3,
  },
  pce: {
    zh: '控制電子',
    en: 'PU-CE',
    role: '讓動力單元隨時能運作的控制電子。',
    facts: [['Overtake', '車手要等控制電子通知「已啟用且已啟動」才能用']],
    count: 3,
  },
};

const PHASE = {
  deploy: {zh: '全油門・馬達出力', sub: '電池 → MGU-K → 後輪', col: C.red},
  empty: {zh: '電池見底・只剩內燃機', sub: '馬達暫停出力', col: C.grey},
  lift: {zh: '收油・回充', sub: 'MGU-K 發電，存進電池', col: C.teal},
  harvest: {zh: '煞車・回收動能', sub: '後輪 → MGU-K → 電池', col: C.teal},
  part: {zh: '部分油門・內燃機帶動發電', sub: '內燃機 → MGU-K → 電池', col: C.teal},
  coast: {zh: '滑行', sub: '', col: C.grey},
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
.call{position:absolute;white-space:nowrap;font-size:14.5px;font-weight:700;color:${C.ink};text-shadow:0 0 6px rgba(246,242,241,.95),0 0 2px rgba(246,242,241,.95)}
.call .en{font-size:11.5px}
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
  add(`<div style="position:absolute;left:36px;top:44px;font-size:30px;font-weight:800;letter-spacing:.5px">2026 動力單元<span class="en" style="font-size:16px">　Power Unit</span></div>`);
  add(`<div style="position:absolute;left:37px;top:88px;font-size:14px;font-weight:600;color:${C.soft}">1600cc V6 90 度・單渦輪・沒有 MGU-H</div>`);
  add(`<div style="position:absolute;left:37px;top:110px;font-size:12.5px;color:${C.mute}">依公開資料重繪的示意模型</div>`);

  // ------------------------------------------------------------ 車速與狀態
  add(`<div class="pn" style="left:36px;top:142px;width:300px;height:132px"></div>`);
  add(`<div class="grp" style="left:52px;top:154px">車速<span style="letter-spacing:0">（示意一圈）</span></div>`);
  const vBig = add(`<div class="num" style="position:absolute;left:50px;top:170px;font-size:54px;line-height:1;color:${C.ink}"></div>`);
  add(`<div style="position:absolute;left:186px;top:200px;font-size:14px;font-weight:600;color:${C.mute}">km/h</div>`);
  const phBig = add(`<div style="position:absolute;left:52px;top:230px;font-size:16px;font-weight:700"></div>`);
  const phSub = add(`<div style="position:absolute;left:52px;top:252px;font-size:12.5px;color:${C.mute}"></div>`);

  // ------------------------------------------------------------ MGU-K 功率曲線
  add(`<div class="pn" data-g="charts" style="left:36px;top:284px;width:300px;height:262px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:296px">${zhEn('MGU-K 可用功率上限', '')}</div>`);
  add(`<div class="mu" data-g="charts" style="position:absolute;left:52px;top:317px;font-size:12px">隨車速下降（技術規章 C5.2.8）</div>`);
  const chart = add(`<svg data-g="charts" style="position:absolute;left:44px;top:338px" width="284" height="150"></svg>`);
  const kNow = add(`<div data-g="charts" style="position:absolute;left:52px;top:496px;font-size:13px;font-weight:600;white-space:nowrap"></div>`);
  const kLeg = add(`<div data-g="charts" class="mu" style="position:absolute;left:52px;top:518px;font-size:12px;white-space:nowrap"></div>`);

  // ------------------------------------------------------------ 電池
  add(`<div class="pn" data-g="charts" style="left:36px;top:556px;width:300px;height:150px"></div>`);
  add(`<div class="h" data-g="charts" style="position:absolute;left:52px;top:568px">${zhEn('電池組', 'ES')}</div>`);
  add(`<div class="mu" data-g="charts" style="position:absolute;left:52px;top:592px;font-size:12px">可動用的電量窗口 ≤ 4 MJ（C5.2.9）</div>`);
  const socBar = add(`<svg data-g="charts" style="position:absolute;left:52px;top:612px" width="268" height="26"></svg>`);
  const socTxt = add(`<div data-g="charts" style="position:absolute;left:52px;top:640px;font-size:12.5px;white-space:nowrap"></div>`);
  const harvBar = add(`<svg data-g="charts" style="position:absolute;left:52px;top:662px" width="268" height="12"></svg>`);
  const harvTxt = add(`<div data-g="charts" style="position:absolute;left:52px;top:678px;font-size:12px;white-space:nowrap;color:${C.mute}"></div>`);

  // ------------------------------------------------------------ 零件卡（右上）
  // 卡片內容由上往下自然排（標題、角色、事實、數量），高度跟著內容走
  const card = add(`<div class="pn" style="left:1262px;top:30px;width:302px;padding:14px 17px 14px"></div>`);
  card.style.pointerEvents = 'none';

  // ------------------------------------------------------------ 按鈕（右下）
  add(`<div class="pn" style="left:1262px;top:574px;width:302px;height:296px"></div>`);
  const btn = {};
  const row = (keys, label, x0, y, w = null) => {
    let x = x0;
    for (const k of keys) {
      const [zh, en] = label(k);
      const width = w ?? Math.round(zh.length * 14 + (en ? en.length * 7.4 + 18 : 0) + 22);
      btn[k] = add(`<div class="tb" style="left:${x}px;top:${y}px;width:${width}px">${zhEn(zh, en)}</div>`);
      x += width + 6;
    }
  };
  add(`<div class="grp" style="left:1278px;top:586px">零件</div>`);
  row(['all', 'ice', 'tc'], (k) => PART_LABEL[k], 1278, 606);
  row(['exh', 'mguk'], (k) => PART_LABEL[k], 1278, 642);
  row(['es', 'pce'], (k) => PART_LABEL[k], 1278, 678);
  add(`<div class="grp" style="left:1278px;top:722px">檢視</div>`);
  row(VIEWS, (k) => [VIEW_LABEL[k], ''], 1278, 742, 64);
  add(`<div class="grp" style="left:1278px;top:786px">操作</div>`);
  btn.ot = add(`<div class="tb" style="left:1278px;top:806px;width:150px">Overtake 模式</div>`);
  btn.pause = add(`<div class="tb" style="left:1434px;top:806px;width:114px">暫停</div>`);
  add(`<div class="mu" style="position:absolute;left:1278px;top:844px;font-size:11.5px;white-space:nowrap">拖曳旋轉・滾輪縮放・H 隱藏面板</div>`);

  // ------------------------------------------------------------ 一圈的條帶（下方中央）
  const LS = {x: 380, y: 768, w: 840, h: 54};
  add(`<div class="grp" style="left:${LS.x}px;top:${LS.y - 24}px">示意一圈<span style="letter-spacing:0;font-weight:500">：車速曲線與馬達狀態（不是任何真實賽道的數據）</span></div>`);
  const lap = add(`<svg style="position:absolute;left:${LS.x}px;top:${LS.y}px" width="${LS.w}" height="${LS.h + 22}"></svg>`);
  // 條帶的底圖只畫一次（車速曲線），游標與色帶每格更新
  const LX = (tau) => (tau / LAP) * LS.w;
  const LY = (v) => LS.h - (v / 360) * (LS.h - 4);
  let lapPath = '';
  for (let i = 0; i <= 400; i++) {
    const tau = (i / 400) * LAP;
    lapPath += `${i ? 'L' : 'M'}${LX(tau).toFixed(1)} ${LY(lapAt(tau).v).toFixed(1)}`;
  }

  // ------------------------------------------------------------ 免責聲明（最下方）
  add(`<div style="position:absolute;left:380px;right:380px;top:868px;text-align:center;font-size:11.5px;color:${C.faint};white-space:nowrap">依公開資料重繪的示意模型：比例與零件位置不是實物，無任何車隊塗裝或標誌。功率曲線依 FIA 2026 技術規章 C5.2.8；一圈的車速與回收量為示意。</div>`);

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

  let lastCard = '';
  return {
    btn,
    spots,
    root: ui,
    lapRect: LS,
    pointer,
    update(s) {
      const st = s.st;
      // 車速與狀態
      vBig.textContent = Math.round(st.v);
      const ph = PHASE[st.phase];
      phBig.textContent = ph.zh;
      phBig.style.color = ph.col;
      phSub.textContent = ph.sub;

      // 功率曲線：一般（實線）、Overtake（虛線），這一格的上限點與實際功率
      {
        const W = 284;
        const H = 150;
        // 車速軸畫到 400，右端留給單位，不跟 345 的刻度擠在一起
        const X = (v) => 34 + (v / 400) * (W - 40);
        const Y = (p) => H - 24 - (p / 350) * (H - 40);
        let h = '';
        for (const p of [0, 175, 350]) h += `<line x1="${X(0)}" x2="${X(360)}" y1="${Y(p)}" y2="${Y(p)}" stroke="${C.line}" stroke-width="1"/><text x="${X(0) - 6}" y="${Y(p) + 4}" font-size="11" text-anchor="end" fill="${C.mute}">${p}</text>`;
        for (const v of [0, 100, 200, 290, 345]) h += `<text x="${X(v)}" y="${H - 6}" font-size="11" text-anchor="middle" fill="${v === 290 || v === 345 ? C.ink : C.mute}" font-weight="${v === 290 || v === 345 ? 700 : 400}">${v}</text>`;
        h += `<text x="${X(0) - 6}" y="${Y(350) - 10}" font-size="10.5" text-anchor="end" fill="${C.mute}">kW</text><text x="${X(400)}" y="${H - 6}" font-size="10.5" text-anchor="end" fill="${C.mute}">km/h</text>`;
        const path = (ot) => {
          let d = '';
          for (let v = 0; v <= 360; v += 1) d += `${v ? 'L' : 'M'}${X(v).toFixed(1)} ${Y(kLimit(v, ot)).toFixed(1)}`;
          return d;
        };
        h += `<path d="${path(true)}" fill="none" stroke="${st.ot ? C.red : C.faint}" stroke-width="${st.ot ? 2.4 : 1.4}" stroke-dasharray="5 4"/>`;
        h += `<path d="${path(false)}" fill="none" stroke="${st.ot ? C.faint : C.ink}" stroke-width="${st.ot ? 1.4 : 2.4}"/>`;
        h += `<line x1="${X(st.v)}" x2="${X(st.v)}" y1="${Y(350) - 4}" y2="${Y(0)}" stroke="${C.mute}" stroke-width="1" stroke-dasharray="2 3"/>`;
        h += `<circle cx="${X(st.v)}" cy="${Y(st.kLim)}" r="5" fill="#fff" stroke="${st.ot ? C.red : C.ink}" stroke-width="2"/>`;
        if (st.kw > 0) h += `<circle cx="${X(st.v)}" cy="${Y(st.kw)}" r="3.5" fill="${C.red}"/>`;
        chart.innerHTML = h;
        const sign = st.kw > 0 ? '出力' : st.kw < 0 ? '回充' : '';
        kNow.innerHTML = `此刻上限 <span class="num" style="font-size:17px">${Math.round(st.kLim)}</span> kW　${sign ? `實際 <span class="num" style="font-size:17px;color:${st.kw > 0 ? C.red : C.teal}">${Math.abs(Math.round(st.kw))}</span> kW ${sign}` : '馬達沒有出力'}`;
        kLeg.innerHTML = `<span style="color:${C.ink}">━</span> 一般　<span style="color:${C.red}">╍</span> Overtake 模式（${st.ot ? '啟用中' : '未啟用'}）`;
      }

      // 電池：窗口內的電量，本圈已回充
      {
        const k = Math.max(0, Math.min(1, st.soc / RULE.esWindow));
        const col = st.kw > 0 ? C.red : st.kw < 0 ? C.teal : C.ink;
        let h = `<rect x="0" y="2" width="268" height="20" rx="5" fill="#efe7e7"/>`;
        h += `<rect x="0" y="2" width="${(268 * k).toFixed(1)}" height="20" rx="5" fill="${col}" opacity=".85"/>`;
        for (let i = 1; i < 4; i++) h += `<line x1="${67 * i}" x2="${67 * i}" y1="2" y2="22" stroke="#fff" stroke-width="1.5"/>`;
        socBar.innerHTML = h;
        socTxt.innerHTML = `窗口內 <span class="num" style="font-size:15px">${st.soc.toFixed(1)}</span> / 4 MJ　<span class="mu">${st.kw > 0 ? '放電中' : st.kw < 0 ? '回充中' : ''}</span>`;
        const hk = Math.min(1, st.harv / RULE.harvestLap);
        harvBar.innerHTML = `<rect x="0" y="2" width="268" height="8" rx="4" fill="#efe7e7"/><rect x="0" y="2" width="${(268 * hk).toFixed(1)}" height="8" rx="4" fill="${C.teal}" opacity=".8"/>`;
        harvTxt.innerHTML = `本圈已回充 <span class="num" style="color:${C.ink}">${st.harv.toFixed(1)}</span> MJ，上限 8.5 MJ（C5.2.10）`;
      }

      // 零件卡
      if (s.focus !== lastCard) {
        lastCard = s.focus;
        const c = CARD[s.focus];
        const facts = c.facts
          .map(([k, v]) => `<div style="padding:8px 0;border-top:1px solid ${C.line}"><div style="font-size:12px;font-weight:700;color:${C.mute};letter-spacing:.5px">${k}</div><div class="sm" style="margin-top:2px">${v}</div></div>`)
          .join('');
        const count = c.count
          ? `<span class="mu">2026 年每位車手一季可用</span>　<span class="num" style="font-size:18px;color:${C.red}">${c.count}</span>　<span class="mu">（運動規章 B8.2）</span>`
          : `<span class="mu">點右下的零件按鈕，拆開來看</span>`;
        card.innerHTML = `<div style="font-size:24px;font-weight:800;white-space:nowrap">${zhEn(c.zh, c.en)}</div>
          <div class="sm" style="margin:8px 0 10px;color:${C.soft}">${c.role}</div>${facts}
          <div style="padding-top:9px;border-top:1px solid ${C.line};font-size:12.5px;white-space:nowrap">${count}</div>`;
      }

      // 一圈的條帶：車速曲線、各段的狀態色、這一格的游標
      {
        let h = '';
        let prev = null;
        let x0 = 0;
        const N = 180;
        for (let i = 0; i <= N; i++) {
          const tau = (i / N) * LAP;
          const p = i < N ? s.phaseAt(tau) : null;
          if (p !== prev) {
            if (prev) h += `<rect x="${x0.toFixed(1)}" y="${LS.h + 4}" width="${(LX(tau) - x0).toFixed(1)}" height="6" fill="${PHASE[prev].col}" opacity="${prev === 'deploy' ? 0.85 : prev === 'empty' || prev === 'coast' ? 0.5 : 0.75}"/>`;
            prev = p;
            x0 = LX(tau);
          }
        }
        h += `<line x1="0" x2="${LS.w}" y1="${LY(290)}" y2="${LY(290)}" stroke="${C.line}" stroke-dasharray="3 3"/><text x="${LS.w + 6}" y="${LY(290) + 4}" font-size="10.5" fill="${C.mute}">290</text>`;
        h += `<path d="${lapPath}" fill="none" stroke="${C.ink}" stroke-width="1.6"/>`;
        const cx = LX(st.tau);
        h += `<line x1="${cx}" x2="${cx}" y1="0" y2="${LS.h + 10}" stroke="${C.red}" stroke-width="2"/><circle cx="${cx}" cy="${LY(st.v)}" r="4.5" fill="${C.red}"/>`;
        h += `<text x="0" y="${LS.h + 22}" font-size="11" fill="${C.mute}"><tspan fill="${C.red}">■</tspan> 馬達出力　<tspan fill="${C.teal}">■</tspan> 回充　<tspan fill="${C.grey}">■</tspan> 電池見底</text>`;
        lap.innerHTML = h;
      }

      // 按鈕狀態
      for (const k of PARTS) toggle(btn[k], s.focus === k);
      for (const k of VIEWS) toggle(btn[k], s.view === k);
      toggle(btn.ot, st.ot, C.red);
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
