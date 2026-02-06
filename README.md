# Voice Travel Agent  
**AI-Powered Voice-Based Travel Planning System**

## Overview  
This repository contains a production-ready voice travel planning agent that generates personalized, multi-day itineraries through natural, real-time voice conversations. The system integrates large language models, speech services, retrieval-augmented generation (RAG), and automated evaluation pipelines to ensure itinerary quality, feasibility, and factual grounding.

The project is designed as a modular experimentation and deployment framework, emphasizing reliability, explainability, and real-world usability in conversational AI systems.

---

## Core Idea  
The Voice Travel Agent enables users to plan trips entirely through voice interaction. It combines:

- Real-time speech-to-text and text-to-speech  
- Tool-augmented LLM reasoning  
- Retrieval-backed travel knowledge  
- Automated quality evaluations  

The system prioritizes natural interaction, practical itineraries, and verifiable information.

---

## System Capabilities  

### Voice-First Interaction  
- Real-time voice-to-voice conversations  
- Live transcript display  
- Human-like speech synthesis  
- Interruptible, multi-turn dialogue  

### Intelligent Itinerary Planning  
- Multi-day travel plans  
- POI discovery using external search tools  
- Weather-aware scheduling  
- Preference-based customization  
- Contextual travel tips via RAG (Wikivoyage)  

### Automated Quality Evaluation  
Every generated or edited itinerary is validated automatically using three evaluation layers:

1. **Feasibility Evaluation**  
   - Time-bounded daily activity validation  
   - Travel duration checks  
   - Balanced daily pacing  

2. **Edit Correctness Evaluation**  
   - Ensures only intended sections are modified  
   - Detects unintended changes  
   - Interprets natural-language edit instructions  

3. **Grounding and Hallucination Evaluation**  
   - Verifies POIs against search results  
   - Enforces source-backed travel tips  
   - Flags uncertainty when information is incomplete  

Evaluation results are persisted for traceability and debugging.

---

## High-Level Architecture  
The system is built around a LangGraph-based agent that orchestrates multiple external tools using the Model Context Protocol (MCP).

**Core Layers:**
- Client Layer: Web UI (WebSocket) and CLI  
- Voice Layer: Speech-to-text and text-to-speech services  
- API Layer: FastAPI server for session handling and email delivery  
- Agent Layer: LangGraph state machine with memory and tool orchestration  
- Tool Layer: Independent MCP servers for POI search, routing, and weather  
- Knowledge Layer: RAG pipeline backed by Wikivoyage  
- Evaluation Layer: Automated itinerary validation system  

This layered separation ensures scalability, testability, and extensibility.

---

## Design Principles  
- Voice-native user experience  
- Tool-grounded LLM reasoning  
- Evaluation-first reliability  
- Modular and extensible services  
- Lazy loading and parallel execution  

---

## Workflow Summary  

1. User speaks a travel request  
2. Speech is transcribed in real time  
3. Agent determines the conversation phase (clarifying, planning, reviewing)  
4. External tools are invoked (POI search, routing, weather, RAG)  
5. Itinerary is synthesized  
6. Automated evaluations validate the output  
7. Response is converted to speech  
8. Results are optionally emailed and logged  

---

## Technology Stack  
- Language: Python  
- Backend: FastAPI, WebSockets  
- Agent Framework: LangGraph  
- LLM Inference: Groq  
- Voice Services: ElevenLabs  
- RAG: Sentence Transformers, Pinecone  
- Routing: OSRM  
- Weather: Open-Meteo  
- Email: Resend  
- Deployment: Docker, Render  

---

## Intended Use Cases  
- Voice-based travel assistants  
- Conversational AI planning tools  
- Agent evaluation research  
- Tool-augmented LLM systems  
- Production-grade AI agent architectures  

---

## License  
This project is licensed under the MIT License.
