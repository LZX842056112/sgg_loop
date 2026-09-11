from typing import TypedDict

from langgraph.constants import START, END
from langgraph.graph import StateGraph


class OverAllState(TypedDict):
    count: int
    output: str

#1.1声明输入状态
class InputState(TypedDict):
    count: int


def inc_node(input_state: InputState) -> OverAllState:
    count = input_state["count"] + 1
    return {"count": count}


def double_node(state: OverAllState) -> OverAllState:
    count = state["count"] * 2
    return {"count": count, "output": 'over'}


# 3.编译图
builder = StateGraph(state_schema=OverAllState, input_schema=InputState)
builder.add_node('inc_node', inc_node)
builder.add_node('double_node', double_node)

builder.add_edge(START, 'inc_node')
builder.add_edge('inc_node', 'double_node')
builder.add_edge('double_node', END)

# 3.3编译=>添加检查点
graph = builder.compile()

result = graph.invoke({"count": 1})
print(result)
