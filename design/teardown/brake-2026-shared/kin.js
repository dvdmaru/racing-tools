// 2026 F1 煞車的數學：沒有 three.js。一個輸入（示意圈上的時間 τ）加上三個條件，推出踏板、四個主缸／卡鉗的相對壓力、
// 後輪的減速分工（MGU-K 回收 vs 卡鉗）與碟盤溫度。
//
// 規章數字（與 articles/f1-101-brakes 同源，條號照 FIA 2026 技術規章 Section C）：
//   C11.1.1  一根踏板推兩個主缸：一個管前輪、一個管後輪；每個後輪不靠動力單元也要有 ≥ 2500 Nm（卡鉗壓力 ≤ 150 barG）
//   C11.3    每輪一片碟盤，厚度 ≤ 34 mm；前盤直徑 325–345 mm、後盤 260–280 mm；冷卻孔最小直徑 2.5 mm
//   C11.4.1  禁止防鎖死（ABS）
//   C11.4.2  卡鉗壓力不得高於車手踩出的壓力，唯一例外是後輪煞車控制系統
//   C11.6    後輪壓力可由電動控制系統提供，但 ≤ 車手同時在後主缸產生壓力的 1.2 倍；電控停用時液壓主缸仍把壓力送到後輪
// Brembo 的說法（文章附來源）：碳碳盤工作窗口通常攝氏 350–550 度、重煞可超過 1,000 度。
// 其餘全是示意，畫面上標「示意」：這一圈的車速與 MGU-K 回收量（沿用動力單元頁同一圈）、車重、煞車平衡的預設值、
// 熱模型（碟盤溫度）、壓力只畫相對值（規章沒有給比賽中的壓力數字，畫面上不顯示 bar）。
import {LAP, lapAt, stateAt as puState} from '../pu-2026-shared/kin.js';
export {wheelAt} from '../aero-2026-shared/kin.js';

export {LAP, lapAt};
export const RULE = {bbwMax: 1.2, rearNm: 2500, rearBarG: 150, winLo: 350, winHi: 550, peak: 1000, discF: [325, 345], discR: [260, 280], thickMax: 34, holeMin: 2.5};
/** 示意的幾何（公釐）：前盤 335、後盤 270、厚 32、冷卻孔 3 */
export const DISC = {f: {d: 335, t: 32}, r: {d: 270, t: 32}, hole: 3};
const MASS = 800; // 示意（公斤，含車手與燃料），畫面上不顯示
export const BAL0 = 0.55; // 煞車平衡預設：前軸 55%（示意；文章舉的是 2021 年賓士「約 52 到 53%」）
const mod = (a, m) => ((a % m) + m) % m;

/** 示意圈上第 τ 秒的減速度（m/s²，只有踩煞車時才算煞車要負責的部分） */
const decel = (tau) => {
  const h = 0.01;
  return Math.max(0, (lapAt(tau - h).v - lapAt(tau + h).v) / 3.6 / (2 * h));
};
// 這一圈最大的煞車力（踏板的 100%）
const F_MAX = (() => {
  let m = 0;
  for (let t = 0; t < LAP; t += 0.01) if (lapAt(t).mode === 'brake') m = Math.max(m, MASS * decel(t));
  return m;
})();

/**
 * 一格的力與壓力。cond＝{bal（前軸比例）, bbw（後輪電控在不在）, harvest（MGU-K 回不回收）}
 * 回傳的力單位是牛頓，壓力是「踏板 100% 時的前後主缸壓力」為 1 的相對值。
 */
export function forcesAt(tau, cond) {
  const {v, mode} = lapAt(tau);
  const vm = Math.max(1, v / 3.6);
  const pu = puState(mod(tau, LAP));
  const kHarv = cond.harvest && pu.kw < 0 ? -pu.kw : 0; // kW
  const braking = mode === 'brake';
  const F = braking ? MASS * decel(tau) : 0; // 車手要的總煞車力
  const pedal = F / F_MAX;
  const Ff = cond.bal * F;
  const Fr = (1 - cond.bal) * F;
  // MGU-K 在後輪造成的減速力：功率 ÷ 車速；煞車時最多就是後輪要的那一份（電控只能減壓，不能出負壓）
  let Fk = (kHarv * 1000) / vm;
  if (braking) Fk = Math.min(Fk, Fr);
  // 主缸壓力：同一根踏板，經平衡桿分給前後（相對值：前後各自在踏板 100% 時為 1）
  const pFM = pedal;
  const pRM = pedal;
  let Frc;
  let pRC;
  if (!braking) {
    Frc = 0;
    pRC = 0;
  } else if (cond.bbw) {
    // 電控：馬達回收了多少，就少給多少油壓，讓後輪的總減速仍等於車手要的那一份（C11.6，上限 1.2 倍）
    Frc = Fr - Fk;
    pRC = Math.min(RULE.bbwMax * pRM, Fr > 0 ? pRM * (Frc / Fr) : 0);
  } else {
    // 電控停用：後主缸的液壓直接送到後輪（C11.6）
    Frc = Fr;
    pRC = pRM;
  }
  let phase;
  if (braking) phase = Fk > 1 ? (cond.bbw ? 'brake' : 'brakeNoBbw') : 'brakeNoK';
  else if (kHarv > 0) phase = 'lift';
  else phase = mode === 'full' ? 'full' : 'part';
  return {tau: mod(tau, LAP), v, mode, phase, F, pedal, Ff, Fr, Fk, Frc, pFM, pRM, pRC, kHarv, soc: pu.soc, braking};
}

// ------------------------------------------------------------ 示意的熱模型（碟盤溫度，攝氏）
// 加熱：每片盤吃到自己那份煞車力 × 車速；散熱：對流（隨車速）＋輻射（高溫時變強）。只為了畫出「窗口很窄、重煞衝破 1,000 度」。
const T_AIR = 40;
const HEAT_CAP = {f: 900, r: 680}; // J/K（示意）
const COOL = {f: 58, r: 42}; // W/K（示意）
const RAD = {f: 4e-9, r: 3e-9};
export function stepThermal(th, tau, dt, cond) {
  const s = forcesAt(tau, cond);
  const vm = s.v / 3.6;
  for (const k of ['f', 'r']) {
    const Fdisc = (k === 'f' ? s.Ff : s.Frc) / 2;
    const T = th[k];
    const P = Fdisc * vm;
    const Tk = T + 273;
    const loss = COOL[k] * (T - T_AIR) * (0.3 + vm / 60) + RAD[k] * (Tk ** 4 - 313 ** 4);
    th[k] = T + ((P - loss) * dt) / HEAT_CAP[k];
  }
  return s;
}

const DT = 1 / 240;
/** 整圈的表：condAt(τ) 給條件；先空跑三圈讓溫度收斂（接回圈首不跳），再記第四圈 */
export function makeTable(condAt) {
  const n = Math.ceil(LAP / DT) + 1;
  const tf = new Float32Array(n);
  const tr = new Float32Array(n);
  const th = {f: 450, r: 400};
  for (let lap = 0; lap < 4; lap++)
    for (let j = 0; j < n; j++) {
      if (lap === 3) {
        tf[j] = th.f;
        tr[j] = th.r;
      }
      stepThermal(th, j * DT, DT, condAt(j * DT));
    }
  const read = (arr, tau) => {
    const u = mod(tau, LAP) / DT;
    const i = Math.min(n - 2, Math.floor(u));
    return arr[i] + (arr[i + 1] - arr[i]) * (u - i);
  };
  return {
    tf,
    tr,
    at: (tau) => ({...forcesAt(tau, condAt(mod(tau, LAP))), cond: condAt(mod(tau, LAP)), Tf: read(tf, tau), Tr: read(tr, tau)}),
  };
}

// ------------------------------------------------------------ 自我檢查（載入時跑，失敗就在 console 大聲說）
export const SELF_CHECK = (() => {
  const bad = [];
  const inR = (x, [a, b], msg) => (x < a || x > b) && bad.push(`${msg}: ${x} 不在 ${a}–${b}`);
  inR(DISC.f.d, RULE.discF, '前盤直徑（C11.3）');
  inR(DISC.r.d, RULE.discR, '後盤直徑（C11.3）');
  if (DISC.f.t > RULE.thickMax || DISC.r.t > RULE.thickMax) bad.push('碟盤厚度超過 34 mm（C11.3）');
  if (DISC.hole < RULE.holeMin) bad.push('冷卻孔小於 2.5 mm（C11.3）');
  const conds = {
    normal: {bal: BAL0, bbw: true, harvest: true},
    noBbw: {bal: BAL0, bbw: false, harvest: true},
    noK: {bal: BAL0, bbw: true, harvest: false},
    fwd: {bal: 0.7, bbw: true, harvest: true},
  };
  for (const [name, c] of Object.entries(conds)) {
    for (let t = 0; t < LAP; t += 0.02) {
      const s = forcesAt(t, c);
      if (s.pRC > RULE.bbwMax * s.pRM + 1e-9) bad.push(`${name}: 後卡鉗壓力超過後主缸的 1.2 倍（C11.6）`);
      if (s.pFM > s.pedal + 1e-9) bad.push(`${name}: 前卡鉗壓力高於車手踩出的壓力（C11.4.2）`);
      if (!c.bbw && s.braking && Math.abs(s.pRC - s.pRM) > 1e-9) bad.push(`${name}: 電控停用時後輪壓力應等於後主缸（C11.6）`);
      if (c.bbw && s.braking && Math.abs(s.Frc + s.Fk - s.Fr) > 1e-6) bad.push(`${name}: 電控下後輪總減速應等於平衡設定的那一份`);
      if (s.Frc < -1e-9 || s.Fk < -1e-9) bad.push(`${name}: 出現負的煞車力`);
    }
  }
  const tab = makeTable(() => conds.normal);
  const peakF = Math.max(...tab.tf);
  const minF = Math.min(...tab.tf);
  if (peakF < RULE.peak || peakF > 1250) bad.push(`示意熱模型：前盤峰值 ${peakF.toFixed(0)}°C 不在 1,000–1,250`);
  if (minF < 200) bad.push(`示意熱模型：前盤最低 ${minF.toFixed(0)}°C 太冷`);
  const noK = makeTable(() => conds.noK);
  if (!(Math.max(...noK.tr) > Math.max(...tab.tr))) bad.push('MGU-K 不回收時，後盤應該更燙');
  if (bad.length) console.error('[brake-2026 自我檢查失敗]', bad.slice(0, 20));
  return {bad, peakF, minF, peakR: Math.max(...tab.tr), peakRnoK: Math.max(...noK.tr), minR: Math.min(...tab.tr)};
})();
