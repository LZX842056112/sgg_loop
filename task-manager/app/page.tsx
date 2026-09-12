// app/page.tsx —— 首页（Client Component）
// "use client" 允许 useState / useEffect / fetch / EventSource / onClick
"use client";

import { useState, useEffect, FormEvent } from "react";
import type { Task, TaskCreate } from "@/types";

const API = "http://localhost:8000"; // ← FastAPI 后端地址

export default function HomePage() {
  // ── 状态 ──
  const [tasks, setTasks] = useState<Task[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "done">("all");
  const [title, setTitle] = useState("");

  // ── SSE 订阅：实时接收任务列表 ──
  useEffect(() => {
    const source = new EventSource(`${API}/tasks/stream`);

    source.onopen = () => {
      setConnected(true);
      setError(null); // ← 重连成功，清除错误
    };

    source.onmessage = (event) => {
      const data: Task[] = JSON.parse(event.data);
      setTasks(data);
    };

    source.onerror = () => {
      setConnected(false);
      setError("SSE 连接断开，正在自动重连...");
    };

    return () => source.close(); // ← 组件卸载时关闭 SSE
  }, []); // ← [] = 仅在挂载时执行一次

  // ── 创建任务（fetch POST）──
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    try {
      const res = await fetch(`${API}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim() } as TaskCreate),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTitle(""); // ← 清空输入框
      // 无需手动更新 tasks —— SSE 会在 2 秒内推送最新列表
    } catch (err: any) {
      setError(err.message);
    }
  }

  // ── 客户端筛选 ──
  const filteredTasks =
    filter === "done" ? tasks.filter((t) => t.done) : tasks;

  // ── 渲染 ──
  return (
    <div className="container">
      {/* 连接状态 */}
      <p className={`status ${connected ? "online" : "offline"}`}>
        {connected ? "🟢 SSE 已连接" : "🔴 SSE 已断开"}
      </p>

      {/* 创建表单 */}
      <form className="form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="输入任务标题..."
          maxLength={100}
        />
        <button type="submit">创建任务</button>
      </form>

      {/* 筛选按钮 */}
      <div className="filter">
        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          全部
        </button>
        <button
          className={filter === "done" ? "active" : ""}
          onClick={() => setFilter("done")}
        >
          已完成
        </button>
      </div>

      {/* 错误提示 */}
      {error && <p className="error">{error}</p>}

      {/* 任务列表 */}
      <ul className="task-list">
        {!error && filteredTasks.length === 0 && (
          <li className="empty">暂无任务，在上方创建第一条</li>
        )}
        {filteredTasks.map((task) => (
          <TaskItem key={task.id} task={task} />
        ))}
      </ul>
    </div>
  );
}

// ── 内联子组件：任务条目 ──
function TaskItem({ task }: { task: Task }) {
  return (
    <li className="task-item">
      <span className="task-title">{task.title}</span>
      <span className={`task-status ${task.done ? "done" : ""}`}>
        {task.done ? "✅ 已完成" : "⏳ 待完成"}
      </span>
    </li>
  );
}