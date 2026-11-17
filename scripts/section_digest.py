#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落盘大页 · 按章节抽段（通用版）

用途：抓取工具把整页落盘到 cache/web/ 之后，页面动辄几万字符——
     整页读回上下文等于烧掉一整轮，而且回显常是 head+tail 截断，
     被丢掉的中间段往往正是正文。本脚本只抽你点名的那几段。

用法：
    python3 section_digest.py                          # 抽默认目录下全部页面
    python3 section_digest.py <文件名子串>              # 只处理匹配的文件
    python3 section_digest.py <子串> --sections Story,Trivia,开发史
    python3 section_digest.py <子串> --dir <目录> --limit 3000

为什么不用通用正文提取器：站点结构一变（Next.js/SPA 把正文嵌进脚本 JSON），
通用提取器会静默丢掉正文；而**落盘件的章节标题是原文**，按标题切最稳。

坑（都踩过）：
  · 章节标题形态多样：`## Story`、`## Story[]`、`## Story\\[ [Sign in to edit](…)]`
    ——正则要同时兜住；只兜一种会返回「未找到目标章节」而你以为源里没有
  · 参数解析用**步进式**：`--sections A,B` 的值不能被当成位置参数，
    否则 B 会变成筛选词 → 全场零命中（这个 bug 静默、无报错）
  · 页面标题行可能缺席（缓存件被截断过／站点结构不同）→ 按内容签名认页
"""
import sys, os, re, glob


def _data_root():
    """数据根探测（可迁移/可发布）：$HERMES_ROOT ＞ $SKILL_ROOT ＞ 脚本上溯 ＞ ~/.hermes ＞ 家目录。
    命中判据：该层下存在 skills/ 目录。2026-10-16 解耦（原为写死绝对路径）。"""
    for _env in ("HERMES_ROOT", "SKILL_ROOT"):
        _v = os.environ.get(_env)
        if _v and os.path.isdir(os.path.join(_v, "skills")):
            return _v
    _here = os.path.dirname(os.path.abspath(__file__))
    _cands = [os.path.abspath(os.path.join(_here, *([".."] * _n))) for _n in range(1, 5)]
    _cands += [os.path.expanduser("~/.hermes"), os.path.expanduser("~")]
    for _c in _cands:
        if os.path.isdir(os.path.join(_c, "skills")):
            return _c
    return os.path.abspath(os.path.join(_here, "..", "..", ".."))


BASE = _data_root()  # 数据根（2026-10-16 解耦；原为写死绝对路径）


DEF_DIR = BASE + '/cache/web'
DEF_SECTIONS = [
    'Story', 'Plot', 'Gameplay', 'Characters', 'Personality',
    'New Features', 'New Features and Differences', 'Development',
    'Development history', 'Missions and Bosses', 'Stages and Bosses',
    'Versions', 'Ports', 'Reception', 'Trivia',
]


def clean(text):
    """去掉编辑按钮尾巴、链接外壳与图片，保留可读文字"""
    text = re.sub(r'\[\[\]\]\([^)]*\)', '', text)              # 空链接（编辑按钮）
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)        # 链接 → 文字
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)            # 图片
    text = re.sub(r'\*{2,}', '', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def page_name(raw, path):
    """认页：URL 行 → 标题行 → 内容签名 → 兜底文件名"""
    m = re.search(r'URL:\s*https?://[^/]+/(?:wiki/)?(\S+)', raw[:3000])
    if m:
        return m.group(1).replace('_', ' ').replace('%27', "'").split('#')[0]
    m = re.search(r'(?m)^#\s*(.+)$', raw)
    if m and m.group(1).strip() not in ('-', '?', 'Contents'):
        return m.group(1).strip()
    return os.path.basename(path)


def digest(path, sections, limit):
    raw = open(path, encoding='utf-8').read()
    name = page_name(raw, path)
    out = [f"\n{'=' * 72}\n### {name}   （{os.path.basename(path)} · {len(raw)} 字符）\n"]
    # 按 2~4 级标题切块；标题行可能带 [] / \[编辑按钮] 尾巴
    parts = re.split(r'\n(?=#{2,4} )', raw)
    seen = set()
    for p in parts:
        first = p.split('\n', 1)[0]
        title = re.sub(r'(\[\]|\\\[.*)$', '', first).lstrip('# ').strip()
        if title not in sections or title in seen:
            continue
        seen.add(title)
        body = clean(p.split('\n', 1)[1] if '\n' in p else '')
        if len(body) < 40:
            continue
        out.append(f"-- {title} --\n{body[:limit]}{'…(截断)' if len(body) > limit else ''}")
    return '\n'.join(out) if len(out) > 1 else f"\n{name}: 未找到目标章节（换 --sections，或先看标题行）"


def main():
    args = sys.argv[1:]
    sections, key, workdir, limit = DEF_SECTIONS, '', DEF_DIR, 2000
    i = 0
    while i < len(args):                      # 步进式解析：选项值不吃成位置参数
        a = args[i]
        if a == '--sections':
            sections = args[i + 1].split(',')
            i += 2
        elif a == '--dir':
            workdir = args[i + 1]
            i += 2
        elif a == '--limit':
            limit = int(args[i + 1])
            i += 2
        elif a.startswith('--'):
            i += 1
        else:
            key = a
            i += 1

    files = sorted(glob.glob(os.path.join(workdir, '*.md')))
    hit = 0
    for f in files:
        if key and key not in f:
            continue
        if os.path.getsize(f) < 1200:          # 壳页/空页跳过
            continue
        print(digest(f, sections, limit))
        hit += 1
    if not hit:
        print(f"（{workdir} 下没有匹配 {key!r} 的页面）", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
