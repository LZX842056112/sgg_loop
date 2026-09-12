// app/layout.tsx —— 根布局（Server Component）
// 无 "use client" → 在服务端渲染，不能使用 hooks 或浏览器 API
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "任务管理",
  description: "Next.js + FastAPI 前后端联调（fetch + SSE）",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="header">
          <h1>📋 任务管理</h1>
          <span className="badge">fetch + SSE 联调</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}