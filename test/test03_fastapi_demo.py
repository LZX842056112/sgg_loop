"""FastAPI 关键概念演示 —— 任务管理 API

运行：uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000
访问：http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import asyncio
import json

# ── 1. 创建应用 + CORS 中间件 ──
app = FastAPI(title="任务管理 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 2. 数据模型（Pydantic） ──
class TaskCreate(BaseModel):
    """创建任务时的请求体"""
    title: str = Field(min_length=1, max_length=100, description="任务标题")
    done: bool = False


class Task(TaskCreate):
    """任务完整模型（含 id，用于响应）"""
    id: int


# ── 3. 依赖注入：共享数据存储 ──
class TaskStore:
    """内存中的任务存储（实际项目用数据库替代）"""

    def __init__(self):
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def add(self, item: TaskCreate) -> Task:
        task = Task(id=self._next_id, **item.model_dump())
        self._tasks[self._next_id] = task
        self._next_id += 1
        return task

    def list_all(self, done: bool | None = None) -> list[Task]:
        tasks = list(self._tasks.values())
        if done is not None:
            tasks = [t for t in tasks if t.done == done]
        return tasks

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)


_store = TaskStore()


def get_store() -> TaskStore:
    """依赖注入函数 —— 返回共享的 TaskStore 实例"""
    return _store


# ── 4. API 路由 ──

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tasks")
def list_tasks(
        status: str | None = None,  # ← 查询参数
        store: TaskStore = Depends(get_store),  # ← 依赖注入
):
    """GET /tasks?status=done —— 查询参数筛选已完成任务"""
    done = None if status is None else (status == "done")
    tasks = store.list_all(done=done)
    return {"count": len(tasks), "tasks": tasks}


from test04_SQLalchemy import get_session


@app.get("/tasks/{task_id}")  # ← 路径参数 {task_id}
def get_task(
        task_id: int,  # ← 路径参数自动解析为 int
        store: TaskStore = Depends(get_store),
        session: Session = Depends(get_session),
):
    """GET /tasks/1 —— 路径参数获取指定任务"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return task


@app.post("/tasks", status_code=201)
def create_task(
        body: TaskCreate,  # ← 请求体（Pydantic 自动校验）
        store: TaskStore = Depends(get_store),
):
    """POST /tasks {"title": "学习 FastAPI"} —— 请求体创建任务"""
    return store.add(body)


# ── 新增 SSE 端点（追加到路由区域末尾）──
@app.get("/tasks/stream")
async def stream_tasks(store: TaskStore = Depends(get_store)):
    """GET /tasks/stream —— SSE 实时推送任务列表"""

    async def event_generator():
        while True:
            tasks = store.list_all()
            items = [t.model_dump() for t in tasks]
            yield f"data: {json.dumps(items)}\n\n"
            await asyncio.sleep(2)  # 每 2 秒推送一次最新列表

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
