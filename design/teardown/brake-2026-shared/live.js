// 煞車頁的互動頁：影片的同一台車與控制台，即時跑。
// 零件按鈕（全部＋五組）、檢視（實體／X 光／剖開／爆炸圖）、條件（煞車平衡往前／往後、後輪電控停用、MGU-K 不回收）、
// 暫停、拖曳旋轉、滾輪縮放、H 隱藏面板。沒人操作時照 film.js 的腳本自動導覽；任何操作就交給訪客，閒置 25 秒再交回。
// 結構照 ../aero-2026-shared/live.js。
import {warmComposer} from 'teardown-kit/warm.js';
import {createConsole, PARTS, VIEWS} from './console.js';
import {camAt, camKey, DURATION, explodeAt, FILM_TABLE, filmCond, focusAt, harvPh, makeCursor, makeFrame, sinceFocus, ss, viewAt, VIEW_FN} from './film.js';
import {LAP, makeTable, stepThermal} from './kin.js';
import {createStage} from './stage.js';

const W = 1600;
const H = 900;
const IDLE = 25;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const wrap = (d) => ((((d + 180) % 360) + 360) % 360) - 180;

const CSS = `
html,body{background:#ece6e5;overflow:hidden}
body{position:fixed;inset:0}
#app{position:absolute!important;inset:auto!important;left:0;top:0;width:${W}px;height:${H}px;transform-origin:0 0}
#gl{touch-action:none;cursor:grab}
#gl.drag{cursor:grabbing}
.tb{pointer-events:auto;cursor:pointer}
.tb:hover{filter:brightness(.96)}
.tourchip{position:absolute;left:800px;top:26px;transform:translateX(-50%);display:flex;align-items:center;gap:8px;height:30px;padding:0 14px;border:1px solid #e6dcdc;border-radius:15px;background:rgba(255,255,255,.95);color:#241a1c;font-size:13px;font-weight:600;letter-spacing:.5px;white-space:nowrap;cursor:pointer;pointer-events:auto}
.tourchip i{display:block;width:7px;height:7px;border-radius:50%;background:#d63a2f}
.tourchip.on i{animation:blink 1.2s steps(2) infinite}
@keyframes blink{50%{opacity:.15}}
.back{position:absolute;left:36px;top:724px;display:flex;align-items:center;height:36px;padding:0 16px;border:1px solid #e6dcdc;border-radius:8px;background:#fff;color:#241a1c;font-size:14px;font-weight:700;text-decoration:none;white-space:nowrap;pointer-events:auto}
.back:hover{border-color:#d63a2f;color:#d63a2f}
.turn{position:fixed;left:16px;right:16px;bottom:18px;text-align:center;font-size:14px;line-height:1.5;color:#786a6e;display:none}
@media (orientation:portrait) and (max-width:820px){.turn{display:block}}
`;

/** opts.back＝{href, text}：左下角「回到文章」的連結 */
export function runLive(opts = {}) {
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);
  const app = document.getElementById('app');
  const canvas = document.createElement('canvas');
  canvas.id = 'gl';
  app.appendChild(canvas);
  const st = createStage({canvas});
  const ui = createConsole(app);
  const tourCursor = makeCursor(ui);
  const frame = makeFrame(ui, st);

  const TIERS = [
    {samples: 8, ao: true, shadow: 4096, pr: 2},
    {samples: 4, ao: false, shadow: 2048, pr: 1.5},
    {samples: 2, ao: false, shadow: 1024, pr: 1},
  ];
  const light = matchMedia('(pointer: coarse)').matches || Math.min(innerWidth, innerHeight) < 700;
  let tier = light ? 2 : 0;
  let scale = 1;
  const fit = () => {
    scale = Math.min(innerWidth / W, innerHeight / H);
    app.style.transform = `translate(${(innerWidth - W * scale) / 2}px, ${(innerHeight - H * scale) / 2}px) scale(${scale})`;
    st.resize(W, H, clamp((devicePixelRatio || 1) * scale, 0.75, TIERS[tier].pr));
  };
  const applyTier = () => {
    const {pr, ...q} = TIERS[tier];
    st.setQuality(q);
    fit();
  };
  applyTier();
  addEventListener('resize', fit);

  const tourChip = document.createElement('div');
  tourChip.className = 'tourchip';
  ui.root.appendChild(tourChip);
  if (opts.back) {
    const a = document.createElement('a');
    a.className = 'back';
    a.href = opts.back.href;
    a.textContent = `← ${opts.back.text}`;
    a.addEventListener('pointerdown', (e) => e.stopPropagation());
    ui.root.appendChild(a);
  }
  const note = document.createElement('div');
  note.className = 'turn';
  note.textContent = '把手機轉成橫向，可以看完整的控制台';
  document.body.appendChild(note);

  // ------------------------------------------------------------ 狀態
  let T = 0;
  let tau = 0;
  let paused = false;
  let focus = 'all';
  let focusAtT = 0;
  let view = 'solid';
  let exK = 0;
  let ph = 0;
  const cond = {...filmCond(0)};
  const th = {f: 450, r: 400};
  const bal = {f: -9, r: -9};
  const off = {az: 0, el: 0, k: 1};
  const cam = {...VIEW_FN.open(0)};
  let ring = {t: -9, x: 0, y: 0};
  let hidden = false;
  let sNow = null;
  const pulse = (x, y) => (ring = {t: T, x, y});
  const strips = {};
  const stripFor = (c) => {
    const key = `${c.bal.toFixed(2)}|${c.bbw}|${c.harvest}`;
    if (!strips[key]) strips[key] = makeTable(() => ({...c}));
    return strips[key];
  };

  // ------------------------------------------------------------ 自動導覽
  const AP = {on: true, t0: 0};
  let lastInput = 0;
  const startTour = () => {
    AP.on = true;
    AP.t0 = T;
    paused = false;
    Object.assign(off, {az: 0, el: 0, k: 1});
  };
  const takeOver = () => {
    lastInput = T;
    if (!AP.on) return;
    AP.on = false;
    // 從導覽當下接手：零件、檢視、條件與碟盤溫度都沿用
    const cyc = (T - AP.t0) % DURATION;
    tau = cyc;
    focus = focusAt(cyc);
    focusAtT = T - sinceFocus(cyc);
    view = viewAt(cyc);
    const r = FILM_TABLE.at(cyc);
    Object.assign(cond, r.cond);
    th.f = r.Tf;
    th.r = r.Tr;
    ph = harvPh(cyc);
  };
  tourChip.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    lastInput = T;
    if (AP.on) takeOver();
    else startTour();
  });
  addEventListener('pointerdown', (e) => {
    if (e.target !== tourChip) takeOver();
  });

  // ------------------------------------------------------------ 按鈕
  const press = (k) => pulse(...ui.spots[k]);
  const setFocus = (k) => {
    if (k !== focus) focusAtT = T;
    focus = k;
    Object.assign(off, {az: 0, el: 0, k: 1});
  };
  const click = (k, fn) =>
    ui.btn[k].addEventListener('click', () => {
      takeOver();
      press(k);
      fn();
    });
  const nudge = (d) => {
    cond.bal = clamp(Math.round((cond.bal + d) * 100) / 100, 0.4, 0.75);
    bal[d > 0 ? 'f' : 'r'] = T;
  };
  for (const k of PARTS) click(k, () => setFocus(k));
  for (const k of VIEWS)
    click(k, () => {
      if (view === 'explode' || k === 'explode') focusAtT = focus === 'all' ? T : focusAtT;
      view = k;
    });
  click('balF', () => nudge(0.02));
  click('balR', () => nudge(-0.02));
  click('bbwOff', () => (cond.bbw = !cond.bbw));
  click('noK', () => (cond.harvest = !cond.harvest));
  click('pause', () => (paused = !paused));
  addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const key = e.key.toLowerCase();
    takeOver();
    const part = {1: 'all', 2: 'pedal', 3: 'fbrake', 4: 'rbrake', 5: 'bbw', 6: 'mguk'}[key];
    if (part) setFocus(part);
    else if (key === ' ') paused = !paused;
    else if (key === 'h') hidden = !hidden;
    else if (key === 'b') cond.bbw = !cond.bbw;
    else if (key === 'k') cond.harvest = !cond.harvest;
    else if (key === 'arrowup') nudge(0.02);
    else if (key === 'arrowdown') nudge(-0.02);
    else return;
    e.preventDefault();
  });
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => {
    drag = {x: e.clientX, y: e.clientY};
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add('drag');
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag) return;
    off.az -= ((e.clientX - drag.x) / scale) * 0.3;
    off.el = clamp(off.el + ((e.clientY - drag.y) / scale) * 0.2, -20, 60);
    drag = {x: e.clientX, y: e.clientY};
    lastInput = T;
  });
  const endDrag = () => {
    drag = null;
    canvas.classList.remove('drag');
  };
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      takeOver();
      off.k = clamp(off.k * Math.exp(e.deltaY * 0.0012), 0.35, 2.2);
    },
    {passive: false},
  );

  // ------------------------------------------------------------ 每一格
  startTour();
  let last = performance.now();
  const perf = {n: 0, sum: 0, slow: 0, age: 0};
  const loop = (now) => {
    const dt = Math.min(0.1, Math.max(0, (now - last) / 1000));
    last = now;
    T += dt;
    if (tier < TIERS.length - 1) {
      perf.age += dt;
      if (perf.age > 0.6) {
        perf.sum += dt;
        perf.n++;
        if (perf.sum >= 0.5 && perf.n >= 6) {
          perf.slow = perf.sum / perf.n > 0.022 ? perf.slow + 1 : 0;
          perf.sum = 0;
          perf.n = 0;
          if (perf.slow >= (perf.age < 6 ? 1 : 2)) {
            tier++;
            applyTier();
            Object.assign(perf, {age: 0, slow: 0});
          }
        }
      }
    }

    let s;
    let tgt;
    let cursor;
    let since;
    let fK;
    let stripAt;
    let phNow;
    if (AP.on) {
      const cyc = (T - AP.t0) % DURATION;
      s = FILM_TABLE.at(cyc);
      focus = focusAt(cyc);
      view = viewAt(cyc);
      since = sinceFocus(cyc);
      fK = ss(0.25, 0.7, since);
      exK = explodeAt(cyc);
      tgt = camAt(cyc);
      cursor = tourCursor(cyc);
      stripAt = (x) => FILM_TABLE.at(x);
      phNow = harvPh(cyc);
      tau = cyc;
    } else {
      if (T - lastInput > IDLE) startTour();
      // 即時累加：跟影片同一支 stepThermal，條件中途切換時溫度連續
      if (!paused || !sNow) {
        const steps = Math.max(1, Math.ceil(dt / (1 / 240)));
        const h = paused ? 0 : dt / steps;
        for (let i = 0; i < steps; i++) {
          tau = (tau + h) % LAP;
          sNow = stepThermal(th, tau, h, cond);
        }
        if (!paused) ph += 0.55 * dt;
      }
      s = {...sNow, cond: {...cond}, Tf: th.f, Tr: th.r};
      since = T - focusAtT;
      fK = ss(0.25, 0.7, since);
      exK += ((view === 'explode' ? 1 : 0) - exK) * (1 - Math.exp(-dt / 0.35));
      tgt = VIEW_FN[camKey(focus, view, -1)](since);
      tgt.az += off.az;
      tgt.el = clamp(tgt.el + off.el, -10, 80);
      tgt.d *= off.k;
      const rk = Math.max(0, 1 - (T - ring.t) / 0.55);
      cursor = {x: -99, y: -99, press: false, ring: rk, ringX: ring.x, ringY: ring.y};
      const strip = stripFor(cond);
      stripAt = (x) => strip.at(x);
      phNow = ph;
    }
    const k = 1 - Math.exp(-dt / (AP.on ? 0.15 : 0.45));
    cam.az += wrap(tgt.az - cam.az) * k;
    for (const key of ['tx', 'ty', 'tz', 'el', 'd', 'sx', 'sy']) cam[key] += (tgt[key] - cam[key]) * k;

    ui.root.style.display = hidden ? 'none' : '';
    frame({tau, s, view, focus, focusK: fK, explodeK: exK, cam, cursor, since, paused, stripAt, ph: phNow, balAge: {f: T - bal.f, r: T - bal.r}});
    if (tourChip.classList.contains('on') !== AP.on || !tourChip.firstChild) {
      tourChip.classList.toggle('on', AP.on);
      tourChip.innerHTML = AP.on ? '<i></i>自動導覽中・點一下接手操作' : '▶ 繼續自動導覽';
    }
    if (!window.SIM_SHOWN) {
      window.SIM_SHOWN = true;
      dispatchEvent(new Event('simframe'));
    }
    requestAnimationFrame(loop);
  };
  warmComposer(st.renderer, st.composer, st.scene, st.camera).then(() => requestAnimationFrame(loop));
  window.LIVE = {st, cam, cond, th, startTour, takeOver, get tier() {
    return tier;
  }, get T() {
    return T;
  }, get s() {
    return sNow;
  }};
}
