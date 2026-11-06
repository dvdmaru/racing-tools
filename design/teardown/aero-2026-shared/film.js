// 主動空力的導覽影片：車（car.js）在攝影棚（stage.js）裡，上面疊控制台（console.js）。
// 導覽長度＝示意一圈（LAP 秒，與動力單元頁同一圈），結束剛好接回圈首。每個鏡頭配一個正在發生的規則：
// 啟動區 1 完全啟用（剖開看後翼襟翼在區尾收回）→ X 光看致動器與 ECU → 啟動區 2 剖開看前翼打開、模擬系統失效
// → 宣告低抓地條件，啟動區 3 只有前翼動 → 爆炸圖。render(t) 是 t 的純函式（capture 逐格呼叫）。
import {runSim} from 'teardown-kit/runtime.js';
import {CENTRE, EXPLODE} from './car.js';
import {createConsole, PART_LABEL} from './console.js';
import {LAP, makeTable, wheelAt} from './kin.js';
import {createStage} from './stage.js';

export const LOW_GRIP = [24.2, 33.6];
export const FAIL_T = 20.2;
export const SCRIPT = [
  {t: 0, focus: 'all', view: 'solid'},
  {t: 3.6, focus: 'ecu', view: 'xray'},
  {t: 7.0, focus: 'rw', view: 'section'},
  {t: 11.4, focus: 'act', view: 'xray'},
  {t: 15.0, focus: 'fw', view: 'section'},
  {t: FAIL_T, fail: true},
  {t: 22.4, focus: 'all', view: 'solid'},
  {t: LOW_GRIP[0], lowGrip: true},
  {t: LOW_GRIP[1], lowGrip: false},
  {t: 35.0, view: 'explode'},
  {t: 41.0, view: 'solid'},
];
export const DURATION = LAP;
export const DEFAULTS = {duration: DURATION, fps: 60, theme: 'light', hud: {enabled: false, title: '2026 主動空力', subtitle: ''}, director: {enabled: false}, watermark: ''};
const D2R = Math.PI / 180;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smoother = (x) => {
  const u = clamp(x, 0, 1);
  return u * u * u * (u * (u * 6 - 15) + 10);
};
export const ss = (a, b, t) => smoother((t - a) / (b - a));

/** 影片用的整圈表：一直「已啟用」、LOW_GRIP 期間宣告低抓地條件、FAIL_T 模擬一次系統失效 */
export const filmCond = (tau) => ({enabled: true, lowGrip: tau >= LOW_GRIP[0] && tau < LOW_GRIP[1]});
export const FILM_TABLE = makeTable(filmCond, FAIL_T);

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
const at = (c, extra) => (u) => ({tx: c[0], ty: c[1], tz: c[2], sx: 0, sy: -40, ...extra(u)});
export const VIEW_FN = {
  open: at(P('all'), (u) => {
    const k = smoother(u / 3.4);
    return {az: 34 + 22 * k, el: 13 + 6 * k, d: 9.6 - 0.6 * k};
  }),
  all: at(P('all'), (u) => ({az: 64 + 1.4 * u, el: 22, d: 11.4})),
  explode: at([0, 0.7, 0], (u) => ({az: 50 + 2 * u, el: 24, d: 11.2})),
  side: at([0, 0.5, 0], (u) => ({az: 90, el: 5 + 0.2 * u, d: 9.2})),
  fw: at(P('fw'), (u) => ({az: 48 + 2.5 * u, el: 16, d: 3.3})),
  fwSide: at([0, 0.2, 2.3], (u) => ({az: 90, el: 3 + 0.3 * u, d: 2.2})),
  rw: at(P('rw'), (u) => ({az: 142 + 2.5 * u, el: 14, d: 3.0})),
  rwSide: at([0, 0.92, -2.36], (u) => ({az: 90, el: 3 + 0.3 * u, d: 2.0})),
  act: at([0, 0.28, 2.2], (u) => ({az: 36 + 3 * u, el: 24, d: 3.1})),
  actSide: at([0, 0.28, 2.2], (u) => ({az: 90, el: 8, d: 2.6})),
  ecu: at([0.1, 0.4, 0], (u) => ({az: 62 + 2 * u, el: 30, d: 8.0})),
  ecuSide: at([0.1, 0.4, 0], (u) => ({az: 90, el: 10, d: 8.0})),
};
/** 鏡頭名：剖開時從側面看斷面；看整體時，開場用 open、爆炸圖用 explode */
export const camKey = (focus, view, t0) => {
  if (view === 'section') return focus === 'all' ? 'side' : `${focus}Side`;
  if (focus === 'all') return view === 'explode' ? 'explode' : t0 === 0 ? 'open' : 'all';
  return focus;
};

function blend(a, b, k, backOff = true) {
  const o = {};
  for (const key in b) o[key] = key === 'az' ? a.az + ((((b.az - a.az + 540) % 360) - 180) * k) : a[key] + (b[key] - a[key]) * k;
  const swing = Math.min(1, Math.abs(((b.az - a.az + 540) % 360) - 180) / 90);
  if (backOff) o.d += Math.max(0, Math.max(a.d, b.d) + 1.2 * swing - o.d) * Math.sin(Math.PI * k);
  return o;
}
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
    let dt = 0;
    if (e.focus !== undefined && e.focus !== focusAt(e.t - 0.01)) {
      EV.push({t: e.t, spot: ui.spots[e.focus]});
      dt = 0.55;
    }
    if (e.view !== undefined && e.view !== viewAt(e.t - 0.01)) EV.push({t: e.t + dt, spot: ui.spots[e.view]});
    if (e.lowGrip !== undefined) EV.push({t: e.t, spot: ui.spots.lowGrip});
    if (e.fail) EV.push({t: e.t, spot: ui.spots.fail});
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

// ------------------------------------------------------------ 一格：車的姿態＋控制台資料（影片與互動頁共用）
// 標籤指在零件上的哪一點（世界座標，爆炸時跟著該組移動），以及往外推的方向（螢幕像素）
const LABELS = {
  fw: {lab: ['前翼元件', 'Front Wing'], at: [0.5, 0.22, 2.3], off: [-120, 70]},
  act: {lab: ['致動器＋位置感測器', 'Actuator'], at: [0.14, 0.37, 2.1], off: [-200, -110]},
  rw: {lab: ['後翼襟翼', 'Rear Wing Flap'], at: [0.3, 0.95, -2.42], off: [40, -100]},
  ecu: {lab: ['FIA 標準 ECU', '位置示意'], at: CENTRE.ecu, off: [70, -150]},
};
export function makeFrame(ui, st) {
  return (o) => {
    const {tau, s, view, focus, focusK, explodeK, cursor, since, paused, modeAt} = o;
    st.frame({s, wheel: wheelAt(tau), view, explodeK, focus, focusK}, {...o.cam, az: o.cam.az * D2R, el: o.cam.el * D2R});
    const vis = focus === 'all' && view !== 'section' ? ss(0.9, 1.6, since) * (o.callouts === false ? 0 : 1) : 0;
    const callouts = [];
    if (vis > 0)
      for (const [key, L] of Object.entries(LABELS)) {
        const e = EXPLODE[key];
        const pt = st.project(L.at[0] + e[0] * explodeK, L.at[1] + e[1] * explodeK, L.at[2] + e[2] * explodeK);
        if (!pt) continue;
        const [dx, dy] = L.off;
        const html = `${L.lab[0]}<span class="en">　${L.lab[1]}</span>`;
        const w = L.lab[0].length * 15 + L.lab[1].length * 8 + 32;
        callouts.push({at: pt, label: [clamp(pt[0] + dx, 360, 1230 - w), clamp(pt[1] + dy, 150, 700)], w, html, o: vis});
      }
    ui.update({st: s, focus, view, paused, cursor, callouts, modeAt});
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
    const modeAt = (tau) => FILM_TABLE.at(tau).mode;
    window.AERO = st;
    return {
      resize,
      render(t) {
        const focus = focusAt(t);
        frame({
          tau: t,
          s: FILM_TABLE.at(t),
          view: viewAt(t),
          focus,
          focusK: ss(0.25, 0.7, sinceFocus(t)),
          explodeK: explodeAt(t),
          cam: camAt(t),
          cursor: cursorAt(t),
          since: sinceFocus(t),
          paused: false,
          modeAt,
        });
        return {};
      },
    };
  };
}

export const run = () => runSim(DEFAULTS, makeFilm());
export {PART_LABEL};
