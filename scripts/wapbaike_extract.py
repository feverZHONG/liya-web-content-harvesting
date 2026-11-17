#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百度百科（wapbaike）完整词条提取器

WHY：通用正文提取器（trafilatura 链路）对 wapbaike 这种 Next.js 页
     **只抓表格块**，正文段落（背景设定/剧情/角色设定…）整块丢失 →
     极易误判成「百科没有剧情」。wapbaike 把完整词条结构嵌在页面脚本的
     `structuredContent` 字段里，直接抠它。

用法：
    python3 wapbaike_extract.py <词条名> [--out 输出.md]
    python3 wapbaike_extract.py <词条名> --file 已存的.html --out 输出.md

判据：正文偏薄 / 全是表格 → 换本脚本；仍无 → 再 grep raw HTML 复核，
     换过通道与词条名变体之后，才允许说「源里没有」。
"""
import sys, re, json, html, subprocess, urllib.parse

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15"


def fetch(lemma):
    url = "https://wapbaike.baidu.com/item/" + urllib.parse.quote(lemma)
    r = subprocess.run(["curl", "-s", "-A", UA, "--max-time", "25", url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore")


def extract_sc(h):
    """从 HTML 里抠出 structuredContent 数组（字符串感知的括号平衡扫描）"""
    i = h.find('"structuredContent":')
    if i < 0:
        return None
    j = h.find('[', i)
    depth, in_str, esc = 0, False, False
    for k in range(j, len(h)):
        c = h[k]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(h[j:k + 1])
                except Exception:
                    return None
    return None


def node_text(node):
    out = []
    for c in node.get("content", []) or []:
        if isinstance(c, str):
            out.append(c)
            continue
        if c.get("tag") == "text":
            out.append(c.get("text", ""))
        elif c.get("tag") in ("image", "img"):
            out.append("[图]")
    return "".join(out).strip()


def walk(items, out=None):
    if out is None:
        out = []
    for it in items or []:
        if isinstance(it, list):
            walk(it, out)
            continue
        tag = it.get("tag")
        if tag == "header":
            lv = min(int(it.get("level") or 1) + 1, 6)
            out.append("\n" + "#" * lv + " " + (it.get("title") or "") + "\n")
        elif tag == "paragraph":
            tx = node_text(it)
            if tx:
                out.append(tx + "\n")
        else:
            tx = node_text(it) if isinstance(it, dict) else ""
            if tx:
                out.append(tx + "\n")
    return out


def main():
    args = sys.argv[1:]
    lemma = src = out_path = None
    i = 0
    while i < len(args):
        if args[i] == "--file":
            src = args[i + 1]; i += 2
        elif args[i] == "--out":
            out_path = args[i + 1]; i += 2
        else:
            lemma = args[i]; i += 1
    if not lemma and not src:
        print("用法: wapbaike_extract.py <词条名> [--file x.html] [--out y.md]")
        sys.exit(2)
    h = open(src, encoding="utf-8", errors="ignore").read() if src else fetch(lemma)
    sc = extract_sc(h)
    if sc is None:
        print("!! 未找到 structuredContent（页面结构变了 / 词条不存在 / 被反爬）", file=sys.stderr)
        sys.exit(1)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(walk(sc))).strip()
    m = re.search(r'name="description" content="([^"]{20,})"', h)
    md = "# " + (lemma or "词条") + "\n\n"
    if m:
        md += "> " + html.unescape(m.group(1)) + "\n\n"
    md += body + "\n"
    if out_path:
        open(out_path, "w", encoding="utf-8").write(md)
        print(f"{out_path}\t{len(md)}字")
    else:
        print(md)


if __name__ == "__main__":
    main()
