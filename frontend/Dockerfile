# 多阶段：Node 构建 SPA 静态产物 → Caddy 托管 + 反代 API
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/out /srv/spa
COPY Caddyfile /etc/caddy/Caddyfile
