// 2026 F1 主動空力的幾何：全部用程式長出來，不載入任何模型檔。
// 這是「依公開資料重繪的示意模型」：通用造型、零塗裝、零標誌；比例、翼片角度與零件位置是示意，不是任何一隊的車。
// 座標：公尺；y 朝上（地面 y＝0）、z 朝車頭（+z）、x 朝車子左側（+x）。
//
// 零件分組：
//   fw   前翼：主翼片（固定）＋兩片會動的元件、端板
//   rw   後翼：主翼片（固定）＋會動的襟翼、端板、下方的小翼
//   act  致動器與位置感測器（前翼兩個、後翼一個）、實體擋塊
//   ecu  FIA 標準 ECU（位置示意）與通往致動器的訊號線
//   body 車身與車輪（不會動的背景脈絡）
import * as THREE from 'three';
import {ease} from './kin.js';

const V3 = THREE.Vector3;
const D2R = Math.PI / 180;
export const PARTS3D = ['fw', 'rw', 'act', 'ecu'];
export const COL = {full: '#d63a2f', partial: '#c8971f', signal: '#2f8a9c', ink: '#241a1c', off: '#9b9092'};

// 示意角度（度）：規章只寫 Straight Mode「攻角變小」，沒有數字，畫面上也不顯示角度
const AOA = {
  fwMain: 4,
  fw1: {corner: 16, straight: 4},
  fw2: {corner: 30, straight: 12},
  rwMain: 8,
  rwFlap: {corner: 40, straight: 10},
};
// 爆炸圖時各組往外移的方向（k＝1 時的位移）
export const EXPLODE = {fw: [0, 0.32, 0.7], rw: [0, 0.55, -0.6], act: [0, 0.6, 0], ecu: [0.75, 0.55, 0], body: [0, 0, 0]};
export const CENTRE = {
  all: [0, 0.42, 0],
  fw: [0, 0.18, 2.3],
  rw: [0, 0.9, -2.34],
  act: [0, 0.3, 2.22],
  ecu: [0.33, 0.3, 0.25],
  body: [0, 0.4, 0],
};

// ------------------------------------------------------------ 幾何小工具
/** 倒裝翼型：弦長 c、厚度比 t、弧度 m（向下拱，吸力面朝下）。前緣在原點，往 −z 延伸，沿 x 方向寬 span */
function wingGeo(c, t, m, span) {
  const N = 28;
  const up = [];
  const lo = [];
  for (let i = 0; i <= N; i++) {
    const u = (1 - Math.cos((Math.PI * i) / N)) / 2;
    const yt = 5 * t * (0.2969 * Math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4);
    const yc = -m * 4 * u * (1 - u);
    up.push([u * c, (yc + yt) * c]);
    lo.push([u * c, (yc - yt) * c]);
  }
  const s = new THREE.Shape();
  s.moveTo(up[0][0], up[0][1]);
  for (const p of up.slice(1)) s.lineTo(p[0], p[1]);
  for (const p of lo.reverse().slice(1)) s.lineTo(p[0], p[1]);
  const g = new THREE.ExtrudeGeometry(s, {depth: span, bevelEnabled: false, curveSegments: 4});
  // 擠出方向是 local z：轉到 x，弦長方向轉到 −z
  g.rotateY(Math.PI / 2);
  g.translate(-span / 2, 0, 0);
  g.computeVertexNormals();
  return g;
}
/** 沿 z 放樣的超橢圓斷面：sec＝[z, 半寬, 底, 頂]，n＝方圓程度（2＝橢圓，越大越方） */
export function loft(sec, n = 3, seg = 40, cx = 0) {
  const pos = [];
  const idx = [];
  const ring = (z, w, yb, yt) => {
    const yc = (yb + yt) / 2;
    const h = (yt - yb) / 2;
    for (let i = 0; i < seg; i++) {
      const a = (i / seg) * Math.PI * 2;
      const c = Math.cos(a);
      const s = Math.sin(a);
      pos.push(cx + w * Math.sign(c) * Math.abs(c) ** (2 / n), yc + h * Math.sign(s) * Math.abs(s) ** (2 / n), z);
    }
  };
  for (const [z, w, yb, yt] of sec) ring(z, w, yb, yt);
  for (let r = 0; r < sec.length - 1; r++)
    for (let i = 0; i < seg; i++) {
      const a = r * seg + i;
      const b = r * seg + ((i + 1) % seg);
      const c2 = a + seg;
      const d = b + seg;
      idx.push(a, c2, b, b, c2, d);
    }
  // 兩端封口
  for (const [r, flip] of [[0, false], [sec.length - 1, true]]) {
    const [z, , yb, yt] = sec[r];
    const ci = pos.length / 3;
    pos.push(cx, (yb + yt) / 2, z);
    for (let i = 0; i < seg; i++) {
      const a = r * seg + i;
      const b = r * seg + ((i + 1) % seg);
      if (flip) idx.push(ci, b, a);
      else idx.push(ci, a, b);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}
export const tube = (pts, r, seg = 48) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map((p) => new V3(...p)), false, 'catmullrom', 0.5), seg, r, 10, false);
export const curve = (pts) => new THREE.CatmullRomCurve3(pts.map((p) => new V3(...p)), false, 'catmullrom', 0.5);
const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
/** 端板：在 y-z 平面上的圓角薄板 */
function plateGeo(z0, z1, y0, y1, th = 0.012) {
  const s = new THREE.Shape();
  const r = 0.03;
  s.moveTo(z0 + r, y0);
  s.lineTo(z1 - r, y0);
  s.quadraticCurveTo(z1, y0, z1, y0 + r);
  s.lineTo(z1, y1 - r);
  s.quadraticCurveTo(z1, y1, z1 - r, y1);
  s.lineTo(z0 + r, y1);
  s.quadraticCurveTo(z0, y1, z0, y1 - r);
  s.lineTo(z0, y0 + r);
  s.quadraticCurveTo(z0, y0, z0 + r, y0);
  const g = new THREE.ExtrudeGeometry(s, {depth: th, bevelEnabled: false});
  // shape 的 x 是 z、y 是 y；擠出 local z → x
  g.rotateY(-Math.PI / 2);
  g.translate(th / 2, 0, 0);
  return g;
}

export function buildCar() {
  const root = new THREE.Group();
  const M = {
    body: new THREE.MeshPhysicalMaterial({color: '#1e2024', roughness: 0.45, metalness: 0.12, clearcoat: 0.6, clearcoatRoughness: 0.28, side: THREE.DoubleSide}),
    wing: new THREE.MeshPhysicalMaterial({color: '#25282d', roughness: 0.4, metalness: 0.12, clearcoat: 0.5, clearcoatRoughness: 0.25, side: THREE.DoubleSide}),
    plate: new THREE.MeshPhysicalMaterial({color: '#2c2f35', roughness: 0.5, metalness: 0.1, clearcoat: 0.3, side: THREE.DoubleSide}),
    floor: new THREE.MeshStandardMaterial({color: '#2a2b2f', roughness: 0.7, metalness: 0.05}),
    alu: new THREE.MeshStandardMaterial({color: '#c9ccd1', roughness: 0.34, metalness: 0.85}),
    steel: new THREE.MeshStandardMaterial({color: '#d0d3d7', roughness: 0.28, metalness: 1}),
    stop: new THREE.MeshStandardMaterial({color: '#e0b84a', roughness: 0.4, metalness: 0.6}),
    sensor: new THREE.MeshStandardMaterial({color: '#2f8a9c', roughness: 0.4, metalness: 0.3}),
    ecu: new THREE.MeshPhysicalMaterial({color: '#3a3d43', roughness: 0.45, metalness: 0.4, clearcoat: 0.3}),
    wire: new THREE.MeshStandardMaterial({color: '#7a7f88', roughness: 0.5, metalness: 0.4}),
    tire: new THREE.MeshStandardMaterial({color: '#232427', roughness: 0.88, metalness: 0}),
    rim: new THREE.MeshStandardMaterial({color: '#6f747b', roughness: 0.35, metalness: 0.8}),
    helmet: new THREE.MeshPhysicalMaterial({color: '#e9e6e4', roughness: 0.3, metalness: 0.05, clearcoat: 0.8}),
    visor: new THREE.MeshPhysicalMaterial({color: '#202226', roughness: 0.1, metalness: 0.3, clearcoat: 1}),
  };
  // 會動的元件：材質各自一份，部署時微微發紅（只是讓眼睛找得到它們，不是塗裝）
  const moveMat = () => {
    const m = M.wing.clone();
    m.emissive = new THREE.Color(COL.full);
    m.emissiveIntensity = 0;
    return m;
  };
  const XRAY = new THREE.MeshPhysicalMaterial({color: '#aab3bd', roughness: 0.2, metalness: 0, transparent: true, opacity: 0.09, depthWrite: false, side: THREE.DoubleSide});
  const EDGE = new THREE.LineBasicMaterial({color: '#5a6470', transparent: true, opacity: 0});

  const groups = {};
  for (const k of [...PARTS3D, 'body']) {
    const g = new THREE.Group();
    g.name = k;
    root.add(g);
    groups[k] = g;
  }
  const meshes = []; // {mesh, comp, shell, base, side}
  const add = (comp, geo, mat, {shell = false, pos, rot, parent, edge = 25, side = 0} = {}) => {
    const m = new THREE.Mesh(geo, mat);
    if (pos) m.position.set(...pos);
    if (rot) m.rotation.set(...rot);
    m.castShadow = true;
    m.receiveShadow = true;
    (parent || groups[comp]).add(m);
    meshes.push({mesh: m, comp, shell, base: mat, side});
    if (shell) {
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo, edge), EDGE);
      e.visible = false;
      m.add(e);
      m.userData.edge = e;
    }
    return m;
  };

  // ------------------------------------------------------------ 車身（背景脈絡）
  // 車鼻到車尾：單體殼＋引擎蓋
  add('body', loft([
    [2.42, 0.05, 0.2, 0.27],
    [2.15, 0.1, 0.16, 0.33],
    [1.7, 0.17, 0.12, 0.45],
    [1.2, 0.26, 0.08, 0.58],
    [0.6, 0.34, 0.07, 0.64],
    [0.0, 0.36, 0.07, 0.66],
    [-0.5, 0.3, 0.08, 0.66],
    [-1.1, 0.22, 0.1, 0.56],
    [-1.7, 0.14, 0.12, 0.42],
    [-2.0, 0.09, 0.14, 0.36],
  ], 3.2, 44), M.body, {shell: true, edge: 40});
  // 進氣口與引擎蓋上方的鰭
  add('body', loft([
    [0.05, 0.09, 0.6, 0.95],
    [-0.35, 0.12, 0.55, 0.93],
    [-0.9, 0.07, 0.5, 0.72],
    [-1.5, 0.02, 0.42, 0.5],
  ], 2.6, 32), M.body, {shell: true, edge: 40});
  // 側箱
  for (const sx of [-1, 1]) {
    add('body', loft([
      [0.62, 0.12, 0.1, 0.44],
      [0.25, 0.2, 0.08, 0.5],
      [-0.4, 0.17, 0.08, 0.44],
      [-1.15, 0.08, 0.1, 0.28],
      [-1.45, 0.03, 0.12, 0.2],
    ], 3.4, 36, sx * 0.47), M.body, {shell: true, edge: 40, side: sx});
  }
  // 底板
  add('body', box(1.36, 0.022, 2.7), M.floor, {shell: true, pos: [0, 0.055, -0.15]});
  // 座艙開口、車手頭盔
  add('body', new THREE.CircleGeometry(1, 40).scale(0.2, 0.38, 1).rotateX(-Math.PI / 2), M.visor, {pos: [0, 0.665, 0.32]});
  add('body', new THREE.SphereGeometry(0.115, 32, 20), M.helmet, {pos: [0, 0.76, 0.2]});
  add('body', new THREE.SphereGeometry(0.117, 32, 12, -0.9, 1.8, 1.1, 0.5), M.visor, {pos: [0, 0.76, 0.2]});
  // Halo
  {
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const a = Math.PI * (i / 24);
      pts.push([0.25 * Math.cos(a), 0.69 + 0.17 * Math.sin(a) ** 0.6, 0.16 + 0.3 * Math.sin(a)]);
    }
    add('body', tube(pts, 0.017, 60), M.body);
    add('body', tube([[0, 0.86, 0.46], [0, 0.82, 0.62], [0, 0.64, 0.74]], 0.02, 24), M.body);
  }
  // 車輪與懸吊
  const wheels = [];
  for (const [z, r, w] of [[1.7, 0.36, 0.3], [-1.7, 0.36, 0.38]]) {
    for (const sx of [-1, 1]) {
      const g = new THREE.Group();
      g.position.set(sx * 0.8, r, z);
      groups.body.add(g);
      const t = add('body', new THREE.CylinderGeometry(r, r, w, 56).rotateZ(Math.PI / 2), M.tire, {parent: g, side: sx});
      const rim = add('body', new THREE.CylinderGeometry(r * 0.62, r * 0.62, w + 0.005, 40).rotateZ(Math.PI / 2), M.rim, {parent: g, side: sx});
      const spokes = [];
      for (let i = 0; i < 5; i++) spokes.push(add('body', box(w + 0.01, 0.025, r * 1.1), M.rim, {parent: g, rot: [(i / 5) * Math.PI, 0, 0], side: sx}));
      wheels.push({g, sx, parts: [t, rim, ...spokes]});
      // 上下 A 臂（示意）
      for (const [y0, y1] of [[0.2, r - 0.08], [0.42, r + 0.1]]) {
        add('body', tube([[sx * 0.2, y0, z + 0.18], [sx * 0.66, y1, z]], 0.012, 8), M.body, {side: sx});
        add('body', tube([[sx * 0.2, y0, z - 0.18], [sx * 0.66, y1, z]], 0.012, 8), M.body, {side: sx});
      }
    }
  }

  // ------------------------------------------------------------ 前翼：主翼片固定、兩片元件會動（C3.10.10 n）
  const FW = {span: 1.36, plateX: 0.69};
  const fwMain = new THREE.Group();
  fwMain.position.set(0, 0.1, 2.56);
  fwMain.rotation.x = AOA.fwMain * D2R;
  groups.fw.add(fwMain);
  add('fw', wingGeo(0.3, 0.09, 0.07, FW.span), M.wing, {parent: fwMain});
  // 兩片會動的元件：pivot 在前緣附近（示意）
  const fwEl = [
    {pos: [0, 0.155, 2.29], c: 0.18, a: AOA.fw1},
    {pos: [0, 0.225, 2.15], c: 0.14, a: AOA.fw2},
  ].map((e) => {
    const g = new THREE.Group();
    g.position.set(...e.pos);
    groups.fw.add(g);
    const mat = moveMat();
    add('fw', wingGeo(e.c, 0.1, 0.06, FW.span - 0.02), mat, {parent: g});
    return {...e, g, mat};
  });
  for (const sx of [-1, 1]) add('fw', plateGeo(2.0, 2.62, 0.035, 0.34), M.plate, {pos: [sx * FW.plateX, 0, 0], side: sx});
  // 車鼻下方的前翼支架
  for (const sx of [-1, 1]) add('fw', box(0.012, 0.12, 0.22), M.plate, {pos: [sx * 0.07, 0.17, 2.45]});

  // ------------------------------------------------------------ 後翼：主翼片固定、襟翼會動（C3.11.6 c）
  const RW = {span: 0.94, plateX: 0.475};
  const rwMain = new THREE.Group();
  rwMain.position.set(0, 0.84, -2.16);
  rwMain.rotation.x = AOA.rwMain * D2R;
  groups.rw.add(rwMain);
  add('rw', wingGeo(0.24, 0.11, 0.06, RW.span), M.wing, {parent: rwMain});
  const rwFlap = new THREE.Group();
  rwFlap.position.set(0, 0.905, -2.37);
  groups.rw.add(rwFlap);
  const rwFlapMat = moveMat();
  add('rw', wingGeo(0.2, 0.1, 0.05, RW.span - 0.02), rwFlapMat, {parent: rwFlap});
  for (const sx of [-1, 1]) add('rw', plateGeo(-2.66, -2.06, 0.36, 1.06), M.plate, {pos: [sx * RW.plateX, 0, 0], side: sx});
  // 下方的小翼（固定）
  const beam = new THREE.Group();
  beam.position.set(0, 0.42, -2.2);
  beam.rotation.x = 10 * D2R;
  groups.rw.add(beam);
  add('rw', wingGeo(0.14, 0.12, 0.04, RW.span - 0.04), M.wing, {parent: beam});
  // 中央支架：從變速箱上方伸到主翼片
  add('rw', tube([[0, 0.34, -1.92], [0, 0.6, -2.08], [0, 0.82, -2.2]], 0.022, 20), M.plate);

  // ------------------------------------------------------------ 致動器、位置感測器、實體擋塊（C3.10.10；C3.11.6）
  // 前翼最多兩個致動器（這裡畫兩個，左右各一，示意位置在車鼻底下）；後翼單一致動器在中央支架頂端
  const acts = [];
  const ACT_LEN = 0.08;
  const mkAct = (base, wing, rodTo) => {
    add('act', new THREE.CylinderGeometry(0.018, 0.018, ACT_LEN, 18), M.alu, {pos: base});
    add('act', box(0.03, 0.022, 0.03), M.sensor, {pos: [base[0] + 0.03, base[1] + 0.01, base[2]]});
    const rod = add('act', new THREE.CylinderGeometry(0.006, 0.006, 1, 10), M.steel);
    acts.push({rod, foot: new V3(base[0], base[1] - ACT_LEN / 2, base[2]), wing, rodTo});
  };
  mkAct([0.14, 0.37, 2.1], 'fw', (k) => elPoint(1, 0.14, k));
  mkAct([-0.14, 0.37, 2.1], 'fw', (k) => elPoint(1, -0.14, k));
  mkAct([0, 1.07, -2.44], 'rw', (k) => flapPoint(k));
  // 實體擋塊：兩個位置的極限（畫在端板內側）
  for (const sx of [-1, 1]) {
    add('act', box(0.02, 0.022, 0.022), M.stop, {pos: [sx * (RW.plateX - 0.02), 0.985, -2.53]});
    add('act', box(0.02, 0.022, 0.022), M.stop, {pos: [sx * (RW.plateX - 0.02), 0.875, -2.57]});
    add('act', box(0.02, 0.02, 0.02), M.stop, {pos: [sx * (FW.plateX - 0.02), 0.29, 2.04]});
    add('act', box(0.02, 0.02, 0.02), M.stop, {pos: [sx * (FW.plateX - 0.02), 0.22, 2.02]});
  }

  // ------------------------------------------------------------ FIA 標準 ECU（位置示意）與訊號線
  const EC = CENTRE.ecu;
  add('ecu', box(0.16, 0.06, 0.22), M.ecu, {pos: EC});
  for (let i = 0; i < 6; i++) add('ecu', box(0.004, 0.018, 0.2), M.alu, {pos: [EC[0] - 0.06 + i * 0.024, EC[1] + 0.039, EC[2]]});
  const ledMat = new THREE.MeshStandardMaterial({color: '#2b2d31', emissive: new THREE.Color(COL.signal), emissiveIntensity: 0.3});
  add('ecu', box(0.02, 0.008, 0.008), ledMat, {pos: [EC[0] + 0.06, EC[1] + 0.02, EC[2] + 0.112]});
  const frontPts = [[EC[0] - 0.02, EC[1] - 0.02, EC[2] + 0.11], [0.2, 0.18, 0.9], [0.14, 0.24, 1.7], [0.14, 0.41, 2.1]];
  const rearPts = [[EC[0] - 0.02, EC[1] - 0.02, EC[2] - 0.11], [0.18, 0.3, -0.6], [0.06, 0.4, -1.6], [0, 0.62, -2.08], [0, 1.11, -2.44]];
  add('ecu', tube(frontPts, 0.006, 60), M.wire);
  add('ecu', tube(rearPts, 0.006, 60), M.wire);
  const sigCurves = {f: curve(frontPts), r: curve(rearPts)};

  // 元件上連桿的接點（隨轉動移動）：前翼第二片元件後緣附近、後翼襟翼中段上緣
  // 元件自己座標裡的一點 (x, h, −弦長×f) 繞 x 轉 a 之後：y' = h·cos a + c·f·sin a，z' = h·sin a − c·f·cos a
  const onElement = (pivot, c, f, h, x, a) => new V3(x, pivot.y + h * Math.cos(a) + c * f * Math.sin(a), pivot.z + h * Math.sin(a) - c * f * Math.cos(a));
  function elPoint(i, x, k) {
    const e = fwEl[i];
    const a = (e.a.corner + (e.a.straight - e.a.corner) * k) * D2R;
    return onElement(e.g.position, e.c, 0.3, 0.012, x, a);
  }
  function flapPoint(k) {
    const a = (AOA.rwFlap.corner + (AOA.rwFlap.straight - AOA.rwFlap.corner) * k) * D2R;
    return onElement(rwFlap.position, 0.2, 0.4, 0.014, 0, a);
  }

  // ------------------------------------------------------------ 訊號粒子（ECU 下指令時沿線流向致動器）
  const sig = {};
  for (const key of ['f', 'r']) {
    const im = new THREE.InstancedMesh(new THREE.SphereGeometry(0.014, 10, 8), new THREE.MeshBasicMaterial({color: COL.signal, transparent: true, opacity: 0, depthWrite: false}), 8);
    im.frustumCulled = false;
    root.add(im);
    sig[key] = im;
  }
  const fm = new THREE.Matrix4();
  const fp = new V3();
  const placeSig = (key, age, on) => {
    const im = sig[key];
    // 指令發出後 0.45 秒內，一串粒子從 ECU 流到致動器
    const k = age / 0.45;
    const op = on && k >= 0 && k < 1 ? Math.sin(Math.PI * k) : 0;
    im.material.opacity = op;
    im.visible = op > 0.01;
    if (!im.visible) return;
    for (let i = 0; i < 8; i++) {
      const u = Math.min(0.999, Math.max(0, k * 1.3 - i * 0.04));
      sigCurves[key].getPointAt(u, fp);
      fm.makeTranslation(fp.x, fp.y, fp.z);
      im.setMatrixAt(i, fm);
    }
    im.instanceMatrix.needsUpdate = true;
  };

  // ------------------------------------------------------------ 模式：實體／X 光／剖開／爆炸圖，與聚焦單一零件
  const CLIP = new THREE.Plane(new V3(-1, 0, 0), 0.32);
  const GHOST = new THREE.MeshBasicMaterial({color: '#8a8183', transparent: true, opacity: 0.07, depthWrite: false});
  const xrayOf = new Map();
  const xray = (mat) => {
    if (!xrayOf.has(mat)) xrayOf.set(mat, XRAY.clone());
    return xrayOf.get(mat);
  };
  // 剖開時切車身與兩副翼（看得到翼型斷面）；致動器、擋塊與 ECU 不切。
  // 判斷落在材質上（同一個材質被好幾個零件共用，逐個 mesh 設會互相覆蓋）
  const NOCUT = new Set([M.alu, M.steel, M.stop, M.sensor, M.ecu, M.wire, ledMat]);
  // 聚焦某組時，跟它直接相關的組也留著：翼片連著推它的致動器；致動器連著它推的翼片；ECU 連著它指揮的致動器
  const KEEP = {fw: ['act'], rw: ['act'], act: ['fw', 'rw'], ecu: ['act']};

  /**
   * 一格畫面的姿態。o：
   *   s（kin.stateOf 的結果）、wheel（車輪轉角，度）
   *   view（'solid'|'xray'|'section'|'explode'）、explodeK（0..1）、focus（'all' 或零件 key）、focusK（0..1）
   */
  const update = (o) => {
    const s = o.s;
    const kf = ease(s.pf);
    const kr = ease(s.pr);
    for (const e of fwEl) e.g.rotation.x = (e.a.corner + (e.a.straight - e.a.corner) * kf) * D2R;
    rwFlap.rotation.x = (AOA.rwFlap.corner + (AOA.rwFlap.straight - AOA.rwFlap.corner) * kr) * D2R;
    for (const e of fwEl) e.mat.emissiveIntensity = 0.55 * kf;
    rwFlapMat.emissiveIntensity = 0.55 * kr;
    for (const w of wheels) w.g.rotation.x = -o.wheel * D2R;
    ledMat.emissiveIntensity = 0.3 + 0.9 * Math.max(0, 1 - Math.min(s.cmdF, s.cmdR) / 0.5);

    // 爆炸圖
    const ek = o.explodeK ?? 0;
    for (const [key, g] of Object.entries(groups)) {
      const v = EXPLODE[key];
      g.position.set(v[0] * ek, v[1] * ek, v[2] * ek);
    }
    // 前翼兩片元件在爆炸圖時再各自往上分開
    fwEl.forEach((e, i) => (e.g.position.y = e.pos[1] + ek * 0.1 * (i + 1)));
    rwFlap.position.y = 0.905 + ek * 0.16;

    // 連桿：從致動器底端拉到元件上的接點（世界座標換回 act 組的座標）；爆炸圖時連桿會斷開，藏起來
    const ks = [kf, kf, kr];
    acts.forEach((a, i) => {
      a.rod.visible = ek < 0.15;
      if (!a.rod.visible) return;
      const to = a.rodTo(ks[i]).add(groups[a.wing].position).sub(groups.act.position);
      const from = a.foot;
      const dir = to.clone().sub(from);
      a.rod.position.copy(from).add(to).multiplyScalar(0.5);
      a.rod.scale.y = Math.max(0.001, dir.length());
      a.rod.quaternion.setFromUnitVectors(new V3(0, 1, 0), dir.normalize());
    });

    // 材質
    const fk = o.focusK ?? 0;
    const view = o.view || 'solid';
    const xOn = view === 'xray';
    const cutOn = view === 'section';
    const solo = o.focus && o.focus !== 'all' && fk > 0.5;
    for (const it of meshes) {
      const other = o.focus && o.focus !== 'all' && it.comp !== o.focus;
      let mat = it.base;
      if (it.shell && xOn && !(other && solo)) mat = xray(it.base);
      if (other && solo && !(KEEP[o.focus] || []).includes(it.comp)) mat = GHOST;
      it.mesh.material = mat;
      // 剖開時，靠鏡頭這一側（+x）的車輪與懸吊整個藏起來，才看得到翼型斷面
      it.mesh.visible = !(cutOn && it.side > 0 && it.comp === 'body' && !it.shell);
      if (it.mesh.userData.edge) it.mesh.userData.edge.visible = xOn && !(other && fk > 0.5);
      if (mat !== GHOST) mat.clippingPlanes = cutOn && !NOCUT.has(it.base) ? [CLIP] : null;
    }
    EDGE.opacity = xOn ? 0.5 : 0;
    const showSig = ek < 0.15;
    placeSig('f', s.cmdF, showSig);
    placeSig('r', s.cmdR, showSig);
  };
  // 環境遮蔽（GTAO）那一趟要把半透明的淡影與 X 光外殼藏起來：不然看不見的大片車身會在畫面上留下一層灰霧
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
  /** 爆炸後某組中心的世界座標（標籤用） */
  const centreOf = (key, ek = 0) => {
    const c = CENTRE[key];
    const v = EXPLODE[key] || [0, 0, 0];
    return [c[0] + v[0] * ek, c[1] + v[1] * ek, c[2] + v[2] * ek];
  };
  return {root, update, M, CLIP, centreOf, groups, aoHide};
}
