// 煞車頁的導覽影片：車（car.js）在攝影棚（stage.js）裡，上面疊控制台（console.js）。
// 導覽長度＝示意一圈（LAP 秒，與動力單元、主動空力頁同一圈），結束剛好接回圈首。每個鏡頭配一件正在發生的事：
// 全車 → X 光看踏板與兩個主缸 → 前輪特寫看第一次重煞把碟盤燒紅、剖開看卡鉗夾住碟盤 → X 光看後輪電控：
// 馬達回收時後卡鉗壓力降下來 → 按「MGU-K 不回收」，後輪特寫看後盤變燙 → 爆炸圖。render(t) 是 t 的純函式。
import {runSim} from 'teardown-kit/runtime.js';
import {CENTRE, EXPLODE} from './car.js';
import {createConsole, PART_LABEL} from './console.js';
import {BAL0, LAP, makeTable, wheelAt} from './kin.js';
import {createStage} from './stage.js';

export const NO_K = [26.0, 37.0];
export const SCRIPT = [
  {t: 0, focus: 'all', view: 'solid'},
  {t: 4.2, focus: 'pedal', view: 'xray'},
  {t: 8.8, focus: 'fbrake', view: 'solid'},
  {t: 13.2, view: 'section'},
  {t: 16.4, focus: 'bbw', view: 'xray'},
  {t: NO_K[0], noK: true},
  {t: 27.6, focus: 'rbrake', view: 'solid'},
  {t: NO_K[1], noK: false},
  {t: 37.6, focus: 'all', view: 'explode'},
  {t: 42.0, view: 'solid'},
];
export const DURATION = LAP;
export const DEFAULTS = {duration: DURATION, fps: 60, theme: 'light', hud: {enabled: false, title: '2026 煞車系統', subtitle: ''}, director: {enabled: false}, watermark: ''};
const D2R = Math.PI / 180;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smoother = (x) => {
  const u = clamp(x, 0, 1);
  return u * u * u * (u * (u * 6 - 15) + 10);
};
export const ss = (a, b, t) => smoother((t - a) / (b - a));

/** 影片用的整圈表：平衡固定在預設、電控一直在、NO_K 期間 MGU-K 不回收 */
export const filmCond = (tau) => ({bal: BAL0, bbw: true, harvest: !(tau >= NO_K[0] && tau < NO_K[1])});
export const FILM_TABLE = makeTable(filmCond);
/** 回收粒子的相位：固定流速，開關交給透明度 */
export const harvPh = (tau) => tau * 0.55;

const last = (key, t) => SCRIPT.filter((e) => e[key] !== undefined && e.t <= t).pop();
export const focusAt = (t) => last('focus', t).focus;
export const viewAt = (t) => last('view', t).view;
export const sinceFocus = (t) => t - last('focus', t).t;
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

// ------------------------------------------------------------ 鏡頭
const P = (key) => CENTRE[key];
// 剖開時正對切面看：碟盤斷面、兩片來令片與跨在上面的卡鉗（目標點對準卡鉗那一側）
const DISC_SIDE_X = CENTRE.fbrake[0];
const at = (c, extra) => (u) => ({tx: c[0], ty: c[1], tz: c[2], sx: 0, sy: -40, ...extra(u)});
export const VIEW_FN = {
  open: at(P('all'), (u) => {
    const k = smoother(u / 4.2);
    return {az: 34 + 22 * k, el: 13 + 7 * k, d: 9.0 - 0.6 * k};
  }),
  all: at(P('all'), (u) => ({az: 56 + 1.4 * u, el: 22, d: 8.6})),
  explode: at([0, 0.55, 0], (u) => ({az: 50 + 2 * u, el: 26, d: 10.4})),
  side: at([0.2, 0.36, 1.7], (u) => ({az: 14 + u, el: 14, d: 3.2})),
  pedal: at([0, 0.23, 1.2], (u) => ({az: 58 + 3 * u, el: 26, d: 0.95})),
  pedalSide: at(P('pedal'), (u) => ({az: 14 + 2 * u, el: 12, d: 1.4})),
  fbrake: at(P('fbrake'), (u) => ({az: 76 + 2 * u, el: 16, d: 1.9})),
  fbrakeSide: at([DISC_SIDE_X, 0.42, 1.7], (u) => ({az: 4 + 0.8 * u, el: 8, d: 1.15})),
  rbrake: at(P('rbrake'), (u) => ({az: 112 + 2 * u, el: 18, d: 2.0})),
  rbrakeSide: at([DISC_SIDE_X, 0.4, -1.7], (u) => ({az: 176 - 0.8 * u, el: 8, d: 1.1})),
  bbw: at([-0.02, 0.28, -1.2], (u) => ({az: 138 + 2 * u, el: 32, d: 3.4})),
  bbwSide: at([-0.02, 0.32, -1.7], (u) => ({az: 172, el: 12, d: 2.6})),
  mguk: at([0.1, 0.26, -0.9], (u) => ({az: 118 + 2 * u, el: 30, d: 3.6})),
  mgukSide: at([0.1, 0.32, -1.7], (u) => ({az: 172, el: 12, d: 2.6})),
};
export const camKey = (focus, view, t0) => {
  if (view === 'section') return focus === 'all' ? 'side' : `${focus}Side`;
  if (focus === 'all') return view === 'explode' ? 'explode' : t0 === 0 ? 'open' : 'all';
  return focus;
};

function blend(a, b, k, backOff = true) {
  const o = {};
  for (const key in b) o[key] = key === 'az' ? a.az + ((((b.az - a.az + 540) % 360) - 180) * k) : a[key] + (b[key] - a[key]) * k;
  const swing = Math.min(1, Math.abs(((b.az - a.az + 540) % 360) - 180) / 90);
  if (backOff) o.d += Math.max(0, Math.max(a.d, b.d) + 1.0 * swing - o.d) * Math.sin(Math.PI * k);
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

// ------------------------------------------------------------ 導覽的游標
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
    if (e.noK !== undefined) EV.push({t: e.t, spot: ui.spots.noK});
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

// ------------------------------------------------------------ 一格
const LABELS = {
  pedal: {lab: ['踏板＋兩個主缸', 'Pedal'], at: [0, 0.25, 1.17], off: [-210, -120]},
  fbrake: {lab: ['前輪煞車', 'Front Brake'], at: [0.64, 0.5, 1.6], off: [50, -130]},
  rbrake: {lab: ['後輪煞車', 'Rear Brake'], at: [0.64, 0.47, -1.62], off: [50, -120]},
  bbw: {lab: ['後輪電控', 'BBW・位置示意'], at: [-0.1, 0.24, -1.05], off: [-230, -100]},
  mguk: {lab: ['MGU-K 回收', '後輪 → 電池'], at: [0.17, 0.2, -0.45], off: [30, 90]},
};
export function makeFrame(ui, st) {
  return (o) => {
    const {tau, s, view, focus, focusK, explodeK, cursor, since, paused, stripAt, balAge} = o;
    st.frame({s, wheel: wheelAt(tau), ph: o.ph, view, explodeK, focus, focusK}, {...o.cam, az: o.cam.az * D2R, el: o.cam.el * D2R});
    const vis = focus === 'all' && view !== 'section' ? ss(0.9, 1.6, since) : 0;
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
    ui.update({st: s, focus, view, paused, cursor, callouts, stripAt, balAge});
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
    const stripAt = (tau) => FILM_TABLE.at(tau);
    window.BRAKE = st;
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
          ph: harvPh(t),
          stripAt,
        });
        return {};
      },
    };
  };
}

export const run = () => runSim(DEFAULTS, makeFilm());
export {PART_LABEL};
