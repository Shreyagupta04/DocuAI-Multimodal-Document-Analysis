# DocuAI – Multimodal Document Analysis

DocuAI is an AI-powered multimodal document analysis system that allows users to upload documents and ask questions about their content.

The system processes **text, tables, and images** from documents and uses multimodal AI models to understand the document and generate relevant answers.

## 🚀 Features

- 📄 Upload and process documents
- 📝 Text extraction and analysis
- 📊 Table understanding
- 🖼️ Image understanding using Vision LLMs
- 🔍 Intelligent document querying
- 🤖 AI-powered question answering
- 🧠 Knowledge graph integration using Neo4j
- ⚡ FastAPI backend
- 💻 React-based frontend

## 🏗️ Architecture

```text
Document Upload
      ↓
Document Processing
      ↓
 ┌────┼────┐
 ↓    ↓    ↓
Text Tables Images
 ↓    ↓    ↓
 └────┼────┘
      ↓
Multimodal Analysis
      ↓
Knowledge Representation
      ↓
User Query
      ↓
Query Analysis
      ↓
AI / LLM Processing
      ↓
Final Answer

### 🛠️ Tech Stack
## Backend
Python
FastAPI
LangChain
LangGraph
REST APIs
## AI / ML
Large Language Models (LLMs)
Vision Language Models (VLMs)
Multimodal Document Processing
NVIDIA AI APIs
## Database
Neo4j
Knowledge Graph
## Frontend
React
JavaScript
Vite
HTML/CSS
## Tools
Git & GitHub
VS Code
Jupyter Notebook

📂 Project Structure
DocuAI-Multimodal-Document-Analysis/
│
├── inference/
│   ├── parser/
│   │   └── parser.py
│   ├── query/
│   │   └── query.py
│   ├── api.py
│   ├── config.py
│   ├── graph.py
│   └── inference.py
│
├── docuai-frontend-react/
│   └── docuai-react/
│       ├── src/
│       ├── public/
│       ├── package.json
│       └── vite.config.js
│
├── interface/
│   ├── console/
│   ├── index.html
│   └── interface.py
│
├── traversal/
│   ├── aithesen/
│   ├── paramarg/
│   ├── traversal.js
│   └── traversal.py
│
├── run.py
├── .gitignore
└── README.md

⚙️ Setup
1. Clone the repository
git clone https://github.com/Shreyagupta04/DocuAI-Multimodal-Document-Analysis.git
cd DocuAI-Multimodal-Document-Analysis
2. Create a virtual environment
python -m venv .venv

Activate it on Windows:

.venv\Scripts\activate
3. Install dependencies

Install the required Python packages according to the project requirements.

4. Configure environment variables

Create a .env file in the project root:

NVIDIA_API_KEY=your_nvidia_api_key
NEO4J_URI=your_neo4j_uri
NEO4J_USER=your_neo4j_username
NEO4J_PASSWORD=your_neo4j_password

Do not commit the .env file or API keys to GitHub.

▶️ Running the Project

Start the backend/API using the project's Python entry point:

python run.py

For the React frontend:

cd docuai-frontend-react/docuai-react
npm install
npm run dev
🎯 Project Objective

The goal of DocuAI is to build an intelligent document analysis system capable of going beyond traditional text-only document processing by understanding multiple modalities such as text, tables, and images and enabling users to interact with their documents through natural language.

## 🔮 Future Improvements

- Support for additional document formats
- Improved multimodal retrieval
- More advanced agentic workflows
- Enhanced document visualization
- Improved response grounding and citations
- Cloud deployment
👩‍💻 Author

Shreya Gupta

B.Tech Computer Science Engineering – AI/ML
