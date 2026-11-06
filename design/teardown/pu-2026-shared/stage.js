// 動力單元的場景：淺色攝影棚、看不見的地板只收陰影、四塊柔光箱讓碳黑外殼有反光可讀。
// 改寫自 teardown skill 的 v8-shared/stage.js（MIT）。frame(o, cam) 擺好零件、畫一格。
import * as THREE from 'three';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {GTAOPass} from 'three/addons/postprocessing/GTAOPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {Pass} from 'three/addons/postprocessing/Pass.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {buildPU} from './pu.js';

const V3 = THREE.Vector3;
// 背景取站上亮色主題的暖灰（--bg #f3e9e9 一族），比純灰多一點溫度
export const BG = {top: '#f6f2f1', mid: '#ece6e5', low: '#e4dedd'};

export function createStage({canvas}) {
  const renderer = new THREE.WebGLRenderer({canvas, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance'});
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  renderer.localClippingEnabled = true;
  const scene = new THREE.Scene();
  {
    const c = document.createElement('canvas');
    c.width = 4;
    c.height = 512;
    const g = c.getContext('2d');
    const gr = g.createLinearGradient(0, 0, 0, 512);
    gr.addColorStop(0, BG.top);
    gr.addColorStop(0.55, BG.mid);
    gr.addColorStop(1, BG.low);
    g.fillStyle = gr;
    g.fillRect(0, 0, 4, 512);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    scene.background = tex;
  }
  const camera = new THREE.PerspectiveCamera(26, 16 / 9, 0.05, 60);
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(4, 4, {type: THREE.HalfFloatType, samples: 8}));
  composer.addPass(new RenderPass(scene, camera));
  const gtao = new GTAOPass(scene, camera, 4, 4);
  gtao.output = GTAOPass.OUTPUT.Default;
  gtao.blendIntensity = 0.7;
  gtao.updateGtaoMaterial({radius: 0.08, distanceExponent: 1.4, thickness: 0.8, scale: 1.0, samples: 16, distanceFallOff: 1.0, screenSpaceRadius: false});
  gtao.updatePdMaterial({lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 16});
  class Toggle extends Pass {
    constructor(fn) {
      super();
      this.needsSwap = false;
      this.fn = fn;
    }
    render() {
      this.fn();
    }
  }
  composer.addPass(new Toggle(() => (shade.visible = false)));
  composer.addPass(gtao);
  composer.addPass(new Toggle(() => (shade.visible = true)));
  composer.addPass(new OutputPass());

  {
    const env = new THREE.Scene();
    env.background = new THREE.Color('#dcd8d7');
    const box = (w, h, pos, k) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({color: new THREE.Color(1, 1, 1).multiplyScalar(k), side: THREE.DoubleSide}));
      m.position.copy(pos);
      m.lookAt(0, 0, 0);
      env.add(m);
    };
    box(12, 12, new V3(0, 14, 2), 2.6);
    box(3, 14, new V3(-12, 4, 6), 3.2);
    box(3, 14, new V3(12, 4, -4), 2.2);
    box(18, 2, new V3(0, 2, 14), 1.6);
    const g = new THREE.Mesh(new THREE.CircleGeometry(40, 32), new THREE.MeshBasicMaterial({color: '#cbc6c5', side: THREE.DoubleSide}));
    g.rotation.x = -Math.PI / 2;
    g.position.y = -2;
    env.add(g);
    const pm = new THREE.PMREMGenerator(renderer);
    scene.environment = pm.fromScene(env, 0.02).texture;
    scene.environmentIntensity = 1.0;
    pm.dispose();
  }
  const sun = new THREE.DirectionalLight('#ffffff', 2.2);
  sun.position.set(-1.6, 4.2, 2.2);
  sun.castShadow = true;
  Object.assign(sun.shadow.camera, {left: -1.6, right: 1.6, top: 1.6, bottom: -1.6, near: 0.5, far: 10});
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.radius = 14;
  sun.shadow.blurSamples = 24;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.003;
  scene.add(sun, sun.target);
  scene.add(new THREE.HemisphereLight('#ffffff', '#d3cecd', 0.75));

  // 地板：只收陰影，貼在輪胎底下
  const FLOOR_Y = -0.342;
  const shade = new THREE.Mesh(
    new THREE.PlaneGeometry(24, 24),
    new THREE.ShadowMaterial({color: '#5f585a', opacity: 0.26, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -8}),
  );
  shade.rotation.x = -Math.PI / 2;
  shade.position.y = FLOOR_Y;
  shade.receiveShadow = true;
  scene.add(shade);

  const pu = buildPU();
  scene.add(pu.root);

  const size = {w: 1600, h: 900};
  const resize = (w, h, pr) => {
    size.w = w;
    size.h = h;
    renderer.setPixelRatio(pr);
    renderer.setSize(w, h, false);
    composer.setPixelRatio(pr);
    composer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  // cam：目標點 (tx, ty, tz)、方位角（從 +z 轉向 +x）、仰角、距離（弧度、公尺）、sx/sy 畫面平移
  let cutOn = false;
  const frame = (o, cam) => {
    pu.update(o);
    const want = o.view === 'section';
    if (want !== cutOn) {
      cutOn = want;
      gtao.normalMaterial.clippingPlanes = want ? [pu.CLIP] : null;
      gtao.normalMaterial.needsUpdate = true;
    }
    const {tx, ty, tz, az, el, d} = cam;
    camera.position.set(tx + d * Math.cos(el) * Math.sin(az), ty + d * Math.sin(el), tz + d * Math.cos(el) * Math.cos(az));
    camera.lookAt(tx, ty, tz);
    camera.setViewOffset(size.w, size.h, -(cam.sx ?? 0), -(cam.sy ?? 0), size.w, size.h);
    camera.updateMatrixWorld();
    composer.render();
  };
  const pv = new V3();
  const project = (x, y, z) => {
    pv.set(x, y, z).project(camera);
    if (pv.z > 1) return null;
    return [(pv.x * 0.5 + 0.5) * size.w, (-pv.y * 0.5 + 0.5) * size.h];
  };
  const setQuality = ({samples, ao, shadow}) => {
    if (samples !== undefined) {
      for (const t of [composer.renderTarget1, composer.renderTarget2]) {
        t.samples = samples;
        t.dispose();
      }
    }
    if (ao !== undefined) gtao.enabled = ao;
    if (shadow !== undefined) {
      sun.shadow.mapSize.set(shadow, shadow);
      sun.shadow.map?.dispose();
      sun.shadow.map = null;
    }
  };
  return {renderer, scene, camera, pu, composer, gtao, sun, resize, frame, project, size, FLOOR_Y, setQuality};
}
