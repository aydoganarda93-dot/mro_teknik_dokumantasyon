# MRO Technical Documentation System

A desktop + API application that processes aviation MRO (Maintenance, Repair & Overhaul) PDF documents and enables intelligent technical search via **RAG (Retrieval Augmented Generation)**.

---

## Features

- Automatic text, table, and section extraction from PDFs (PyMuPDF)
- ATA 100 chapter detection, part number and SB/AD reference extraction
- Local embedding generation (no internet required)
- Persistent vector indexing with ChromaDB
- Fast, free RAG queries via Groq LLM
- Source-referenced answers (document, page, ATA chapter)
- REST API via FastAPI server
- Professional customtkinter desktop GUI
- n8n webhook integration

---

## Tech Stack

| Layer | Technology |
|---|---|
| PDF Processing | PyMuPDF 1.24+ |
| Embedding | sentence-transformers/all-MiniLM-L6-v2 (local, 384-dim) |
| Vector DB | ChromaDB (persistent) |
| LLM | Groq — llama-3.3-70b-versatile (free) |
| API Server | FastAPI + uvicorn (port 8100) |
| Desktop GUI | customtkinter 5.x |
| Automation | n8n webhook |
| Configuration | python-dotenv + mro_config.json |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/aydoganarda93-dot/mro_teknik_dokumantasyon.git
cd mro_teknik_dokumantasyon
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> The embedding model (~90 MB) is downloaded automatically on first run.

### 3. Get a Groq API key

Sign up for free at [console.groq.com](https://console.groq.com) and create an API key.

### 4. Create the `.env` file

```bash
copy .env.example .env
```

Open `.env` and fill in your `GROQ_API_KEY`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
EMBEDDING_MODE=local
MRO_DOCS_DIR=D:\mro_docs
```

### 5. Start the application

Start the **ingestion server** in a separate terminal:

```bash
baslat_server.bat
```

Launch the **desktop GUI**:

```bash
baslat_gui.bat
```

---

## Usage

### Loading PDFs

1. Click **PDF Seç ve Yükle** (Select & Upload PDF) in the GUI.
2. Once processed, the "Last Upload Summary" panel displays document metadata — type, page count, ATA chapters, part numbers, SB/AD references, and table count.

For bulk loading, drop PDFs into `D:\mro_docs\inbox` and click **Toplu Yükle** (Batch Upload).

### Technical Queries

Type an ATA chapter number, part number, or free-text query into the search box and click **Sorguyu Çalıştır** (Run Query).

**Example queries:**

```
ATA 32-10-01 landing gear removal procedure
P/N 5001234-01 which ATA chapter does this part belong to?
Hydraulic system pressure check CAUTION warnings
```

Each answer includes the source document, page number, and ATA reference.

---

## API Reference (port 8100)

| Method | Path | Description |
|---|---|---|
| `POST` | `/process` | Process and index a single PDF |
| `POST` | `/search` | Run a RAG query |
| `POST` | `/batch` | Process all PDFs in the inbox folder |
| `GET` | `/stats` | Vector store statistics |
| `GET` | `/documents` | List indexed documents |
| `DELETE` | `/documents/{doc_id}` | Delete a document |
| `GET` | `/health` | Health check |
| `GET` | `/log` | Ingestion history |

**Example query:**

```bash
curl -X POST http://localhost:8100/search \
  -H "Content-Type: application/json" \
  -d '{"query": "landing gear retraction sequence", "top_k": 5}'
```

---

## Directory Structure

```
mro_teknik_dokumantasyon/
├── main.py                     # Standalone GUI launcher
├── mro_config.py               # Configuration manager
├── requirements.txt
├── .env.example                # Environment variable template
├── baslat_server.bat           # Ingestion server launcher
├── baslat_gui.bat              # GUI launcher
├── mro/
│   ├── pdf_processor.py        # PDF parsing
│   ├── chunker.py              # ATA-aware smart chunking
│   ├── metadata_extractor.py   # Part no, ATA, SB/AD extraction
│   ├── embedder.py             # Embedding generation
│   ├── vector_store.py         # ChromaDB operations
│   ├── rag_engine.py           # RAG pipeline
│   ├── ingestion_server.py     # FastAPI server
│   ├── mro_domain.py           # ATA map, regex patterns
│   └── n8n_mro_client.py       # n8n webhook client
├── ui/
│   └── mro_panel.py            # Desktop GUI panel
└── n8n_workflows/
    ├── mro_ingest_workflow.json
    └── mro_batch_workflow.json

D:\mro_docs\                    # Data folder (created automatically)
├── inbox\                      # Drop PDFs here
├── processed\                  # Successfully processed documents
├── failed\                     # Failed documents
├── chroma_db\                  # Vector database
└── cache\                      # Text extraction cache
```

---

## Alternative LLM Providers

Change `LLM_PROVIDER` in your `.env` file to switch providers:

| Provider | Speed | Cost | Requirement |
|---|---|---|---|
| `groq` | Very fast | Free | GROQ_API_KEY |
| `ollama` | Slow | Free | Local Ollama installation |
| `anthropic` | Fast | Paid | ANTHROPIC_API_KEY |

---

## License

MIT
