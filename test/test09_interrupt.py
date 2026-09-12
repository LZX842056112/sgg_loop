from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command


# 1. 定义状态
class ReviewState(TypedDict):
    content: str
    approved: bool
    review_content: str


# 2. 定义节点
# 2.1 初始写入数据节点
def write_draft(state: ReviewState) -> dict:
    return {"content": "这是一份需要人工审核的草稿."}


# 2.2 人审批节点
def human_review(state: ReviewState) -> dict:
    # 要想实现中断 => 节点函数中调用中断方法
    decision = interrupt({
        "question": f"请审批以下的内容:\n{state['content']}",
        "options": ["approve", "reject", "revise"]
    })
    return {"review_content": str(decision)}


# 2.3 判断是否通过的节点
def publish(state: ReviewState) -> dict:
    review = eval(state["review_content"])
    return {"approved": review["decision"] == "approve"}


# 3. 构建图
builder = StateGraph(state_schema=ReviewState)

# 3.1 添加节点
builder.add_node("write_draft", write_draft)
builder.add_node("human_review", human_review)
builder.add_node("publish", publish)

# 3.2 添加边
builder.add_edge(START, "write_draft")
builder.add_edge("write_draft", "human_review")
builder.add_edge("human_review", "publish")
builder.add_edge("publish", END)

# 4. 编译的时候一定要添加检查点 => 中断依赖检查点存储的
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# 5. 第一次执行的时候 => 触发中断 停下来
config = {"configurable": {"thread_id": "123"}}
result = graph.invoke({}, config=config)

# 获取当前中断的状态
state = graph.get_state(config=config)
print("当前状态为:", state.next)
print("中断信息为:", state.interrupts)

# 6. 恢复执行
result1 = graph.invoke(Command(resume={"decision": "reject", "comment": "有问题"}), config=config)
print(result1)
