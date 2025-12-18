from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
import pandas as pd
import requests
import os

# For RAG
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
import hashlib

# Tools
search_tool = DuckDuckGoSearchRun()

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
    """
    file_name = "FINAL_CONSOLIDATED_STUDENT_DATA.xlsx"
    
    try:
        df = pd.read_excel(file_name)
        student_row = df[df['Roll_Number'] == roll_no]
        
        if student_row.empty:
            return {}
        
        student_details = student_row.iloc[0].to_dict()
        student_details = {
            key: ('' if pd.isna(value) else value) 
            for key, value in student_details.items()
        }
        
        return student_details
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Excel file '{file_name}' not found in the current directory")
    except Exception as e:
        raise Exception(f"Error reading student details: {str(e)}")


def generate_file_id(file_path: str) -> str:
    """Generate a unique hash for a file based on its content"""
    return hashlib.md5(file_path.encode()).hexdigest()

@tool
def RAG(file_path: str, query: str) -> str:
    """
    Retrieval Augmented Generation tool that searches through uploaded documents.
    
    Use this tool when users ask questions about an uploaded document. This tool will
    find and return the most relevant passages from the document that can answer the query.
    
    Args:
        file_path (str): Path to the PDF or DOCX file
        query (str): User's question or search query about the document
    
    Returns:
        str: Retrieved relevant text passages from the document. These passages should be
             read carefully and synthesized into a comprehensive answer.
    """
    try:
        # Validate file exists
        if not os.path.exists(file_path):
            return f"Error: File not found at path: {file_path}"
        
        file_id = generate_file_id(file_path=file_path)
        
        embedding = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        vector_store = Chroma(
            embedding_function=embedding,
            persist_directory="RAG_Docs",
            collection_name=f"file_{file_id}"
        )
        
        existing_docs = vector_store.get()
        
        if not existing_docs["ids"]:
            print("🔹 Processing document for the first time...")

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1200,
                chunk_overlap=300
            )

            if file_path.endswith(".pdf"):
                docs = PDFPlumberLoader(file_path).load()
            elif file_path.endswith(".docx"):
                docs = Docx2txtLoader(file_path).load()
            else:
                return "Error: Only PDF and DOCX files are supported."

            chunks = splitter.split_documents(docs)

            if not chunks:
                return "Error: No text content found in the document."

            vector_store.add_documents(chunks)
            print("✅ Document processed and indexed successfully.")
        else:
            print("✅ Using existing document index.")

        # Detect if query is asking for overview/summary
        overview_keywords = ["about", "summary", "summarize", "overview", "what is this", "explain this", "describe this"]
        is_overview_query = any(keyword in query.lower() for keyword in overview_keywords)
        
        # Adjust retrieval strategy based on query type
        if is_overview_query:
            # For overview questions, get more diverse chunks
            retriever = vector_store.as_retriever(
                search_type="mmr",  # Maximum Marginal Relevance for diversity
                search_kwargs={"k": 8, "fetch_k": 20}  # Get 8 diverse passages from 20 candidates
            )
        else:
            # For specific questions, use similarity search
            retriever = vector_store.as_retriever(
                search_type="similarity",
                search_kwargs={"k": 5}
            )
        
        retrieved_docs = retriever.invoke(query)

        if not retrieved_docs:
            return "No relevant information found in the document for your query."

        # Format results with explicit numbering
        result_parts = [
            "=== RETRIEVED PASSAGES FROM DOCUMENT ===",
            ""
        ]
        
        for i, doc in enumerate(retrieved_docs, 1):
            content = doc.page_content.strip()
            content = ' '.join(content.split())
            
            result_parts.append(f"📄 PASSAGE {i} OF {len(retrieved_docs)}:")
            result_parts.append(content)
            result_parts.append("")
        
        result_parts.append("=== END OF PASSAGES ===")
        result_parts.append("")
        
        # Add tailored instruction based on query type
        if is_overview_query:
            result_parts.append("INSTRUCTION: The user asked for an overview/summary of the document.")
            result_parts.append("Please read ALL passages above and provide a comprehensive summary covering:")
            result_parts.append("- Main topic and purpose of the document")
            result_parts.append("- Key sections or problem statements mentioned")
            result_parts.append("- Overall structure and content")
            result_parts.append("Do NOT focus on just one passage - synthesize information from ALL passages.")
        else:
            result_parts.append("INSTRUCTION: Read ALL passages above carefully and synthesize them into")
            result_parts.append("a comprehensive answer to the user's specific question.")
        
        return "\n".join(result_parts)
    
    except Exception as e:
        error_msg = f"Error processing document: {str(e)}"
        print(f"❌ RAG Error: {error_msg}")
        return error_msg


tools = [search_tool, get_stock_price, get_student_details, RAG]