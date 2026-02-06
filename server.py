
"""FastAPI server for Voice Travel Agent."""
import logging
import sys
import httpx
from pathlib import Path
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

from app.config import settings
from app.voice.stt_service import STTService
from app.voice.tts_service import TTSService
from app.voice.session_manager import VoiceSessionManager
from app.voice.websocket_handler import VoiceWebSocketHandler
from app.agent.factory import AgentFactory

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('voice_agent.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("server")

# Create FastAPI app
app = FastAPI(
    title="Voice Travel Agent",
    description="AI-powered voice travel planning assistant",
    version="1.0.0"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (will be set in startup event)
stt_service: STTService = None
tts_service: TTSService = None
session_manager: VoiceSessionManager = None
ws_handler: VoiceWebSocketHandler = None
agent_factory: AgentFactory = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on server startup."""
    global stt_service, tts_service, session_manager, ws_handler, agent_factory

    logger.info("=== Starting Voice Travel Agent Server ===")
    logger.info(f"Server host: {settings.server_host}:{settings.server_port}")
    logger.info(f"Voice: {settings.elevenlabs_voice_id}")
    logger.info(f"Model: {settings.elevenlabs_model_id}")

    # Log LangSmith configuration
    if settings.langsmith_tracing.lower() == "true":
        logger.info(f"LangSmith tracing: ENABLED (Project: {settings.langsmith_project})")
    else:
        logger.info("LangSmith tracing: DISABLED")

    # Initialize services
    logger.info("Initializing STT service...")
    stt_service = STTService(api_key=settings.elevenlabs_api_key)

    logger.info("Initializing TTS service...")
    tts_service = TTSService(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_model_id,
    )

    logger.info("Initializing session manager...")
    session_manager = VoiceSessionManager()

    logger.info("Initializing agent factory...")
    agent_factory = AgentFactory()
    await agent_factory.initialize()

    logger.info("Initializing WebSocket handler...")
    ws_handler = VoiceWebSocketHandler(
        stt_service=stt_service,
        tts_service=tts_service,
        session_manager=session_manager,
        agent_factory=agent_factory,
    )

    logger.info("=== Server startup complete ===")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on server shutdown."""
    logger.info("=== Shutting down server ===")
    if agent_factory:
        await agent_factory.cleanup()
    logger.info("=== Shutdown complete ===")


@app.get("/")
async def get_index():
    """Serve the main UI."""
    static_path = Path(__file__).parent / "static" / "index.html"
    if static_path.exists():
        return FileResponse(static_path)
    else:
        return JSONResponse(
            content={"error": "Frontend not found. Please ensure app/static/index.html exists."},
            status_code=404
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint - basic liveness probe."""
    return {
        "status": "healthy",
        "service": "voice-travel-agent",
        "version": "1.0.0",
        "active_sessions": session_manager.get_session_count() if session_manager else 0,
    }


@app.get("/api/ready")
async def readiness_check():
    """
    Readiness check endpoint - indicates when server is ready to accept requests.
    Returns 200 when agent is initialized, 503 otherwise.
    """
    if agent_factory is None or agent_factory._agent is None:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "message": "Agent not initialized yet"
            }
        )

    return {
        "ready": True,
        "message": "Server is ready to accept requests",
        "service": "voice-travel-agent",
        "version": "1.0.0"
    }


class EmailItineraryRequest(BaseModel):
    """Request model for sending itinerary via email."""
    email: EmailStr
    destination: str
    itinerary_content: str


@app.post("/api/send-itinerary")
async def send_itinerary_email(request: EmailItineraryRequest):
    """
    Send itinerary to email address.

    Args:
        request: Email request with recipient, destination, and itinerary content

    Returns:
        Success or error message
    """
    logger.info(f"Sending itinerary email to {request.email} for {request.destination}")

    try:
        # Get Resend API key
        api_key = settings.resend_api_key
        if not api_key:
            logger.error("RESEND_API_KEY not configured")
            raise HTTPException(
                status_code=500,
                detail="Email service not configured. Please contact administrator."
            )

        # Create HTML email (simplified inline version)
        html_body = create_email_html(request.destination, request.itinerary_content)

        # Send email via Resend API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": f"{settings.email_sender_name} <{settings.email_sender}>",
                    "to": [request.email],
                    "subject": f"Your Travel Itinerary - {request.destination}",
                    "html": html_body
                },
                timeout=30.0
            )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Email sent successfully. ID: {result.get('id')}")
            return {
                "success": True,
                "message": f"Itinerary sent successfully to {request.email}!",
                "email_id": result.get("id")
            }
        else:
            error_data = response.json()
            logger.error(f"Failed to send email: {response.status_code} - {error_data}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {error_data.get('message', 'Unknown error')}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error sending email: {str(e)}"
        )


def create_email_html(destination: str, itinerary_content: str) -> str:
    """Create HTML email template for itinerary."""
    # Convert markdown to basic HTML
    html_content = itinerary_content
    lines = html_content.split("\n")
    formatted_lines = []
    in_list = False

    for line in lines:
        if line.strip().startswith("# "):
            formatted_lines.append(f"<h2 style='color: #4f46e5; margin-top: 24px; margin-bottom: 12px;'>{line.strip()[2:]}</h2>")
        elif line.strip().startswith("## "):
            formatted_lines.append(f"<h3 style='color: #6366f1; margin-top: 16px; margin-bottom: 8px;'>{line.strip()[3:]}</h3>")
        elif line.strip().startswith("* ") or line.strip().startswith("- "):
            if not in_list:
                formatted_lines.append("<ul style='margin-left: 20px;'>")
                in_list = True
            formatted_lines.append(f"<li style='margin-bottom: 8px;'>{line.strip()[2:]}</li>")
        else:
            if in_list:
                formatted_lines.append("</ul>")
                in_list = False
            if line.strip().startswith("**"):
                formatted_lines.append(f"<p style='margin: 16px 0; font-weight: 600;'>{line.strip().replace('**', '')}</p>")
            elif line.strip():
                formatted_lines.append(f"<p style='margin: 10px 0;'>{line}</p>")
            else:
                formatted_lines.append("<br>")

    if in_list:
        formatted_lines.append("</ul>")

    formatted_content = "\n".join(formatted_lines)

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 600;">🎙️ Voice Travel Agent</h1>
            <p style="margin: 10px 0 0 0; color: #e0e7ff; font-size: 16px;">Your Personalized Travel Itinerary</p>
        </div>
        <div style="background-color: #4f46e5; padding: 20px 30px; text-align: center;">
            <h2 style="margin: 0; color: #ffffff; font-size: 24px;">📍 {destination}</h2>
        </div>
        <div style="padding: 30px;">
            {formatted_content}
        </div>
        <div style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
            <p style="margin: 0 0 10px 0; color: #6b7280; font-size: 14px;">Have a wonderful trip! ✈️</p>
            <p style="margin: 0; color: #9ca3af; font-size: 12px;">Generated by Voice Travel Agent • Powered by ElevenLabs, Groq, and LangGraph</p>
        </div>
    </div>
</body>
</html>
"""


@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    """Voice interaction WebSocket endpoint."""
    if ws_handler is None:
        await websocket.close(code=1011, reason="Server not initialized")
        return

    await ws_handler.handle_connection(websocket)


# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted from: {static_dir}")
else:
    logger.warning(f"Static directory not found: {static_dir}")


if __name__ == "__main__":
    import uvicorn

    # Run server
    uvicorn.run(
        "app.server:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,  # Enable auto-reload for development
        log_level=settings.log_level.lower(),
    )
