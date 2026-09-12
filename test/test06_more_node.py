from typing import TypedDict
from langgraph.constants import START, END
from langgraph.graph import StateGraph


# 1.声明状态
class OverAllState(TypedDict):
    raw_data: str
    clear_data: str
    summary: str


# 2.声明节点
def collect_node(state: OverAllState) -> dict:
    return {"raw_data": '    hello  world  langgraph  hi  nihao   '}


# 节点对状态的更新允许部分更新 没有写到的字段默认不更新
def clear_node(state: OverAllState) -> dict:
    clear_data = state["raw_data"].strip().replace('  ', ' ')
    return {"clear_data": clear_data}


def summary_node(state: OverAllState) -> dict:
    summary = len(state["clear_data"].split(' '))
    return {"summary": summary}


# 3.编排图
builder = StateGraph(state_schema=OverAllState)
builder.add_node('collect_node', collect_node)
builder.add_node('clear_node', clear_node)
builder.add_node('summary_node', summary_node)

builder.add_edge(START, 'collect_node')
builder.add_edge('collect_node', 'clear_node')
builder.add_edge('clear_node', 'summary_node')
builder.add_edge('summary_node', END)

graph = builder.compile()
result = graph.invoke({})
print(result)
