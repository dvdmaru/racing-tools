// 2026 F1 主動空力的規則：沒有 three.js。一個輸入（示意圈上的時間 τ）加上三個條件，推出兩片翼片的位置。
//
// 規章數字與條件（與 articles/f1-101-active-aero 同源，條號照 FIA 2026 運動規章 Section B 與技術規章 Section C）：
//   B7.1.1 a        會動的只有前翼元件與後翼襟翼，由 FIA 標準 ECU 控制
//   B7.1.1 b、c、d  停用＝前後都在 Corner Mode；部分啟用＝前翼 Straight、後翼 Corner；完全啟用＝前後都在 Straight
//   B7.1.2 a        車手要先被通知「已啟用」才可以啟用
//   C3.10.10 w；C3.11.6 j   只有在車輛靜止、或完全位於啟動區內時，才可以處於部署狀態
//   B7.1.2 b        宣告低抓地條件後，只准在低抓地啟動區內部分啟用（後翼襟翼不能到 Straight Mode）
//   C3.10.10 o；C3.11.6 d   兩個位置之間切換不得超過 400 毫秒
//   C3.10.10 t；C3.11.6 h   除了失效與切換過程，翼片只能待在兩個位置
//   C3.10.10 v；C3.11.6 i   調整系統失效時，翼片回到 Corner Mode
// 其餘全是示意，畫面上標「示意」：這一圈的車速（沿用動力單元頁的同一圈）、啟動區的位置與長度、
// 切換實際花的時間（規章只給上限）、翼片的角度（規章沒有數字，畫面上不顯示角度）。
import {LAP, lapAt} from '../pu-2026-shared/kin.js';

export {LAP, lapAt};
export const RULE = {switchMax: 0.4};
/** 示意的切換時間（秒）：規章只給上限 400 毫秒，沒有實測值 */
export const T_SW = 0.3;

// ------------------------------------------------------------ 示意的啟動區（同一圈的三條長直線；第四條短直線沒有啟動區）
// 規章：啟動區由 FIA 訂、賽前至少 4 週通知車隊、起點至少一側有標示牌（B7.1.1 e、f）。位置與長度條文沒有列，這裡是示意。
// 這一圈也把三個啟動區當成低抓地啟動區（示意）。
export const ZONES = [
  [1.2, 10.0],
  [18.6, 21.8],
  [27.8, 32.3],
];
const mod = (a, m) => ((a % m) + m) % m;
export const zoneAt = (tau) => {
  tau = mod(tau, LAP);
  return ZONES.findIndex(([a, b]) => tau >= a && tau < b);
};

const smoother = (x) => {
  const u = Math.min(1, Math.max(0, x));
  return u * u * u * (u * (u * 6 - 15) + 10);
};
/** 位置 p（0＝Corner、1＝Straight）換成畫面上的轉動比例：切換時頭尾放慢，看起來像致動器在推 */
export const ease = smoother;

/** 一片翼片的狀態：p 位置、target 目標、t0 這次切換開始的時鐘、ms 上一次切換花的毫秒、cmd 上一次換目標的時鐘 */
const wing = () => ({p: 0, target: 0, t0: 0, ms: 0, cmd: -9});
export const newAero = () => ({clock: 0, f: wing(), r: wing(), zone: -1, failed: false, last: null});

function move(w, target, a, dt, key) {
  if (target !== w.target) {
    w.target = target;
    w.t0 = a.clock;
    w.cmd = a.clock;
  }
  if (w.p === w.target) return;
  const dir = w.target > w.p ? 1 : -1;
  w.p = Math.min(1, Math.max(0, w.p + (dir * dt) / T_SW));
  if ((dir > 0 && w.p >= 1) || (dir < 0 && w.p <= 0)) {
    w.p = w.target;
    w.ms = (a.clock - w.t0) * 1000;
    a.last = {wing: key, ms: w.ms, to: w.target};
  }
}

/**
 * 主動空力的一步（影片的整圈表與互動頁的即時累加共用這一支，規則只寫一次）。
 * a＝newAero() 的狀態（會被改寫）；cond＝{enabled, lowGrip, fail}：fail 為真的那一步發生「系統失效」。
 * 示意：失效之後到這個啟動區結束前都停在 Corner Mode；在區外發生，就停到下一個啟動區結束。
 */
export function stepAero(a, tau, dt, cond) {
  a.clock += dt;
  const z = zoneAt(tau);
  if (z !== a.zone) {
    if (a.zone >= 0 && z < 0) a.failed = false; // 離開啟動區，失效狀態解除（示意）
    a.zone = z;
  }
  if (cond.fail) a.failed = true;
  // 翼片必須在離開啟動區之前回到 Corner Mode（部署狀態只准發生在區內），所以提早一次切換的時間收回
  const inZone = z >= 0 && mod(tau, LAP) < ZONES[z][1] - T_SW - 0.05;
  const ok = inZone && cond.enabled && !a.failed;
  move(a.f, ok ? 1 : 0, a, dt, 'f');
  move(a.r, ok && !cond.lowGrip ? 1 : 0, a, dt, 'r');
}

/** 一格畫面需要的一切 */
export function stateOf(tau, a, cond) {
  const {v} = lapAt(tau);
  const pf = a.f.p;
  const pr = a.r.p;
  const moving = (pf > 0 && pf < 1) || (pr > 0 && pr < 1) || pf !== a.f.target || pr !== a.r.target;
  let mode;
  if (moving) mode = 'switch';
  else if (pf === 1 && pr === 1) mode = 'full';
  else if (pf === 1) mode = 'partial';
  else mode = 'off';
  const z = zoneAt(tau);
  return {
    tau: mod(tau, LAP),
    v,
    pf,
    pr,
    tf: a.f.target,
    tr: a.r.target,
    mode,
    deploy: pf > 0 || pr > 0 || a.f.target > 0 || a.r.target > 0,
    zone: z,
    enabled: cond.enabled,
    lowGrip: cond.lowGrip,
    failed: a.failed,
    lastMs: a.last ? a.last.ms : 0,
    lastWing: a.last ? a.last.wing : null,
    cmdF: a.clock - a.f.cmd,
    cmdR: a.clock - a.r.cmd,
  };
}

// ------------------------------------------------------------ 整圈的表（影片用；互動頁的狀態色帶也用）
const DT = 1 / 240;
/** condAt(τ) → {enabled, lowGrip, failAt?}；failAt＝這一圈發生失效的 τ（沒有就省略） */
export function makeTable(condAt = () => ({enabled: true, lowGrip: false}), failAt = null) {
  const n = Math.ceil(LAP / DT) + 1;
  const rows = new Array(n);
  const a = newAero();
  for (let j = 0; j < n; j++) {
    const tau = j * DT;
    const c = condAt(tau);
    const fail = failAt !== null && tau >= failAt && tau - DT < failAt;
    stepAero(a, tau, DT, {...c, fail});
    rows[j] = stateOf(tau, a, c);
  }
  const at = (tau) => {
    const u = mod(tau, LAP) / DT;
    const i = Math.min(n - 2, Math.floor(u));
    const k = u - i;
    const r0 = rows[i];
    const r1 = rows[i + 1];
    // 位置內插（畫面平滑），其餘取最近格
    return {...(k < 0.5 ? r0 : r1), tau: mod(tau, LAP), v: lapAt(tau).v, pf: r0.pf + (r1.pf - r0.pf) * k, pr: r0.pr + (r1.pr - r0.pr) * k};
  };
  return {rows, at, DT};
}

// ------------------------------------------------------------ 車輪轉角（示意，只讓畫面活著；播放時已大幅放慢）
const wheelRate = (tau) => (lapAt(tau).v / 3.6 / 0.36) * (180 / Math.PI) * 0.06;
const WHEEL = (() => {
  const n = Math.ceil(LAP / DT) + 1;
  const arr = new Float64Array(n);
  for (let j = 1; j < n; j++) arr[j] = arr[j - 1] + wheelRate((j - 0.5) * DT) * DT;
  return arr;
})();
export const wheelAt = (tau) => {
  const laps = Math.floor(tau / LAP);
  const u = mod(tau, LAP) / DT;
  const i = Math.min(WHEEL.length - 2, Math.floor(u));
  return laps * WHEEL[WHEEL.length - 1] + WHEEL[i] + (WHEEL[i + 1] - WHEEL[i]) * (u - i);
};

// ------------------------------------------------------------ 自我檢查（載入時跑，失敗就在 console 大聲說）
// 對三種條件各跑一整圈，驗規章寫的每一條：只有兩個位置、切換 ≤ 400 毫秒、部署只在啟動區內、
// 低抓地時後翼襟翼不動、失效後回到 Corner Mode、三種狀態的定義。
export const SELF_CHECK = (() => {
  const bad = [];
  if (!(T_SW <= RULE.switchMax)) bad.push(`示意切換時間 ${T_SW}s 超過上限 ${RULE.switchMax}s`);
  const cases = {
    normal: makeTable(() => ({enabled: true, lowGrip: false})),
    lowGrip: makeTable(() => ({enabled: true, lowGrip: true})),
    notEnabled: makeTable(() => ({enabled: false, lowGrip: false})),
    fail: makeTable(() => ({enabled: true, lowGrip: false}), 20.2),
  };
  for (const [name, tab] of Object.entries(cases)) {
    let run = 0;
    for (const r of tab.rows) {
      for (const p of [r.pf, r.pr]) if (p < 0 || p > 1) bad.push(`${name}: 位置 ${p} 超出兩個位置的範圍`);
      const between = (r.pf > 0 && r.pf < 1) || (r.pr > 0 && r.pr < 1);
      run = between ? run + tab.DT : 0;
      if (run > RULE.switchMax + 1e-9) bad.push(`${name}: τ=${r.tau.toFixed(3)} 停在兩個位置之間超過 400 毫秒`);
      if (r.lastMs > RULE.switchMax * 1000 + 1e-6) bad.push(`${name}: 切換花了 ${r.lastMs} 毫秒`);
      if ((r.pf > 0 || r.pr > 0) && r.zone < 0) bad.push(`${name}: τ=${r.tau.toFixed(3)} 在啟動區外仍處於部署狀態`);
      if (r.mode === 'full' && !(r.pf === 1 && r.pr === 1)) bad.push(`${name}: 完全啟用的定義不符`);
      if (r.mode === 'partial' && !(r.pf === 1 && r.pr === 0)) bad.push(`${name}: 部分啟用的定義不符`);
    }
  }
  if (cases.lowGrip.rows.some((r) => r.pr > 0)) bad.push('低抓地條件下後翼襟翼離開了 Corner Mode');
  if (!cases.lowGrip.rows.some((r) => r.mode === 'partial')) bad.push('低抓地條件下應該看得到部分啟用');
  if (cases.notEnabled.rows.some((r) => r.pf > 0 || r.pr > 0)) bad.push('沒有被通知已啟用，翼片卻動了');
  if (!cases.normal.rows.some((r) => r.mode === 'full')) bad.push('一般條件下應該看得到完全啟用');
  {
    const f = cases.fail.rows.find((r) => r.tau >= 20.2 + T_SW + 0.01);
    if (!f || f.pf !== 0 || f.pr !== 0) bad.push('失效後翼片沒有回到 Corner Mode');
  }
  if (bad.length) console.error('[aero-2026 自我檢查失敗]', bad.slice(0, 20));
  return bad;
})();
