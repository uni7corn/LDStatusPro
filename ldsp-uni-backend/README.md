# LDStatusPro Unified AI Backend

基于 FastAPI + LangChain + RAG 的统一 AI 管理后台，整合 LDStatusPro 和 LD 士多两大业务域。

> **状态**: 已完成迁移，可部署上线  
> **路由**: 391 个 API 端点  
> **定时任务**: 22 个

## 文档

- [架构设计](./docs/ARCHITECTURE.md) - 详细架构说明
- [部署指南](./docs/DEPLOYMENT_GUIDE.md) - 手把手部署教程
- [迁移进度](./docs/PROGRESS.md) - 迁移完成状态

## 架构概览

```
api.ldspro.qzz.io  → CF Worker [保持不变]
api1.ldspro.qzz.io → Nginx → ldsp-uni-backend (端口 8790)
api2.ldspro.qzz.io → Nginx → ldsp-uni-backend (端口 8790)
                              ↑ 同一个服务
```

**前端无需修改** - api1/api2 反代到同一服务，路由 100% 兼容

## 快速开始

### 环境要求

- Python 3.11+
- Docker & Docker Compose (可选)

### 本地开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 等

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8790 --reload

# 访问 API 文档
# http://localhost:8790/api/docs
```

### Docker 部署

```bash
docker compose up -d
```

### 部署更新
```bash
cd /opt/ldsp/ldsp-uni-backend
git fetch origin
git checkout -B main origin/main
docker compose down
docker compose up -d --build
docker compose logs --tail 50
```

## 项目结构

```
app/
├── main.py                        # FastAPI 入口
├── config/                        # 配置
├── core/                          # 认证/CORS/日志/异常
├── gateway/                       # AI 网关 (Agent/RAG/LLM/Tools)
│   ├── agents/                    # LangChain Agent 工作流
│   ├── rag/                       # RAG 知识库
│   ├── tools/                     # Agent 工具集
│   ├── routes/                    # 网关 API
│   └── models/                    # 数据模型
├── domains/                       # 业务域
│   ├── ldsp/                      # LDStatusPro 域
│   └── store/                     # LD 士多域
├── common/                        # 共享模块
└── db/                            # 数据库引擎
```

## API 文档

启动后访问 http://localhost:8790/api/docs 查看 OpenAPI 文档。

## 测试

```bash
pytest tests/ -v
```
