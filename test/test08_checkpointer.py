from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver


class CounterState(TypedDict):
    count: int


def increment(state: CounterState) -> dict:
    return {"count": state["count"] + 1}


builder = StateGraph(CounterState)
builder.add_node("increment", increment)
builder.add_edge(START, "increment")
builder.add_edge("increment", END)

# 编译时传入 checkpointer
memory = InMemorySaver()
graph = builder.compile(checkpointer=memory)

# 使用 thread_id 区分不同对话/任务
config = {"configurable": {"thread_id": "user-001"}}

# 第一次运行
result1 = graph.invoke({"count": 0}, config=config)
print(result1)  # {'count': 1}

# 第二次运行（同一个 thread_id，从上一次 checkpoint 继续）
result2 = graph.invoke({}, config=config)  # 0 会被忽略，从上一次的 1 继续
print(result2)  # {'count': 2}

# 第三次运行
result3 = graph.invoke({}, config=config)
print(result3)  # {'count': 3}
