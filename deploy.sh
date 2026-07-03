#!/usr/bin/env bash
# ============================================================
# 远航开发助手 — VPS 一键部署（Docker）
#
# 全新部署:   git clone <repo> && cd Trade && sudo ./deploy.sh
# 更新版本:   sudo ./deploy.sh update
# 查看状态:   ./deploy.sh status
# 跟踪日志:   ./deploy.sh logs [服务名]
# 数据备份:   sudo ./deploy.sh backup
# 恢复备份:   sudo ./deploy.sh restore backups/xxx.sql.gz
#
# 要求: Ubuntu/Debian 类 VPS（其他发行版需已装 Docker），1G 内存起
# ============================================================
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
COMPOSE="docker compose -f $COMPOSE_FILE"
cd "$(dirname "$0")"

# ---------- 输出工具 ----------
say()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

need_root() { [ "$(id -u)" = 0 ] || die "此操作需要 root：请用 sudo ./deploy.sh $*"; }

# ---------- 步骤 1：确保 Docker ----------
ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker 已就绪（$(docker --version | cut -d, -f1)）"
    return
  fi
  need_root install
  say "安装 Docker（官方脚本 get.docker.com）…"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose 插件安装失败"
  ok "Docker 安装完成"
}

# ---------- 步骤 2：生成 .env ----------
gen_secret() { openssl rand -hex 32; }

ensure_env() {
  if [ -f .env ]; then
    ok ".env 已存在（跳过生成，如需重置请先备份后删除）"
    return
  fi
  say "首次部署：生成 .env（自动生成全部密钥）"

  read -rp "  域名（已解析到本机则填写，回车跳过用 IP 访问）: " DOMAIN_IN || true
  DOMAIN_IN=${DOMAIN_IN:-}

  local PG_PW SECRET ENC
  PG_PW=$(gen_secret)
  SECRET=$(gen_secret)
  ENC=$(openssl rand -base64 32)

  local BASE_URL
  if [ -n "$DOMAIN_IN" ]; then BASE_URL="https://$DOMAIN_IN";
  else BASE_URL="http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"; fi

  cat > .env <<EOF
# ===== 由 deploy.sh 生成于 $(date -u +%FT%TZ)，密钥请勿泄露 =====
DOMAIN=${DOMAIN_IN}
POSTGRES_PASSWORD=${PG_PW}
DATABASE_URL=postgresql+psycopg://outreach:${PG_PW}@postgres:5432/outreach
REDIS_URL=redis://redis:6379/0
SECRET_KEY=${SECRET}
ENCRYPTION_KEY=${ENC}
APP_BASE_URL=${BASE_URL}

# ---- 免费数据源 Key（留空则对应适配器自动停用，可随时补填后 ./deploy.sh update）----
GOOGLE_PSE_API_KEY=
GOOGLE_PSE_CX=
GOOGLE_MAPS_API_KEY=
COMPANIES_HOUSE_API_KEY=

# ---- 邮箱验证（自托管 Reacher，可选）----
REACHER_BASE_URL=

# ---- LLM（平台代付 Key，可选；用户可在产品内配 BYOK）----
ANTHROPIC_API_KEY=
LLM_STRONG_MODEL=claude-sonnet-5
LLM_CHEAP_MODEL=claude-haiku-4-5-20251001

# ---- OAuth 应用凭据（Gmail/Outlook 通道，可选）----
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
MS_CLIENT_ID=
MS_CLIENT_SECRET=

# ---- 发信护栏（免费版默认，勿放宽）----
SEND_DAILY_LIMIT_HEALTHY=20
SEND_DAILY_LIMIT_WARMING=5
BOUNCE_RATE_THROTTLE=0.03
COMPLAINT_RATE_PAUSE=0.001
EOF
  chmod 600 .env
  ok ".env 已生成（密钥随机、权限 600）"
}

# ---------- 步骤 3：构建与启动 ----------
build_and_up() {
  say "构建镜像（前端在容器内构建，VPS 无需 Node）…"
  $COMPOSE build --pull
  say "启动全部服务…"
  $COMPOSE up -d --remove-orphans
  ok "容器已启动"
}

# ---------- 步骤 4：数据库迁移 + RLS ----------
migrate() {
  say "等待 Postgres 就绪…"
  for _ in $(seq 1 30); do
    $COMPOSE exec -T postgres pg_isready -U outreach -d outreach >/dev/null 2>&1 && break
    sleep 2
  done
  say "执行数据库迁移（alembic upgrade head）…"
  $COMPOSE run --rm api alembic upgrade head
  say "应用行级安全策略（RLS，幂等）…"
  $COMPOSE exec -T postgres psql -q -U outreach -d outreach < backend/sql/rls.sql
  ok "数据库就绪"
}

# ---------- 步骤 5：健康检查 ----------
health_check() {
  say "健康检查…"
  for _ in $(seq 1 20); do
    if $COMPOSE exec -T api python -c \
      "import httpx;httpx.get('http://localhost:8000/api/health',timeout=3).raise_for_status()" \
      >/dev/null 2>&1; then
      ok "API 健康"
      return
    fi
    sleep 3
  done
  warn "API 健康检查超时，请查看日志：./deploy.sh logs api"
  exit 1
}

summary() {
  # shellcheck disable=SC1091
  source <(grep -E '^(DOMAIN|APP_BASE_URL)=' .env) || true
  echo
  echo "=============================================================="
  ok "部署完成 🎉"
  echo
  echo "  访问地址:   ${APP_BASE_URL:-http://<本机IP>}"
  [ -n "${DOMAIN:-}" ] && echo "  HTTPS:      Caddy 已为 $DOMAIN 自动签发证书（需 80/443 开放）"
  echo
  echo "  下一步（建议顺序）:"
  echo "   1. 打开上述地址注册账号，填品牌资产库，接入发信邮箱"
  echo "      （强烈建议使用独立发信域名，并配好 SPF/DKIM/DMARC）"
  echo "   2. 编辑 .env 补填数据源 Key（Google PSE/Maps、Companies House 均可免费申请）"
  echo "      与 LLM Key，然后执行: sudo ./deploy.sh update"
  echo "   3. 建议配置每日备份: crontab 加一行"
  echo "      0 3 * * * cd $(pwd) && ./deploy.sh backup >/dev/null"
  echo
  echo "  常用命令: status / logs [服务] / update / backup"
  echo "=============================================================="
}

# ---------- 子命令 ----------
cmd_install() {
  ensure_docker
  ensure_env
  build_and_up
  migrate
  health_check
  summary
}

cmd_update() {
  [ -f .env ] || die "未找到 .env，请先执行首次部署：sudo ./deploy.sh"
  if [ -d .git ]; then
    say "拉取最新代码…"
    git pull --ff-only || warn "git pull 失败（本地有改动？），继续用当前代码构建"
  fi
  build_and_up
  migrate
  health_check
  ok "更新完成（前端为静态产物，浏览器强刷即可）"
}

cmd_status() {
  $COMPOSE ps
  echo
  $COMPOSE exec -T postgres psql -U outreach -d outreach -tAc \
    "SELECT '租户: '||count(*) FROM tenants" 2>/dev/null || true
}

cmd_logs() { $COMPOSE logs -f --tail=200 "${1:-}"; }

cmd_backup() {
  mkdir -p backups
  local f="backups/outreach-$(date +%Y%m%d-%H%M%S).sql.gz"
  $COMPOSE exec -T postgres pg_dump -U outreach outreach | gzip > "$f"
  # 保留最近 30 份
  ls -t backups/outreach-*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
  ok "备份完成: $f（$(du -h "$f" | cut -f1)）— 请定期同步到异地存储"
}

cmd_restore() {
  local f="${1:-}"
  [ -f "$f" ] || die "用法: ./deploy.sh restore backups/xxx.sql.gz"
  read -rp "⚠ 将覆盖当前数据库，输入 yes 确认: " confirm
  [ "$confirm" = "yes" ] || die "已取消"
  gunzip -c "$f" | $COMPOSE exec -T postgres psql -q -U outreach -d outreach
  ok "恢复完成"
}

case "${1:-install}" in
  install) cmd_install ;;
  update)  cmd_update ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-}" ;;
  backup)  cmd_backup ;;
  restore) cmd_restore "${2:-}" ;;
  *) die "未知命令: $1（可用: install/update/status/logs/backup/restore）" ;;
esac
