from langchain_cohere import ChatCohere
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage

from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from Tools import tools

load_dotenv()
llm = ChatCohere(model="command-r-plus-08-2024")

llm_with_tools = llm.bind_tools(tools)

class RAGState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    file_path: str

def chat_node(state: RAGState) -> dict:
    """LLM node that may answer to the query of user or request a tool call"""
    
    messages = list(state["messages"])
    
    from langchain_core.messages import ToolMessage, HumanMessage
    
    # Check if the last message is from RAG tool
    last_msg = messages[-1] if messages else None
    is_after_rag = isinstance(last_msg, ToolMessage) and "RETRIEVED PASSAGES" in last_msg.content
    
    if state.get("file_path"):
        has_doc_system_msg = any(
            isinstance(msg, SystemMessage) and "document has been uploaded" in msg.content.lower()
            for msg in messages
        )
        
        if not has_doc_system_msg and not is_after_rag:
            # Initial guidance about document availability
            system_msg = SystemMessage(
                content=f"""A document has been uploaded at: {state['file_path']}

When the user asks questions about the document:
- Use the RAG tool with file_path='{state['file_path']}' and query=<user's question>
- The RAG tool will return multiple relevant passages
- You MUST read and synthesize ALL passages, not just the first one

For general questions unrelated to the document, answer normally."""
            )
            messages = [system_msg] + messages
        
        elif is_after_rag:
            # Strong synthesis instruction after receiving RAG results
            synthesis_msg = SystemMessage(
                content="""CRITICAL SYNTHESIS INSTRUCTIONS:

You have received multiple passages from the document. You MUST:

1. READ EVERY SINGLE PASSAGE - Not just the first one!
2. IDENTIFY all distinct topics, problem statements, and themes
3. SYNTHESIZE the information into a coherent, comprehensive answer
4. STRUCTURE your response logically (use bullet points if listing multiple items)
5. DO NOT simply paraphrase the first passage - integrate ALL information

If the user asked "what is this about?", describe the ENTIRE document's content and structure.
If asking for a specific item (like "4th problem statement"), identify it precisely from the passages.

Remember: Multiple passages = Multiple pieces of information to combine!"""
            )
            # Insert just before the tool response
            tool_msg_idx = len(messages) - 1
            messages = messages[:tool_msg_idx] + [synthesis_msg] + [messages[tool_msg_idx]]
    
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

graph = StateGraph(RAGState)
graph.add_node("chat_node", chat_node)
graph.add_node("tools", tool_node)

graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge("tools", "chat_node")

conn = sqlite3.connect(database="synapse_db", check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS chat_titles (
    thread_id TEXT PRIMARY KEY,
    title TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS thread_files (
    thread_id TEXT PRIMARY KEY,
    file_path TEXT
)
""")
conn.commit()
checkpointer = SqliteSaver(conn=conn)

app = graph.compile(checkpointer=checkpointer)

def retriever_all_threads():
    all_thread = {}
    cursor = conn.execute("SELECT thread_id, title FROM chat_titles")
    return {row[0]: row[1] for row in cursor.fetchall()}

def save_thread_file(thread_id: str, file_path: str):
    """Associate a file with a thread"""
    conn.execute(
        "INSERT OR REPLACE INTO thread_files VALUES (?, ?)",
        (thread_id, file_path)
    )
    conn.commit()

def get_thread_file(thread_id: str) -> str:
    """Get the file path for a thread"""
    cursor = conn.execute(
        "SELECT file_path FROM thread_files WHERE thread_id = ?",
        (thread_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else None