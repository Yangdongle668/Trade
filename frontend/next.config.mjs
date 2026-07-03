/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',          // SPA 静态导出，由 Caddy 托管（架构 V1.1）
  trailingSlash: true,
  async rewrites() {
    // 仅本地开发代理到 FastAPI；生产由 Caddy 反代 /api/*
    return process.env.NODE_ENV === 'development'
      ? [{ source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' }]
      : [];
  },
};
export default nextConfig;
