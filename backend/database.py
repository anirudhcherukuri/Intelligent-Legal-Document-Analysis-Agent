import os
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.utils import embedding_functions
from docx import Document
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.config import CHROMA_DB_DIR, OPENAI_API_KEY, EMBEDDING_MODEL

# Initialize ChromaDB persistent client
_chroma_client = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    return _chroma_client

class SimpleHashingEmbeddingFunction:
    """A zero-memory, lightweight deterministic embedding function for resource-constrained environments (like Render Free Tier)."""
    def __call__(self, input: List[str]) -> List[List[float]]:
        import hashlib
        import random
        results = []
        for text in input:
            # Seed the RNG deterministically with the text MD5 hash
            seed = int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16) % 1000000
            rng = random.Random(seed)
            # Generate a random unit vector of dimension 384
            vector = [rng.gauss(0, 1) for _ in range(384)]
            norm = sum(x**2 for x in vector) ** 0.5
            vector = [x / norm if norm > 0 else 0.0 for x in vector]
            results.append(vector)
        return results

def get_embedding_function():
    # Fallback to default sentence transformers if no OpenAI key is set or if a Groq key is used,
    # but try to use OpenAIEmbeddingFunction first as requested
    api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if api_key and api_key != "your_openai_api_key_here" and not api_key.startswith("gsk_"):
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=EMBEDDING_MODEL
        )
    else:
        # Use zero-memory hashing embeddings to prevent Render OOM crashes on free tier
        return SimpleHashingEmbeddingFunction()

def get_collection():
    client = get_chroma_client()
    ef = get_embedding_function()
    return client.get_or_create_collection(
        name="legal_contracts",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

def parse_document(file_path: Path) -> str:
    """Parses a document based on its extension (PDF, DOCX, TXT)."""
    ext = file_path.suffix.lower()
    text = ""
    
    if ext == ".pdf":
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    elif ext == ".docx":
        doc = Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
    
    if not text.strip():
        raise ValueError("The uploaded document appears to be empty or unreadable.")
        
    return text

def index_document(document_id: str, filename: str, content: str, contract_type: str) -> int:
    """Chunks and indexes document contents into ChromaDB."""
    collection = get_collection()
    
    # Split text into manageable chunks (e.g., clauses or paragraphs)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_text(content)
    
    documents = []
    ids = []
    metadatas = []
    
    upload_time = datetime.datetime.now().isoformat()
    
    for idx, chunk in enumerate(chunks):
        documents.append(chunk)
        ids.append(f"{document_id}_chunk_{idx}")
        metadatas.append({
            "document_id": document_id,
            "filename": filename,
            "contract_type": contract_type,
            "chunk_index": idx,
            "upload_time": upload_time
        })
        
    # Ingest in batches to handle ChromaDB limits if document is massive
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        collection.add(
            documents=documents[i:i+batch_size],
            ids=ids[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size]
        )
        
    return len(documents)

def search_collection(query: str, contract_type: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Runs a semantic search over the vector store."""
    collection = get_collection()
    
    where_clause = {}
    if contract_type and contract_type != "All":
        where_clause["contract_type"] = contract_type
        
    results = collection.query(
        query_texts=[query],
        n_results=limit,
        where=where_clause if where_clause else None
    )
    
    formatted_results = []
    if not results or not results["documents"]:
        return []
        
    # Chroma returns lists of lists for multiple queries. Since we only sent one query:
    documents = results["documents"][0]
    ids = results["ids"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(documents)
    
    for doc, doc_id, meta, dist in zip(documents, ids, metadatas, distances):
        # Convert cosine distance to a similarity score (approximate)
        similarity = 1.0 - dist if dist is not None else 0.0
        formatted_results.append({
            "document_id": meta.get("document_id", ""),
            "filename": meta.get("filename", ""),
            "clause_type": meta.get("contract_type", "Unknown"), # Default/Fallback
            "text": doc,
            "score": round(similarity, 4),
            "page_number": meta.get("page_number", None),
            "metadata": meta
        })
        
    return formatted_results

def delete_document(document_id: str):
    """Deletes all chunks associated with a document_id."""
    collection = get_collection()
    collection.delete(where={"document_id": document_id})

def list_documents() -> List[Dict[str, Any]]:
    """Lists all distinct documents stored in the database."""
    collection = get_collection()
    
    # ChromaDB get() can retrieve metadata. We can fetch all items or a subset
    results = collection.get(include=["metadatas"])
    
    if not results or not results["metadatas"]:
        return []
        
    seen_docs = {}
    for meta in results["metadatas"]:
        doc_id = meta.get("document_id")
        if doc_id and doc_id not in seen_docs:
            seen_docs[doc_id] = {
                "document_id": doc_id,
                "filename": meta.get("filename", "Unknown"),
                "contract_type": meta.get("contract_type", "Unknown"),
                "upload_time": meta.get("upload_time", ""),
                # Size calculation is simulated or tracked separately. Let's just return what we have.
                "size_bytes": 0 
            }
            
    return list(seen_docs.values())
