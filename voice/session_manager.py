"""Session management for voice WebSocket connections."""
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("session-manager")


class VoiceSessionManager:
    """Manage voice WebSocket sessions and their state."""

    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, Dict] = {}
        logger.info("Session manager initialized")

    def create_session(self, websocket_id: str) -> Dict:
        """
        Create a new voice session.

        Args:
            websocket_id: Unique identifier for the WebSocket connection

        Returns:
            Session data dictionary
        """
        thread_id = f"voice-session-{uuid.uuid4()}"

        session = {
            "thread_id": thread_id,
            "config": {"configurable": {"thread_id": thread_id}},
            "created_at": datetime.now(),
            "audio_buffer": [],
            "is_recording": False,
            "conversation_turns": 0,
            # Conversation state for multi-phase flow
            "phase": "CLARIFYING",  # CLARIFYING -> PLANNING -> REVIEWING
            "clarifying_questions_asked": 0,
            "destination": None,
            "duration": None,
            "start_date": None,
            "interests": [],
            "current_itinerary": None,
        }

        self.sessions[websocket_id] = session
        logger.info(f"Created session {thread_id} for websocket {websocket_id}")
        return session

    def get_session(self, websocket_id: str) -> Optional[Dict]:
        """
        Get session data for a WebSocket connection.

        Args:
            websocket_id: Unique identifier for the WebSocket connection

        Returns:
            Session data dictionary or None if not found
        """
        return self.sessions.get(websocket_id)

    def remove_session(self, websocket_id: str):
        """
        Remove a session when WebSocket disconnects.

        Args:
            websocket_id: Unique identifier for the WebSocket connection
        """
        session = self.sessions.pop(websocket_id, None)
        if session:
            logger.info(f"Removed session {session['thread_id']} for websocket {websocket_id}")
        else:
            logger.warning(f"Attempted to remove non-existent session for websocket {websocket_id}")

    def update_session(self, websocket_id: str, **kwargs):
        """
        Update session data.

        Args:
            websocket_id: Unique identifier for the WebSocket connection
            **kwargs: Fields to update in session data
        """
        session = self.sessions.get(websocket_id)
        if session:
            session.update(kwargs)
            logger.debug(f"Updated session for websocket {websocket_id}: {kwargs}")
        else:
            logger.warning(f"Attempted to update non-existent session for websocket {websocket_id}")

    def get_all_sessions(self) -> Dict[str, Dict]:
        """Get all active sessions."""
        return self.sessions.copy()

    def get_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self.sessions)
