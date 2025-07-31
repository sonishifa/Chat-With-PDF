import os
import uuid
import fitz  # PyMuPDF
from typing import List
from dotenv import load_dotenv
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

load_dotenv()

# Constants
MILVUS_URI = os.getenv("MILVUS_URI")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COLLECTION_NAME = "pdf_chunks"
EMBEDDING_DIM = 384
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# Load embedder
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Milvus Setup
def connect_milvus():
    connections.connect(
        alias="default",
        uri=MILVUS_URI,
        token=MILVUS_TOKEN
    )

def create_collection() -> Collection:
    if utility.has_collection(COLLECTION_NAME):
        return Collection(COLLECTION_NAME)

    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=36),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=2048),
        FieldSchema(name="source_file", dtype=DataType.VARCHAR, max_length=512)
    ]

    schema = CollectionSchema(fields=fields, description="RAG PDF chunks")
    collection = Collection(name=COLLECTION_NAME, schema=schema)
    collection.create_index("embedding", {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 1024}})
    collection.load()
    return collection

def setup_milvus() -> Collection:
    connect_milvus()
    return create_collection()

# Document Processing
def read_pdf(file_path: str) -> str:
    with fitz.open(file_path) as doc:
        return "".join([page.get_text() for page in doc])

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def ingest_pdf(file_path: str, collection: Collection):
    base_name = os.path.basename(file_path)
    text = read_pdf(file_path)
    chunks = chunk_text(text)
    vectors = embedder.encode(chunks, show_progress_bar=True)

    data = [
        [str(uuid.uuid4()) for _ in chunks],
        vectors,
        chunks,
        [base_name] * len(chunks)
    ]
    collection.insert(data)
    collection.flush()

# Context Retrieval
def retrieve_context(query: str, collection: Collection, top_k: int = 3) -> str:
    query_vec = embedder.encode([query])[0].tolist()
    results = collection.search(
        data=[query_vec],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=top_k,
        output_fields=["text"]
    )
    return "\n\n".join([hit.entity.get("text") for hit in results[0]])

# Chatbot
class Chatbot:
    def __init__(self, collection: Collection):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment.")
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.collection = collection

    def chat(self, user_message: str) -> str:
        context = retrieve_context(user_message, self.collection)
        prompt = (
            "You are a helpful AI assistant. Use the context to answer questions. "
            "If you don't know the answer, just say so. Do not hallucinate.\n\n"
            f"Context:\n{context}\n\nUser: {user_message}"
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {e}"
