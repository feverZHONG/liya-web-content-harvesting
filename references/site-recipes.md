# 站点配方与通道矩阵

> 只在遇到对应站点时看。每条都是「通用提取器在这里为什么失手 + 换成什么」。

## 通道矩阵（同一台机器上不同出口，结论不同）

| 目标 | `curl` 直连 | 工具通道 `web_extract` | 备注 |
|:--|:--|:--|:--|
| Fandom wiki（游戏/动漫类） | ❌ 000 | ✅ 可达，完整页落盘 `cache/web/<host>-<hash>.md` | 判死 wiki 前必试工具通道 |
| wapbaike.baidu.com | ✅（需移动 UA） | ✅ | 主域 `baike.baidu.com` 403，走 wapbaike |
| 萌娘百科 | ✅ 但连发即 403 | — | 分批发、留间隔，冷却后可单发重试 |
| 摩点 modian.com（项目/更新） | ⚠️ 项目页 ✅（SSR）；更新详情 ❌ 418 | — | 更新详情走 Playwright 截获接口，见下 |

**通则**：`curl` 不通 ≠ 拿不到。换通道再判死；把「哪个通道可用」写进档案，下次不用重试。

## 两个通道并排跑时怎么判

- 判据不是字数百分比，是**丢了哪些块**：SPA 站上常是整段消失（语言切换入口、口号行、列表入口、正文段一起没）
- 也看「多出来的是不是有信息量」——数字涨了但多出来的是导航/页脚，等于没赢
- 整页只剩壳（净化器 0 字、正文全在 chunk）时两边都救不了 → 不只是换通道的事，走 `nextjs-app-router.md`

## 摩点（Modian，众筹平台）

- **为什么不直连**：更新详情走内部接口 `apim.modian.com/honor/product/update_detail?id=<更新id>`，它**校验请求时间签名**：裸 `curl` 稳定回 `{"status":20000,"message":"当前手机系统时间不准确…","sys_msg":"418 Request expired"}`。**不是封 IP、不是缺 cookie**，是缺页面 JS 现算的参数——别去手算签名，也别把 418 当「页面没了」。
- **正路（更新详情）**：Playwright 打开 `https://www.modian.com/project/update/detail/<id>`，`page.on("response", h)` 拦 `url` 含 `update_detail` 的响应 → `resp.json()`。一次就拿全：`content`（HTML 正文）、`title`、**`num`＝「第 N 次更新」**、**`ctime`＝发布时间**、`like_count`／`comment_count`、`pro_id`／`pro_title`。`num` 与 `ctime` 是「这条公告到底什么时候发的」的唯一硬锚，归档必记。
- **项目页**：桌面 **SSR 已直出**金额／进度／支持者／全档位实销 —— `curl https://www.modian.com/project/<id>.html`（301 → `zhongchou.modian.com/item/<id>.html`）即可，只有取不到才上渲染。榜单 `https://zhongchou.modian.com/{games,all}/top_money/all` 同样 SSR。
- **移动页 `m.modian.com` 是 SPA 壳**，`apim` 直连仍 418 —— 别在那条路上反复试。
- **提取后**：`content` 里 `<p>`／`<br>` 转换行、剥标签、`html.unescape`；长 QA／公告按「节标题＋Q 编号」拆节，别整篇倒回上下文（实测一份 48 问 QA 原文 27KB，只需交分节摘要）。

## 百度百科（wapbaike）

- **症状**：词条返回 1~2k 字、**全是表格**（数值/武器/曲目/载具表），`背景设定` / `剧情` 段落整块消失
- **机理**：wapbaike 是 Next.js 页，通用正文提取器只抓到表格容器；完整词条结构嵌在页面脚本的 `structuredContent` 字段（header / paragraph / text / 图片节点）
- **正路**：`scripts/wapbaike_extract.py <词条名> [--out x.md]`
- **旁证技巧**：曲目表可当剧情旁证——BGM 里出现 `Good ending` / `Bad ending` ＝该作有双结局；`Final Boss First Half` 类曲名能补 BOSS 阶段结构
- 百科「背景设定」普遍**只写到开场简报**，结局/最终 BOSS 常不载 → 结局另找（见下节）

## Fandom wiki

- **机理**：完整页由工具通道抓回，但回显是 head+tail 截断，**被丢掉的中间段正是 Story** → 必须从落盘文件取
- **标题形态不统一**：同一站同时存在 `## Story`、`## Story[]`、`## Story\[ [Sign in to edit](…)]`——定位正则三种都要兜
- **正文位置**：页面**第二个 `# <页面名>`** 之后（首个是导航壳）；正文之前的 `## Contents` 是目录
- **抽段**：写个 digest 脚本从落盘页里只取需要的章节（`--sections Story,New Features`）；脚本参数用步进式解析
- **归档去重**：缓存文件名是 hash，同页常有多个副本——按正文里的 URL/标题识别页面，保留最长版本
- **价值排序**：游戏页（结局/双结局描述 + BOSS 表 + 开发史）＞ 角色页 ＞ 组织/阵营页 ＞ Trivia（花絮）
- **结局缺口补法**：游戏页的「Missions and Bosses」表 + 结局描述段是首选；角色页补人物线；仍缺的才回到游戏内结局字幕（录像/字幕工具）

## 游民星空 game-wiki 图鉴（`gamersky.com/tools/game-wiki/wiki/<id>`）

- **别解析页面数据**：站点是 Nuxt 3，页面内 `__NUXT_DATA__` 是 devalue 扁平数组（值是索引指针），手工递归解会在循环引用/越界上翻车——**直接走后台接口**，结构干净得多。
- **找 base**：`curl` 页面 HTML 后 grep `webApiBaseUrl` → `https://renderer.gamersky.com/gameWiki/web`（runtimeConfig 内联在 HTML 里；只探 base 根路径会 404，别据此判接口不存在）。
- **找路径**：抓 `_nuxt/*.js` chunk，grep `getHome` / `getEntries` 找 `$fetch` 拼路径那段。实测三件套：
  - `GET /wikis/{wikiId}/home` → `data.wiki.categories[]`（id/name/enabled/visibleOnNavigation）
  - `GET /wikis/{wikiId}/categories/{catId}/entries?cursor=<nextCursor>` → `items[]`＋`total`＋`nextCursor`（每页 20 条，**参数名是 `cursor`**，`page`/`after` 会被忽略并静默返回首页）
  - `GET /wikis/{wikiId}/entries/{entryId}` → `entry.moduleValues[*].html` 是正文，模块标题在 `entry.modules[]`（`type`＋`title`）
- **分页必对账**：`items` 累加数与 `total` 逐个分类比对，差数就是漏页；`visibleOnNavigation:false` 的分类照样能取（隐藏分类，最容易被漏掉）。
- **正文形态**：书籍类的全文在「书页内容」模块（单条可达 3k 字），物品/敌人是「介绍」「背景故事」「记忆对话」——这类是游戏内文本，比摘要权威。
- **设定层 / 机制层按模块标题切开**：设定＝`背景故事`／`书页内容`／`记忆花瓣`／`介绍`；机制＝`能力属性`／`初始用法`／`升级效果`／`铸魂`／`获取方法`／`作用效果`／`打法攻略`／`区域`。做资料库时前者进正文、后者只留原件（实测一款游戏 506 条：可读 29.5 万字，其中设定层 13.2 万、机制层 8.3 万）。
- **多形态要按角色合并**：同一角色的多条 BOSS 条目（本体／银发／改造形态）在映射表里必须归一个档；`X：形态名` 的尾段不一定是人名（`「玉琮」：寒冰` 是形态名）。不合并会把一个角色拆成四五个档。
- **模块标题对不上就别猜**：`modules[].id` 是 int、`moduleValues` 的 key 是字符串——照 `{m["id"]: m}` 建表后 `mods.get(mid)` 全部落空，md 小节标题会变成一串 13 位数字（正文没丢、分类全废，肉眼看内容才认得出）。建表两端都 `str()` 取 key，并留一个「从原件重生成 md」的入口（`--rebuild-md`），改渲染逻辑后不必重抓。
- **图别进仓库**：封面/立绘一条一张，500 条量级就有 10MB+。索引只存 `coverUrl`，图片放本地并 gitignore，重跑 `--images` 随时补——归档件照样能复现。
- **抓法**：一个脚本搞定「分类→全条目→详情」，6 并发约 100 条/分，落 `raw/{分类}/{codexId}_{名称}.json` ＋ `md/{分类}/…` 可读版；成品脚本见 phantom-blade-archive `scripts/gamersky_wiki.py`（改 `WIKI` 常量即可移植到同站其它游戏图鉴）。
- **抓完入库接哪一步**：这类图鉴的落库流程（条目→目标档映射表、骨架档自动生成、同人异名留指针）在 `archive-library-ops` 的 `references/structure-and-granularity.md` 第 49 条，本档只管取数。

## 系列作品类（游戏/动画全集）

- **总条目 vs 独立条目**：总条目的「衍生作品 / 角色介绍」段常逐作给一段剧情概览，比单作词条更全；单作词条的「背景设定」比总条目细。**两边都要走一遍**，别只翻一种
- **词条名变体**：`<系列>1` vs `<系列>`（初代常挂在系列名或带副标题的页面）、外传/强化版（XX、Advance、3D）各有独立页
- **落档骨架**：作品线（一作一档）× 剧情线 × 角色/势力 × 双轨年表（现实发行 × 世界观内），比「按角色铺」更适合剧情薄、作品多的系列
- **档内四段**：发行信息 / 剧情线（始作俑者·经过·结局·BOSS）/ 新要素 / 版本与差异——「谁搞的事」这类提问就落在第二段

## 酷狗音乐（专辑／歌单／单曲）

- **分享链不是全集**：`t1.kugou.com/album.html?id=c_xxx` 是预览页，只吐前 **50** 首（整数上限，页面上没有「更多」提示）。`web_extract` 抓它得到的是一份排版完整、看不出缺口的前 50 首清单——**别据此判断某曲不在专辑里**。
- **三步拿全量**：
  1. 分享短码 ≠ 内部 id。先用搜索接口反查：
     ```bash
     curl -sS "https://songsearch.kugou.com/song_search_v2?keyword=<曲名>&page=1&pagesize=3&platform=WebFilter&userid=-1&clientver=2000&iscorrection=1&privilege_filter=0&filter=10&token=&appid=1014" -H "User-Agent: Mozilla/5.0"
     ```
     返回的 `lists[]` 每项带 `SongName`／`SingerName`／`AlbumName`／`AlbumID`／`HQDuration`（秒）——`AlbumID` 就是要的正式 id。
  2. 走专辑接口拿全量：
     ```bash
     curl -sS "http://mobilecdn.kugou.com/api/v3/album/song?albumid=<AlbumID>&page=1&pagesize=-1&version=8000&plat=0&area_code=1" -H "User-Agent: Mozilla/5.0"
     ```
     `data.total` 是总数，`data.info[]` 是曲目数组：`filename`（形如「歌手 - 曲名」，曲名取 ` - ` 后半）、`duration`（秒）。
  3. **对账**：`total` 与 `len(info)` 不等就分页补齐；两者相等才算全量。
- **一次列全某人的专辑**（建谱系的第一步）：`http://mobilecdn.kugou.com/api/v3/search/album?keyword=<作者名>&page=1&pagesize=10&version=8000&plat=0` → `data.info[]` 每项带 `albumname`／`albumid`／`songcount`／`publishtime`。比按曲名逐首反查快得多，还能一眼看出「哪几年出过哪些辑」。
- **单曲归属哪张专辑**：`.../api/v3/search/song?keyword=<曲名>&page=1&pagesize=5&...` → `data.info[]` 带 `SongName`／`album_name`／`album_id`／`singername`／`duration`。判「这首是老曲重编还是新写」先做这步，再回专辑接口取全曲。
- **这个主机走 http**：`mobilecdn.kugou.com` 的 https 证书 subject 不匹配（`no alternative certificate subject name`），`https://` 直连会在 TLS 握手就被拒——换 `http://`，别当成站点挂了解释。
- **响应带未转义控制字符**：直接 `json.loads` 会报 `Invalid control character`——先落盘再 `json.loads(open(p, encoding='utf-8', errors='replace').read(), strict=False)`。
- **时长与顺序都要落**：专辑顺序就是 `info[]` 序（与分享页前 50 对得上，可拿来交叉验证解析有没有错位）；总时长按 `duration` 求和，报「X 小时 Y 分」比「N 首」有用。

## QQ 音乐（专辑详情页）

- **`y.qq.com/n/ryqq_v2/albumDetail/<albumMid>` 直接 `web_extract` 就拿得到**：曲目（曲名＋时长）、**专辑简介全文**、以及页底「该歌手的其他专辑」列表。
- **「该歌手的其他专辑」是建谱系的最快入口**：一次给出该作者在平台上架的全部专辑名＋发行日（实测一次拿到十张、跨 2013–2026），再逐张走曲目接口。比逐张搜专辑名少一大半请求。
- **简介是作曲者自述的富矿**：创作缘起、每期配乐思路、乐器用法常整段写在专辑简介里，且是作者署名的一手自述——比媒体转述权威，直接可作【本人自述】层引用。
- **简介里的年份口径常与自述不符**（如宣传稿写「十八年前」而作者自述其实是十几年前）——**并列留档，不硬裁**，标注两个口径的来源。
- 老版 `music.qq.com/midportal/static/album/…` 页的曲目行是竖线分隔的裸数据（`songid|曲名|singerid|歌手|albumid|专辑|…|时长ms`），正则匹配 `\|<曲名>\|<singerid>\|` 即可；但该页回显会被截断在中间，**完整曲目仍以酷狗专辑接口为准**，QQ 页只用来拿简介与作者专辑列表。

## 曲目谱系比对（跨专辑找重制／改编版）

判「新专辑里哪些是旧曲重制」时，别靠眼看名字对——写脚本三档判：

1. **归一化**：去年份／版本尾缀（`re.sub(r'\s*20\d\d$','',name)`）、去「· 作品名」尾注、去空格与全角空格——旧曲重制常只加年份或作品名后缀，归一化后就能精确命中。
2. **精确命中 → 实锤**：归一化串与旧专辑曲名完全相等。逐条记「本作名／时长 ← 原曲名／时长／来源专辑」，时长差一并列出（拉长＝循环段重编成完整曲，缩短＝裁成关卡长度）。
3. **`difflib.get_close_matches(cutoff=0.75)` → 近似**：只标「待核」，不能当结论。
4. **完全改名的抓不到**（如旧曲《X》拆成新专辑的《X 传承》《X 诀别》三首）——比对器一律漏，只能靠同名根／曲族人工发现，同样标待核。

报告分三档写死：**实锤 N 条（带对照表）／近似 M 条／疑似改名 K 条**。只说「疑似重制」不给条数，等于没查。
