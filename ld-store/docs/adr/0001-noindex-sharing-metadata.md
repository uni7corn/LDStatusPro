# ADR-0001：全站 noindex 与分享元数据并存

- 状态：已接受
- 日期：2026-09-01
- 适用范围：LD 士多商城前端与 Cloudflare Pages Worker

## 背景

LD 士多当前面向 Linux DO 社区用户提供商城服务，并不以传统搜索引擎获客为目标。页面仍需要被论坛、即时通信与社交平台的链接抓取器访问，以生成 canonical、Open Graph、Twitter Card 和 oEmbed 分享预览。动态内容还存在登录、信任等级与可见性边界，分享链路不能泄漏内容是否存在。

## 决策

1. 所有 HTML 都保持 `noindex, nofollow, noarchive`，Worker HTML 响应同时返回同值的 `X-Robots-Tag`。
2. Worker 生成的 OG 图片和 oEmbed 响应显式返回 `X-Robots-Tag`；分享元数据、canonical、Open Graph、Twitter Card 与 oEmbed discovery 继续保留。
3. `robots.txt` 使用 `Allow: /`。抓取器必须能够读取页面和响应头，才能观察 noindex，也才能生成分享预览；禁止通过全站 Disallow 代替 noindex。
4. 不发布 sitemap，不新增 JSON-LD、SSR、预渲染或面向搜索排名的内容；`meta keywords` 不再保留。
5. 合法动态路由遇到不存在或不可公开访问的内容时，继续返回不泄漏存在性的通用 HTTP 200 预览。只有未注册路由返回真实 HTTP 404。

## 强制门禁

收录策略不得只修改单一层。任何从 noindex 切换为可收录的变更，必须在同一变更集中显式更新并评审以下四处：

- 本 ADR；
- `index.html` 的静态元数据；
- `public/_worker.js` 的动态元数据与响应头；
- `tests/` 中的策略、分享预览、隐私回退与未知路由测试。

`scripts/validate-noindex-policy.mjs` 会检查源码和生产构建，CI 与本地 `npm run check` 均执行该门禁。`scripts/validate-open-graph.mjs` 继续验证分享标签与同源图片资产。

## 结果与取舍

- 搜索引擎不会把商城页面作为搜索结果或网页快照使用。
- 抓取器仍可访问公开响应，因此分享卡片保持可用；`robots.txt` 的 Allow 不代表授权收录。
- 不可见内容继续使用统一占位文案，避免通过分享接口枚举内容。
- 取消收录相关建设，减少 sitemap、结构化数据与渲染体系的维护成本，但不影响站内路由和用户分享。

## 重新评估收录的前置条件

只有同时满足以下条件，才能提出新的 ADR 取代本决策：

1. 产品负责人确认搜索流量目标、允许收录的页面类型和成功指标。
2. 完成匿名可见性、个人信息、交易信息、下架内容及信任等级边界的安全审计。
3. 明确 canonical、分页、筛选参数、旧域名和内容失效的索引规则。
4. 基于真实数据完成 SSR、预渲染或纯客户端抓取效果与容量评估。
5. 建立 sitemap、结构化数据、抓取监控、紧急下线和搜索结果移除流程。
6. 同步修改上述四处门禁并完成隔离环境回归；不得仅删除 robots meta 或响应头。
