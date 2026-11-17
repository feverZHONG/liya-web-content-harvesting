# 网页内容全量收割 · 提取器失手之后怎么救

> 通用正文提取器拿不到你要的东西时走这页。两件事：① **失手之后怎么救**；② **一开始就不该交给它的活**——数据在 RSC／chunk／交互流程里（题库、配置、逐条文案、算法）。
> 铁律：**工具没抓到 ≠ 源里没有。** 先质疑提取器，再下「无证据」的结论。

## 什么时候该走这条

先分诊，别硬试：

- 要一段**连续正文** → 通用正文提取器就够
- 要**字段／逐条／条数／公式** → 直接从这页开始，别绕
- 页面是**结构化**的（题库、商品表、关卡表、报价）→ 这页
- 页面**跑一遍才出结果**（测验、计算器、报告页）→ 这页
- 你要的是**全站清单**而不是某页内容 → 这页

提取器跑过但结果不对：正文几乎全是表格、字数明显偏薄（百科词条 < 2k 字、wiki 页 < 5k 字）、只拿到导航壳 → 进下面的升级路径。

## 升级路径（按序试，别跳步）

1. **raw HTML 一秒证伪**：`curl -s -A "<UA>" "<url>" -o x.html && grep -c "<关键词>" x.html`。关键词在 HTML 里出现，就证明是提取器丢了正文，不是源里没有。短链／分享跳转页的目标 URL 也在正文里（`var url='…'` / `window.location.replace(…)`），`curl -I` 没有 `Location` 不代表死链。
2. **抠结构化数据**：`__NEXT_DATA__`、`__NUXT__`、`structuredContent`、`application/ld+json`；多语言站先找 `/langs/<locale>.js`、`/i18n/` 这类语言包（正文常整块放在里面，且要按语种各打一次看体量，只抓英文版会误判「站里没内容」）。
   一条命令版：`python3 scripts/siteprobe.py <url>`（体检）／`--chunks`（按汉字数排 chunk）／`--dump N`（括号平衡挖数据数组成 JSON）／`--text`（SSR 正文落 md）。
   **要整库就先找接口**，别抠 payload：`__NUXT_DATA__` 是 devalue 扁平数组（值是索引指针），手写递归遇循环引用就炸，而且只装首屏那几十条。
3. **换通道**（两个轴：出口、客户端）：`curl` 000 不等于拿不到，另一个客户端常是 200；反向也成立，`requests` 返 403 时同机 `curl` 往往 200。降级链：提取器 → curl 抓 HTML 落临时文件 → 让提取器读本地文件净化。
   **带签名／时间戳校验的接口**：裸 curl 回 418／`Request expired` 不是被封，是缺参数，别手算签名——用浏览器打开**页面**拦响应（`page.on("response")`），页面 JS 会自己算好参数。
4. **换词条名／换入口**：等价词条名、带数字 id 的 URL 直读并核标题；作品页普遍只写到开场，结局与最终 BOSS 从「最终 BOSS 页＋关键角色页＋关卡清单」反推。

## 三个只有对账才发现的静默坑

- **分页键必须实测**：候选（`cursor`／`after`／`page`）各打一次比对返回条目 id，「参数被忽略」和「只有一页」在响应里长得一模一样。
- **渲染出的目录不是清单**：`visibleOnNavigation:false` 的分类接口照样给数据，遍历要按接口 `categories` 全量走。
- **分享页／移动 H5 预览页不是全集**：常把条目截到 20／50，页面没有任何「还有更多」的提示，提取器也会返回一份排版完整、看不出缺口的清单。否定判断（「X 不在这个库里」）之前必须拿 `total` 逐个对账。

## 大页别读回上下文

抓取工具的回显常是 head+tail 截断，**被丢掉的中间段往往正是正文**。完整页会落盘，正确姿势是**落盘 + 按章节抽段**：

```bash
python3 scripts/section_digest.py <落盘的md> --sections Story,开发史
```

抓之前先定「我要哪几段」，别先抓后想。

## 正文是一张长图

官方宣传页／「档案大公开」类帖子正文常常只有一句「点击下方图片查看」，真内容是一张宽几百、高近万像素的 JPG。做法：`curl` 带 referer 落到本地 → 按 ~1800px 竖切（相邻片留 80px 重叠）→ 逐片转录。图里的小字（对照表、脚注）不许照抄进档，标「以原图为准」。

## 整站打包成单文件

```bash
python3 scripts/site_bundle.py <站点目录> -o out.html [--quality 78] [--max-width 1400]
python3 scripts/site_bundle.py <站点目录> --entry index.html
python3 scripts/site_bundle.py <站点目录> --pages index.html,faq.html
```

CSS/JS 内联、图片转 data URI、多页底部 tab 切换。跑完打两行账：命中缓存张数 ＋ 未命中清单（`⚠️ 0 处` 才是干净包）。体积参考：17 MB 图站打成 13.7 MB，`--quality 62 --max-width 1000` 压到 7.4 MB。

## 落档与结论纪律

抓到的原文先落盘，结论另起一段，**别把摘要当原文**；引用带 URL ＋ 抓取日期；数字、名单、时间回原文核；抓不到就写「抓不到／被墙／需登录」，不拿旧快照冒充当前；页面结构与抓取路径写进档，下次复现不靠记忆。

## 依赖

```bash
pip install requests lxml      # siteprobe.py
```

- `scripts/siteprobe.py`：站点体检 / chunk 排序 / 数据数组挖掘 / SSR 正文（需要 requests、lxml；`--dump` 需要 node）
- `scripts/section_digest.py`：大页按章节抽段（标准库）
- `scripts/site_bundle.py`：整站打包成单个自包含 HTML（标准库）
- `scripts/wapbaike_extract.py`：百科 `structuredContent` 提取器（标准库）
- `scripts/quiz_audit.js`：测验页复核（外发通道扫描／题库求值／分辨率）（node）

## 怎么用

```bash
git clone https://github.com/feverZHONG/liya-web-content-harvesting.git <你的数据根>/skills/web-content-harvesting
```

## 姊妹仓库

- [liya-subtraction-skill](https://github.com/feverZHONG/liya-subtraction-skill) —— 技能库做减法：冗余检测 / 拆薄 / 合并 / 归档判断
- [liya-persona-authoring](https://github.com/feverZHONG/liya-persona-authoring) —— 给 AI agent 写身份文件（SOUL.md 类）：创作流程 / 砍装饰留行为 / 减法与漂移对照
- [liya-sillytavern-cards](https://github.com/feverZHONG/liya-sillytavern-cards) —— 酒馆角色卡写法：V2 格式 / PList+Ali:Chat / 三个 Python 工具
- [liya-sillytavern-worldbook](https://github.com/feverZHONG/liya-sillytavern-worldbook) —— 酒馆世界书（Lorebook）：触发链源码实证 + 体检 / 模拟 / 生成工具
- [liya-vision-recognition-traps](https://github.com/feverZHONG/liya-vision-recognition-traps) —— 视觉模型识图陷阱：22 条实测与对策（附真 OCR 通道、生图物理体检、两图差分）
- [liya-chat-game-referee](https://github.com/feverZHONG/liya-chat-game-referee) —— 群聊小游戏裁判：扫雷 / 五子棋 / 大话骰 / 骗子牌 / 掷骰决斗，一位裁判带六个引擎
- [liya-spy-game](https://github.com/feverZHONG/liya-spy-game) —— 谁是卧底：黑板规则 / 出题方法论 / 词库验证 / 身份分配器
- [liya-sea-turtle-soup](https://github.com/feverZHONG/liya-sea-turtle-soup) —— 海龟汤：推理方法论 + 档案流水线（turtle CLI）
- [liya-delegation-and-verification](https://github.com/feverZHONG/liya-delegation-and-verification) —— 委派与验收：任务书写法 / 并行隔离 / 把「自报」验成事实
- [liya-tavern-card-refinement](https://github.com/feverZHONG/liya-tavern-card-refinement) —— 酒馆角色卡精修：7 字段清单 / 槽位归位 / 6 类断言 / 可用性验收
- [liya-prose-quality-metrics](https://github.com/feverZHONG/liya-prose-quality-metrics) —— 稿子读起来「平」怎么办：先量再改（对话占比·句长σ·标点谱）＋ 7 个工具
- [liya-ruozhiba-wordbank](https://github.com/feverZHONG/liya-ruozhiba-wordbank) —— 弱智吧题防御手册：160 道逐题拆解 + 三连防御法（拆前提→指谬误→反杀）
- [liya-subtitle-proofreading](https://github.com/feverZHONG/liya-subtitle-proofreading) —— 字幕校对 / 重建 / 外挂 SRT（5 个纯标准库工具）
- [liya-corpus-line-mining](https://github.com/feverZHONG/liya-corpus-line-mining) —— 从语料 / 会话库挖可复用原句：候选池筛选 + 人审落库（零依赖）
- [liya-story-revision-plan](https://github.com/feverZHONG/liya-story-revision-plan) —— 小说全稿修订方案：评估 / 缺口清单 / 逐章大纲 / 信息融合 / 优先级
- [liya-dev-workflow](https://github.com/feverZHONG/liya-dev-workflow) —— 开发全流程方法论：环境侦查 / 计划 / spike / TDD / 调试 / 推送排障 / 同步验收
- [liya-news-verification](https://github.com/feverZHONG/liya-news-verification) —— 验证伞：轻量核查 / 交付前多源验证 / 链接危险识别 / 厂商官宣核实 / 链接考古
- [liya-knowledge-persistence](https://github.com/feverZHONG/liya-knowledge-persistence) —— 知识持久化：信息该放记忆层 / 文件 / 技能库的分层规范
- [liya-incident-review](https://github.com/feverZHONG/liya-incident-review) —— 社群事件复盘：素材收集 → 时间线重构 → 交叉验证 → 矛盾管理（输出理解不输出建议）
- [liya-source-code-investigation](https://github.com/feverZHONG/liya-source-code-investigation) —— 外部项目调查：源码审计 / 拆包分层 / 数据实测 / 身份链（结论导向，非取用）
- [liya-character-voice-simulation](https://github.com/feverZHONG/liya-character-voice-simulation) —— 角色声线推演：锚点表双向用——分队推演（隔离上下文）＋ 反查认说话人
- [liya-dialogue-system-builder](https://github.com/feverZHONG/liya-dialogue-system-builder) —— 台词系统脚手架：触发维度画格子 / 模板+变量兜底 / 覆盖率验证（含 17 子命令工作台与示例角色）
- [liya-md-link-maintenance](https://github.com/feverZHONG/liya-md-link-maintenance) —— Markdown 文档库搬家与断链修复：git mv 保历史 / 断链自动修 / 收尾全量校验
- [liya-technical-report-audit](https://github.com/feverZHONG/liya-technical-report-audit) —— 第三方技术报告审计：事实项打官方源 / 判断项算术对账 / 200 兜底基线 / 只读核查清单
- [liya-published-piece-retrofit](https://github.com/feverZHONG/liya-published-piece-retrofit) —— 存量修订与原号重发：一次改透 / 指标只作体检 / 台词零改动 / 重发后逐段核对线上
## 提思路 / 提修正

- 你踩过的「提取器说没有、其实在 chunk 里」案例 → 开 [Issue](https://github.com/feverZHONG/liya-web-content-harvesting/issues)
- 想直接改 → Fork + PR

## 许可

**双许可**：

- **代码**（`scripts/`）：**MIT**（全文见 `LICENSE`）
- **文档**（`SKILL.md`、`references/`、本 README 正文）：**[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**，可自由使用、改编、商用，**但要署名**（莉娅 / [@feverZHONG](https://github.com/feverZHONG)）并注明来源

---

*莉娅（[@feverZHONG](https://github.com/feverZHONG)）· 宇宙美好记录官*
