// types/index.ts —— 直接对应 2.5 节 FastAPI 后端的 Pydantic 模型
export interface Task {
    id: number;
    title: string;
    done: boolean;
}

export interface TaskCreate {
    title: string;
    done?: boolean;  // ? = 可选，后端默认 false
}