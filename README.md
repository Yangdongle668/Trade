# 远航开发助手（Outreach Copilot）

替外贸业务员干"开发客户"苦活的 AI 助手：自动找到对的公司、挖到对的人、
用地道英语写千人千面的开发信、按最佳节奏多轮跟进——热线索交回业务员本人去谈。

文档：`docs/requirements/`（需求）· `docs/design/`（产品/渠道/免费版/架构）

## 技术栈（架构文档 05 · V1.1）

- 后端：Python 3.11+ / FastAPI 模块化单体 + SQLAlchemy 2.0 + Celery(Redis)
- 前端：Next.js SPA（静态导出）+ Tailwind，OpenAPI 生成 TS 客户端
- 数据库：PostgreSQL 16（多租户 tenant_id + RLS）
- 部署：单 VPS Docker Compose（月成本目标 <$50）

## VPS 一键部署（生产）

```bash
git clone <本仓库> outreach && cd outreach
sudo ./deploy.sh          # 自动装 Docker → 生成密钥 → 构建 → 迁移+RLS → 健康检查
```

首次运行会询问域名（可跳过用 IP）；密钥全部自动生成并写入 `.env`（权限 600）。
之后补填数据源/LLM Key 到 `.env`，执行 `sudo ./deploy.sh update` 生效。

| 命令 | 作用 |
|------|------|
| `sudo ./deploy.sh` | 首次部署（幂等，可重复执行） |
| `sudo ./deploy.sh update` | 拉代码 → 重建 → 迁移 → 滚动重启 |
| `./deploy.sh status` | 容器状态 + 租户数 |
| `./deploy.sh logs [api\|worker\|beat\|caddy]` | 跟踪日志 |
| `sudo ./deploy.sh backup` | 备份数据库到 `backups/`（保留 30 份） |
| `sudo ./deploy.sh restore <文件>` | 恢复备份 |

架构：Caddy（自动 HTTPS + SPA 静态 + `/api` 反代）→ FastAPI → Postgres/Redis，
Celery worker+beat 跑流水线与序列引擎。前端在镜像内构建，VPS 无需 Node。

## 本地开发

```bash
cp .env.example .env          # 填入各免费数据源的 Key（可先留空，对应适配器自动停用）
docker compose up -d postgres redis
cd backend
pip install -e ".[dev]"
alembic upgrade head          # 或首次: make db-init（开发环境快速建表）
uvicorn app.main:app --reload # API: http://localhost:8000  文档: /docs
celery -A app.celery_app worker -Q discovery,sequence,mailbox,maintenance -l info
celery -A app.celery_app beat -l info
cd ../frontend && npm i && npm run dev   # 前端: http://localhost:3000
```

测试：`cd backend && pytest`

## 仓库结构

```
backend/app/
  core/        配置/DB/安全/租户上下文/日志
  common/      域名归一化等共享工具
  modules/     领域模块（identity/brandkit/campaign/discovery/contact/
               sequence/mailbox/triage/ai_gateway/quota/audit）
frontend/      Next.js SPA
docs/          需求与设计文档（01–05）
```

## 关键工程约束（来自架构 ADR）

- 序列引擎：长排程存 Postgres（next_action_at），Celery 只做即时执行（ADR-4）
- 绝不重发：send_jobs.idempotency_key 数据库唯一约束（ADR-6）
- AI 写信反幻觉：具体事实必须能匹配 BrandKit/ResearchFact 出处（ADR-7）
- 邮件：Gmail API / MS Graph / 通用 SMTP+IMAP 三通道统一适配器（ADR-8）
