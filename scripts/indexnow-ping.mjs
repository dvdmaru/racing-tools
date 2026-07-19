#!/usr/bin/env node
/**
 * IndexNow ping — 把新增/更新的 URL 推給 IndexNow（api.indexnow.org 分發給
 * Bing/Yandex/Naver/Seznam 等參與引擎；Bing 索引另餵 ChatGPT search / Copilot）。
 *
 * 用法：node scripts/indexnow-ping.mjs <url> [url...]
 *   - URL 必須屬於 HOST，其他一律拒收（避免誤 ping 別人的站吃信譽懲罰）
 *   - 回 200/202 都算成功（202 = key 驗證排程中，正常）
 *
 * 源自 dvdmaru/aire 同名腳本（twtools 生態系「互連+收錄」計畫），改 HOST/KEY 而來。
 * racing 的接點：update-racing.py deploy 成功後收集本次變動 URL 呼叫本腳本。
 */
const HOST = process.env.INDEXNOW_HOST ?? 'racing.twtools.cc';
const KEY = process.env.INDEXNOW_KEY ?? '2ff0c6c08ab0101f4d705e7f229b7211';

const urls = [...new Set(process.argv.slice(2))];
const bad = urls.filter((u) => !u.startsWith(`https://${HOST}/`) && u !== `https://${HOST}`);
if (bad.length) {
  console.error(`ABORT: URL 不屬於 ${HOST}：\n${bad.join('\n')}`);
  process.exit(1);
}
if (!urls.length) {
  console.error('用法：node scripts/indexnow-ping.mjs <url> [url...]');
  process.exit(1);
}

const res = await fetch('https://api.indexnow.org/indexnow', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  body: JSON.stringify({
    host: HOST,
    key: KEY,
    keyLocation: `https://${HOST}/${KEY}.txt`,
    urlList: urls,
  }),
});

const body = await res.text();
console.log(`IndexNow → HTTP ${res.status} ${body || '(empty body)'}`);
console.log(urls.map((u) => `  ✓ ${u}`).join('\n'));
if (res.status !== 200 && res.status !== 202) process.exit(1);
