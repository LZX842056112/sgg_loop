from time import sleep
from typing import TypedDict
from langgraph.graph import END, START, StateGraph


class StepState(TypedDict):
    step: str


def step_a(state: StepState) -> dict:
    return {"step": "A 执行完毕"}


def step_b(state: StepState) -> dict:
    sleep(1)
    return {"step": "B 执行完毕"}


def step_c(state: StepState) -> dict:
    sleep(1)
    return {"step": "C 执行完毕"}


builder = StateGraph(StepState)
builder.add_node("A", step_a)
builder.add_node("B", step_b)
builder.add_node("C", step_c)
builder.add_edge(START, "A")
builder.add_edge("A", "B")
builder.add_edge("B", "C")
builder.add_edge("C", END)

graph = builder.compile()

# stream_mode="updates"：每个节点执行完返回一次
for chunk in graph.stream({"step": ""}, stream_mode="updates"):
    print(chunk)
