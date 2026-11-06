// 動力單元的導覽影片：零件（pu.js）在攝影棚（stage.js）裡，上面疊控制台（console.js）。
// 導覽長度＝示意一圈（LAP 秒），結束剛好接回圈首。每個鏡頭配一個正在發生的物理現象：
// 直道末段功率往下掉時看 MGU-K、收油與煞車時看電池充電、部分油門時剖開看內燃機帶動發電、
// 開 Overtake 看曲線換線、最後拆成爆炸圖。render(t) 是 t 的純函式（capture 逐格呼叫）。
import {runSim} from 'teardown-kit/runtime.js';
import {createConsole, PART_LABEL} from './console.js';
import {crankAt, exhAt, fuelAt, LAP, makeTable, turboAt, wheelAt} from './kin.js';
import {CENTRE} from './pu.js';
import {createStage} from './stage.js';

export const OT_ON = [26.6, 33.6];
export const SCRIPT = [
  {t: 0, focus: 'all', view: 'solid'},
  {t: 4.6, focus: 'mguk', view: 'xray'},
  {t: 10.6, focus: 'es'},
  {t: 16.4, focus: 'all', view: 'section'},
  {t: 21.0, view: 'xray'},
  {t: OT_ON[0], ot: true},
  {t: 31.0, focus: 'tc'},
  {t: OT_ON[1], ot: false},
  {t: 36.2, focus: 'all', view: 'explode'},
  {t: 41.4, view: 'solid'},
];
export const DURATION = LAP;
export const DEFAULTS = {duration: DURATION, fps: 60, theme: 'light', hud: {enabled: false, title: '2026 動力單元', subtitle: ''}, director: {enabled: false}, watermark: ''};
const D2R = Math.PI / 180;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smoother = (x) => {
  const u = clamp(x, 0, 1);
  return u * u * u * (u * (u * 6 - 15) + 10);
};
export const ss = (a, b, t) => smoother((t - a) / (b - a));

// 影片用的能量表：照 OT_ON 開關 Overtake
export const FILM_TABLE = makeTable((tau) => tau >= OT_ON[0] && tau < OT_ON[1]);

// ------------------------------------------------------------ 腳本在 t 時的狀態
const last = (key, t) => SCRIPT.filter((e) => e[key] !== undefined && e.t <= t).pop();
export const focusAt = (t) => last('focus', t).focus;
export const viewAt = (t) => last('view', t).view;
export const sinceFocus = (t) => t - last('focus', t).t;
/** 爆炸圖的展開量：鏡頭先拉遠 0.8 秒，再用 1.4 秒展開；離開時 0.9 秒收回 */
export const explodeAt = (t, events = SCRIPT) => {
  let k = 0;
  let prevView = 'solid';
  for (const e of events) {
    if (e.view === undefined || e.t > t) continue;
    if (e.view === 'explode' && prevView !== 'explode') k = ss(e.t + 0.8, e.t + 2.2, t);
    else if (e.view !== 'explode' && prevView === 'explode') k = 1 - ss(e.t, e.t + 0.9, t);
    else if (e.view !== 'explode') k = 0;
    prevView = e.view;
  }
  return k;
};

// ------------------------------------------------------------ 鏡頭：每個都是「進來後經過的秒數 u」的函式
const P = (key) => CENTRE[key];
const partCam = {
  ice: {az: 38, el: 30, d: 1.95},
  tc: {az: 142, el: 22, d: 1.3},
  exh: {az: 118, el: 28, d: 2.3},
  mguk: {az: 62, el: 14, d: 1.2},
  es: {az: 24, el: 38, d: 1.5},
  pce: {az: 28, el: 34, d: 1.15},
};
export const VIEW_FN = {
  open: (u) => {
    const k = smoother(u / 4.4);
    return {tx: P('all')[0], ty: P('all')[1], tz: P('all')[2], az: 24 + 30 * k, el: 18 + 8 * k, d: 4.9 - 0.45 * k, sx: 0, sy: -40};
  },
  all: (u) => ({tx: P('all')[0], ty: P('all')[1], tz: P('all')[2], az: 54 + 2.4 * u, el: 26, d: 4.45, sx: 0, sy: -40}),
  explode: (u) => ({tx: 0, ty: 0.08, tz: -0.02, az: 50 + 2 * u, el: 28, d: 5.6, sx: 0, sy: -40}),
};
for (const [k, c] of Object.entries(partCam)) {
  VIEW_FN[k] = (u) => ({tx: P(k)[0], ty: P(k)[1], tz: P(k)[2], az: c.az + 3 * u, el: c.el + 0.6 * u, d: c.d, sx: 0, sy: -40});
}
/** 鏡頭名：看整體時，開場用 open、爆炸圖用 explode */
export const camKey = (focus, view, t0) => (focus === 'all' ? (view === 'explode' ? 'explode' : t0 === 0 ? 'open' : 'all') : focus);

function blend(a, b, k, backOff = true) {
  const o = {};
  for (const key in b) o[key] = key === 'az' ? a.az + ((((b.az - a.az + 540) % 360) - 180) * k) : a[key] + (b[key] - a[key]) * k;
  const swing = Math.min(1, Math.abs(((b.az - a.az + 540) % 360) - 180) / 90);
  if (backOff) o.d += Math.max(0, Math.max(a.d, b.d) + 0.5 * swing - o.d) * Math.sin(Math.PI * k);
  return o;
}
// 鏡頭的轉換點：focus 改變，或看整體時切進／切出爆炸圖
const CAMS = (() => {
  const list = [];
  let key = null;
  for (const e of SCRIPT) {
    const k = camKey(focusAt(e.t), viewAt(e.t), e.t);
    if (k !== key) {
      list.push([e.t, k]);
      key = k;
    }
  }
  return list;
})();
export const camAt = (t) => {
  let i = 0;
  while (i < CAMS.length - 1 && CAMS[i + 1][0] <= t) i++;
  const cur = VIEW_FN[CAMS[i][1]](t - CAMS[i][0]);
  if (i === 0) return cur;
  const k = ss(CAMS[i][0], CAMS[i][0] + 1.7, t);
  if (k >= 1) return cur;
  return blend(VIEW_FN[CAMS[i - 1][1]](t - CAMS[i - 1][0]), cur, k);
};

// ------------------------------------------------------------ 導覽的游標：每個事件去按對應的按鈕
const REST = [[800, 470], [700, 420], [900, 520], [760, 380]];
export function makeCursor(ui) {
  const EV = [];
  for (const e of SCRIPT.filter((x) => x.t > 0)) {
    // 一個事件可能同時換零件與檢視：先按零件、0.5 秒後按檢視
    let dt = 0;
    if (e.focus !== undefined && e.focus !== focusAt(e.t - 0.01)) {
      EV.push({t: e.t, spot: ui.spots[e.focus]});
      dt = 0.55;
    }
    if (e.view !== undefined && e.view !== viewAt(e.t - 0.01)) EV.push({t: e.t + dt, spot: ui.spots[e.view]});
    if (e.ot !== undefined) EV.push({t: e.t, spot: ui.spots.ot});
  }
  const WP = [[0, 980, 640]];
  EV.forEach((e, i) => {
    WP.push([e.t - 0.2, ...e.spot]);
    WP.push([e.t + 0.25, ...e.spot]);
    WP.push([e.t + 1.6, ...REST[i % REST.length]]);
  });
  WP.sort((a, b) => a[0] - b[0]);
  return (t) => {
    let i = 0;
    while (i < WP.length - 2 && t > WP[i + 1][0]) i++;
    const [t0, x0, y0] = WP[i];
    const [t1, x1, y1] = WP[i + 1];
    const k = ss(t0, t1, t);
    const len = Math.hypot(x1 - x0, y1 - y0);
    const bow = Math.sin(Math.PI * k) * Math.min(24, len * 0.07);
    let press = false;
    let ring = 0;
    let rx = 0;
    let ry = 0;
    for (const e of EV) {
      if (t >= e.t - 0.07 && t < e.t + 0.1) press = true;
      if (t >= e.t && t < e.t + 0.55) {
        ring = 1 - (t - e.t) / 0.55;
        [rx, ry] = e.spot;
      }
    }
    return {x: x0 + (x1 - x0) * k + (len ? (-(y1 - y0) / len) * bow : 0), y: y0 + (y1 - y0) * k + (len ? ((x1 - x0) / len) * bow : 0), press, ring, ringX: rx, ringY: ry, events: EV};
  };
}

// ------------------------------------------------------------ 一格：零件姿態＋控制台資料（影片與互動頁共用）
const LABELS = {
  ice: PART_LABEL.ice,
  tc: PART_LABEL.tc,
  exh: PART_LABEL.exh,
  mguk: PART_LABEL.mguk,
  es: PART_LABEL.es,
  pce: PART_LABEL.pce,
  drive: ['後輪', '示意'],
};
// 標籤相對零件中心往外推的方向（螢幕像素），各自錯開避免互相壓到
const LABEL_OFF = {ice: [-150, -120], tc: [40, -110], exh: [110, -40], mguk: [90, 70], es: [-190, 60], pce: [-170, -70], drive: [80, 60]};
export function makeFrame(ui, st) {
  return (o) => {
    const {tau, s, view, focus, focusK, explodeK, cursor, since, paused, ph, phaseAt} = o;
    st.frame(
      {th: crankAt(tau), turbo: turboAt(tau), wheel: wheelAt(tau), s, ph, view, viewK: 1, explodeK, focus, focusK, flows: 1},
      {...o.cam, az: o.cam.az * D2R, el: o.cam.el * D2R},
    );
    const vis = focus === 'all' ? ss(0.9, 1.6, since) * (o.callouts === false ? 0 : 1) : 0;
    const callouts = [];
    if (vis > 0)
      for (const [key, lab] of Object.entries(LABELS)) {
        const at = st.project(...st.pu.centreOf(key, explodeK));
        if (!at) continue;
        const [dx, dy] = LABEL_OFF[key];
        const html = `${lab[0]}<span class="en">　${lab[1]}</span>`;
        const w = lab[0].length * 15 + lab[1].length * 8 + 18;
        callouts.push({at, label: [clamp(at[0] + dx, 360, 1230 - w), clamp(at[1] + dy, 40, 720)], w, html, o: vis});
      }
    ui.update({st: s, focus, view, paused, cursor, callouts, phaseAt});
  };
}

export function makeFilm() {
  return async ({canvas, capture}) => {
    const st = createStage({canvas});
    const resize = () => st.resize(1600, 900, capture ? devicePixelRatio || 1 : Math.min(devicePixelRatio || 1, 2));
    resize();
    const ui = createConsole(document.getElementById('app'));
    const cursorAt = makeCursor(ui);
    const frame = makeFrame(ui, st);
    const phaseAt = (tau) => FILM_TABLE.at(tau).phase;
    window.PU = st;
    return {
      resize,
      render(t) {
        const tau = t;
        const focus = focusAt(t);
        frame({
          tau,
          s: FILM_TABLE.at(tau),
          view: viewAt(t),
          focus,
          focusK: ss(0.25, 0.7, sinceFocus(t)),
          explodeK: explodeAt(t),
          cam: camAt(t),
          cursor: cursorAt(t),
          since: sinceFocus(t),
          paused: false,
          ph: {fuel: fuelAt(tau), exh: exhAt(tau), elec: FILM_TABLE.elecAt(tau)},
          phaseAt,
        });
        return {};
      },
    };
  };
}

export const run = () => runSim(DEFAULTS, makeFilm());
