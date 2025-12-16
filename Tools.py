#Tools.py

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
import pandas as pd
import requests
import os

#For RAG
from langchain_community.document_loaders import PDFPlumberLoader,Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
import hashlib

# Tools
search_tool=DuckDuckGoSearchRun()

@tool
def get_stock_price(symbol: str) -> dict:
    """Fetch latest stock price for a given symbol (e.g. 'AAPL', 'TSLA')
    using Alpha Vantage with API key in the URL.
    """

    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=19W1GEHJXPPUTKR2"
    r = requests.get(url)
    return r.json()

@tool
def get_student_details(roll_no: int) -> dict:
    """
    Fetch all details of a student from the Excel file based on their roll number.
    
    This function searches for a student by their roll number in the consolidated student database
    and returns all available information about them including personal details, academic information,
    course enrollments, faculty assignments, and schedule details.
    
    Args:
        roll_no (int): The roll number of the student to search for (e.g., 10265575, 21051174)
    
    Returns:
        dict: A dictionary containing all student details with column names as keys and their 
              corresponding values. Returns empty dict if student not found.
              
              Example return structure:
              {
                  'Serial_Number': 1,
                  'Roll_Number': 10265575,
                  'Name': 'Shivanee Rao',
                  'Section': 'CSE-23',
                  'Faculty_Name': 'Prof. Akshaya Kumar Pati',
                  'Course_Title': 'IOT and Applications',
                  'Superset_ID': '',
                  'Stream': 'B.Tech',
                  'Branch': 'CSE',
                  'Skills': 'Python, Machine Learning',
                  'Profile': 'Software Developer',
                  'Personal_Email': 'student@example.com',
                  'Current_Degree_Branch': 'Computer Science',
                  'Timetable (Day, Time, Room No)': 'Mon 9-10 AM, Room 201'
              }
    
    Raises:
        FileNotFoundError: If the Excel file doesn't exist
        Exception: For any other errors during file reading or processing
    """
    
    file_name = "FINAL_CONSOLIDATED_STUDENT_DATA.xlsx"
    
    try:
        # Read the Excel file
        df = pd.read_excel(file_name)
        
        # Search for the student by roll number
        student_row = df[df['Roll_Number'] == roll_no]
        
        # If student not found, return empty dict
        if student_row.empty:
            return {}
        
        # Convert the first matching row to dictionary
        # This handles NaN values by converting them to None
        student_details = student_row.iloc[0].to_dict()
        
        # Clean up the dictionary - convert NaN to empty string for better readability
        student_details = {
            key: ('' if pd.isna(value) else value) 
            for key, value in student_details.items()
        }
        
        return student_details
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Excel file '{file_name}' not found in the current directory")
    except Exception as e:
        raise Exception(f"Error reading student details: {str(e)}")


def generate_file_id(file_path:str)->str:
    """Generate a unique hash for a file based on its content"""
    return hashlib.md5(file_path.encode()).hexdigest()

@tool
def RAG(file_path:str,query:str):
    """
    Retrieval Augmented Generation tool that searches through uploaded documents.
    
    This tool:
    1. Embeds the document only once (reuses embeddings on subsequent queries)
    2. Retrieves relevant chunks based on the user's query
    3. Returns the most relevant text passages
    
    Args:
        file_path (str): Path to the PDF or DOCX file
        query (str): User's question or search query
    
    Returns:
        str: Retrieved relevant text passages from the document
    """
    file_id=generate_file_id(file_path=file_path)
    
    embedding=HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    vector_store=Chroma(
        embedding_function=embedding,
        persist_directory="RAG_Docs",
        collection_name=f"file_{file_id}"
    )
    
    existing_docs=vector_store.get()
    
    if not existing_docs["ids"]:
        print("🔹 No embeddings found. Generating embeddings...")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

        if file_path.endswith(".pdf"):
            docs = PDFPlumberLoader(file_path).load()
        elif file_path.endswith(".docx"):
            docs = Docx2txtLoader(file_path).load()
        else:
            return "Error: Only PDF and DOCX files are supported."

        chunks = splitter.split_documents(docs)

        vector_store.add_documents(chunks)
        vector_store.persist()

        print("✅ Embeddings generated and stored.")

    else:
        print("✅ Existing embeddings found. Skipping embedding step.")

    # 🔎 retrieval
    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    retrieved_docs = retriever.invoke(query)

    result = "\n\n---\n\n".join(doc.page_content for doc in retrieved_docs)
    return result


tools = [search_tool, get_stock_price, get_student_details, RAG]