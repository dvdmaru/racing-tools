// 2026 F1 煞車系統的幾何：全部用程式長出來，不載入任何模型檔。
// 「依公開資料重繪的示意模型」：通用造型、零塗裝、零標誌；比例與零件位置是示意。碟盤尺寸照 C11.3 的範圍取值（kin.js 的 DISC）。
// 座標：公尺；y 朝上（地面 y＝0）、z 朝車頭（+z）、x 朝車子左側（+x）。與主動空力頁同一台車的比例。
//
// 零件分組：
//   pedal   踏板、兩個主缸、儲油杯，以及前輪油路與「後主缸 → 電控」那一段油管
//   fbrake  前輪：碟盤（含冷卻孔）、卡鉗、來令片、輪轂
//   rbrake  後輪：同上
//   bbw     後輪電控單元（線傳煞車）與「電控 → 後卡鉗」的油管
//   mguk    MGU-K、變速箱、傳動軸與電池（回收路徑）
//   body    車身與輪胎（背景脈絡，固定半透明）
import * as THREE from 'three';
import {loft, tube, curve} from '../aero-2026-shared/car.js';
import {DISC} from './kin.js';

const V3 = THREE.Vector3;
const D2R = Math.PI / 180;
export const PARTS3D = ['pedal', 'fbrake', 'rbrake', 'bbw', 'mguk'];
export const COL = {press: '#d63a2f', harvest: '#2f8a9c', ink: '#241a1c', hot: '#ff8a2a'};
const R_WHEEL = 0.36;
const AXLE = {f: 1.7, r: -1.7};
const DISC_X = 0.64;
export const CENTRE = {
  all: [0, 0.32, 0],
  pedal: [0, 0.22, 1.18],
  fbrake: [DISC_X, R_WHEEL, AXLE.f],
  rbrake: [DISC_X, R_WHEEL, AXLE.r],
  bbw: [-0.1, 0.22, -1.05],
  mguk: [0.12, 0.22, -0.6],
  body: [0, 0.4, 0],
};
const EXPLODE = {pedal: [0, 0.4, 0.1], bbw: [-0.2, 0.42, 0], mguk: [0, 0.5, 0], fbrake: [0, 0, 0], rbrake: [0, 0, 0], body: [0, 0, 0]};
export {EXPLODE};
const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
/** 溫度 → 發光顏色與強度（示意的黑體色：暗紅 → 橘 → 橘黃） */
const C_LO = new THREE.Color('#6a1205');
const C_MID = new THREE.Color('#ff3c0c');
const C_HI = new THREE.Color('#ffb24a');
export function heatGlow(T, out) {
  const k = Math.min(1, Math.max(0, (T - 450) / 650));
  if (k < 0.5) out.copy(C_LO).lerp(C_MID, k / 0.5);
  else out.copy(C_MID).lerp(C_HI, (k - 0.5) / 0.5);
  return k <= 0 ? 0 : 0.08 + 1.5 * k ** 1.7;
}

export function buildCar() {
  const root = new THREE.Group();
  const M = {
    shell: new THREE.MeshPhysicalMaterial({color: '#9aa1a8', roughness: 0.3, metalness: 0, transparent: true, opacity: 0.1, depthWrite: false, side: THREE.DoubleSide}),
    tire: new THREE.MeshStandardMaterial({color: '#2a2b2e', roughness: 0.85, metalness: 0, transparent: true, opacity: 0.22, depthWrite: false}),
    rim: new THREE.MeshStandardMaterial({color: '#7d8289', roughness: 0.35, metalness: 0.8, transparent: true, opacity: 0.3, depthWrite: false}),
    disc: new THREE.MeshPhysicalMaterial({color: '#2c2c30', roughness: 0.55, metalness: 0.1, clearcoat: 0.2}),
    hole: new THREE.MeshBasicMaterial({color: '#0e0e10'}),
    alu: new THREE.MeshStandardMaterial({color: '#c9ccd1', roughness: 0.34, metalness: 0.85}),
    caliper: new THREE.MeshPhysicalMaterial({color: '#b9bdc3', roughness: 0.3, metalness: 0.8, clearcoat: 0.3}),
    pad: new THREE.MeshStandardMaterial({color: '#5b4e44', roughness: 0.8, metalness: 0.1}),
    steel: new THREE.MeshStandardMaterial({color: '#d0d3d7', roughness: 0.28, metalness: 1}),
    dark: new THREE.MeshPhysicalMaterial({color: '#25282d', roughness: 0.45, metalness: 0.2, clearcoat: 0.4}),
    reservoir: new THREE.MeshPhysicalMaterial({color: '#e8e4dc', roughness: 0.25, metalness: 0, transmission: 0, transparent: true, opacity: 0.85}),
    copper: new THREE.MeshStandardMaterial({color: '#b6743c', roughness: 0.38, metalness: 0.9}),
    cell: new THREE.MeshStandardMaterial({color: '#e8e9eb', roughness: 0.5, metalness: 0.1}),
  };
  const lineMat = () => new THREE.MeshStandardMaterial({color: '#7a7f88', roughness: 0.45, metalness: 0.5, emissive: new THREE.Color(COL.press), emissiveIntensity: 0});
  const LINE = {front: lineMat(), rearM: lineMat(), rearC: lineMat()};
  const XRAY = new THREE.MeshPhysicalMaterial({color: '#aab3bd', roughness: 0.2, metalness: 0, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide});
  const EDGE = new THREE.LineBasicMaterial({color: '#5a6470', transparent: true, opacity: 0});
  const GHOST = new THREE.MeshBasicMaterial({color: '#8a8183', transparent: true, opacity: 0.06, depthWrite: false});

  const groups = {};
  for (const k of [...PARTS3D, 'body']) {
    const g = new THREE.Group();
    g.name = k;
    root.add(g);
    groups[k] = g;
  }
  const meshes = []; // {mesh, comp, shell, base, side, tag}
  const add = (comp, geo, mat, {shell = false, pos, rot, parent, tag, side = 0} = {}) => {
    const m = new THREE.Mesh(geo, mat);
    if (pos) m.position.set(...pos);
    if (rot) m.rotation.set(...rot);
    m.castShadow = !mat.transparent;
    m.receiveShadow = true;
    (parent || groups[comp]).add(m);
    meshes.push({mesh: m, comp, shell, base: mat, side, tag});
    if (shell) {
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), EDGE);
      e.visible = false;
      m.add(e);
      m.userData.edge = e;
    }
    return m;
  };

  // ------------------------------------------------------------ 車身（背景脈絡，固定半透明）
  add('body', loft([
    [2.42, 0.05, 0.2, 0.27], [2.15, 0.1, 0.16, 0.33], [1.7, 0.17, 0.12, 0.45], [1.2, 0.26, 0.08, 0.58], [0.6, 0.34, 0.07, 0.64],
    [0.0, 0.36, 0.07, 0.66], [-0.5, 0.3, 0.08, 0.66], [-1.1, 0.22, 0.1, 0.56], [-1.7, 0.14, 0.12, 0.42], [-2.0, 0.09, 0.14, 0.36],
  ], 3.2, 44), M.shell, {tag: 'shell'});
  for (const sx of [-1, 1]) {
    add('body', loft([[0.62, 0.12, 0.1, 0.44], [0.25, 0.2, 0.08, 0.5], [-0.4, 0.17, 0.08, 0.44], [-1.15, 0.08, 0.1, 0.28], [-1.45, 0.03, 0.12, 0.2]], 3.4, 36, sx * 0.47), M.shell, {tag: 'shell'});
  }
  add('body', box(1.36, 0.022, 2.7), M.shell, {pos: [0, 0.055, -0.15], tag: 'shell'});
  add('body', box(1.36, 0.02, 0.5), M.shell, {pos: [0, 0.12, 2.3], tag: 'shell'}); // 前翼（只是輪廓）
  add('body', box(0.94, 0.04, 0.26), M.shell, {pos: [0, 0.88, -2.3], tag: 'shell'}); // 後翼（只是輪廓）

  // ------------------------------------------------------------ 四個輪角
  const corners = [];
  for (const axle of ['f', 'r']) {
    const comp = axle === 'f' ? 'fbrake' : 'rbrake';
    const dR = DISC[axle].d / 2000;
    const dT = DISC[axle].t / 1000;
    for (const sx of [1, -1]) {
      const z = AXLE[axle];
      // 會轉的：輪胎、輪圈、碟盤（碟盤鎖在輪轂上，跟著車輪轉）
      const spin = new THREE.Group();
      spin.position.set(0, R_WHEEL, z);
      root.add(spin);
      const wheelG = new THREE.Group();
      wheelG.position.x = sx * 0.8;
      spin.add(wheelG);
      const w = axle === 'f' ? 0.3 : 0.38;
      const tire = add('body', new THREE.CylinderGeometry(R_WHEEL, R_WHEEL, w, 56).rotateZ(Math.PI / 2), M.tire, {parent: wheelG, tag: 'tire', side: sx});
      const rim = add('body', new THREE.CylinderGeometry(R_WHEEL * 0.62, R_WHEEL * 0.62, w + 0.004, 40, 1, true).rotateZ(Math.PI / 2), M.rim, {parent: wheelG, tag: 'tire', side: sx});
      for (let i = 0; i < 5; i++) add('body', box(0.02, 0.025, R_WHEEL * 1.12), M.rim, {parent: wheelG, rot: [(i / 5) * Math.PI, 0, 0], pos: [sx * (w / 2 - 0.01), 0, 0], tag: 'tire', side: sx});
      const discG = new THREE.Group();
      discG.position.x = sx * DISC_X;
      spin.add(discG);
      const discMat = M.disc.clone();
      discMat.emissive = new THREE.Color('#000');
      add(comp, new THREE.CylinderGeometry(dR, dR, dT, 64).rotateZ(Math.PI / 2), discMat, {parent: discG, side: sx});
      add(comp, new THREE.CylinderGeometry(dR * 0.42, dR * 0.42, dT + 0.03, 32).rotateZ(Math.PI / 2), M.alu, {parent: discG, side: sx});
      // 冷卻孔：盤緣一圈一圈的小孔（孔數是示意）
      const rows = axle === 'f' ? 4 : 3;
      const per = axle === 'f' ? 84 : 66;
      const holes = new THREE.InstancedMesh(new THREE.SphereGeometry(0.0021, 6, 4), M.hole, rows * per);
      {
        const m4 = new THREE.Matrix4();
        let k = 0;
        for (let r = 0; r < rows; r++)
          for (let i = 0; i < per; i++) {
            const a = ((i + (r % 2) * 0.5) / per) * Math.PI * 2;
            m4.makeTranslation(((r + 0.5) / rows - 0.5) * dT * 0.8, (dR + 0.0004) * Math.sin(a), (dR + 0.0004) * Math.cos(a));
            holes.setMatrixAt(k++, m4);
          }
      }
      discG.add(holes);
      // 冷卻孔與碟盤同組：聚焦別處時一起變淡、剖開時一起被切
      meshes.push({mesh: holes, comp, shell: false, base: M.hole, side: sx});
      // 不轉的：輪轂支架、卡鉗、來令片（卡鉗在碟盤後上方）
      const fix = new THREE.Group();
      fix.position.set(sx * DISC_X, R_WHEEL, z);
      groups[comp].add(fix);
      add(comp, new THREE.CylinderGeometry(0.05, 0.05, 0.18, 24).rotateZ(Math.PI / 2), M.steel, {parent: fix, pos: [sx * 0.08, 0, 0], side: sx});
      add(comp, box(0.04, 0.26, 0.08), M.dark, {parent: fix, pos: [-sx * 0.05, 0, 0], side: sx});
      const phi = (axle === 'f' ? 125 : 55) * D2R;
      const calG = new THREE.Group();
      calG.position.set(0, (dR - 0.022) * Math.sin(phi), (dR - 0.022) * Math.cos(phi));
      calG.rotation.x = Math.PI / 2 - phi;
      fix.add(calG);
      add(comp, box(dT + 0.062, 0.062, 0.15), M.caliper, {parent: calG, shell: true, side: sx});
      const pads = [];
      for (const s of [-1, 1]) pads.push(add(comp, box(0.009, 0.044, 0.125), M.pad, {parent: calG, pos: [s * (dT / 2 + 0.006), -0.004, 0], side: sx}));
      corners.push({axle, sx, comp, spin, wheelG, discG, discMat, fix, calG, tire, rim, pads, caliperAt: new V3(sx * DISC_X, R_WHEEL + (dR - 0.022) * Math.sin(phi), z + (dR - 0.022) * Math.cos(phi))});
    }
  }

  // ------------------------------------------------------------ 踏板與兩個主缸（C11.1.1）
  const P = CENTRE.pedal;
  const pedalG = new THREE.Group();
  pedalG.position.set(0, 0.11, 1.3);
  groups.pedal.add(pedalG);
  add('pedal', box(0.03, 0.2, 0.012), M.alu, {parent: pedalG, pos: [0, 0.1, 0]});
  add('pedal', box(0.07, 0.05, 0.012), M.dark, {parent: pedalG, pos: [0, 0.19, 0.008]});
  add('pedal', box(0.16, 0.03, 0.06), M.dark, {pos: [0, 0.1, 1.3]});
  // 平衡桿＋兩根推桿
  add('pedal', new THREE.CylinderGeometry(0.005, 0.005, 0.12, 10).rotateZ(Math.PI / 2), M.steel, {pos: [0, 0.24, 1.26]});
  const masters = {};
  for (const [key, x] of [['front', 0.045], ['rear', -0.045]]) {
    add('pedal', new THREE.CylinderGeometry(0.015, 0.015, 0.11, 20).rotateX(Math.PI / 2), M.alu, {pos: [x, 0.24, 1.17], shell: true});
    add('pedal', new THREE.CylinderGeometry(0.004, 0.004, 0.06, 8).rotateX(Math.PI / 2), M.steel, {pos: [x, 0.24, 1.24]});
    add('pedal', new THREE.CylinderGeometry(0.013, 0.013, 0.035, 18), M.reservoir, {pos: [x, 0.275, 1.17]});
    masters[key] = new V3(x, 0.24, 1.11);
  }
  // 前輪油路：前主缸 → 左右前卡鉗
  const fc = corners.filter((c) => c.axle === 'f');
  const rc = corners.filter((c) => c.axle === 'r');
  for (const c of fc) {
    const to = c.caliperAt;
    add('pedal', tube([[masters.front.x, masters.front.y, masters.front.z], [c.sx * 0.12, 0.22, 1.32], [c.sx * 0.42, 0.3, 1.58], [to.x - c.sx * 0.02, to.y + 0.03, to.z]], 0.005, 40), LINE.front);
  }
  // 後輪油路：後主缸 → 電控單元 → 左右後卡鉗
  const BB = CENTRE.bbw;
  add('pedal', tube([[masters.rear.x, masters.rear.y, masters.rear.z], [-0.12, 0.13, 0.9], [-0.13, 0.12, 0.0], [-0.12, 0.14, -0.7], [BB[0], BB[1] - 0.02, BB[2] + 0.06]], 0.005, 60), LINE.rearM);
  for (const c of rc) {
    const to = c.caliperAt;
    add('bbw', tube([[BB[0], BB[1], BB[2] - 0.06], [c.sx * 0.2, 0.3, -1.3], [c.sx * 0.45, 0.4, -1.55], [to.x - c.sx * 0.02, to.y + 0.03, to.z]], 0.005, 40), LINE.rearC);
  }

  // ------------------------------------------------------------ 後輪電控單元（位置示意）
  add('bbw', box(0.12, 0.075, 0.11), M.dark, {pos: BB, shell: true});
  add('bbw', box(0.07, 0.03, 0.06), M.alu, {pos: [BB[0], BB[1] + 0.052, BB[2]]});
  const bbwLed = new THREE.MeshStandardMaterial({color: '#2b2d31', emissive: new THREE.Color(COL.harvest), emissiveIntensity: 0.2});
  add('bbw', box(0.02, 0.008, 0.008), bbwLed, {pos: [BB[0] + 0.04, BB[1] + 0.02, BB[2] + 0.057]});

  // ------------------------------------------------------------ 回收路徑：後輪 → 傳動軸 → 變速箱 → MGU-K → 電池（位置示意）
  const MK = [0.17, 0.2, -0.45];
  add('mguk', new THREE.CylinderGeometry(0.068, 0.068, 0.16, 36).rotateX(Math.PI / 2), M.dark, {pos: MK, shell: true});
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    add('mguk', box(0.014, 0.02, 0.13), M.copper, {pos: [MK[0] + 0.05 * Math.cos(a), MK[1] + 0.05 * Math.sin(a), MK[2]], rot: [0, 0, a]});
  }
  add('mguk', box(0.2, 0.16, 0.42), M.dark, {pos: [0, 0.25, -1.4], shell: true});
  add('mguk', box(0.27, 0.15, 0.4), M.dark, {pos: [0, 0.22, -0.55], shell: true}); // 內燃機（只是輪廓）
  for (const sx of [-1, 1]) add('mguk', tube([[sx * 0.08, 0.3, -1.62], [sx * 0.35, 0.33, -1.67], [sx * 0.6, R_WHEEL, AXLE.r]], 0.016, 16), M.steel);
  add('mguk', box(0.42, 0.11, 0.3), M.dark, {pos: [0, 0.12, 0.25], shell: true});
  const cells = new THREE.InstancedMesh(box(0.028, 0.07, 0.036), M.cell, 40);
  {
    const m4 = new THREE.Matrix4();
    let k = 0;
    for (let iz = 0; iz < 4; iz++)
      for (let ix = 0; ix < 10; ix++) {
        m4.makeTranslation(-0.17 + ix * 0.038, 0.12, 0.16 + iz * 0.06);
        cells.setMatrixAt(k++, m4);
      }
  }
  groups.mguk.add(cells);
  meshes.push({mesh: cells, comp: 'mguk', shell: false, base: M.cell});
  const cellCol = new THREE.Color();
  const CELL = {off: new THREE.Color('#3a3e45'), on: new THREE.Color('#e8e9eb'), charge: new THREE.Color(COL.harvest)};
  const harvCurves = [1, -1].map((sx) => curve([[sx * 0.6, R_WHEEL, AXLE.r], [sx * 0.3, 0.33, -1.66], [sx * 0.06, 0.3, -1.6], [0.02, 0.26, -1.2], [0.1, 0.22, -0.75], [MK[0], MK[1], MK[2] - 0.08], [MK[0], MK[1], MK[2] + 0.08], [0.12, 0.15, 0.0], [0.05, 0.13, 0.2]]));

  // ------------------------------------------------------------ 粒子：油壓（沿油管，紅）與回收（沿回收路徑，青）
  const mkFlow = (crv, n, color, size) => {
    const im = new THREE.InstancedMesh(new THREE.SphereGeometry(size, 10, 8), new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0, depthWrite: false}), n);
    im.frustumCulled = false;
    root.add(im);
    return {im, crv, n};
  };
  const flows = harvCurves.map((c) => mkFlow(c, 18, COL.harvest, 0.011));
  const fm = new THREE.Matrix4();
  const fp = new V3();
  const placeFlow = (f, phase, op) => {
    f.im.material.opacity = op;
    f.im.visible = op > 0.01;
    if (!f.im.visible) return;
    for (let i = 0; i < f.n; i++) {
      let u = (i / f.n + phase) % 1;
      if (u < 0) u += 1;
      f.crv.getPointAt(u, fp);
      fm.makeTranslation(fp.x, fp.y, fp.z);
      f.im.setMatrixAt(i, fm);
    }
    f.im.instanceMatrix.needsUpdate = true;
  };

  // ------------------------------------------------------------ 模式
  const CLIP = new THREE.Plane(new V3(0, 0, -1), AXLE.f);
  const xrayOf = new Map();
  const xray = (mat) => {
    if (!xrayOf.has(mat)) xrayOf.set(mat, XRAY.clone());
    return xrayOf.get(mat);
  };
  const KEEP = {fbrake: ['pedal'], rbrake: ['bbw'], bbw: ['rbrake', 'pedal'], mguk: ['rbrake'], pedal: []};
  const glow = new THREE.Color();

  /**
   * o：s（kin 的一格，含 Tf、Tr、pFM、pRM、pRC、Fk、Fr、pedal）、wheel（車輪轉角）、ph（回收粒子相位）
   *    view、explodeK、focus、focusK
   */
  const update = (o) => {
    const s = o.s;
    const ek = o.explodeK ?? 0;
    for (const c of corners) c.spin.rotation.x = -o.wheel * D2R;
    pedalG.rotation.x = -0.32 * s.pedal;
    // 碟盤溫度 → 發光
    for (const c of corners) {
      const k = heatGlow(c.axle === 'f' ? s.Tf : s.Tr, glow);
      c.discMat.emissive.copy(glow);
      c.discMat.emissiveIntensity = k;
    }
    // 油管依壓力發紅
    LINE.front.emissiveIntensity = 0.9 * s.pFM;
    LINE.rearM.emissiveIntensity = 0.9 * s.pRM;
    LINE.rearC.emissiveIntensity = 0.9 * s.pRC;
    // 來令片夾緊（只是看得出來）
    for (const c of corners) {
      const p = c.axle === 'f' ? s.pFM : s.pRC;
      const dT = DISC[c.axle].t / 1000;
      c.pads.forEach((pad, i) => (pad.position.x = (i ? 1 : -1) * (dT / 2 + 0.006 - 0.0025 * p)));
    }
    bbwLed.emissiveIntensity = 0.2 + 1.4 * (s.Fr > 0 ? s.Fk / s.Fr : 0);
    // 電池跟著電量亮起
    const lit = Math.round((s.soc / 4) * 40);
    for (let i = 0; i < 40; i++) {
      cellCol.copy(i < lit ? CELL.on : CELL.off);
      if (i < lit && i >= lit - 10 && s.Fk > 0) cellCol.lerp(CELL.charge, 0.6);
      cells.setColorAt(i, cellCol);
    }
    cells.instanceColor.needsUpdate = true;

    // 爆炸圖：各組往外移；輪角另外拆開：輪胎往外、卡鉗往上、碟盤往外一點
    for (const [key, g] of Object.entries(groups)) {
      const v = EXPLODE[key];
      g.position.set(v[0] * ek, v[1] * ek, v[2] * ek);
    }
    for (const c of corners) {
      c.wheelG.position.x = c.sx * (0.8 + 0.5 * ek);
      c.discG.position.x = c.sx * (DISC_X + 0.18 * ek);
      c.calG.position.y = (DISC[c.axle].d / 2000 - 0.022) * Math.sin(c.axle === 'f' ? 125 * D2R : 55 * D2R) + 0.22 * ek;
    }

    // 材質
    const fk = o.focusK ?? 0;
    const view = o.view || 'solid';
    const xOn = view === 'xray';
    const cutOn = view === 'section';
    const solo = o.focus && o.focus !== 'all' && fk > 0.5;
    // 剖開：切過聚焦的那個車軸（後輪聚焦切後軸，從車尾看；其他切前軸，從車頭看）
    const rearCut = o.focus === 'rbrake' || o.focus === 'bbw' || o.focus === 'mguk';
    CLIP.normal.set(0, 0, rearCut ? 1 : -1);
    CLIP.constant = rearCut ? -AXLE.r : AXLE.f;
    for (const it of meshes) {
      const other = o.focus && o.focus !== 'all' && it.comp !== o.focus && it.comp !== 'body';
      let mat = it.base;
      if (it.shell && xOn) mat = xray(it.base);
      if (other && solo && !(KEEP[o.focus] || []).includes(it.comp)) mat = GHOST;
      // 輪胎是背景：聚焦單一零件時退成淡影，不擋住碟盤；X 光與剖開時整個藏起來
      if (it.tag === 'tire') {
        it.mesh.visible = !xOn && !cutOn;
        if (solo) mat = GHOST;
      }
      it.mesh.material = mat;
      if (it.mesh.userData.edge) it.mesh.userData.edge.visible = xOn && mat !== GHOST;
      if (mat !== GHOST && mat !== M.shell) mat.clippingPlanes = cutOn ? [CLIP] : null;
    }
    EDGE.opacity = xOn ? 0.5 : 0;
    // 回收粒子
    const kOp = s.Fk > 1 ? Math.min(1, 0.25 + s.Fk / 6000) : 0;
    const show = ek < 0.15 && !(solo && !['mguk', 'bbw', 'rbrake'].includes(o.focus));
    for (let i = 0; i < flows.length; i++) placeFlow(flows[i], (o.ph ?? 0) + i * 0.03, show ? kOp : 0);
  };
  const hidden = [];
  const aoHide = (on) => {
    if (on) {
      for (const it of meshes) if (it.mesh.visible && it.mesh.material.transparent) {
        it.mesh.visible = false;
        hidden.push(it.mesh);
      }
    } else {
      for (const m of hidden) m.visible = true;
      hidden.length = 0;
    }
  };
  const centreOf = (key, ek = 0) => {
    const c = CENTRE[key];
    const v = EXPLODE[key] || [0, 0, 0];
    return [c[0] + v[0] * ek, c[1] + v[1] * ek, c[2] + v[2] * ek];
  };
  return {root, update, M, CLIP, centreOf, groups, aoHide, corners};
}
