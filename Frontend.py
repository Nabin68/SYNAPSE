import streamlit as st
from Backend import app,retriever_all_threads,conn
from langchain_core.messages import HumanMessage
import uuid

#********************************Utility Function*****************************************
def add_thread(thread_id,title):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"][thread_id]=title
        conn.execute(
            "INSERT OR REPLACE INTO chat_titles VALUES (?, ?)",
            (thread_id, title)
        )
        conn.commit()
        
def generate_thread_id():
    thread_id=str(uuid.uuid4())  # Convert to string
    return thread_id
    
def reset_chat():
    thread_id=generate_thread_id()
    st.session_state["thread_id"]=thread_id
    st.session_state["messages_history"]=[]
    
def load_conversation(thread_id):
    state=app.get_state(config={"configurable":{"thread_id":thread_id}})
    if state.values and "messages" in state.values:
        return state.values["messages"]
    return []
    
#*******************************Session State*********************************************

if "messages_history" not in st.session_state:
    st.session_state["messages_history"]=[]

if "no_of_thread" not in st.session_state:
    st.session_state["no_of_thread"]=0
    
if "thread_id" not in st.session_state:
    st.session_state["thread_id"]=generate_thread_id()

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"]=retriever_all_threads()

#********************************Sidebar UI***********************************************
st.sidebar.title("Omnis v2")

if st.sidebar.button("New Chat"):
    reset_chat()
    st.rerun()
    
st.sidebar.header("My conversations")
for thread_id,title in reversed(st.session_state["chat_threads"].items()):
    if st.sidebar.button(title,key=f"thread_{thread_id}"):
        st.session_state["thread_id"]=thread_id
        messages=load_conversation(thread_id=thread_id)
        temp_messages=[]
        for msg in messages:
            if isinstance(msg,HumanMessage):
                role="user"
            else:
                role="assistant"
            temp_messages.append({"role":role,"content":msg.content})
        st.session_state["messages_history"]=temp_messages
        st.rerun()

#***********************************Main UI************************************************
for message in st.session_state["messages_history"]:
    with st.chat_message(message["role"]):
        st.text(message["content"])

user_input=st.chat_input("Text here...")
if user_input:
    if len(st.session_state["messages_history"])==0:
        chat_title=user_input[:30]
        add_thread(st.session_state["thread_id"],chat_title)
        
    st.session_state["messages_history"].append({"role":"user","content":user_input})
    with st.chat_message("user"):
        st.text(user_input)
   
    CONFIG={"configurable":{"thread_id":st.session_state["thread_id"]}}
    

    with st.chat_message("assistant"):
        response=st.write_stream(
            messages_chunk.content for messages_chunk,metadata in app.stream(
                {"messages":[HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages"
            )
        )
        st.session_state["messages_history"].append({"role":"assistant","content":response})
        # st.text(response)