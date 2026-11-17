---
name: web-content-harvesting
tier: T2  # T分级: T2=直接做 / T1=先请示 / T0=一律拒
description: 正文抓薄或数据藏在JS/交互里要扒结构时用。RSC·chunk挖掘、多通道复核、落盘抽段。
---

# 网页内容全量收割

> 定位两件事：① 通用正文提取器**失手之后**怎么救；② **一开始就不该交给它的活**——页面数据在 RSC / chunk / 交互流程里（题库、配置、逐条文案、算法）。
> 事前分诊：**要一段连续正文 → 先用通用正文提取器；要字段/逐条/公式 → 直接从这儿开始，别绕。**
> 铁律：**工具没抓到 ≠ 源里没有。** 先质疑提取器，再下「无证据」的结论。

## 读者须知（工具与环境）

文中 `read-url` 是作者环境里那个「取正文」的提取器（**未单独公开**），读者换自己手上那支即可——本档讲的都是「它失手之后怎么办」的判据，与具体实现无关。`bin/…` 形式的命令请改走本仓 `scripts/` 下同名脚本（例：`python3 scripts/siteprobe.py <url>`）。示例里的日期读作「某次实测样本」，站点名只作型别举例。

## 一、先判「该不该走这里」

出现任一条 → 当场改道（别先用正文提取器试一轮）：

- 页面是**结构化的**：题库、商品表、关卡表、报告、报价——你要的是字段与条数，不是段落
- 页面是**跑一遍才出结果**的：测验、计算器、报告页（要判「这测验准不准／收不收数据」→ 见「测验页再往前一步」小节）
- 你想拿的是**全站清单**（所有类型 / 所有条目），而不是某页内容

已经在正文提取器上跑过的，出现下面任一条 → 进第二节：

- 返回**几乎全是表格**（数值/武器/曲目表），没有段落
- 字数明显偏薄（百科词条 < 2k 字、wiki 游戏页 < 5k 字）
- 只拿到目录/导航壳，正文缺席

## 二、升级路径（按序试，别跳步）

1. **raw HTML 一秒证伪**——成本最低，先做：
   ```bash
   curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)" "<url>" -o x.html
   grep -c "<关键词>" x.html
   ```
   关键词在 HTML 里出现（哪怕一次）就证明是提取器丢了正文，不是源里没有。
   **1·补 短链／分享跳转页：目标 URL 在正文里，不在响应头。** 这类页（`m.x.com/h.<code>`、`t.cn/xxx`、各大 App 的分享链）`curl -I` 返回 **200 且完全没有 `Location`**，看着像死链，实际正文里写着 `var url = '...'` / `window.location.replace("...")`——把那行 grep 出来就是真目标（一条链接能同时告诉你目标页面、业务类型和附带的 token）。
   ```bash
   curl -sL "<短链>" -o page.html
   grep -oE "var url = '[^']*'|window\.location[^;]*" page.html | head
   ```
   判据：**别先上浏览器**；只有当正文里既没有目标 URL 又是纯 JS 拼装时才走 Playwright 拦网络请求。目标里带 ID 的顺手拆出来（店铺 ID / 商品 ID / 专辑 ID），后续问接口或搜名字都有了锚点。
2. **抠结构化数据**——现代内容站（Next.js/SPA）把正文嵌在页面脚本的 JSON 里：`structuredContent`、`__NEXT_DATA__`、`__NUXT__`、`application/ld+json`。写个小抠取器（括号平衡扫描定位数组 → `json.loads` → 按节点 tag 还原 markdown），比任何通用正文提取器都准。现成件：`scripts/wapbaike_extract.py`（百科 `structuredContent`）
   **多语言站/产品官网先找语言包（比 chunk 更好挖）**：正文常整块放在 `/langs/<locale>.js`、`/i18n/`、`/locales/`、`/js/lang/`，形如 `const zhCN = { home: {...}, news: { items: {...} } }` 的对象字面量——新闻全文、界面文案、版本说明、配置需求全在里面，纯文本可直接 grep 中文串。抓之前**把几个语种各打一次看体量**：实测某游戏官网 `zh-CN.js` 16KB 载全部新闻正文，同站 `en-US.js` 只有 436B 空壳——只抓英文版会误判「站里没内容」。语言包路径常写在入口 HTML 的 `config.js`／`i18n.js` 里（`file: 'zh-CN.js'` + `langPath` 拼接）。
   **Next.js / SPA 站：一条命令，别手工重跑这条链。**
   ```bash
   python3 scripts/siteprobe.py <url>          # 体检：技术栈 / robots 路由图 / sitemap / SSR 正文字数 / chunk 数
   python3 scripts/siteprobe.py <url> --page /quiz --chunks  # 探指定路由，下载它的 chunk 并按汉字数排序（数据文件排前面）
   python3 scripts/siteprobe.py <url> --page /quiz --dump 0  # 把第 [0] 个 chunk 里的数据数组挖成 JSON（--hint 换关键词）
   python3 scripts/siteprobe.py <url> --text   # SSR 正文落 md（比 read-url 多拿列表/小标题）
   ```
   它内部就是「带 UA 抓 HTML → 读 robots/sitemap → 列 chunk → 汉字数排序 → 括号平衡取数组 → node 求值」。**只有当它挖错数组**（用 `--hint 'title:'` 指定）**或要走交互层**（Playwright 跑流程）时，才翻 `references/nextjs-app-router.md` 手动做。
   **要整库（图鉴/词条列表/商品表）时，先找接口，别抠 payload**：SSR 页面里的 `__NUXT_DATA__` 是 devalue 扁平数组（值是索引指针），手写递归解遇循环引用就炸，而且只装首屏那几十条。顺序是 ① grep 入口 HTML 的运行时配置（`webApiBaseUrl`／`apiBaseUrl`／`public.*BaseUrl`）拿 API 主机 ② grep `_nuxt/*.js`／`_next/static/chunks/*.js` 里的 `getHome`／`getEntries`／`fetch(` 拿路由模板 ③ 按列表接口的分页参数循环到底，逐分类用 `total` 对账。实例见 `references/site-recipes.md` 游民星空图鉴条。
   **2·补2 正文根本不在文字里，而是一张长图**：官方宣传页／「档案大公开」类帖子正文常常只有一句「点击下方图片查看」，真内容是一张宽几百、高近万像素的 JPG（实测 473×9999）。正文提取器与纯文字 OCR 都空手——做法：`curl` 带 `referer` 落到本地 → PIL 按 ~1800px 竖切（相邻片留 80px 重叠，防一行字被切断）→ 逐片 `vision_analyze` 转录。**图里的小字（颜色／数值对照表、脚注）不许照抄进档**：切片 OCR 在密集小字上最容易整列错位，标「以原图／游戏内为准」；正文段落与小标题可以放心转。
   **三个静默坑，只有对账才发现**：① 分页键必须实测——候选（`cursor`／`after`／`page`／`nextCursor`）各打一次并比对返回条目的 id，「参数被忽略」与「只有一页」在响应里长得一模一样（都是 200＋第一页），看状态码永远判不出来；② 渲染出的目录不是清单——`visibleOnNavigation:false`／首页不展示的分类，接口照样给数据，遍历要按接口的 `categories` 全量走，别拿页面上看得见的导航项当全集；③ **分享页／移动 H5 预览页不是全集**——`t1.x.com/album.html?id=…`、`m.x.com/share/…` 这类分享链常把条目截到整数上限（20／50），页面**没有任何「还有更多」的提示**，`web_extract` 也照样返回一份排版完整、看不出缺口的清单。拿它当全集会连着犯两个错：漏掉后半数，以及**据此下否定判断**（「这张专辑没有那首」「这个歌单不收这首」）。正确顺序：从预览页／搜索接口反查对象的正式 id → 走该对象的列表接口 → **`total` 与返回条数逐个对账**，不等就 `pagesize=-1`／循环分页拉到底。否定判断（「X 不在这个库里」）之前必须先对上 `total`——这类错误是静默的，页面上永远看不出来。
3. **换通道——两个轴：出口，和客户端**。命令行 `curl` 不通（连不上 / 000）**不等于拿不到**：不同抓取通道出口不同。实测：某 wiki 站 `curl` 000 而 `web_extract` 工具通道可达；百科主域 403 而 wapbaike 可达。**判死一个源之前，至少换一次通道。**
   **反方向同样成立，而且更常撞上**：以 `requests` 为底的提取器返 **403** 时，**同一 URL、同一台机器用 `curl` 直抓往往是 200**——客户端有别（TLS 指纹 / header 组合），403 说的是「这条路不行」，不是「这个源不给」。判别法：拿同一 URL 分别用两个客户端各打一次，看状态码分不分岔；分岔就上**降级链**：提取器 → `curl` 抓 HTML 落到临时文件 → 让提取器读**本地文件**净化（本地读不涉网络，必不被拦）。
   附带的假象：`probe` 类「只探存在性」的命令若本来就走 curl，会出现**「probe 通、抓正文挂」**——那是通道差，不是词条不存在，别据此删档或判死源。
   **做通道对照前先看 stderr 确认真走了哪条路**：带降级链的提取器（如 `read-url --ds` 这类）失败时会**静默退回本地提取**，stdout 与默认通道逐字相同——两路输出一致最容易把「退回」误读成「无差别」。加 `-v` 看到「→ 通道失败，退回本地提取」就重跑或改走 HTML 解析。
   ⚠️ **降级链的临时文件必须按输入取唯一名**：固定路径 + 下游提取器带文件缓存（`read-url` 有 5 分钟文件缓存）= **静默串档**——抓第二个输入时提取器直接回上一次的缓存，把 A 的正文写进 B 的定义。修法：临时名按 URL 取哈希 + 显式 `--no-cache`；批量抓取至少抽一个**验首句**（串档不报错、格式也正常，只有看内容才认得出）。
   **3·补 带签名/时间戳校验的接口：直连必挂，走「页面自己算好参数」那条路。** 现代站的内部 API 常校验时间签名，裸 `curl` 回 **418 / `Request expired` / `sign invalid`**——这不是被封，是缺参数，**别去手算签名**。正确做法：Playwright 打开**页面**（不要直接开 API URL），`page.on("response", …)` 拦 `url` 含接口名的响应、`resp.json()` 拿走结构化正文；浏览器里的请求参数（含时间戳、session）由页面 JS 自动生成。要点：① 拦的是**响应**不是请求，重复请求也能命中；② 内容字段常是 HTML（如 `content`），剥标签转文本再落档；③ 顺手记元数据字段（发布时刻 `ctime`、序号 `num`／「第 N 次更新」、赞／评数），它们日后是「这条信息到底什么时候发的」的唯一硬锚；④ 渲染前给固定超时（6–10 s）＋ 拿不到就回落到 `inner_text`，别死等 `networkidle`。站点实例（摩点众筹项目更新页）见 `references/site-recipes.md`。

4. **换词条名 / 换入口**——百科类试等价词条名（「<系列>1」vs「<系列>」）；**同名条目别靠搜索**（「米拉」既是柯南角色又是游戏角色）：百科直读工具会静默命中另一个义项，而输出看上去像一条完整词条——用带数字 id 的 URL `.../item/<名>/<id>` 直读，并核返回标题是不是本词条；系列类先确认**总条目 vs 独立条目**各自的覆盖面（总条目的「衍生作品 / 角色介绍」段常比独立词条更全，反之亦然）。
5. **作品页只写到开场 → 换「页的角色」，不是换站**：游戏／影视类条目与 wiki 的剧情段**普遍只到开场简报**，结局／最终 BOSS 的归属与胜负**大多不载**。别据此判「没有结局」，改从**最终 BOSS 页**（写它怎么被打倒、之后如何）**＋关键角色页**（写它各代的下场）**＋关卡与 BOSS 清单段**反推——按这条能把整条作品线的结局补齐，比在作品页里翻省事得多。同理：角色页的「Personality / Trivia」段是人物性格与设计原型的富矿，作品页往往一个字不提。

## 三、大页别读回上下文

- 抓取工具的回显常是 head+tail 截断，**被丢掉的中间段往往正是正文**；完整页会落盘（形如 `cache/web/<host>-<hash>.md`）
- 正确姿势：**落盘 + 按章节抽段**（只取 Story / 背景设定 / 开发史…）——单页 4~6 万字符，整页回上下文等于烧掉一整轮
- **抓之前先定「我要哪几段」**，别先抓后想

## 四、落档与结论纪律（速记 · 全文见 `references/落档与结论纪律.md`）

- 抓到的原文先落盘，结论另起一段；**别把摘要当原文**。
- 引用带 URL＋抓取日期；数字、名单、时间要回原文核。
- 抓不到就写「抓不到／被墙／需登录」，不拿旧快照冒充当前。
- 页面结构与抓取路径写进档，下次复现不靠记忆。

## 四·五、整站打包成单文件（`scripts/site_bundle.py`）

把抓下来的静态站目录打成**一个自包含 HTML**：CSS/JS 内联、图片转 data URI（可压）、多页底部 tab ＋ iframe 切换。

```bash
site-bundle <站点目录> -o out.html [--quality 78] [--max-width 1400]
site-bundle <站点目录> --entry index.html            # 只打单页
site-bundle <站点目录> --pages index.html,faq.html   # 指定页
```

**通用面（不只适合本站）**：
- 标签属性全覆盖：`src`／`poster`／`srcset`（逗号列表）／`<link rel=icon>`／`<video>`／`<source>`；CSS 里 `url()` 与内联 `style` 同处理。
- **路径两种都认**：相对路径（`assets/x.png`、`../x.png`）与**站点绝对路径**（`/assets/x.png`，按站点根解析）——抓站工具常把后者原样存下，不认就会大片破图。
- 自动剥 `?query`／`#hash` 后再找文件。
- 跑完打两行账：命中缓存张数 ＋ **未命中清单**（最多 12 条）——`⚠️ 0 处`才是干净包。

- 多页模式默认 `index.html` 排第一（否则字母序会先开 `bind.html`）。
- **两个必踩的坑（2026-10-20 实测）**：① 页面 HTML 塞进 `<script>` 前必须把 `<` 转义成 `\u003c`，否则内容里的 `</script>` 会提前闭合 → `Uncaught SyntaxError`、整页白屏；② U+2028/2029 同理，一并转义。
- 体积参考：17 MB 图站，完整包约 13.7 MB；`--quality 62 --max-width 1000` 压到 7.4 MB（够发 IM）。
- 验收三条：`⚠️ 0 处未命中`、无残留 `src="assets/..."`、headless 截首屏不白屏。

## 五、踩坑

- **Playwright 报 `Executable doesn't exist at …/chromium_headless_shell-<rev>`＝装的浏览器与库期望的版本号不一致**：别想着往浏览器目录里建软链（那目录常是 root 属主，软链会被拒）——`p.chromium.launch(executable_path="<已装的 …/chrome-headless-shell-linux64/chrome-headless-shell>")` 直接指二进制；探针脚本把 `executable_path` 写成「存在则用、不存在则默认」的兜底，换机器不用改代码
- **批量改档：先求值、后写盘**——`open(p,'w').write(build(t))` 会先截断文件再求值，`build()` 一抛异常（常见：锚点没匹配上）文件就留下 **0 字节**，且不报错。写法固定为 `out = build(t)` → 确认无异常 → `open(p,'w').write(out)`；已被截断的文件用 `git checkout -- <path>` 回上一版重做，别凭记忆重写
- **锚点必须与标题全字匹配**：`## 一、两人（原文）` 不能用 `## 一、两人` 匹配；锚点从目标文件的 `grep '^## '` 输出里抄，不凭印象写
- 长 python **别用 `python3 - <<'EOF'` 直接喂 shell**——内容会被安全扫描当命令文本解析、容易误拦；先 `write_file` 落成 `.py` 再跑（顺带可复用、可重跑）
- 章节定位正则要同时兜多种标题形态：`## Story`、`## Story[]`、`## Story\[ [Sign in to edit](…)]`
- 抽段脚本的参数解析用**步进式**（`--sections` 后跟的值别和位置参数抢），否则 `--sections A,B` 会把 `B` 吃成筛选词 → 全场零命中
- 抓取失败先自检**路径 / 参数 / 编码**，再怀疑站点

## 支持文件

- `scripts/wapbaike_extract.py`——百度百科（wapbaike）完整词条提取器：抠页面嵌的 `structuredContent`，还你被通用提取器丢掉的正文段落
- `scripts/siteprobe.py`（`python3 scripts/siteprobe.py`）——Next.js/SPA 扒站一条命令：站点体检（技术栈/robots 路由图/sitemap/SSR 正文字数）＋ `--chunks` 按汉字数排 chunk ＋ `--dump N` 括号平衡挖数据数组（node 求值成 JSON）＋ `--text` 抽 SSR 正文
- `scripts/section_digest.py`——落盘大页**按章节抽段**：单页几万字符只取你点名的几段（Story／开发史／Trivia…），不把整页读回上下文；带多形态标题正则与步进式参数解析
- `references/site-recipes.md`——站点配方与通道矩阵（百科 / Fandom wiki / 游民星空 game-wiki 图鉴 / 系列总条目）
- `references/nextjs-app-router.md`——Next.js App Router 站：RSC payload 取正文、从 chunk 挖题库/配置（**数组锚点要连开头的 `[` 一起定、挖完先对条数与形状**）、Playwright 跑交互拿结果页（含路由与 URL 参数反查）
- `scripts/quiz_audit.js`——娱乐测验页复核一条命令：外发通道扫描 ＋ 题库/角色向量求值 ＋ 每维覆盖 ＋ 百分比函数（是不是名次写死）＋ 蒙特卡洛分辨率与头部集中度
- `references/quiz-scoring-audit.md`——测验页判读尺子：安全面怎么判、数据面为什么不能正则抠、三个判据的阈值表、结论怎么写

## 拆分记录

- 2026-11-10：「四、落档与结论纪律」整节搬 `references/落档与结论纪律.md`；本文 9,363 → 7,552 字符，守恒 0 缺失。
