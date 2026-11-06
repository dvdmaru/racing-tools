// 冒煙測試：只有 3D，沒有控制台。每一秒換一種鏡頭或模式，用 capture --stills 拼成總覽圖檢查幾何。
import {runSim} from 'teardown-kit/runtime.js';
import {crankAt, stateAt, turboAt, wheelAt, fuelAt, exhAt, elecAt} from '../pu-2026-shared/kin.js';
import {createStage} from '../pu-2026-shared/stage.js';

const D2R = Math.PI / 180;
const SHOTS = [
  {cam: {tx: 0, ty: 0.05, tz: -0.08, az: 48, el: 24, d: 4.4}, view: 'solid'},
  {cam: {tx: 0, ty: 0.05, tz: -0.08, az: 100, el: 12, d: 4.2}, view: 'solid'},
  {cam: {tx: 0, ty: 0.08, tz: 0, az: 40, el: 30, d: 2.2}, view: 'xray'},
  {cam: {tx: 0, ty: 0.08, tz: 0, az: 70, el: 18, d: 2.2}, view: 'section'},
  {cam: {tx: 0, ty: 0.05, tz: 0, az: 48, el: 26, d: 5.2}, view: 'solid', explodeK: 1},
  {cam: {tx: 0.2, ty: -0.02, tz: 0.3, az: 60, el: 16, d: 1.2}, view: 'xray', focus: 'mguk'},
  {cam: {tx: 0, ty: 0.24, tz: -0.38, az: 130, el: 22, d: 1.3}, view: 'xray', focus: 'tc'},
  {cam: {tx: 0, ty: -0.05, tz: 0.62, az: 20, el: 40, d: 1.5}, view: 'xray', focus: 'es'},
];
runSim({duration: SHOTS.length, fps: 30, hud: {enabled: false}, director: {enabled: false}}, async ({canvas}) => {
  const st = createStage({canvas});
  const resize = () => st.resize(1600, 900, 1);
  resize();
  return {
    resize,
    render(t) {
      const i = Math.min(SHOTS.length - 1, Math.floor(t));
      const sh = SHOTS[i];
      const tau = 2.3 + t * 0.7;
      st.frame(
        {
          th: crankAt(tau),
          turbo: turboAt(tau),
          wheel: wheelAt(tau),
          s: stateAt(tau),
          ph: {fuel: fuelAt(tau), exh: exhAt(tau), elec: elecAt(tau)},
          view: sh.view,
          viewK: 1,
          explodeK: sh.explodeK || 0,
          focus: sh.focus || 'all',
          focusK: 1,
          flows: 1,
        },
        {...sh.cam, az: sh.cam.az * D2R, el: sh.cam.el * D2R},
      );
      return {};
    },
  };
});
