#!/usr/bin/env node
'use strict';
/* 娱乐测验页复核：一条命令给出「收不收数据 + 准不准」的全部指标。
   用法: node quiz_audit.js <page.html|page.htm> [--samples 5000] [--keys rat,ord,...] [--pct-fn pct] [--hdr hdr.txt]
   前提: 数据以内嵌 <script> 的 window.X = [...] 形式存在（纯静态页）。走接口/SSR JSON 的页先用 siteprobe --dump。
   判读阈值见 references/quiz-scoring-audit.md */
const fs = require('fs');
const argv = process.argv.slice(2);
const file = argv.find(a => !a.startsWith('--'));
if (!file) { console.error('用法: node quiz_audit.js <page.html> [--samples N] [--keys a,b,c] [--pct-fn pct] [--hdr hdr.txt]'); process.exit(1); }
const opt = (n, d) => { const i = argv.indexOf('--' + n); return i > -1 && argv[i + 1] ? argv[i + 1] : d; };
const SAMPLE = parseInt(opt('samples', '5000'), 10) || 5000;
const html = fs.readFileSync(file, 'utf8');
const say = (...a) => console.log(...a);

/* ---------- 1. 安全面 ---------- */
say('== 安全面（外发通道扫描；命中需读请求代码确认，CSS url() 不算）==');
const hdr = opt('hdr', null);
if (hdr && fs.existsSync(hdr)) {
  const s = fs.readFileSync(hdr, 'utf8').split(/\r?\n/).find(l => /^server:/i.test(l));
  if (s) say('  ' + s.trim() + '  ← 静态托管/源站线索'
    + (/cloudstudio|vercel|netlify|github|oss|cdn/i.test(s) ? '（静态托管，随机子域名=临时部署）' : ''));
}
const netTokens = {
  'fetch(': /\bfetch\s*\(/g, 'XMLHttpRequest': /XMLHttpRequest/g, sendBeacon: /sendBeacon/g,
  'document.cookie': /document\.cookie/g, localStorage: /localStorage/g, sessionStorage: /sessionStorage/g,
  'new Image': /new\s+Image\s*\(/g, analytics: /\b(gtag|umami|_hmt|analytics)\b/g
};
let hits = 0;
for (const [k, re] of Object.entries(netTokens)) { const c = (html.match(re) || []).length; if (c) { hits += c; say(`  ⚠ ${k}: ${c}`); } }
say(hits ? '  → 有命中：读那段代码看 payload 收了什么，再定「偷不偷数据」' : '  ✅ 未见外发通道：纯本地算分');

/* ---------- 2. 数据面：沙箱求值 ---------- */
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const dataCode = blocks.filter(b => /(?:window|var|let|const)\s+\w+\s*=\s*\[/.test(b) && !/document\./.test(b)).join('\n');
const sandbox = {};
try { new Function('window', dataCode)(sandbox); }
catch (e) { console.error('数据块求值失败（页面可能不是内嵌静态数据）：' + e.message); process.exit(2); }
const arrays = Object.values(sandbox).filter(Array.isArray);
const isQ = a => a.length > 0 && a.filter(x => x && Array.isArray(x.o) && x.o.length && x.o.every(o => o && typeof o.s === 'object' && o.s)).length >= a.length * 0.8;
const isC = a => a.length > 0 && a.filter(x => x && Array.isArray(x.v) && x.v.length && x.v.every(n => typeof n === 'number')).length >= a.length * 0.8;
const QS = arrays.find(isQ);
const CHS = arrays.filter(isC).flat();
if (!QS || !CHS.length) { console.error('未识别出题库/向量表：形状不符，改走 references/nextjs-app-router.md 手工抠'); process.exit(3); }
const keysArg = opt('keys', null);
const keys = keysArg ? keysArg.split(',') : [...new Set(QS.flatMap(q => q.o.flatMap(o => Object.keys(o.s || {}))))];
say(`\n== 数据 ==\n  题目 ${QS.length} 道 | 结果向量 ${CHS.length} 条 | 维度 ${keys.length} 个: ${keys.join(',')}`);
const optCounts = QS.reduce((a, q) => { a[q.o.length] = (a[q.o.length] || 0) + 1; return a; }, {});
say('  每题选项数分布: ' + JSON.stringify(optCounts));
const lenBad = CHS.filter(c => c.v.length !== keys.length).length;
if (lenBad) say(`  ⚠ ${lenBad} 条向量维度与 keys 不等长，--keys 可能传错`);

/* ---------- 3. 覆盖 ---------- */
const cover = {}; keys.forEach(k => cover[k] = { q: 0, w: 0, max: 0 });
QS.forEach(q => { const hit = new Set(); q.o.forEach(o => { for (const k in (o.s || {})) { if (!cover[k]) continue; hit.add(k); cover[k].w += Math.abs(o.s[k]); cover[k].max = Math.max(cover[k].max, Math.abs(o.s[k])); } }); hit.forEach(k => cover[k].q++); });
say('\n== 每维覆盖（题数 / 总权重 / 单次封顶）==');
keys.forEach(k => say(`  ${k}\t${cover[k].q} 题\t权重 ${cover[k].w}\t封顶 ±${cover[k].max}`));
const perQ = QS.map(q => { const s = new Set(); q.o.forEach(o => Object.keys(o.s || {}).forEach(k => s.add(k))); return s.size; });
say('  每题涉及维度数: ' + JSON.stringify(perQ.reduce((a, n) => { a[n] = (a[n] || 0) + 1; return a; }, {})) + '（一题打满多维=信息被摊薄）');
const dupGroups = Object.entries(CHS.reduce((a, c) => { const k = c.v.join(','); (a[k] = a[k] || []).push(c.n || '?'); return a; }, {})).filter(([, g]) => g.length > 1);
say(`  向量唯一数: ${new Set(CHS.map(c => c.v.join(','))).size} / ${CHS.length}` + (dupGroups.length ? '  ⚠ 撞车: ' + dupGroups.map(([, g]) => g.join('=')).join(' | ') : ''));

/* ---------- 4. 百分比函数签名 ---------- */
function extractFn(name) {
  const m = new RegExp('function\\s+' + name + '\\s*\\(([^)]*)\\)\\s*\\{').exec(html);
  if (!m) return null;
  let depth = 0;
  for (let j = m.index + m[0].length - 1; j < html.length; j++) {
    if (html[j] === '{') depth++;
    else if (html[j] === '}' && --depth === 0) return { src: html.slice(m.index, j + 1), params: m[1] };
  }
  return null;
}
const pctName = opt('pct-fn', 'pct');
const fn = extractFn(pctName);
say(`\n== 百分比函数 ${pctName}() ==`);
if (!fn) say('  未按 function 形式找到——可能写成箭头/变量，手工搜 renderResult 里的百分比拼装');
else {
  say(`  签名: (${fn.params})` + (fn.params.split(',').length === 1 ? ' ← 只吃一个参数' : ''));
  try {
    const p = new Function('N', 'return ' + fn.src)(CHS.length);
    const head = [0, 1, 2, 3, 4].map(r => `${r + 1}名=${p(r)}%`).join(' ');
    say(`  ${head} 末位=${p(CHS.length - 1)}%`);
    say(fn.params.split(',').length === 1
      ? '  ❗ 只吃名次 ⇒ 百分比是名次映射，与用户答案无关（换谁做第一名都一样）'
      : '  吃多个参数，需再看函数体是否真的用到用户向量');
  } catch (e) { say('  求值失败（依赖外部变量）：' + e.message); }
}

/* ---------- 5. 蒙特卡洛：分辨率 + 垄断 ---------- */
const BASE = (() => { const mean = {}, sd = {}; keys.forEach(k => { let m = 0, vs = 0; QS.forEach(q => { const vals = q.o.map(o => (o.s && o.s[k]) || 0); const mu = vals.reduce((a, b) => a + b, 0) / vals.length; m += mu; vs += vals.reduce((a, v) => a + (v - mu) ** 2, 0) / vals.length; }); mean[k] = m; sd[k] = Math.sqrt(vs) || 1; }); return { mean, sd }; })();
const scoreUser = ans => { const v = {}; keys.forEach(k => v[k] = 0); ans.forEach((ai, qi) => { const s = QS[qi].o[ai].s || {}; for (const k in s) if (v[k] !== undefined) v[k] += s[k]; }); return keys.map(k => (v[k] - BASE.mean[k]) / BASE.sd[k]); };
const norm = v => { const m = Math.sqrt(v.reduce((a, x) => a + x * x, 0)) || 1; return v.map(x => x / m); };
const CV = CHS.map(c => norm(c.v.slice(0, keys.length)));
const rank = vec => { const u = norm(vec); return CHS.map((c, i) => { let cos = 0, d2 = 0; const cv = CV[i]; for (let j = 0; j < u.length; j++) { cos += u[j] * cv[j]; d2 += (u[j] - cv[j]) ** 2; } const d = Math.sqrt(d2); return { i, s: 0.72 * cos + 0.28 * Math.max(0, 1 - d / 1.6) }; }).sort((a, b) => b.s - a.s); };
let seed = 12345 >>> 0;
const rnd = () => { seed = (seed + 0x6D2B79F5) >>> 0; let t = seed; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };  // mulberry32：别用 seed*1103515245（超 2^53 丢精度，分布退化）
const randAns = () => QS.map(q => Math.floor(rnd() * q.o.length));
const counts = {}; const tops = [];
for (let t = 0; t < SAMPLE; t++) { const r = rank(scoreUser(randAns())); const n = CHS[r[0].i].n || String(r[0].i); counts[n] = (counts[n] || 0) + 1; tops.push(r[0].s); }
const dist = Object.entries(counts).sort((a, b) => b[1] - a[1]);
const hhi = dist.reduce((a, [, c]) => a + (c / SAMPLE) ** 2, 0);
say(`\n== 随机 ${SAMPLE} 份答卷 ==`);
say(`  当过第一的角色: ${dist.length} / ${CHS.length}`);
say('  前 5: ' + dist.slice(0, 5).map(([n, c]) => `${n} ${(c / SAMPLE * 100).toFixed(1)}%`).join(' | '));
say(`  HHI ${(hhi * 100).toFixed(1)}，均匀值 ${(100 / CHS.length).toFixed(2)}，倍数 ${(hhi * CHS.length).toFixed(1)}×` + (hhi * CHS.length > 10 ? '  ⚠ 头部垄断' : ''));
tops.sort((a, b) => a - b);
say(`  第一名原始分 5%/50%/95%: ${tops[Math.floor(SAMPLE * .05)].toFixed(3)} / ${tops[Math.floor(SAMPLE * .5)].toFixed(3)} / ${tops[Math.floor(SAMPLE * .95)].toFixed(3)}`);
const flip = flips => { let changed = 0, T = 0; for (let t = 0; t < 40; t++) { const a = randAns(); const base = CHS[rank(scoreUser(a))[0].i].n; for (let k = 0; k < 120; k++) { const a2 = a.slice(); for (let f = 0; f < flips; f++) { const qi = Math.floor(rnd() * QS.length); a2[qi] = Math.floor(rnd() * QS[qi].o.length); } if (CHS[rank(scoreUser(a2))[0].i].n !== base) changed++; T++; } } return changed / T * 100; };
say('\n== 分辨率（改题后第一名换人概率）==');
[1, 3, 5].forEach(n => { const p = flip(n); say(`  改 ${n} 题: ${p.toFixed(1)}%` + (p > 30 ? '  ⚠ 噪声大过向量间距' : p < 10 ? '  ✅ 稳' : '')); });
say('\n判读阈值见 references/quiz-scoring-audit.md §三；非本页公式的站需改第 5 段（混合权重/归一化方式）。');
