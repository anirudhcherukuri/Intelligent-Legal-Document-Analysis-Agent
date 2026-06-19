# Intelligent Legal Document Analysis Agent

An AI-powered legal contract review and risk assessment pipeline. Built with **LangGraph**, **LangChain**, **FastAPI**, and **ChromaDB**, featuring a premium custom dashboard.

## System Features

1. **3-Agent LangGraph Workflow**:
   - **Extractor Agent**: Classifies contract type and extracts target legal clauses (Confidentiality, Liability Caps, Governing Law, Non-Competes, etc.).
   - **Risk Analyzer Agent**: Performs a risk assessment on each clause and generates detailed warning details and mitigation guidance.
   - **Comparator Agent**: Automatically cross-references extracted clauses against your corporate legal playbook to assess compliance status and draft a renegotiation script.
2. **Sub-second Semantic Vector Search**: Leverages a local ChromaDB index to search over contract segments and identify critical legal text in natural language.
3. **Interactive Control Dashboard**: Responsive, glassmorphic dark-theme UI to upload contracts, track real-time agent execution states, edit playbook guidelines, search records, and manage the database.

---

## Getting Started

### Prerequisites
- Python 3.10+
- OpenAI API Key

### Installation

1. Clone or copy the project files to a local directory:
   ```bash
   git clone <repository_url>
   cd "Intelligent Legal Document Analysis Agent"
   ```

2. Set up a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. Install required Python packages:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. Configure environment variables. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your OpenAI credentials:
   ```env
   OPENAI_API_KEY=sk-your-openai-api-key
   ```
   *Note: You can also enter and save your API key directly through the settings panel on the web interface.*

---

## Running the Application

Start the FastAPI application using `uvicorn`:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Once running, navigate to **`http://localhost:8000`** in your browser to view the interactive web dashboard.

---

## Project Structure

- `backend/`: FastAPI API endpoints, LangGraph agent workflows, database schemas, and ChromaDB integrations.
- `frontend/`: Single-Page Application (SPA) dashboard built using premium CSS styling and custom UI scripts.
- `playbook/`: Configurable legal comparison standards (e.g. `default_playbook.json`).
- `data/`: Ingested document copies and ChromaDB persistent database files.

---

## Deployment Guidelines

### Docker Deployment
Create a `Dockerfile` in the root folder:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run the container:
```bash
docker build -t legal-agent-app .
docker run -d -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data legal-agent-app
```
