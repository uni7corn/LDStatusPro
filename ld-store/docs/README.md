# LD 士多前端文档

| 文档 | 内容 |
| --- | --- |
| [Open Graph 功能说明](./open-graph.md) | Linux DO 分享预览的显示逻辑、接口、OG Image、安全、缓存、部署和验收 |
| [ADR-0001：全站 noindex 与分享元数据并存](./adr/0001-noindex-sharing-metadata.md) | 继续禁止搜索收录、允许分享抓取的决策、门禁与重新评估条件 |

关键实现入口：

- `public/_worker.js`：Pages 边缘元标签注入、oEmbed 和同源 `/og/*` 图片代理。
- `index.html`：无 Worker 场景的完整静态分享标签。
- `scripts/validate-open-graph.mjs`：生产构建后的标签唯一性与兜底 PNG 校验。
- `scripts/validate-noindex-policy.mjs`：源码与生产构建的 noindex、robots、Worker 和 ADR 一致性门禁。
- `tests/worker-open-graph.test.js`：路由矩阵、失败降级、HEAD、oEmbed 和图片缓存回归测试。

修改分享逻辑后执行 `npm run check`；不要只检查浏览器内由 Vue 更新后的 `<head>`，论坛抓取器读取的是首个 HTTP HTML 响应。
