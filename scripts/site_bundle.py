#!/usr/bin/env python3
"""site_bundle.py — 把抓下来的静态站目录打包成单个自包含 HTML。

用法:
    python3 site_bundle.py <站点目录> [-o out.html] [--entry index.html]
                           [--pages all|a.html,b.html] [--quality 80] [--max-width 1400]

做什么:
  - CSS/JS 内联进 <style>/<script>
  - 图片（img src / css url()）转 data URI，可选压缩
  - 多页：外层一个 tab 导航 + 单个 iframe（每页存成模板，切换时写入 srcdoc）

为什么: 单文件可直接发人、双击打开、不依赖目录结构；且原始页面一字未改。
"""
import argparse
import base64
import io
import os
import re
import sys

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def read(p, binary=False):
    with open(p, "rb" if binary else "r", encoding=None if binary else "utf-8",
              errors=None if binary else "replace") as f:
        return f.read()


def img_to_data_uri(path, quality=80, max_width=1400):
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}.get(ext, "application/octet-stream")
    raw = read(path, binary=True)
    if ext == ".svg" or not HAVE_PIL or quality <= 0:
        return f"data:{mime};base64," + base64.b64encode(raw).decode()
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width > max_width:
            im = im.resize((max_width, int(im.height * max_width / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            im.save(buf, "PNG", optimize=True)
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        im = im.convert("RGB")
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return f"data:{mime};base64," + base64.b64encode(raw).decode()


def resolve_rel(rel, base, root):
    """相对路径解析：支持 /abs 形式（按站点根）、../、query/hash 剥离。"""
    rel = rel.split("?")[0].split("#")[0]
    if rel.startswith("/"):
        return os.path.normpath(os.path.join(root, rel.lstrip("/")))
    return os.path.normpath(os.path.join(base, rel))


def inline_one(html_path, root, args, cache, missing):
    base = os.path.dirname(html_path)
    html = read(html_path)

    def abs_join(rel):
        return resolve_rel(rel, base, root)

    # 1) 外链 CSS -> <style>
    def rep_css(m):
        tag, href = m.group(0), m.group(1)
        p = abs_join(href)
        if not os.path.exists(p):
            missing.append((os.path.basename(html_path), href))
            return tag
        css = read(p)
        css = sub_urls(css, os.path.dirname(p), root, args, cache, missing)
        return f"<style>\n{css}\n</style>"

    html = re.sub(r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>', rep_css, html, flags=re.I)

    # 2) 外链 JS -> <script>
    def rep_js(m):
        tag, src = m.group(0), m.group(1)
        p = abs_join(src)
        if not os.path.exists(p):
            missing.append((os.path.basename(html_path), src))
            return tag
        js = read(p)
        return "<script>\n" + js.replace("</script>", "<\\/script>") + "\n</script>"

    html = re.sub(r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>\s*</script>', rep_js, html, flags=re.I)

    # 3) 任意标签的 src / poster（img、source、video、audio、embed、link icon…）
    def rep_src(m):
        full, attr, src = m.group(0), m.group(1), m.group(2)
        if src.startswith(("data:", "http://", "https://", "//", "mailto:", "javascript:")):
            return full
        p = abs_join(src)
        if not os.path.exists(p):
            missing.append((os.path.basename(html_path), src))
            return full
        if p not in cache:
            cache[p] = img_to_data_uri(p, args.quality, args.max_width)
        return full.replace(f'{attr}="{src}"', f'{attr}="{cache[p]}"').replace(f"{attr}='{src}'", f'{attr}="{cache[p]}"')

    html = re.sub(r'\b(src|poster)=["\']([^"\']+)["\']', rep_src, html, flags=re.I)

    # 4) srcset（逗号分隔的候选列表）
    def rep_srcset(m):
        urls = m.group(1).split(",")
        out = []
        for u in urls:
            u = u.strip()
            if not u:
                continue
            parts = u.split()
            src = parts[0]
            desc = " ".join(parts[1:])
            if src.startswith(("data:", "http")):
                out.append(u)
                continue
            p = abs_join(src)
            if not os.path.exists(p):
                missing.append((os.path.basename(html_path), src))
                out.append(u)
                continue
            if p not in cache:
                cache[p] = img_to_data_uri(p, args.quality, args.max_width)
            out.append(cache[p] + (" " + desc if desc else ""))
        return 'srcset="' + ", ".join(out) + '"'

    html = re.sub(r'srcset=["\']([^"\']+)["\']', rep_srcset, html, flags=re.I)

    # 5) 内联 style 里的 url()
    html = re.sub(r'url\((["\']?)([^)"\']+)\1\)',
                  lambda m: m.group(0) if m.group(2).startswith(("data:", "http", "//")) else
                  (f'url({cache.setdefault(abs_join(m.group(2)), img_to_data_uri(abs_join(m.group(2)), args.quality, args.max_width))})'
                   if os.path.exists(abs_join(m.group(2))) else m.group(0)), html)
    return html


def sub_urls(css, css_dir, root, args, cache, missing):
    def rep(m):
        u = m.group(2)
        if u.startswith(("data:", "http://", "https://", "//")):
            return m.group(0)
        p = resolve_rel(u, css_dir, root)
        if not os.path.exists(p):
            missing.append((os.path.basename(css_dir) + "/", u))
            return m.group(0)
        if p not in cache:
            cache[p] = img_to_data_uri(p, args.quality, args.max_width)
        return f"url({cache[p]})"
    return re.sub(r'url\((["\']?)([^)"\']+)\1\)', rep, css)


PAGE_WRAP = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
 html,body{{margin:0;height:100%}}
 .bg-tabs{{position:fixed;left:0;right:0;bottom:0;z-index:9999;display:flex;gap:6px;
   padding:8px 10px;background:rgba(12,14,18,.92);backdrop-filter:blur(8px);
   font:13px/1.4 -apple-system,"PingFang SC",sans-serif;overflow-x:auto}}
 .bg-tabs button{{flex:0 0 auto;background:#1b2029;color:#c9d3e0;border:1px solid #2a3240;
   border-radius:6px;padding:6px 14px;cursor:pointer}}
 .bg-tabs button.on{{background:#e05c5c;border-color:#e05c5c;color:#fff}}
 iframe{{width:100%;height:100%;border:0;display:block}}
 body{{padding-bottom:46px}}
</style></head><body>
<iframe id="f" srcdoc=""></iframe>
<div class="bg-tabs">{buttons}</div>
<script>
const PAGES={pages};
function show(k){{document.getElementById('f').srcdoc=PAGES[k];
 document.querySelectorAll('.bg-tabs button').forEach(b=>b.classList.toggle('on',b.dataset.k===k));}}
document.querySelectorAll('.bg-tabs button').forEach(b=>b.onclick=()=>show(b.dataset.k));
show('{first}');
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("-o", "--out")
    ap.add_argument("--entry", default=None, help="单页模式：只打包这一页")
    ap.add_argument("--pages", default="all", help="多页模式：all 或逗号分隔")
    ap.add_argument("--quality", type=int, default=80, help="JPEG 质量，0 = 不压缩")
    ap.add_argument("--max-width", type=int, default=1400)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.site)
    if not os.path.isdir(root):
        sys.exit(f"不是目录: {root}")

    cache = {}
    missing = []
    title = args.title or os.path.basename(root)

    if args.entry:
        out_html = inline_one(os.path.join(root, args.entry), root, args, cache, missing)
    else:
        pages = args.pages
        if pages == "all":
            pages = [f for f in sorted(os.listdir(root)) if f.endswith(".html")]
        else:
            pages = [p.strip() for p in pages.split(",") if p.strip()]
        if not pages:
            sys.exit("没找到 html 页")
        # 首页优先：index.html 放最前（否则按字母序会先开 bind.html）
        if "index.html" in pages:
            pages.remove("index.html")
            pages.insert(0, "index.html")
        import json
        data, buttons = {}, []
        for p in pages:
            fp = os.path.join(root, p)
            if not os.path.exists(fp):
                print(" 跳过（不存在）:", p, file=sys.stderr)
                continue
            print(" 内联:", p, file=sys.stderr)
            data[p] = inline_one(fp, root, args, cache, missing)
            buttons.append(f'<button data-k="{p}">{p.replace(".html","")}</button>')
        # 塞进 <script> 前必须转义：</script>、U+2028/2029 都会炸 JS 字符串
        pages_json = json.dumps(data, ensure_ascii=False)
        pages_json = (pages_json.replace("<", "\\u003c")
                                .replace("\u2028", "\\u2028")
                                .replace("\u2029", "\\u2029"))
        out_html = PAGE_WRAP.format(
            title=title,
            buttons="".join(buttons),
            pages=pages_json,
            first=pages[0],
        )

    out = args.out or os.path.join(root, "..", os.path.basename(root) + "-bundle.html")
    out = os.path.abspath(out)
    with open(out, "w", encoding="utf-8") as f:
        f.write(out_html)
    size = os.path.getsize(out) / 1024 / 1024
    print(f"✅ {out}  ({size:.1f} MB)  图片缓存 {len(cache)} 张", file=sys.stderr)
    if missing:
        uniq = sorted(set(missing))
        print(f"⚠️ {len(uniq)} 处引用未命中（原样保留；多为外链或漏抓）:", file=sys.stderr)
        for f, r in uniq[:12]:
            print(f"   {f} -> {r}", file=sys.stderr)


if __name__ == "__main__":
    main()
