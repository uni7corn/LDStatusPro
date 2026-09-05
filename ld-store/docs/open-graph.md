# LD 士多 Open Graph 功能说明

## 1. 目标与架构

该功能为 Linux DO / Discourse Onebox 及其他支持 Open Graph、Twitter Card 或 oEmbed 的抓取器提供准确、可读、无副作用的分享预览。LD 士多是面向 Linux.do 社区的独立服务，不应在文案或图片中表述为 Linux DO 官方服务。

数据流：

```text
分享页面请求
  → Cloudflare Pages Worker
  → api2 /api/shop/share-meta（只读、5 分钟边缘缓存）
  → Worker 将 canonical + OG + Twitter + oEmbed 写入首个 HTML 响应

分享图片请求 /og/{kind}/{key}.png?v={revision}
  → Worker Cache API（命中直接返回）
  → api2 /api/shop/share-image/{kind}/{key}
  → 安全获取内容图 + sharp 渲染 1200×630 PNG
  → Worker 校验 PNG 和尺寸后缓存并返回
```

后端不复用商品、小店或求购的公开详情方法，因此论坛抓取、机器人预览和 oEmbed 请求不会增加浏览量。没有数据库迁移。

## 2. 页面显示逻辑

| 页面 | 标题与摘要 | 图片主体 | 卡片核心数字 | OG 类型/附加字段 |
| --- | --- | --- | --- | --- |
| `/` | 平台名称与积分兑换简介 | 默认社区小店底图 | `24 / 7` | `website` |
| `/product/:id` | 商品名；清理 Markdown/HTML 后的描述 | 商品图；失败用商品插画 | 最终折后价（LDC） | `product`；价格、币种、库存状态 |
| `/merchant/:username` | 昵称或用户名的士多小店 | 头像；失败用商家插画 | 公开在售商品数 | `profile` |
| `/shop/:id` | 小店名称与简介 | 小店徽标；失败用小店插画 | 累计访问数 | `website` |
| `/buy-request/:id` | 求购标题与详情摘要 | 发布者头像；失败用求购插画 | LDC 预算 | `website` |
| `/coupon/:token` | 优惠券名称、范围、门槛和领取状态 | 指定商品图；失败用优惠券插画 | 减额或折扣 | `website` |
| `/category/:name` | 分类名称与公开商品说明 | 置顶/最新公开商品图；失败用商品插画 | 公开商品数 | `website` |
| `/search?q=...` | `搜索「关键词」 - LD士多` | 默认品牌图 | `24 / 7` | `website` |
| `/docs/*`、`/support`、`/ld-image` | 对应工具或文档的固定标题/摘要 | 默认品牌图 | `24 / 7` | `website` |
| 登录、订单、个人中心、卖家后台 | 仅显示不含用户数据的通用标题/摘要 | 默认品牌图 | `24 / 7` | `website` |
| 合法动态路由，但内容需要登录/信任等级或已不可用 | `对应类型暂不可公开预览`，不显示原内容 | 默认品牌图 | `24 / 7` | HTTP 200 |
| 未注册路由 | 页面未找到 | 默认品牌图 | `24 / 7` | HTTP 404 |

动态内容的公开边界与匿名访问一致：

- 商品只允许审核通过、未删除且匿名 TL0 可见分类；CDK 库存按实际可用卡密计算。
- 商家必须至少有一件匿名可见的审核通过商品。
- 小店只允许 `active` / `approved`。
- 求购只允许 `open` / `negotiating` / `matched`。
- 高信任等级分类及其商品不会向抓取器泄露标题、摘要、卖家或原图。
- 优惠券链接可显示当前 `领取中 / 即将开始 / 已过期 / 已停止领取 / 已领完 / 已停用` 状态；关联商品不可公开时不使用其名称和图片。

api2 对“不存在”和“不可公开访问”刻意使用同一个 404，避免未授权抓取器枚举内容。Worker 收到该响应时，对商品、商家、小店、求购、优惠券和分类等合法动态路由统一输出 HTTP 200 权限提示卡片，文案使用“可能需要登录、满足社区信任等级，或当前已不可用”，既不泄露内容是否存在，也不把权限边界误报为失效链接。只有未注册路由才输出真正的 404。

api2 超时、5xx 或返回无效结构时，Worker仍返回对应页面的通用卡片和 HTTP 200，避免瞬时故障被解释为内容下架。

## 3. 元标签与 canonical

每个 HTML 响应保证以下标签各只有一个：

- `<title>`、`description`、`robots`、`canonical` 和 oEmbed discovery。
- `og:title`、`og:description`、`og:type`、`og:url`、`og:site_name`、`og:locale`。
- `og:image`、`og:image:secure_url`、`og:image:type`、宽、高和 alt。
- `twitter:card`、标题、描述、图片和图片 alt。
- 商品页面额外提供 `product:price:amount`、`product:price:currency=LDC`、`product:availability`；其他页面会主动移除这些字段。

全站保持 `noindex, nofollow, noarchive`，HTML、oEmbed 和 Worker 生成的 OG 图片响应同时设置 `X-Robots-Tag`。`robots.txt` 允许抓取是为了让抓取器读取 noindex 并生成分享预览，不代表允许搜索引擎收录。完整决策与重新评估条件见 [ADR-0001](./adr/0001-noindex-sharing-metadata.md)。

canonical 规则：

- 去除尾部斜杠（首页除外）、fragment、UTM、分页、tab、排序和其他展示参数。
- 搜索页只保留清理、截断后的 `q`。
- 旧域名请求 301 到 `https://ldcstore.com`，保留原路径和查询参数；最终页面 canonical 仍按上述规则归一化。

## 4. OG Image 规则

所有最终图片固定为 1200×630 `image/png`，目标小于 500 KB。模板使用米白 `#FAF9F7`、炭灰 `#3D3D3D`、沙色 `#B5A898` 与金色 `#DAA520`；左侧为内容主体，右侧为代码生成的类型、两行内标题和一个核心数字。标题至少 52 px，核心数字 56 px，其余信息至少 28 px，适合 Linux DO Onebox 的小尺寸缩略图。

默认店铺场景图只用于首页和通用提示卡片。商品、商家、小店、求购、优惠券和分类等动态卡片的左侧使用代码生成的低对比米白渐变，避免内容图叠在复杂场景上。真实内容图使用单层圆角画框和轻阴影；商品图采用 `contain` 保留截图、海报和卡密图片的完整信息；透明兜底插画直接合成到干净背景，不添加第二层白色画框。

固定资产位于 api2 仓库：

```text
assets/og/default-base.png
assets/og/illustrations/fallback-product.png
assets/og/illustrations/fallback-buy-request.png
assets/og/illustrations/fallback-coupon.png
assets/og/illustrations/fallback-shop.png
assets/og/illustrations/fallback-merchant.png
```

`ld-store/public/og-default.png` 是 api2 不可用时使用的同源静态兜底。它应由当前后端模板重新渲染，不应手工编辑文字。替换 AI 插画时保持 1024×1024、透明背景、15% 安全边距、无第三方商标和水印；标题、价格、预算与折扣一律由代码生成。

第三方内容图的安全处理：

- 仅允许无凭据、标准 443 端口的 HTTPS 地址。
- DNS 解析结果全部必须为公网 IP；连接固定到已验证 IP，重定向逐跳重新解析。
- 拒绝 localhost、单标签/内部域名、私网、链路本地、保留、文档和混合公网/私网地址。
- 下载超时 4 秒、最多 3 次重定向、最大 5 MiB、最大 2000 万像素。
- 不信任 HTTP `Content-Type`；由 sharp 按实际字节识别，仅接受单帧 JPEG/PNG/WebP/AVIF，拒绝 SVG、动画和损坏文件。
- 所有来源重新编码为 PNG 后再合成；失败自动使用对应类型插画或默认底图。

## 5. 接口与缓存

### 分享元数据

```http
GET /api/shop/share-meta?path=/product/42
```

主要响应字段：

```ts
type ShareMetadata = {
  kind: 'product' | 'merchant' | 'shop' | 'buy_request' | 'coupon' | 'category'
  canonicalPath: string
  title: string
  description: string
  ogType: 'website' | 'product' | 'profile'
  revision: string
  image: { path: string; alt: string; type: 'image/png'; width: 1200; height: 630 }
  product?: { priceAmount: string; priceCurrency: 'LDC'; availability: 'in stock' | 'out of stock' }
}
```

### 图片

```http
GET /api/shop/share-image/:kind/:key
GET https://ldcstore.com/og/:kind/:key.png?v=:revision
```

缓存策略：

| 内容 | 策略 |
| --- | --- |
| 页面 HTML | `no-store, no-cache, must-revalidate` |
| 分享元数据 | 浏览器 60 秒、边缘 5 分钟、允许 1 小时 stale revalidate |
| oEmbed | 5 分钟，允许 1 小时 stale revalidate |
| 带 `v` 的成功 PNG | 浏览器/边缘 1 天、允许 7 天 stale revalidate、immutable |
| 无版本 PNG 或静态失败兜底 | 5 分钟 |

`revision` 根据模板版本、标题、摘要、核心数字、内容图和更新时间等字段生成。内容或模板变更后图片 URL 自动变化，不需要主动清 Cloudflare Cache；Worker 只把通过 PNG 签名、1 MiB 上限和 1200×630 尺寸检查的成功响应写入 Cache API。

## 6. 部署与验收

部署顺序固定为：

1. 部署 `ld-store-backend-new`，确认 `/api/shop/share-meta` 和 `/api/shop/share-image` 可用，运行容器已安装 Noto CJK 字体并复制 `assets/`。
2. 部署 `LDStatusPro/ld-store` Pages 项目，设置 `LD_STORE_SITE_URL=https://ldcstore.com/` 与正确的 `LD_STORE_META_API_BASE`。
3. 使用未在 Linux DO 分享过的商品、求购和优惠券链接，在帖子草稿中检查桌面、移动端和深色主题 Onebox。

本地检查：

```bash
# api2
npm run check
npm run build

# ld-store
npm run check
```

线上抽查：

```bash
curl -sS -A 'Discoursebot/1.0' https://ldcstore.com/product/42
curl -I 'https://ldcstore.com/og/product/42.png?v=<revision>'
curl -sS 'https://ldcstore.com/oembed.json?url=https%3A%2F%2Fldcstore.com%2Fproduct%2F42'
```

验收要点：HTML 中标签唯一、canonical 无跟踪参数、图片响应是 1200×630 PNG、分享请求前后浏览量不变、不可见内容不泄露。Linux DO/Discourse 会缓存已经烘焙的 Onebox；上线后旧帖子不会保证自动刷新，应编辑并重新保存帖子，或用未分享过的链接进行验证。必要时可给测试链接增加一次性 `?share=<版本>` 触发新的 Onebox 键，页面 canonical 仍会归一化。
