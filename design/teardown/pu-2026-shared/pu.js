// 2026 F1 動力單元的幾何：全部用程式長出來，不載入任何模型檔。
// 這是「依公開資料重繪的示意模型」：通用造型、零塗裝、零標誌；比例與零件位置是示意，各廠實際布置不同。
// 座標：公尺；y 朝上、z 朝車頭（+z）、x 朝車子左側（+x）。曲軸沿 z 軸，位在原點。
//
// 零件分組（對應規章的六類受管制元件，外加傳動與能量流）：
//   ice  內燃機（V6 缸體、缸頭、活塞、連桿、曲軸、進氣室）
//   tc   渦輪增壓器（壓縮機＋渦輪，同軸）
//   exh  排氣（左右排集氣管、尾管）
//   mguk 電動馬達 MGU-K（定子、轉子、與曲軸相接的齒輪組）
//   es   電池組 ES（電芯陣列）
//   pce  動力單元控制電子 PU-CE
//   drive 傳動與後輪（不屬於動力單元，只為了看出「推動後輪」）
import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import {BANK, bankXY, CYL, ICE, piston, pinXY} from './kin.js';

const V3 = THREE.Vector3;
const D2R = Math.PI / 180;
export const COMPS = ['ice', 'tc', 'exh', 'mguk', 'es', 'pce'];
export const COL = {deploy: '#d63a2f', harvest: '#2f8a9c', fuel: '#c8971f', exh: '#8f8a84', ink: '#241a1c'};

// 爆炸圖時各組往外移的方向（公尺，k＝1 時的位移）
const EXPLODE = {
  ice: [0, 0, 0],
  tc: [0, 0.3, -0.06],
  exh: [0, -0.04, -0.06],
  mguk: [0.4, -0.04, 0.16],
  es: [0, -0.16, 0.4],
  pce: [0, 0.28, 0.42],
  drive: [0, 0, -0.5],
};
// 各組的中心（相機對焦、標籤指線、剖開平面都用這個）
export const CENTRE = {
  all: [0, 0.06, -0.05],
  ice: [0, 0.1, 0],
  tc: [0, 0.24, -0.38],
  exh: [0, 0.08, -0.2],
  mguk: [0.2, -0.04, 0.33],
  es: [0, -0.08, 0.62],
  pce: [0, 0.035, 0.6],
  drive: [0, 0, -0.75],
};

// ------------------------------------------------------------ 幾何小工具
function gearGeo(teeth, rOut, rRoot, width, holeR = 0) {
  const s = new THREE.Shape();
  const n = teeth * 4;
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    const q = i % 4;
    const r = q === 1 || q === 2 ? rOut : rRoot;
    const x = r * Math.cos(a);
    const y = r * Math.sin(a);
    if (i === 0) s.moveTo(x, y);
    else s.lineTo(x, y);
  }
  if (holeR > 0) {
    const h = new THREE.Path();
    h.absarc(0, 0, holeR, 0, Math.PI * 2, true);
    s.holes.push(h);
  }
  const g = new THREE.ExtrudeGeometry(s, {depth: width, bevelEnabled: false, curveSegments: 4});
  g.translate(0, 0, -width / 2);
  return g;
}
const tube = (pts, r, seg = 64, closed = false) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map((p) => new V3(...p)), closed, 'catmullrom', 0.5), seg, r, 12, false);
const curve = (pts) => new THREE.CatmullRomCurve3(pts.map((p) => new V3(...p)), false, 'catmullrom', 0.5);
// 葉輪：輪轂＋扭轉的葉片（沿 x 軸）
function wheelGeo(r, len, blades, twist) {
  const parts = [new THREE.CylinderGeometry(r * 0.32, r * 0.55, len, 24).rotateZ(Math.PI / 2)];
  for (let i = 0; i < blades; i++) {
    const b = new THREE.BoxGeometry(len * 0.9, r * 0.62, 0.0035);
    b.translate(0, r * 0.62, 0);
    b.rotateX((i / blades) * Math.PI * 2);
    b.rotateX(0);
    const m = new THREE.Matrix4().makeRotationAxis(new V3(0, Math.cos((i / blades) * Math.PI * 2), Math.sin((i / blades) * Math.PI * 2)), twist);
    b.applyMatrix4(m);
    parts.push(b);
  }
  return mergeGeometries(parts.map((g) => g.toNonIndexed()));
}

export function buildPU() {
  const root = new THREE.Group();
  const M = {
    carbon: new THREE.MeshPhysicalMaterial({color: '#1c1e22', roughness: 0.42, metalness: 0.15, clearcoat: 0.55, clearcoatRoughness: 0.25}),
    head: new THREE.MeshPhysicalMaterial({color: '#2a2c31', roughness: 0.5, metalness: 0.3, clearcoat: 0.3}),
    alu: new THREE.MeshStandardMaterial({color: '#c9ccd1', roughness: 0.36, metalness: 0.85}),
    steel: new THREE.MeshStandardMaterial({color: '#d0d3d7', roughness: 0.28, metalness: 1}),
    exh: new THREE.MeshStandardMaterial({color: '#a39a90', roughness: 0.42, metalness: 0.85}),
    copper: new THREE.MeshStandardMaterial({color: '#b6743c', roughness: 0.38, metalness: 0.9}),
    cell: new THREE.MeshStandardMaterial({color: '#ffffff', roughness: 0.5, metalness: 0.1}),
    hv: new THREE.MeshStandardMaterial({color: '#d9742f', roughness: 0.55, metalness: 0.05}),
    line: new THREE.MeshStandardMaterial({color: '#6a6f77', roughness: 0.4, metalness: 0.6}),
    // 後輪只是背景脈絡（看得出「推動後輪」即可），固定半透明
    tire: new THREE.MeshStandardMaterial({color: '#2a2b2e', roughness: 0.85, metalness: 0, transparent: true, opacity: 0.2, depthWrite: false}),
    rim: new THREE.MeshStandardMaterial({color: '#7d8289', roughness: 0.35, metalness: 0.8, transparent: true, opacity: 0.28, depthWrite: false}),
    glass: new THREE.MeshPhysicalMaterial({color: '#ffffff', roughness: 0.05, metalness: 0, transparent: true, opacity: 0.14, depthWrite: false, side: THREE.DoubleSide, envMapIntensity: 1.4}),
    glow: new THREE.MeshStandardMaterial({color: '#2b2d31', roughness: 0.4, metalness: 0.4, emissive: new THREE.Color(COL.deploy), emissiveIntensity: 0}),
  };
  // X 光：外殼換成半透明，邊線浮出來
  const XRAY = new THREE.MeshPhysicalMaterial({color: '#aab3bd', roughness: 0.2, metalness: 0, transparent: true, opacity: 0.1, depthWrite: false, side: THREE.DoubleSide});
  const EDGE = new THREE.LineBasicMaterial({color: '#5a6470', transparent: true, opacity: 0.0});

  const groups = {};
  for (const k of [...COMPS, 'drive']) {
    const g = new THREE.Group();
    g.name = k;
    root.add(g);
    groups[k] = g;
  }
  const meshes = []; // {mesh, comp, shell}
  const add = (comp, geo, mat, {shell = false, pos, rot, parent} = {}) => {
    const m = new THREE.Mesh(geo, mat);
    if (pos) m.position.set(...pos);
    if (rot) m.rotation.set(...rot);
    m.castShadow = true;
    m.receiveShadow = true;
    (parent || groups[comp]).add(m);
    meshes.push({mesh: m, comp, shell, base: mat});
    if (shell) {
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), EDGE);
      e.visible = false;
      m.add(e);
      m.userData.edge = e;
    }
    return m;
  };

  // ------------------------------------------------------------ 內燃機：90 度 V6
  const ice = groups.ice;
  // 曲軸箱
  add('ice', new THREE.BoxGeometry(0.27, 0.15, 0.4), M.carbon, {shell: true, pos: [0, -0.02, 0]});
  // 兩排缸體與缸頭（沿缸軸方向的盒子）
  for (const bank of ['L', 'R']) {
    const B = BANK[bank];
    const ang = Math.atan2(B.b[1], B.b[0]) - Math.PI / 2; // 讓盒子的 y 軸對齊缸軸
    const [bx, by] = bankXY(bank, 0, 0.12);
    add('ice', new THREE.BoxGeometry(0.115, 0.13, 0.36), M.carbon, {shell: true, pos: [bx, by, 0], rot: [0, 0, ang]});
    const [hx, hy] = bankXY(bank, 0, 0.205);
    add('ice', new THREE.BoxGeometry(0.125, 0.06, 0.37), M.head, {shell: true, pos: [hx, hy, 0], rot: [0, 0, ang]});
    const [cx, cy] = bankXY(bank, -0.01, 0.25);
    add('ice', new THREE.BoxGeometry(0.09, 0.03, 0.35), M.head, {shell: true, pos: [cx, cy, 0], rot: [0, 0, ang]});
  }
  // 進氣室（在 V 字中間）
  add('ice', new THREE.BoxGeometry(0.1, 0.07, 0.3), M.carbon, {shell: true, pos: [0, 0.2, 0.01]});
  // 缸套（玻璃）、活塞、連桿
  const pist = [];
  const rods = [];
  for (const cy of CYL) {
    const B = BANK[cy.bank];
    const ang = Math.atan2(B.b[1], B.b[0]) - Math.PI / 2;
    const [lx, ly] = bankXY(cy.bank, 0, 0.125);
    add('ice', new THREE.CylinderGeometry(ICE.bore / 2 + 0.002, ICE.bore / 2 + 0.002, 0.12, 32, 1, true), M.glass, {pos: [lx, ly, cy.z], rot: [0, 0, ang]});
    const p = add('ice', new THREE.CylinderGeometry(ICE.bore / 2 - 0.001, ICE.bore / 2 - 0.001, 0.034, 32), M.alu);
    p.rotation.z = ang;
    pist.push(p);
    const r = add('ice', new THREE.BoxGeometry(0.012, 1, 0.01), M.steel);
    rods.push(r);
  }
  // 曲軸：主軸頸＋三個曲柄（配重盤＋曲柄銷）
  const crank = new THREE.Group();
  ice.add(crank);
  add('ice', new THREE.CylinderGeometry(0.017, 0.017, 0.44, 24).rotateX(Math.PI / 2), M.steel, {parent: crank});
  // 曲柄在曲軸自己的座標裡是固定的：銷在 pinXY(p, 0)，曲柄臂從軸心伸向銷，配重在反方向
  for (let p = 0; p < 3; p++) {
    const z = (1 - p) * ICE.pitch;
    const [x, y] = pinXY(p, 0);
    const rz = Math.atan2(y, x) - Math.PI / 2;
    for (const dz of [-0.026, 0.026]) {
      add('ice', new THREE.BoxGeometry(0.034, 0.05, 0.012), M.steel, {parent: crank, pos: [x * 0.45, y * 0.45, z + dz], rot: [0, 0, rz]});
      add('ice', new THREE.BoxGeometry(0.07, 0.034, 0.012), M.steel, {parent: crank, pos: [-x * 1.05, -y * 1.05, z + dz], rot: [0, 0, rz]});
    }
    add('ice', new THREE.CylinderGeometry(0.015, 0.015, 0.064, 20).rotateX(Math.PI / 2), M.steel, {parent: crank, pos: [x, y, z]});
  }

  // ------------------------------------------------------------ 渦輪增壓器（單一顆，壓縮機在 −x、渦輪在 +x，同軸沿 x）
  const TC = CENTRE.tc;
  const tcG = groups.tc;
  add('tc', new THREE.CylinderGeometry(0.068, 0.068, 0.07, 40).rotateZ(Math.PI / 2), M.alu, {shell: true, pos: [TC[0] - 0.085, TC[1], TC[2]]});
  add('tc', new THREE.TorusGeometry(0.07, 0.022, 14, 40).rotateY(Math.PI / 2), M.alu, {shell: true, pos: [TC[0] - 0.085, TC[1], TC[2]]});
  add('tc', new THREE.CylinderGeometry(0.06, 0.06, 0.065, 40).rotateZ(Math.PI / 2), M.exh, {shell: true, pos: [TC[0] + 0.085, TC[1], TC[2]]});
  add('tc', new THREE.TorusGeometry(0.062, 0.02, 14, 40).rotateY(Math.PI / 2), M.exh, {shell: true, pos: [TC[0] + 0.085, TC[1], TC[2]]});
  add('tc', new THREE.CylinderGeometry(0.03, 0.03, 0.1, 24).rotateZ(Math.PI / 2), M.head, {shell: true, pos: [TC[0], TC[1], TC[2]]});
  const tcShaft = new THREE.Group();
  tcShaft.position.set(...TC);
  tcG.add(tcShaft);
  add('tc', new THREE.CylinderGeometry(0.006, 0.006, 0.24, 12).rotateZ(Math.PI / 2), M.steel, {parent: tcShaft});
  const comp = add('tc', wheelGeo(0.055, 0.04, 11, 0.5), M.alu, {parent: tcShaft});
  comp.position.x = -0.085;
  const turb = add('tc', wheelGeo(0.05, 0.035, 11, -0.55), M.exh, {parent: tcShaft});
  turb.position.x = 0.085;
  // 壓縮機出口到進氣室
  const intakeCurve = [[TC[0] - 0.085, TC[1] + 0.07, TC[2] + 0.02], [-0.05, 0.3, -0.25], [0, 0.235, -0.15]];
  add('tc', tube(intakeCurve, 0.028), M.alu, {shell: true});

  // ------------------------------------------------------------ 排氣：每排三缸的集氣管匯進渦輪，再從尾管出去
  const exhCurves = [];
  for (const bank of ['L', 'R']) {
    const sgn = bank === 'L' ? 1 : -1;
    const collector = [sgn * 0.27, 0.06, -0.24];
    const [px0, py0] = bankXY(bank, 0.07, 0.205);
    for (const cy of CYL.filter((c) => c.bank === bank)) {
      const pts = [[px0, py0, cy.z], [px0 + sgn * 0.05, py0 - 0.04, cy.z], [sgn * 0.27, 0.07, cy.z * 0.6 - 0.1], collector];
      add('exh', tube(pts, 0.012, 48), M.exh);
    }
    // 渦輪入口在渦輪殼下方；右排（−x）從壓縮機殼底下穿過去
    const inlet = [TC[0] + 0.085, TC[1] - 0.085, TC[2]];
    const toTurb = bank === 'L' ? [collector, [0.2, 0.1, -0.33], inlet] : [collector, [-0.2, 0.11, -0.33], [-0.02, 0.13, -0.45], inlet];
    add('exh', tube(toTurb, 0.02, 48), M.exh);
    exhCurves.push(curve([[px0, py0, 0], [sgn * 0.27, 0.07, -0.1], ...toTurb]));
  }
  const tail = [[TC[0] + 0.12, TC[1] + 0.02, TC[2]], [0.13, 0.27, -0.55], [0.06, 0.29, -0.82], [0.03, 0.3, -1.0]];
  add('exh', tube(tail, 0.03, 48), M.exh);
  const tailCurve = curve(tail);

  // ------------------------------------------------------------ MGU-K：曲軸前端經齒輪組帶動的電動馬達
  const MK = CENTRE.mguk;
  const mk = groups.mguk;
  const GZ = 0.225; // 齒輪組所在的平面（曲軸前端）
  add('mguk', new THREE.CylinderGeometry(0.068, 0.068, 0.16, 40, 1, true).rotateX(Math.PI / 2), M.carbon, {shell: true, pos: MK});
  add('mguk', new THREE.CylinderGeometry(0.07, 0.07, 0.012, 40).rotateX(Math.PI / 2), M.head, {shell: true, pos: [MK[0], MK[1], MK[2] - 0.085]});
  add('mguk', new THREE.CylinderGeometry(0.07, 0.07, 0.012, 40).rotateX(Math.PI / 2), M.head, {shell: true, pos: [MK[0], MK[1], MK[2] + 0.085]});
  // 定子線圈（12 組）
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    add('mguk', new THREE.BoxGeometry(0.016, 0.022, 0.13), M.copper, {pos: [MK[0] + 0.05 * Math.cos(a), MK[1] + 0.05 * Math.sin(a), MK[2]], rot: [0, 0, a]});
  }
  const rotor = new THREE.Group();
  rotor.position.set(...MK);
  mk.add(rotor);
  const rotorCore = add('mguk', new THREE.CylinderGeometry(0.034, 0.034, 0.13, 32).rotateX(Math.PI / 2), M.glow, {parent: rotor});
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    add('mguk', new THREE.BoxGeometry(0.012, 0.004, 0.13), M.steel, {parent: rotor, pos: [0.034 * Math.cos(a), 0.034 * Math.sin(a), 0], rot: [0, 0, a]});
  }
  // 轉子軸往後伸到齒輪平面
  add('mguk', new THREE.CylinderGeometry(0.008, 0.008, 0.24, 12).rotateX(Math.PI / 2), M.steel, {parent: rotor, pos: [0, 0, GZ - MK[2] + 0.1]});
  // 齒輪組：曲軸齒輪 → 惰輪 → MGU-K 小齒輪（齒輪平面在 z＝GZ）
  const r0 = 0.055;
  const r2 = 0.032;
  const r1 = 0.06;
  const C2 = [MK[0], MK[1]];
  const d = Math.hypot(...C2);
  const a1 = r0 + r1;
  const a2 = r1 + r2;
  const aa = (a1 * a1 - a2 * a2 + d * d) / (2 * d);
  const hh = Math.sqrt(Math.max(0, a1 * a1 - aa * aa));
  const ux = C2[0] / d;
  const uy = C2[1] / d;
  const C1 = [aa * ux - hh * uy, aa * uy + hh * ux];
  const gears = [
    {r: r0, c: [0, 0], teeth: 34},
    {r: r1, c: C1, teeth: 37},
    {r: r2, c: C2, teeth: 20},
  ].map((g) => {
    const m = add('mguk', gearGeo(g.teeth, g.r + 0.004, g.r - 0.003, 0.018, 0.008), M.steel, {pos: [g.c[0], g.c[1], GZ]});
    return {...g, m};
  });
  const gearRatio = r0 / r2; // MGU-K 轉速 ÷ 曲軸轉速（示意）

  // ------------------------------------------------------------ 電池組 ES：電芯陣列
  const ES = CENTRE.es;
  add('es', new THREE.BoxGeometry(0.48, 0.13, 0.32), M.carbon, {shell: true, pos: ES});
  const NX = 12;
  const NZ = 6;
  const cells = new THREE.InstancedMesh(new THREE.BoxGeometry(0.03, 0.09, 0.04), M.cell, NX * NZ);
  cells.castShadow = true;
  {
    const m4 = new THREE.Matrix4();
    let k = 0;
    for (let iz = 0; iz < NZ; iz++)
      for (let ix = 0; ix < NX; ix++) {
        m4.makeTranslation(ES[0] - 0.2 + ix * (0.4 / (NX - 1)), ES[1], ES[2] - 0.115 + iz * (0.23 / (NZ - 1)));
        cells.setMatrixAt(k++, m4);
      }
    cells.instanceMatrix.needsUpdate = true;
  }
  groups.es.add(cells);
  meshes.push({mesh: cells, comp: 'es', shell: false, base: M.cell});
  const cellCol = new THREE.Color();
  const CELL = {off: new THREE.Color('#3a3e45'), on: new THREE.Color('#e8e9eb'), charge: new THREE.Color(COL.harvest), draw: new THREE.Color(COL.deploy)};

  // ------------------------------------------------------------ PU-CE：控制電子（放在電池上方，散熱鰭片朝上）
  const PC = CENTRE.pce;
  add('pce', new THREE.BoxGeometry(0.26, 0.05, 0.17), M.head, {shell: true, pos: [PC[0], PC[1], PC[2]]});
  for (let i = 0; i < 9; i++) add('pce', new THREE.BoxGeometry(0.004, 0.024, 0.15), M.alu, {pos: [PC[0] - 0.1 + i * 0.025, PC[1] + 0.037, PC[2]]});
  // 指示燈：聚焦別的零件時 mesh 會換成淡影材質，所以發光色改在自己留住的材質上
  const ledMat = M.glow.clone();
  add('pce', new THREE.BoxGeometry(0.02, 0.008, 0.008), ledMat, {pos: [PC[0] + 0.1, PC[1] + 0.01, PC[2] + 0.087]});
  // 高壓線（電池 → 控制電子 → MGU-K）
  const hvPts = [[PC[0] + 0.12, PC[1] - 0.01, PC[2] - 0.085], [0.19, 0.0, 0.47], [MK[0], MK[1], MK[2] + 0.09]];
  const hvTube = add('pce', tube(hvPts, 0.009, 48), M.hv);
  const hvCurve = curve([[ES[0] + 0.15, ES[1] + 0.06, ES[2] - 0.1], [PC[0] + 0.1, PC[1], PC[2] - 0.05], ...hvPts]);
  // 燃料管：從車頭方向（油箱在電池上方，未畫出）接到進氣室
  const fuelPts = [[-0.1, 0.16, 0.92], [-0.1, 0.14, 0.72], [-0.06, 0.2, 0.36], [0, 0.235, 0.165]];
  const fuelTube = add('ice', tube(fuelPts, 0.007, 48), M.line);
  const fuelCurve = curve(fuelPts);

  // ------------------------------------------------------------ 傳動與後輪（示意，不屬於動力單元）
  const dr = groups.drive;
  add('drive', new THREE.CylinderGeometry(0.085, 0.1, 0.26, 32).rotateX(Math.PI / 2), M.carbon, {shell: true, pos: [0, -0.01, -0.33]});
  add('drive', new THREE.BoxGeometry(0.2, 0.16, 0.42), M.carbon, {shell: true, pos: [0, -0.01, -0.67]});
  const axle = new THREE.Group();
  axle.position.set(0, -0.01, -0.8);
  dr.add(axle);
  add('drive', new THREE.CylinderGeometry(0.018, 0.018, 1.1, 16).rotateZ(Math.PI / 2), M.steel, {parent: axle});
  const wheels = [];
  for (const sx of [-1, 1]) {
    const w = new THREE.Group();
    w.position.set(sx * 0.64, 0, 0);
    axle.add(w);
    const tireM = add('drive', new THREE.CylinderGeometry(0.33, 0.33, 0.3, 48).rotateZ(Math.PI / 2), M.tire, {parent: w});
    const rimM = add('drive', new THREE.CylinderGeometry(0.22, 0.22, 0.305, 40).rotateZ(Math.PI / 2), M.rim, {parent: w});
    // 輪輻：轉起來才看得出輪子在動
    for (let i = 0; i < 5; i++) add('drive', new THREE.BoxGeometry(0.31, 0.03, 0.18), M.rim, {parent: w, rot: [(i / 5) * Math.PI, 0, 0]});
    for (const m of [tireM, rimM, ...w.children]) m.castShadow = false;
    wheels.push(w);
  }

  // ------------------------------------------------------------ 能量流的粒子
  const flows = {};
  const mkFlow = (key, crv, n, color, size) => {
    const im = new THREE.InstancedMesh(new THREE.SphereGeometry(size, 10, 8), new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0, depthWrite: false}), n);
    im.frustumCulled = false;
    root.add(im);
    flows[key] = {im, crv, n, mat: im.material};
  };
  mkFlow('fuel', fuelCurve, 16, COL.fuel, 0.008);
  mkFlow('elec', hvCurve, 22, COL.deploy, 0.011);
  mkFlow('exhL', exhCurves[0], 10, COL.exh, 0.007);
  mkFlow('exhR', exhCurves[1], 10, COL.exh, 0.007);
  mkFlow('tail', tailCurve, 10, COL.exh, 0.009);
  const fm = new THREE.Matrix4();
  const fp = new V3();
  const placeFlow = (f, phase, op, color) => {
    f.mat.opacity = op;
    f.im.visible = op > 0.01;
    if (color) f.mat.color.set(color);
    for (let i = 0; i < f.n; i++) {
      let u = (i / f.n + phase) % 1;
      if (u < 0) u += 1;
      f.crv.getPointAt(u, fp);
      fm.makeTranslation(fp.x, fp.y, fp.z);
      f.im.setMatrixAt(i, fm);
    }
    f.im.instanceMatrix.needsUpdate = true;
  };

  // ------------------------------------------------------------ 模式：實體／X 光／剖開／爆炸圖，與聚焦單一零件
  const CLIP = new THREE.Plane(new V3(-1, 0, 0), 0);
  // 淡影用不吃環境反光的單色材質：物理材質的反光不會跟著 opacity 變淡，疊多了會變成一片白霧
  const GHOST = new THREE.MeshBasicMaterial({color: '#8a8183', transparent: true, opacity: 0.04, depthWrite: false});
  const ghostOf = new Map([[null, GHOST]]);
  const ghost = () => GHOST;
  const xrayOf = new Map();
  const xray = (mat) => {
    if (!xrayOf.has(mat)) {
      const g = XRAY.clone();
      xrayOf.set(mat, g);
    }
    return xrayOf.get(mat);
  };

  /**
   * 一格畫面的姿態。o：
   *   th（曲軸角，度）、turbo（渦輪轉角，度）、wheel（後輪轉角，度）
   *   s（kin.stateAt 的結果）、ph（{fuel, exh, elec} 粒子相位，圈）
   *   view（'solid'|'xray'|'section'|'explode'）、viewK（0..1，切換時的漸變）、explodeK（0..1）
   *   focus（'all' 或零件 key）、focusK（0..1）、flows（0..1，能量流顯示）
   */
  const update = (o) => {
    const th = o.th;
    // 活塞與連桿
    CYL.forEach((cy, i) => {
      const B = BANK[cy.bank];
      const {s, P} = piston(i, th);
      const px = s * B.b[0];
      const py = s * B.b[1];
      pist[i].position.set(px, py, cy.z);
      const r = rods[i];
      const mx = (px + P[0]) / 2;
      const my = (py + P[1]) / 2;
      r.position.set(mx, my, cy.z);
      r.scale.y = Math.hypot(px - P[0], py - P[1]);
      r.rotation.z = Math.atan2(py - P[1], px - P[0]) - Math.PI / 2;
    });
    // 曲軸：整體轉 th（pinXY 的角度順時針、從 +z 看），所以繞 z 轉 −th
    crank.rotation.z = -th * D2R;
    // 齒輪：曲軸齒輪、惰輪反轉、小齒輪
    gears[0].m.rotation.z = -th * D2R;
    gears[1].m.rotation.z = th * D2R * (r0 / r1);
    gears[2].m.rotation.z = -th * D2R * gearRatio;
    rotor.rotation.z = -th * D2R * gearRatio;
    tcShaft.rotation.x = o.turbo * D2R;
    for (const w of wheels) w.rotation.x = -o.wheel * D2R;

    // MGU-K 與電池的狀態色
    const s = o.s;
    const k = Math.abs(s.kw) / 350;
    M.glow.emissive.set(s.kw >= 0 ? COL.deploy : COL.harvest);
    M.glow.emissiveIntensity = 0.85 * k;
    ledMat.emissive.set(s.kw >= 0 ? COL.deploy : COL.harvest);
    ledMat.emissiveIntensity = 0.3 + 0.7 * k;
    const lit = Math.round((s.soc / 4) * NX * NZ);
    for (let i = 0; i < NX * NZ; i++) {
      const on = i < lit;
      cellCol.copy(on ? CELL.on : CELL.off);
      // 最上緣那一排跟著充放電變色
      if (on && i >= lit - NX) cellCol.lerp(s.kw > 0 ? CELL.draw : s.kw < 0 ? CELL.charge : CELL.on, 0.65 * Math.min(1, k * 1.3));
      cells.setColorAt(i, cellCol);
    }
    cells.instanceColor.needsUpdate = true;

    // 爆炸圖：各組往外移
    const ek = o.explodeK ?? 0;
    for (const [key, g] of Object.entries(groups)) {
      const v = EXPLODE[key];
      g.position.set(v[0] * ek, v[1] * ek, v[2] * ek);
    }
    // 管線在爆炸時會斷開，跟著淡掉
    hvTube.visible = ek < 0.15;
    fuelTube.visible = ek < 0.15;

    // 材質：聚焦的零件保持原樣，其他變淡；X 光把外殼換掉；剖開只切外殼
    const fk = o.focusK ?? 0;
    const view = o.view || 'solid';
    const vk = o.viewK ?? 1;
    const xOn = view === 'xray' && vk > 0.5;
    const cutOn = view === 'section' && vk > 0.02;
    const fc = CENTRE[o.focus || 'all'];
    CLIP.constant = cutOn ? fc[0] + (EXPLODE[o.focus]?.[0] ?? 0) * ek : 0;
    const solo = o.focus && o.focus !== 'all' && fk > 0.5;
    groups.drive.visible = !solo;
    for (const it of meshes) {
      const other = o.focus && o.focus !== 'all' && it.comp !== o.focus;
      let mat = it.base;
      // 聚焦時，其他零件的外殼直接退成淡影，不再疊一層 X 光
      if (it.shell && xOn && !(other && solo)) mat = xray(it.base);
      if (other && solo) mat = ghost(it.base);
      it.mesh.material = mat;
      if (it.shell) {
        // 傳動不屬於動力單元，剖開時不切（切半的變速箱只剩一片薄板，看起來像刀片）
        mat.clippingPlanes = cutOn && !other && it.comp !== 'drive' ? [CLIP] : null;
        if (it.mesh.userData.edge) {
          it.mesh.userData.edge.visible = xOn && !(other && fk > 0.5);
        }
      }
    }
    EDGE.opacity = xOn ? 0.55 : 0;

    // 能量流
    const fl = (o.flows ?? 1) * (ek < 0.15 ? 1 : 0);
    const ph = o.ph || {fuel: 0, exh: 0, elec: 0};
    const focusFade = (key) => (solo && !key.includes(o.focus) ? 0 : 1);
    placeFlow(flows.fuel, ph.fuel, fl * (0.25 + 0.7 * s.thr) * focusFade('ice'));
    placeFlow(flows.elec, ph.elec, fl * Math.min(1, 0.1 + k * 1.1) * focusFade('mguk es pce'), s.kw >= 0 ? COL.deploy : COL.harvest);
    const ex = fl * (0.15 + 0.45 * s.thr) * focusFade('exh tc');
    placeFlow(flows.exhL, ph.exh, ex);
    placeFlow(flows.exhR, ph.exh + 0.03, ex);
    placeFlow(flows.tail, ph.exh * 1.3, ex);
  };
  const setClipNormal = (n) => CLIP.normal.copy(n);
  /** 爆炸後某組中心的世界座標（標籤用） */
  const centreOf = (key, ek = 0) => {
    const c = CENTRE[key];
    const v = EXPLODE[key] || [0, 0, 0];
    return [c[0] + v[0] * ek, c[1] + v[1] * ek, c[2] + v[2] * ek];
  };
  return {root, update, M, CLIP, setClipNormal, centreOf, groups};
}
