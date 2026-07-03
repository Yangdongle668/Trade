# 远航开发助手（Outreach Copilot）

替外贸业务员干"开发客户"苦活的 AI 助手：自动找到对的公司、挖到对的人、
用地道英语写千人千面的开发信、按最佳节奏多轮跟进——热线索交回业务员本人去谈。

文档：`docs/requirements/`（需求）· `docs/design/`（产品/渠道/免费版/架构）

## 技术栈（架构文档 05 · V1.1）

- 后端：Python 3.11+ / FastAPI 模块化单体 + SQLAlchemy 2.0 + Celery(Redis)
- 前端：Next.js SPA（静态导出）+ Tailwind，OpenAPI 生成 TS 客户端
- 数据库：PostgreSQL 16（多租户 tenant_id + RLS）
- 部署：单 VPS Docker Compose（月成本目标 <$50）

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
