#!/usr/bin/env python3
"""siteprobe — 扒站结构的一条命令。

为什么有这个：read-url 管「这页说了什么」，不管「这页怎么搭的」。
遇到题库/配置/算法这类结构化数据，正文提取器只会吐壳。这套流程原来散在
web-content-harvesting 的手工步骤里（抓 HTML → 找 chunk → grep → 括号平衡 → node 求值），
2026-10-18 压成一条命令。

用法：
  siteprobe <url>                 # 站点体检：技术栈/路由图/正文/ chunk 清单
  siteprobe <url> --chunks        # 下载全部 chunk，按汉字数排序（哪几个像数据文件）
  siteprobe <url> --dump N        # 从第 N 个 chunk 里挖数据数组，落 JSON
  siteprobe <url> --text          # SSR 正文抽出来落 markdown
  siteprobe <url> --json          # 机器可读（配合上面任意开关）

产物落 <数据根>/workspace/records/siteprobe/<host>/（数据根用 HERMES_ROOT 指定，默认当前目录）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from lxml import html as LH

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ROOT = os.environ.get("HERMES_ROOT") or os.getcwd()
OUT_BASE = os.path.join(ROOT, "workspace", "records", "siteprobe")


def fetch(url, timeout=45, retries=3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"抓取失败 {url}: {last}")


def probe_page(url):
    info = {"url": url, "ok": False}
    try:
        r = fetch(url)
    except RuntimeError as e:
        info["error"] = str(e)
        return info
    html = r.text
    m = re.search(r"<title>([^<]*)", html)
    info.update({
        "ok": r.status_code == 200,
        "status": r.status_code,
        "bytes": len(r.content),
        "final_url": r.url,
        "title": (m.group(1).strip() if m else ""),
        "app_router": "self.__next_f.push" in html,
        "csr_bailout": "BAILOUT_TO_CLIENT_SIDE_RENDERING" in html,
        "chunks": sorted(set(re.findall(r"/_next/static/chunks/[A-Za-z0-9_.\-]+\.js", html))),
    })
    info["ssr_text_chars"] = len(extract_text(html))
    return info


def extract_text(html):
    """从 SSR HTML 抽正文：main/article 优先，抽 h1-h3/p/li。"""
    try:
        doc = LH.fromstring(html)
    except Exception:  # noqa: BLE001
        return ""
    roots = doc.xpath("//main") or doc.xpath("//article") or doc.xpath("//body")
    if not roots:
        return ""
    root = roots[0]
    parts, seen = [], None
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in ("h1", "h2", "h3", "p", "li"):
            t = " ".join(el.text_content().split())
            if not t or t == seen:
                continue
            seen = t
            parts.append(("# " if tag in ("h1", "h2") else "") + t)
    return "\n\n".join(parts)


def probe_robots(url):
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    out = {"disallow": [], "sitemap": None}
    try:
        r = fetch(base + "/robots.txt", timeout=20, retries=2)
        if r.status_code == 200:
            for line in r.text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    p = line.split(":", 1)[1].strip()
                    if p and p not in out["disallow"]:
                        out["disallow"].append(p)
                if line.lower().startswith("sitemap:"):
                    out["sitemap"] = line.split(":", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return out


def probe_sitemap(sitemap_url):
    out = {"count": 0, "locales": [], "sample": []}
    if not sitemap_url:
        return out
    try:
        r = fetch(sitemap_url, timeout=30, retries=2)
        locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
        langs = sorted(set(re.findall(r'hreflang="([^"]+)"', r.text)))
        out.update({"count": len(locs), "locales": langs, "sample": locs[:8]})
    except Exception:  # noqa: BLE001
        pass
    return out


def download_chunks(url, chunks, outdir):
    results = []
    for c in chunks:
        name = c.rsplit("/", 1)[-1]
        path = os.path.join(outdir, "chunks", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            try:
                r = fetch(urljoin(url, c), timeout=45, retries=2)
                open(path, "wb").write(r.content)
            except Exception as e:  # noqa: BLE001
                results.append({"name": name, "error": str(e)})
                continue
        txt = open(path, encoding="utf-8", errors="replace").read()
        han = len(re.findall(r"[\u4e00-\u9fff]", txt))
        results.append({"name": name, "bytes": len(txt), "han": han,
                        "has_data_array": bool(re.search(r'\{\s*id\s*:\s*"', txt))})
    results.sort(key=lambda x: -x.get("han", 0))
    return results


def _balanced_array(s, start_idx):
    i = s.index("[", start_idx)
    depth, instr, esc = 0, None, False
    for j in range(i, len(s)):
        ch = s[j]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == instr:
                instr = None
            continue
        if ch in "\"'`":
            instr = ch
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return s[i:j + 1]
    return None


def dump_chunk(path, out_json, hint=None):
    """从 chunk 里找数据数组，交 node 求值成 JSON。"""
    s = open(path, encoding="utf-8", errors="replace").read()
    raw = [hint] if hint else ['{id:"', '{ id:"', "{id:'", '{id:"Q']
    hints = [h if h.startswith("[") else "[" + h for h in raw]
    found = None
    for h in hints:
        k = s.find(h)
        if k > 0:
            arr = _balanced_array(s, k)
            if arr:
                found = arr
                break
    if not found:
        return {"ok": False, "error": "没找到 {id:\"...\" 形态的数据数组", "hint": "用 --grep 关键词自己定位"}
    js = os.path.join(os.path.dirname(out_json), "_eval.js")
    open(js, "w", encoding="utf-8").write("const n=" + found + ";console.log(JSON.stringify(n));")
    try:
        res = subprocess.run(["node", js], capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            return {"ok": False, "error": "node 求值失败（数组里可能有函数/template literal）",
                    "stderr": res.stderr[:500]}
        data = json.loads(res.stdout)
        json.dump(data, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return {"ok": True, "items": len(data) if isinstance(data, list) else 1, "out": out_json}
    finally:
        try:
            os.remove(js)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="扒站结构：路由图 / chunk 数据 / SSR 正文")
    ap.add_argument("url")
    ap.add_argument("--page", default="", help="要探的路由（如 /quiz）；默认探首页")
    ap.add_argument("--chunks", action="store_true", help="下载全部 chunk 并按汉字数排序")
    ap.add_argument("--dump", type=int, metavar="N", help="从第 N 个（0 起）chunk 挖数据数组")
    ap.add_argument("--hint", help="dump 时的定位关键词，如 title:")
    ap.add_argument("--text", action="store_true", help="SSR 正文落 markdown")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--out", help="落盘目录")
    args = ap.parse_args()

    host = urlparse(args.url).netloc.replace(":", "_") or "site"
    outdir = args.out or os.path.join(OUT_BASE, host)
    os.makedirs(outdir, exist_ok=True)

    target = urljoin(args.url, args.page) if args.page else args.url
    page = probe_page(target)
    robots = probe_robots(args.url)
    sitemap = probe_sitemap(robots.get("sitemap"))

    report = {"page": page, "target": target, "robots": robots, "sitemap": sitemap}
    chunks_info: list = []
    if args.chunks or args.dump is not None:
        chunks_info = download_chunks(target, page.get("chunks", []), outdir)
        report["chunks"] = chunks_info

    if args.dump is not None:
        if not chunks_info:
            print("没有 chunk 可挖", file=sys.stderr)
            return 1
        idx = args.dump
        target = os.path.join(outdir, "chunks", chunks_info[idx]["name"])
        out_json = os.path.join(outdir, f"dump-{chunks_info[idx]['name']}.json")
        report["dump"] = dump_chunk(target, out_json, args.hint)
        report["dump"]["chunk"] = chunks_info[idx]["name"]

    if args.text:
        try:
            r = fetch(args.url)
            md = extract_text(r.text)
            p = os.path.join(outdir, "page.md")
            open(p, "w", encoding="utf-8").write(md)
            report["text_file"] = {"path": p, "chars": len(md)}
        except Exception as e:  # noqa: BLE001
            report["text_file"] = {"error": str(e)}

    json.dump(report, open(os.path.join(outdir, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    p = page
    print(f"站点 {p.get('final_url', target)}")
    print(f"  状态 {p.get('status')} · {p.get('bytes', 0)} B · 标题 {p.get('title', '')[:60]}")
    print(f"  技术栈 {'Next.js App Router' if p.get('app_router') else '普通 SSR/静态'}"
          f"{' · 客户端渲染兜底' if p.get('csr_bailout') else ''}")
    print(f"  SSR 正文 {p.get('ssr_text_chars', 0)} 字 · chunk {len(p.get('chunks', []))} 个")
    if robots["disallow"]:
        print(f"  robots 隐藏路由（= 功能图）：{' '.join(robots['disallow'][:12])}")
    if sitemap["count"]:
        print(f"  sitemap {sitemap['count']} 条 · 语言 {'/'.join(sitemap['locales'][:6])}")
    if chunks_info:
        print("  chunk 按汉字数排序（像数据文件的排前面）：")
        for i, c in enumerate(chunks_info[:8]):
            print(f"    [{i}] {c.get('name')} · {c.get('bytes', 0)} B · {c.get('han', 0)} 汉字"
                  f"{' · 含数据数组' if c.get('has_data_array') else ''}")
    if "dump" in report:
        d = report["dump"]
        print(f"  挖出：{d.get('ok')} {d.get('items', '')} 条 → {d.get('out', d.get('error', ''))}")
    if "text_file" in report:
        t = report["text_file"]
        print(f"  正文 → {t.get('path', t.get('error'))}（{t.get('chars', 0)} 字）")
    print(f"  落盘 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
