import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '远航开发助手',
  description: '外贸 AI 客户开发助手 — 自动找客户、写开发信、多轮跟进',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
