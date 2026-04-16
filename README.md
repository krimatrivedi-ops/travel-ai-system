# Travel AI System

A production-grade, multi-agent travel orchestration system implemented manually using FastAPI and function-based agents.

## Project Architecture
- `app.py`: Entry point for FastAPI application.
- `core/`: System-wide configurations, logging, and core utilities.
- `agents/`: Manual implementation of function-based agents.
- `services/`: External integrations (e.g., flight APIs, hotel services).
- `runtime/`: Logic for orchestrating agents and task execution.
- `state/`: Global and local state management (session memory).
- `events/`: Event system for inter-agent communication.
- `ui/`: User interface components.

## Requirements
- Python 3.10+
- FastAPI
- Uvicorn
- Pydantic Settings

## Installation

1. **Create Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Setup:**
   ```bash
   cp .env.example .env
   # Edit .env with your LLM API keys
   ```

## Running the Application

```bash
uvicorn app:app --reload
```
The API will be available at `http://localhost:8000`.
Health check: `http://localhost:8000/health`
Documentation: `http://localhost:8000/docs`

## Design Principles
- **No Agent Frameworks:** All orchestration is manual.
- **Modular and Decoupled:** Clear separation of concerns between agents, services, and runtime.
- **Stateless API:** State management is explicitly handled in the `state/` package.
