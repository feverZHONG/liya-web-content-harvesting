# Next.js App Router 站：正文与数据都不在 HTML 里

> 通用净化器在这一类站上只有两种表现：抓到壳（一堆导航/页脚）或抓到 0 字。**这不是源里没有，是正文根本没写进初始 HTML。**

## 判据（什么时候走这条路）

- 净化器返回 0 字或只剩导航/页脚，但 HTML 体积不小（30KB+）
- HTML 里出现 `BAILOUT_TO_CLIENT_SIDE_RENDERING` —— 这一段被标成「客户端渲染兜底」
- 找不到 `__NEXT_DATA__`（App Router 已不用它）
- 页面是「跑一遍流程才出结果」的形态（测验、报价、报告）

区分两种失败：**抓得到但抓不全 → 补块（第 1 层）；抓不到 → 才上 Playwright（第 3 层）。**

## 三层挖掘，由浅入深

### 第 1 层：RSC payload（最快，先试这个）

App Router 把整棵 React 树流式推入 `self.__next_f.push([1,"…"])`。文本节点按出现顺序拼起来就是页面正文，而且**比净化器多出整块**（语言入口、口号行、列表入口、正文段落）。

```python
import re
html = open('page.html', encoding='utf-8', errors='replace').read()
blocks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
s = blocks[0].encode().decode('unicode_escape')   # 粗略反转义
```

- 文本节点形如 `["$","p",null,{"children":"…"}]`：直接按序取中文字符串即可；要层级就看节点的 tag/className
- 大页会有多个 push 块，全部拼接再取
- `unicode_escape` 对 emoji 会出问题（拆成代理对）；要精确就用 `json.loads('"' + block + '"')`

### 第 2 层：静态 chunk 里的数据字面量

题库、类型表、配置常量常直接写成 JS 数组躺在 `/_next/static/chunks/*.js`。不用逆向 webpack：**找到数组起点，括号平衡切出来，交给 node 求值。**

先走现成命令——`python3 scripts/siteprobe.py <url> --page <路由> --chunks` 定位 chunk、`--dump N` 直接落 JSON；下面这段只在它挖错数组（`--hint` 换关键词）或没有 CLI 时手写。

```python
# 1) 找起点：把开头的 [ 一起锚定
#    只搜 id:"Q01" 再取它后面第一个 [，会撞进同一条目内的嵌套数组（options:[...]），
#    挖出来是 4 个选项却当成「题库」——能解析、不报错，静默取错对象
i = s.index('[{id:"')      # JS 字面量 n=[{id:"Q01",...；key 带引号时搜 '[{"id"'
# 2) 括号平衡扫描（必须跳过字符串内的括号）
depth = 0; instr = None; esc = False
for j in range(i, len(s)):
    ch = s[j]
    if instr:
        if esc: esc = False
        elif ch == '\\': esc = True
        elif ch == instr: instr = None
        continue
    if ch in '"\'`': instr = ch; continue
    if ch == '[': depth += 1
    elif ch == ']':
        depth -= 1
        if depth == 0: end = j + 1; break
# 3) 交给 node 求值成 JSON
open('q.js','w').write('const n=' + s[i:end] + ';console.log(JSON.stringify(n))')
# node q.js > q.json
```

- **挑 chunk 用汉字数筛**：`len(re.findall(r'[\u4e00-\u9fff]', s))`；别用 `grep '[一-龥]'`（C locale 下报 `Invalid collation character`，一律 0 命中，看不出是坑）
- 首页 chunk 不多时全下回来逐个筛，比在浏览器 network 面板里翻快
- node 求值只适合**纯数据字面量**；数组里有函数/template literal 就换第 3 层
- **取完先对条数与形状，别只看「JSON 能解析」**：套出来的可能只是条目内部的子数组（选项、标签、章节）。拿页面自报的数量与字段核一遍——页面说 42 题、挖出 4 条，就是挖到 options 了；对不上换锚点重挖，别把错数组写进档（这类错不抛异常，格式还正常）

### 第 3 层：Playwright 跑一遍交互

数据由服务端算、或只在结果页出现时，跑真流程。

```bash
cd <你的工作目录> && PLAYWRIGHT_BROWSERS_PATH=<浏览器缓存目录> python3 run.py
```

- **启动必须带 `PLAYWRIGHT_BROWSERS_PATH`**（指向你自己装的浏览器目录；默认路径指向别处会报 `Executable doesn't exist`，看着像包坏了，其实只是路径）
- 监听 `response`，把 `/_next/static/chunks/*.js` 全落盘——**新路由的 chunk 只在进入该路由时才加载**，不监听就永远拿不到结果页的代码
- 监听 `/api/*`：若结果页没有 API 调用，说明数据是 SSR 算好塞进 RSC 的（那就回头用第 1 层解析结果页 HTML）
- 走完读 `localStorage`：会话码/结果码/草稿常在这里，比翻 DOM 稳
- 流程页常有**过渡页**（「PART n」「繼續」）：每轮先清过渡页再等目标选择器，别假设选完就自动出题
- 表单/测验类：允许时先用「跳过」「测自己」这类中性项，省掉填昵称

## 路由与参数：别猜

- `robots.txt` 的 `Disallow` 列表就是隐藏路由图（`result` / `share` / `report` / `couple` / `premium` / `api`）——比 sitemap 有用
- `sitemap.xml` 给的是公开页，且 `hreflang` 标出所有语言前缀（`/en` `/zh-CN` …）；要全量就按它抓，别只抓默认语言
- SPA 路由可能既不在 sitemap 也不在 HTML 的 `href` 里（按钮跳转）→ 直接对码表打：`/quiz` `/result` `/share` `/<type>/<slug>`，看 200 vs 404
- **结果链接的 query 参数从代码里反查**：搜 `buildUrls` / `new URL(` / `searchParams.set`。猜错参数会返回 200 的落地页（看着成功、内容不对），最难发现

## 坑

- 这类站**慢**：单页 10s+ 常见，批量抓要重试 2~3 次并把 timeout 放到 45s；`curl` 抓 SSR 结果页常超时，真实浏览器却能打开（SSR 计算慢，浏览器会等）
- 502 是间歇性的，重试就好——别据此判站挂了
- **一次失败不算判据**：0 字、超时、502 都可能是瞬时的。要把「某通道只抓到 N 字」写进档，先复跑两次（`read-url -v` 的 stderr 会说明这一轮走了哪条路）；单次结果写进文档，下次照它对账就全错。
- **读到算法就复现一遍，才算读懂**：把源码里的常量与公式在本机重算，输出要能与页面实跑闭合（同一题库＋同一套挑题规则 → 必然算出同一条卷子）。闭合了才写「已复现」；没闭合就写「未复现／推断」，别把推断当结论写进档。
- 同一份数据可能既在 RSC 又在 chunk 里：拿渲染结果对一遍源数据能顺带验算（页面显示的分数 vs 题库权重）

## 别做

- 别把净化器的「提取失败」当「源里没有」（本 skill 的铁律）
- 别一上来就 Playwright：RSC 一层十有八九就够，快十倍
- 别用 `grep` 的字符类筛中文（locale 坑）
