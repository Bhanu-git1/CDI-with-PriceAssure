# Salesforce MCP Chat Assistant (Standalone Architecture)

This workspace contains a standalone React Chat UI that communicates with a FastAPI backend server. The backend leverages the **Model Context Protocol (MCP)** to securely retrieve data from your Salesforce CRM using an LLM (Gemini or local Ollama) to translate natural language into read-only SOQL queries.

---

## Prerequisites

Before starting, ensure your team has the following installed:

1. **Python 3.10+** (Ensure it is added to your system `PATH`)
2. **Node.js (v18+) & npm**
3. **A Salesforce account** (Developer Edition or Sandbox recommended) with API access.
4. **LLM Provider:**
   - **Option A (Recommended):** A Google Gemini API Key.
   - **Option B (Local):** [Ollama](https://ollama.com/) running locally with the `qwen2.5-coder:7b` model pulled (`ollama pull qwen2.5-coder:7b`).

---

## Quick Start Guide

### 1. Clone the Repository
```bash
git clone https://github.com/Ijaz-z/MCP-Server---Salesforce.git
cd MCP-Server---Salesforce
```

---

### 2. Backend Setup & Run

The backend is a FastAPI server that manages the Salesforce MCP subprocess client.

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     source venv/bin/activate
     ```

4. **Install Python dependencies:**
   *Note: Always use `python -m pip` to ensure installation into the correct active environment.*
   ```bash
   python -m pip install -r requirements.txt
   ```

5. **Configure Environment Variables:**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and configure:
   - **Salesforce Credentials:**
     - `SF_USERNAME`: Your Salesforce login email.
     - `SF_PASSWORD`: Your Salesforce account password.
     - `SF_SECURITY_TOKEN`: Your Salesforce Security Token (Reset this in Salesforce under *Settings -> Reset My Security Token*).
     - `SF_DOMAIN`: Set to `login` (Production/Dev org) or `test` (Sandbox).
   - **LLM Settings:**
     - If using Gemini, paste your key into `GEMINI_API_KEY`.
     - If using local Ollama, leave `GEMINI_API_KEY` blank, ensure `OLLAMA_HOST=http://localhost:11434` is correct, and run `ollama serve`.

6. **Start the Backend:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *Verify that you see `Successfully connected to MCP Salesforce server.` in the terminal logs.*

---

### 3. Frontend Setup & Run

The frontend is a Vite + React application.

1. **Open a new terminal window** and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Configure Environment Variables:**
   Create a file named `.env` in the `frontend` directory:
   ```env
   VITE_API_URL=http://localhost:8000
   ```

4. **Start the Frontend Dev Server:**
   ```bash
   npm run dev
   ```
   Open your browser and navigate to: [http://localhost:3000](http://localhost:3000)

---

## Testing the Application

1. Open [http://localhost:3000](http://localhost:3000) in your browser.
2. Check the top-right header status dot:
   - **Green (Online):** App connected successfully to backend.
   - **Red (Offline):** Check if backend is running on port `8000`.
3. Try typing a query into the chat input:
   - *Show me the top 5 accounts by annual revenue*
   - *Find all contacts belonging to Dickenson plc*
   - *What is the total opportunity amount by stage?*
4. The AI will translate the prompt into SOQL, run it via the Salesforce MCP client, and present the results in tabular or chart format.

---

## Folder Structure

```
MCP-Server---Salesforce/
├── backend/
│   ├── app/
│   │   ├── config.py         # Config loader
│   │   ├── llm_service.py    # LLM & prompt orchestration
│   │   ├── mcp_client.py     # Stdio client connecting to MCP server
│   │   └── main.py           # FastAPI entrypoint
│   ├── mcp_server/
│   │   └── salesforce_server.py # FastMCP Salesforce server script
│   ├── .env.example          # Template for backend settings
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── src/                  # React source files (UI components)
│   ├── .env                  # Frontend environment settings (API URL)
│   ├── index.html            # Entry HTML
│   └── vite.config.js        # Vite build tool config
└── README.md                 # This guide!
```
