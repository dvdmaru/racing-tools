#!/usr/bin/env node
// racing.twtools.cc 的 teardown 頁面打包器：把 <sim>/main.js 打成一個可離線開啟的 HTML。
// 改寫自 teardown skill 的 sims/build.mjs（elvarofficial/teardown，MIT，commit a91262ac），差在三處：
//   1. 不內嵌 Inter／JetBrains Mono；數字與英文內嵌站上用的 Chakra Petch（SIL OFL，fonts/），
//      中文走系統字型（PingFang TC → Noto Sans TC → 微軟正黑體），與站上 --font-ui 同序。
//   2. <html lang="zh-Hant">。
//   3. 輸出到 TEARDOWN_OUT（預設 ./teardown-out/dist），不寫進 repo。
//
//   node design/teardown/build.mjs design/teardown/pu-2026-live
//
// 依賴（three、esbuild）與 kit 都讀已安裝的 skill：TEARDOWN_SKILL，預設 ~/.claude/skills/teardown。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = process.env.TEARDOWN_SKILL || path.join(os.homedir(), '.claude/skills/teardown');
const DEPS = path.join(SKILL, 'node_modules');
const KIT = path.join(SKILL, 'sims/kit');
const OUT = path.resolve(process.env.TEARDOWN_OUT || 'teardown-out');
const DIST = path.join(OUT, 'dist');
const esbuild = createRequire(path.join(DEPS, 'x.js'))('esbuild');

const b64 = (f) => fs.readFileSync(path.join(HERE, 'fonts', f)).toString('base64');
const FONTS = [500, 600, 700]
  .map((w) => `@font-face{font-family:'Chakra Petch';font-weight:${w};font-style:normal;font-display:block;src:url(data:font/woff2;base64,${b64(`chakra-petch-latin-${w}.woff2`)}) format('woff2');}`)
  .join('\n');
const KIT_CSS = fs.readFileSync(path.join(KIT, 'style.css'), 'utf8');

const kitPlugin = {
  name: 'teardown-kit',
  setup(b) {
    b.onResolve({filter: /^teardown-kit\//}, (args) => ({path: path.join(KIT, args.path.slice('teardown-kit/'.length))}));
  },
};

const args = process.argv.slice(2);
if (!args.length) {
  console.error('usage: node design/teardown/build.mjs <sim folder with main.js> [...]');
  process.exit(1);
}
fs.mkdirSync(DIST, {recursive: true});
for (const arg of args) {
  const dir = path.resolve(arg);
  if (!fs.existsSync(path.join(dir, 'main.js'))) {
    console.error(`no main.js in ${dir}`);
    process.exit(1);
  }
  const name = path.basename(dir);
  const t0 = Date.now();
  const res = await esbuild.build({
    plugins: [kitPlugin],
    entryPoints: [path.join(dir, 'main.js')],
    bundle: true,
    nodePaths: [DEPS],
    format: 'esm',
    minify: !process.env.SIMS_DEBUG,
    write: false,
    target: 'es2022',
    legalComments: 'none',
    logLevel: 'warning',
  });
  const js = res.outputFiles[0].text.replace(/<\/script/g, '<\\/script');
  const css = fs.existsSync(path.join(dir, 'style.css')) ? fs.readFileSync(path.join(dir, 'style.css'), 'utf8') : '';
  const title = fs.existsSync(path.join(dir, 'title.txt')) ? fs.readFileSync(path.join(dir, 'title.txt'), 'utf8').trim() : name;
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex">
<title>${title}</title>
<style>
${FONTS}
${KIT_CSS}
${css}
</style>
</head>
<body>
<div id="app"></div>
<script type="module">
${js}
</script>
</body>
</html>
`;
  const out = path.join(DIST, `${name}.html`);
  fs.writeFileSync(out, html);
  console.log(`${out}  ${(Buffer.byteLength(html) / 1024).toFixed(0)} KB  ${Date.now() - t0} ms`);
}
