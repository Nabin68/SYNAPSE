from langchain_cohere import ChatCohere
from dotenv import load_dotenv
from typing import TypedDict,Annotated
from langchain_core.messages import BaseMessage

from langgraph.graph import START,END,StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode,tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from Tools import tools

load_dotenv()
llm=ChatCohere(model="command-r-plus-08-2024")

llm_with_tools=llm.bind_tools(tools)

class RAGState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]
    
def chat_node(state:RAGState)->dict:
    
    """LLM node that may answer to the query of user or request a tool call"""
    response=llm_with_tools.invoke(state["messages"])
    return {"messages":[response]}

tool_node=ToolNode(tools)

graph = StateGraph(RAGState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")

conn=sqlite3.connect(database="synapse_db",check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS chat_titles (
    thread_id TEXT PRIMARY KEY,
    title TEXT
)
""")
conn.commit()
checkpointer=SqliteSaver(conn=conn)

app = graph.compile(checkpointer=checkpointer)

def retriever_all_threads():
    all_thread={}
    cursor = conn.execute("SELECT thread_id, title FROM chat_titles")
    return {row[0]: row[1] for row in cursor.fetchall()}
