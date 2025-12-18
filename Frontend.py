import streamlit as st
from Backend import app, retriever_all_threads, conn, save_thread_file, get_thread_file
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import uuid
import os

# ********************************Utility Function*****************************************
def add_thread(thread_id, title):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"][thread_id] = title
        conn.execute(
            "INSERT OR REPLACE INTO chat_titles VALUES (?, ?)",
            (thread_id, title)
        )
        conn.commit()

def generate_thread_id():
    thread_id = str(uuid.uuid4())
    return thread_id

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    st.session_state["messages_history"] = []
    st.session_state["current_file_path"] = None

def load_conversation(thread_id):
    state = app.get_state(config={"configurable": {"thread_id": thread_id}})
    if state.values and "messages" in state.values:
        return state.values["messages"]
    return []

def handle_file_upload(uploaded_file, thread_id):
    """Save uploaded file to disk and return the path"""
    if uploaded_file is None:
        return None
    
    upload_dir = "uploaded_files"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_extension = os.path.splitext(uploaded_file.name)[1]
    file_path = os.path.join(upload_dir, f"{thread_id}{file_extension}")
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    save_thread_file(thread_id, file_path)
    
    return file_path

# *******************************Session State*********************************************
if "messages_history" not in st.session_state:
    st.session_state["messages_history"] = []

if "no_of_thread" not in st.session_state:
    st.session_state["no_of_thread"] = 0

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = retriever_all_threads()

if "current_file_path" not in st.session_state:
    st.session_state["current_file_path"] = get_thread_file(st.session_state["thread_id"])

# ********************************Sidebar UI***********************************************
st.sidebar.title("SYNAPSE")

if st.sidebar.button("New Chat"):
    reset_chat()
    st.rerun()

uploaded_file = st.sidebar.file_uploader(
    "Upload PDF or DOCX for RAG",
    type=["pdf", "docx"],
    key=f"file_uploader_{st.session_state['thread_id']}"
)

if uploaded_file is not None:
    if st.session_state["current_file_path"] is None:
        file_path = handle_file_upload(uploaded_file, st.session_state["thread_id"])
        st.session_state["current_file_path"] = file_path
        st.sidebar.success(f"✅ File uploaded: {uploaded_file.name}")
        st.rerun()

if st.session_state["current_file_path"]:
    file_name = os.path.basename(st.session_state["current_file_path"])
    st.sidebar.info(f"📄 Active document: {file_name}")

st.sidebar.header("My conversations")
for thread_id, title in reversed(st.session_state["chat_threads"].items()):
    if st.sidebar.button(title, key=f"thread_{thread_id}"):
        st.session_state["thread_id"] = thread_id
        st.session_state["current_file_path"] = get_thread_file(thread_id)
        messages = load_conversation(thread_id=thread_id)
        temp_messages = []
        for msg in messages:
            # FILTER OUT TOOL MESSAGES - only show user and assistant messages
            if isinstance(msg, HumanMessage):
                temp_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                # Only add AI messages that have actual content (not just tool calls)
                if msg.content and msg.content.strip():
                    temp_messages.append({"role": "assistant", "content": msg.content})
            # Skip ToolMessage completely
        st.session_state["messages_history"] = temp_messages
        st.rerun()

# ***********************************Main UI************************************************
for message in st.session_state["messages_history"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Text here...")
if user_input:
    if len(st.session_state["messages_history"]) == 0:
        chat_title = user_input[:30]
        add_thread(st.session_state["thread_id"], chat_title)

    st.session_state["messages_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    CONFIG = {"configurable": {"thread_id": st.session_state["thread_id"]}}

    with st.chat_message("assistant"):
        try:
            initial_state = {
                "messages": [HumanMessage(content=user_input)]
            }
            
            if st.session_state.get("current_file_path"):
                initial_state["file_path"] = st.session_state["current_file_path"]
            
            response_placeholder = st.empty()
            full_response = ""
            
            # Stream the response with filtering
            for messages_chunk, metadata in app.stream(
                initial_state,
                config=CONFIG,
                stream_mode="messages"
            ):
                # CRITICAL: Only process AIMessage content, skip ToolMessage
                if isinstance(messages_chunk, AIMessage):
                    if hasattr(messages_chunk, 'content') and messages_chunk.content:
                        full_response += messages_chunk.content
                        response_placeholder.markdown(full_response)
                # Skip ToolMessage completely - don't show retrieved passages to user
            
            # Store only the final AI response
            if full_response.strip():
                st.session_state["messages_history"].append({
                    "role": "assistant", 
                    "content": full_response
                })
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            st.error(error_msg)
            st.session_state["messages_history"].append({"role": "assistant", "content": error_msg})