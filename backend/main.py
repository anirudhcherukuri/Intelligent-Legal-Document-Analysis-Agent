import os
import uuid
import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import UPLOAD_DIR, PLAYBOOK_PATH, OPENAI_API_KEY
from backend.schemas import (
    AnalysisResponse,
    SearchResponse,
    PlaybookSchema,
    ExtractedClause,
    RiskAnalysis,
    ComparisonItem
)
from backend.database import (
    parse_document,
    index_document,
    search_collection,
    list_documents,
    delete_document,
    get_collection
)
from backend.agents import run_agent_pipeline

app = FastAPI(
    title="Intelligent Legal Document Analysis Agent API",
    description="Backend API for contract clause extraction, risk assessment, and comparison",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class KeyUpdateRequest(BaseModel):
    openai_api_key: str

class AnalyzeRequest(BaseModel):
    document_id: str
    contract_type: Optional[str] = None

# Helper to reconstruct document text from Chroma chunks
def get_document_text(document_id: str) -> str:
    collection = get_collection()
    results = collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])
    if not results or not results["documents"]:
        raise HTTPException(status_code=404, detail="Document not found in vector database.")
    
    # Sort chunks by chunk_index
    chunks_with_meta = list(zip(results["documents"], results["metadatas"]))
    chunks_with_meta.sort(key=lambda x: x[1].get("chunk_index", 0))
    
    return "\n".join([c[0] for c in chunks_with_meta])

@app.get("/api/config")
async def get_config():
    """Checks if the OpenAI API Key is configured."""
    key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
    is_configured = bool(key and key != "your_openai_api_key_here")
    return {"openai_key_configured": is_configured}

@app.post("/api/config")
async def update_config(payload: KeyUpdateRequest):
    key = payload.openai_api_key.strip()
    if not (key.startswith("sk-") or key.startswith("gsk_")):
        raise HTTPException(status_code=400, detail="Invalid API Key format. Should start with 'sk-' (OpenAI) or 'gsk_' (Groq).")
    
    # Update environment variables
    os.environ["OPENAI_API_KEY"] = key
    import backend.config as config
    config.OPENAI_API_KEY = key
    import backend.agents as agents
    # Trigger reload of LLM clients
    
    # Persist to .env file
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines = []
    key_exists = False
    
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("OPENAI_API_KEY="):
                    lines.append(f"OPENAI_API_KEY={key}\n")
                    key_exists = True
                else:
                    lines.append(line)
                    
    if not key_exists:
        lines.append(f"\nOPENAI_API_KEY={key}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    return {"message": "API key updated successfully."}

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    contract_type: str = Form("General")
):
    """Uploads a contract, parses it, and indexes it in ChromaDB."""
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
        
    # Generate unique ID and save file
    doc_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{doc_id}_{filename}"
    
    try:
        # Save upload to disk
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
            
        # Parse document text
        text_content = parse_document(file_path)
        
        # Index in ChromaDB
        num_chunks = index_document(doc_id, filename, text_content, contract_type)
        
        return {
            "document_id": doc_id,
            "filename": filename,
            "contract_type": contract_type,
            "chunks_indexed": num_chunks,
            "message": "File uploaded and indexed successfully."
        }
    except Exception as e:
        # Cleanup file on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@app.post("/api/analyze")
async def analyze_document(payload: AnalyzeRequest):
    """Runs the 3-agent pipeline on a document already indexed in ChromaDB."""
    # Check if key is configured
    key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
    if not key or key == "your_openai_api_key_here":
        raise HTTPException(
            status_code=400, 
            detail="OpenAI API Key is not configured. Please set it in Settings."
        )

    doc_id = payload.document_id
    
    try:
        # 1. Retrieve the document details
        docs = list_documents()
        doc_meta = next((d for d in docs if d["document_id"] == doc_id), None)
        if not doc_meta:
            raise HTTPException(status_code=404, detail="Document not found.")
            
        filename = doc_meta["filename"]
        determined_type = payload.contract_type or doc_meta["contract_type"]
        
        # 2. Reconstruct document text from vector store
        text_content = get_document_text(doc_id)
        
        # 3. Run the LangGraph 3-Agent Workflow
        result_state = run_agent_pipeline(text_content, determined_type)
        
        if result_state.get("error"):
            raise HTTPException(status_code=500, detail=result_state["error"])
            
        # Extract risk list
        risks = result_state.get("risk_analysis", [])
        
        # Calculate overall risk score
        overall_risk = result_state.get("overall_risk_score", "Low")
        summary = result_state.get("summary", "Analysis completed.")
        
        return {
            "document_id": doc_id,
            "filename": filename,
            "contract_type": result_state.get("contract_type", determined_type),
            "extracted_clauses": result_state.get("extracted_clauses", []),
            "risk_analysis": risks,
            "comparison_results": result_state.get("comparison_results", []),
            "overall_risk_score": overall_risk,
            "summary": summary
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing agent pipeline: {str(e)}")

@app.get("/api/documents")
async def get_all_documents():
    """Lists all uploaded documents metadata."""
    try:
        docs = list_documents()
        # Add file size details if available
        for doc in docs:
            filename = doc["filename"]
            doc_id = doc["document_id"]
            # Search file system for size
            matches = list(UPLOAD_DIR.glob(f"{doc_id}_*"))
            if matches:
                doc["size_bytes"] = matches[0].stat().st_size
                # Format a friendly date
                doc["upload_time"] = datetime.datetime.fromtimestamp(
                    matches[0].stat().st_ctime
                ).strftime("%Y-%m-%d %H:%M:%S")
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")

@app.delete("/api/documents/{document_id}")
async def delete_contract_document(document_id: str):
    """Deletes a contract from vectors store and uploaded files."""
    try:
        # Delete from ChromaDB
        delete_document(document_id)
        
        # Delete physical file
        files = list(UPLOAD_DIR.glob(f"{document_id}_*"))
        for f in files:
            f.unlink()
            
        return {"message": "Document deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@app.get("/api/search", response_model=SearchResponse)
async def search_contracts(
    query: str = Query(..., description="The semantic search query"),
    contract_type: Optional[str] = Query("All", description="Filter by contract type"),
    limit: int = Query(5, description="Number of results to return")
):
    """Performs semantic search across all contracts or a specific type."""
    try:
        results = search_collection(query, contract_type, limit)
        return {
            "query": query,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/playbook")
async def read_playbook():
    """Reads the current contract playbooks."""
    try:
        if PLAYBOOK_PATH.exists():
            with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"contract_types": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load playbook: {str(e)}")

@app.post("/api/playbook")
async def update_playbook(payload: PlaybookSchema):
    """Updates the contract playbooks."""
    try:
        with open(PLAYBOOK_PATH, "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(), f, indent=2)
        return {"message": "Playbook updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write playbook: {str(e)}")

# Mount static frontend files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_dir}")
