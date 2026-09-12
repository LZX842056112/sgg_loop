from typing import TypedDict

from langgraph.constants import START, END
from langgraph.graph import StateGraph


class ApproveState(TypedDict):
    score: int
    comment: str
    approved: bool


def collect_node(state: ApproveState) -> dict:
    return {}


def approve_node(state: ApproveState) -> dict:
    state['approved'] = True
    return {'comment': 'approved'}


def reject_node(state: ApproveState) -> dict:
    return {'comment': 'rejected'}


def review_node(state: ApproveState) -> dict:
    return {'comment': 'reviewed'}


def route_for_node(state: ApproveState) -> str:
    if state['score'] > 80:
        return 'approve_node'
    elif state['score'] < 50:
        return 'reject_node'
    else:
        return 'review_node'


builder = StateGraph(state_schema=ApproveState)
builder.add_node('collect_node', collect_node)
builder.add_node('approve_node', approve_node)
builder.add_node('reject_node', reject_node)
builder.add_node('review_node', review_node)

builder.add_edge(START, 'collect_node')
builder.add_conditional_edges('collect_node',
                              route_for_node,
                              path_map={'approve_node': 'approve_node',
                                        'reject_node': 'reject_node',
                                        'review_node': 'review_node'
                                        }
                              )
builder.add_edge('approve_node', END)
builder.add_edge('reject_node', END)
builder.add_edge('review_node', END)

graph = builder.compile()
res = graph.invoke({'score': 85})
print(res)

res = graph.invoke({'score': 60})
print(res)

res = graph.invoke({'score': 20})
print(res)
