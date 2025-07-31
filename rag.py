import os
import uuid
import fitz  # PyMuPDF for PDF processing
from typing import List
from dotenv import load_dotenv
import chromadb
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configuration
PERSIST_DIRECTORY = "./chroma_data"
COLLECTION_NAME = "rag_documents_collection"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# read the PDF file and extract text
def read_pdf(file_path: str) -> str:
    with fitz.open(file_path) as pdf_document:
        text = ""
        for page in pdf_document:
            text += page.get_text()
    return text

# Split text into chunks
def chunk_text(text: str) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + CHUNK_SIZE, text_length)
        chunk = text[start:end]
        chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
        if start < 0:
            start = 0
    return chunks

#setup ChromaDB client and collection
def setup_chromadb():
    os.makedirs(PERSIST_DIRECTORY, exist_ok=True)
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    print(f"ChromaDB initialized at: {PERSIST_DIRECTORY}")
    return client, collection

#take a PDF file path and store its chunks in ChromaDB
def ingest_pdf(file_path: str, collection: chromadb.Collection):
    if not file_path.lower().endswith(".pdf"):
        raise ValueError("File must be a PDF.")
    print(f"Processing PDF: {file_path}")
    base_name = os.path.basename(file_path)

    text = read_pdf(file_path)
    if not text:
        print("No text extracted from PDF.")
        return
    chunks = chunk_text(text)
    print(f"Generated {len(chunks)} chunks")

    # Generate embeddings using sentence-transformers 
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    vectors = embedder.encode(chunks, show_progress_bar=True)
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"text": chunk, "source_file": base_name} for chunk in chunks]
    # Store in ChromaDB
    collection.add(
        documents=chunks,
        embeddings=[vec.tolist() for vec in vectors],
        metadatas=metadatas,
        ids=ids
    )
    print(f"Successfully stored {len(chunks)} chunks in ChromaDB")

# Retrieve context from ChromaDB based on user query
embedder = SentenceTransformer("all-MiniLM-L6-v2")
def retrieve_context(query: str, collection: chromadb.Collection, top_k: int = 3) -> str:
    """Retrieve top-k relevant chunks from ChromaDB for the query."""
    query_embed = embedder.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embed],
        n_results=top_k,
        include=['documents']
    )
    context_snippets = results['documents'][0]
    return "\n\n".join(context_snippets)

class Chatbot:
    def __init__(self, collection: chromadb.Collection):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Please set 'GEMINI_API_KEY' in .env file.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        self.collection = collection

    def chat(self, user_message: str) -> str:
        # Retrieve context
        context = retrieve_context(user_message, self.collection)
        prompt = (
            "You are a helpful AI assistant. Answer questions based on the provided context. "
            "If the context doesn't contain the answer, say you don't know. "
            "Don't make up information.\n\n"
            f"Context:\n{context}\n\nUser: {user_message}"
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {e}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="RAG Chat with PDF")
    parser.add_argument("--pdf", type=str, help="Path to PDF file to ingest")
    args = parser.parse_args()
    # Initialize ChromaDB
    collection = setup_chromadb()
    # Ingest PDF if provided
    if args.pdf:
        if not os.path.exists(args.pdf):
            print(f"Error: PDF file '{args.pdf}' not found.")
            return
        ingest_pdf(args.pdf, collection)
    # Start chat
    print("\n--- Chat with your PDF ---")
    print("Type 'exit' to quit.")
    chatbot = Chatbot(collection)
    while True:
        user_input = input("\nYour question: ")
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break
        if not user_input.strip():
            print("Please enter a question.")
            continue
        response = chatbot.chat(user_input)
        print(f"\nAI: {response}")

if __name__ == "__main__":
    main()
