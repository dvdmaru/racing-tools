// 2026 F1 動力單元的數學：沒有 three.js。一個輸入（示意圈上的時間 τ）推出所有讀數與零件姿態。
//
// 規章數字（與 articles/f1-101-power-unit 同源，條號照 FIA 2026 技術規章 Section C）：
//   C5.2.7  MGU-K 直流電功率上限 350 kW
//   C5.2.8  MGU-K 可用功率隨車速下降（未啟用 Overtake）：<340 km/h 為 1800−5v；340 起未滿 345 為 6900−20v；≥345 為 0
//   Overtake 曲線：7100−20v，355 km/h 歸零（文章「Overtake 模式」節）
//   C5.2.9  電池最高與最低電量差 ≤ 4 MJ
//   C5.2.10 每圈回充上限 8.5 MJ
// 其餘（這一圈的車速、哪裡煞車、回收功率、部分油門發電量）全是示意，畫面上一律標「示意」。
// 單位：km/h、kW、MJ、秒。

export const RULE = {kMax: 350, esWindow: 4, harvestLap: 8.5, taperFrom: 290, zeroAt: 345, otFullTo: 337.5, otZeroAt: 355};

/** C5.2.8：車速 v 時 MGU-K 可用的功率上限（kW）。ot＝Overtake 模式啟用 */
export const kLimit = (v, ot = false) => {
  let p;
  if (ot) p = v < 355 ? 7100 - 20 * v : 0;
  else if (v < 340) p = 1800 - 5 * v;
  else if (v < 345) p = 6900 - 20 * v;
  else p = 0;
  return Math.max(0, Math.min(RULE.kMax, p));
};

// ------------------------------------------------------------ 示意的一圈
// 每段：[秒數, 起速, 終速, 狀態]。full＝全油門、lift＝收油、brake＝煞車、part＝彎中部分油門。
// 文章依據：「賽車會在煞車、部分油門與收油時回充電池」（F1 官方解釋 2026 新詞）。
export const LAP_SEGS = [
  [4.6, 92, 300, 'full'],
  [3.6, 300, 333, 'full'],
  [1.8, 333, 341, 'full'],
  [1.8, 341, 327, 'lift'],
  [3.2, 327, 100, 'brake'],
  [2.4, 100, 104, 'part'],
  [4.4, 104, 282, 'full'],
  [0.9, 282, 276, 'lift'],
  [2.4, 276, 150, 'brake'],
  [1.8, 150, 154, 'part'],
  [4.4, 154, 312, 'full'],
  [1.0, 312, 316, 'full'],
  [1.4, 316, 304, 'lift'],
  [3.0, 304, 88, 'brake'],
  [2.4, 88, 92, 'part'],
  [3.0, 92, 214, 'full'],
  [1.8, 214, 92, 'brake'],
  [1.6, 92, 92, 'part'],
];
export const LAP = LAP_SEGS.reduce((s, g) => s + g[0], 0);
const SEG_T0 = [];
{
  let t = 0;
  for (const g of LAP_SEGS) {
    SEG_T0.push(t);
    t += g[0];
  }
}
const mod = (a, m) => ((a % m) + m) % m;
// 加速段用前快後慢的曲線（出彎猛、高速時阻力大），煞車段前段減速最猛
const easeAcc = (u) => 1 - (1 - u) ** 1.8;
const easeBrk = (u) => 1 - (1 - u) ** 1.35;

/** 示意圈上第 τ 秒：車速與狀態 */
export const lapAt = (tau) => {
  tau = mod(tau, LAP);
  let i = LAP_SEGS.length - 1;
  while (i > 0 && SEG_T0[i] > tau) i--;
  const [d, v0, v1, mode] = LAP_SEGS[i];
  const u = Math.min(1, (tau - SEG_T0[i]) / d);
  const k = mode === 'brake' ? easeBrk(u) : mode === 'full' ? easeAcc(u) : u;
  return {v: v0 + (v1 - v0) * k, mode, seg: i};
};

// 示意的能量策略：全油門時馬達照上限出力（電池見底就停）；煞車時以 350 kW 回收；
// 收油時 LIFT_KW、彎中部分油門時 PART_KW（內燃機帶動 MGU-K 發電）。窗口滿、或本圈回充到 8.5 MJ，就不再回充。
export const PART_KW = 240;
export const LIFT_KW = 350;
const HARV_KW = {brake: RULE.kMax, lift: LIFT_KW, part: PART_KW};
const DT = 1 / 120;
const SOC0 = 2.6;

/**
 * 能量的一步（影片的整圈預算與互動頁的即時累加共用這一支，規則只寫一次）。
 * e＝{soc, harv}（MJ，會被改寫），回傳這一步 MGU-K 的功率（kW，正＝出力、負＝回充）。
 */
export function stepEnergy(e, tau, dt, ot) {
  const {v, mode} = lapAt(tau);
  let p = 0;
  if (mode === 'full') p = e.soc > 1e-6 ? kLimit(v, ot) : 0;
  else if (Math.min(RULE.esWindow - e.soc, RULE.harvestLap - e.harv) > 1e-6) p = -HARV_KW[mode];
  const dE = (p * dt) / 1000;
  if (p > 0) e.soc = Math.max(0, e.soc - dE);
  else if (p < 0) {
    const take = Math.min(-dE, RULE.esWindow - e.soc, RULE.harvestLap - e.harv);
    e.soc += take;
    e.harv += take;
  }
  return p;
}

/** 依 Overtake 時間表 otAt(τ) 算一整圈的表：先空跑三圈讓起點電量收斂（接回圈首不跳），再記第四圈 */
export function makeTable(otAt = () => false) {
  const n = Math.ceil(LAP / DT) + 1;
  const soc = new Float32Array(n);
  const kw = new Float32Array(n);
  const harv = new Float32Array(n);
  const ot = new Uint8Array(n);
  const e = {soc: SOC0, harv: 0};
  for (let lap = 0; lap < 4; lap++) {
    e.harv = 0;
    for (let j = 0; j < n; j++) {
      const o = !!otAt(j * DT);
      if (lap === 3) {
        soc[j] = e.soc;
        harv[j] = e.harv;
        ot[j] = o ? 1 : 0;
      }
      const p = stepEnergy(e, j * DT, DT, o);
      if (lap === 3) kw[j] = p;
    }
  }
  const read = (arr, tau) => {
    const u = mod(tau, LAP) / DT;
    const i = Math.min(arr.length - 2, Math.floor(u));
    return arr[i] + (arr[i + 1] - arr[i]) * (u - i);
  };
  // 功率與 Overtake 取最近格（不內插），避免在出力與回收切換處算出不存在的中間值
  const near = (arr, tau) => arr[Math.min(n - 1, Math.round(mod(tau, LAP) / DT))];
  // 電流粒子的相位（圈）：沿高壓線的流速跟功率走
  const elec = new Float64Array(n);
  for (let j = 1; j < n; j++) elec[j] = elec[j - 1] + (kw[j - 1] / RULE.kMax) * 0.6 * DT;
  return {
    harvestPerLap: harv[n - 1],
    soc,
    at: (tau) => stateFrom(tau, near(kw, tau), read(soc, tau), read(harv, tau), !!near(ot, tau)),
    elecAt: (tau) => Math.floor(tau / LAP) * elec[n - 1] + read(elec, tau),
  };
}

/** 一格畫面需要的一切（由車速、這一步的功率與電量組出來） */
export function stateFrom(tau, kw, soc, harv, ot) {
  const {v, mode, seg} = lapAt(tau);
  let phase;
  if (mode === 'full') phase = kw > 0 ? 'deploy' : 'empty';
  else if (mode === 'brake') phase = kw < 0 ? 'harvest' : 'coast';
  else if (mode === 'lift') phase = kw < 0 ? 'lift' : 'coast';
  else phase = kw < 0 ? 'part' : 'coast';
  return {
    tau: mod(tau, LAP),
    v,
    mode,
    seg,
    phase,
    thr: mode === 'full' ? 1 : mode === 'part' ? 0.35 : mode === 'lift' ? 0.12 : 0,
    ot,
    kLim: kLimit(v, ot),
    kw,
    soc,
    harv,
  };
}

// 固定模式的兩張穩態表（冒煙測試與自我檢查用）
const TAB = {false: makeTable(() => false), true: makeTable(() => true)};
export const HARVEST_PER_LAP = {false: TAB.false.harvestPerLap, true: TAB.true.harvestPerLap};
export const stateAt = (tau, ot = false) => TAB[ot].at(tau);

// ------------------------------------------------------------ 動畫用的轉角（示意，不顯示數字）
// 曲軸與渦輪的轉速只跟油門與車速走，用來讓畫面「活著」；播放時已大幅放慢。
const crankRate = (tau) => {
  const {v, mode} = lapAt(tau);
  return 160 + v * 2.2 + (mode === 'full' ? 260 : 0); // 度／秒（畫面上的）
};
const turboRate = (tau) => {
  const {v, mode} = lapAt(tau);
  return 300 + (mode === 'full' ? 2600 : mode === 'part' ? 900 : 200) * (0.4 + v / 560);
};
const wheelRate = (tau) => (lapAt(tau).v / 3.6 / 0.36) * (180 / Math.PI) * 0.06; // 後輪（同樣放慢）
const integ = (rate) => {
  const n = Math.ceil(LAP / DT) + 1;
  const a = new Float64Array(n);
  for (let j = 1; j < n; j++) a[j] = a[j - 1] + rate((j - 0.5) * DT) * DT;
  return a;
};
const CRANK = integ(crankRate);
const TURBO = integ(turboRate);
const WHEEL = integ(wheelRate);
// 能量流的粒子相位（圈／秒）：燃料跟油門走，電流跟 MGU-K 功率走（正＝電池往馬達，負＝回充），排氣跟油門與車速走
const FUEL = integ((tau) => 0.1 + 0.55 * stateAt(tau).thr);
const EXH = integ((tau) => {
  const s = stateAt(tau);
  return 0.12 + s.thr * (0.25 + s.v / 900);
});
const angle = (arr, tau) => {
  const laps = Math.floor(tau / LAP);
  const u = mod(tau, LAP) / DT;
  const i = Math.min(arr.length - 2, Math.floor(u));
  return laps * arr[arr.length - 1] + arr[i] + (arr[i + 1] - arr[i]) * (u - i);
};
export const crankAt = (tau) => angle(CRANK, tau);
export const turboAt = (tau) => angle(TURBO, tau);
export const wheelAt = (tau) => angle(WHEEL, tau);
export const fuelAt = (tau) => angle(FUEL, tau);
export const exhAt = (tau) => angle(EXH, tau);
export const elecAt = (tau, ot = false) => TAB[ot].elecAt(tau);

// ------------------------------------------------------------ V6 的曲柄連桿（示意尺寸，公尺）
// 90 度 V6，左右各三缸；尺寸只為了畫得像，不是任何廠商的實際數字，畫面上不顯示。
export const ICE = {r: 0.026, rod: 0.12, bore: 0.08, pitch: 0.098, bankOff: 0.012};
const S = Math.SQRT1_2;
export const BANK = {L: {b: [S, S], p: [S, -S]}, R: {b: [-S, S], p: [-S, -S]}};
// 缸 1-3 在左排（+x），4-6 在右排；三個曲柄銷相隔 120 度，左右排共用一個銷
export const CYL = [0, 1, 2, 3, 4, 5].map((i) => {
  const L = i < 3;
  const pin = i % 3;
  return {i, bank: L ? 'L' : 'R', pin, z: (1 - pin) * ICE.pitch + (L ? ICE.bankOff : -ICE.bankOff)};
});
export const PIN_PHASE = [0, 120, 240];
export const pinXY = (p, th) => {
  const a = ((th + PIN_PHASE[p]) * Math.PI) / 180;
  return [ICE.r * Math.sin(a), ICE.r * Math.cos(a)];
};
/** 第 i 缸：活塞銷沿缸軸的距離 s、曲柄銷位置 P */
export const piston = (i, th) => {
  const cy = CYL[i];
  const B = BANK[cy.bank];
  const P = pinXY(cy.pin, th);
  const pb = P[0] * B.b[0] + P[1] * B.b[1];
  const pp = P[0] * B.p[0] + P[1] * B.p[1];
  const s = pb + Math.sqrt(ICE.rod * ICE.rod - pp * pp);
  return {s, P};
};
export const bankXY = (bank, w, d) => {
  const B = BANK[bank];
  return [d * B.b[0] + w * B.p[0], d * B.b[1] + w * B.p[1]];
};

// ------------------------------------------------------------ 自我檢查（載入時跑，失敗就在 console 大聲說）
export const SELF_CHECK = (() => {
  const bad = [];
  const eq = (a, b, msg) => Math.abs(a - b) > 1e-9 && bad.push(`${msg}: ${a} ≠ ${b}`);
  eq(kLimit(0), 350, '0 km/h 應為 350');
  eq(kLimit(290), 350, '290 km/h 應為 350');
  eq(kLimit(300), 300, '300 km/h 應為 1800−5×300');
  eq(kLimit(340), 100, '340 km/h 兩段公式應銜接在 100');
  eq(kLimit(345), 0, '345 km/h 應歸零');
  eq(kLimit(337.5, true), 350, 'Overtake 337.5 km/h 應為 350');
  eq(kLimit(355, true), 0, 'Overtake 355 km/h 應歸零');
  for (const ot of [false, true]) {
    if (HARVEST_PER_LAP[ot] > RULE.harvestLap + 1e-6) bad.push(`每圈回充 ${HARVEST_PER_LAP[ot]} 超過 8.5 MJ`);
    for (const s of TAB[ot].soc) if (s < -1e-6 || s > RULE.esWindow + 1e-6) bad.push(`電量 ${s} 超出 4 MJ 窗口`);
  }
  if (bad.length) console.error('[pu-2026 自我檢查失敗]', bad);
  return bad;
})();
