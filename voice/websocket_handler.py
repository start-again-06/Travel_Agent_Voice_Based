
"""WebSocket handler for voice interactions."""
import logging
import json
import base64
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect

from app.voice.stt_service import STTService
from app.voice.tts_service import TTSService
from app.voice.session_manager import VoiceSessionManager
from app.agent.factory import AgentFactory
from app.agent.graph import get_system_message
from app.agent.prompts import get_clarifying_prompt, get_planning_prompt, get_reviewing_prompt
from langchain_core.messages import SystemMessage
import re
from datetime import datetime, timedelta

logger = logging.getLogger("websocket-handler")


class VoiceWebSocketHandler:
    """Handle WebSocket connections for voice interactions."""

    def __init__(
        self,
        stt_service: STTService,
        tts_service: TTSService,
        session_manager: VoiceSessionManager,
        agent_factory: AgentFactory,
    ):
        """
        Initialize WebSocket handler.

        Args:
            stt_service: Speech-to-text service
            tts_service: Text-to-speech service
            session_manager: Session manager
            agent_factory: Agent factory for getting agent instance
        """
        self.stt_service = stt_service
        self.tts_service = tts_service
        self.session_manager = session_manager
        self.agent_factory = agent_factory

        logger.info("WebSocket handler initialized")

    def _extract_trip_details(self, user_text: str, agent_response: str, session: dict):
        """Extract trip details from conversation and update session."""
        text_lower = (user_text + " " + agent_response).lower()

        # Extract destination
        if not session.get("destination"):
            # Common patterns: "to Jaipur", "in Paris", "visit Tokyo"
            destination_patterns = [
                r'(?:to|in|visit|going to|plan.*?for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            ]
            for pattern in destination_patterns:
                match = re.search(pattern, user_text + " " + agent_response)
                if match:
                    session["destination"] = match.group(1).strip()
                    logger.info(f"Extracted destination: {session['destination']}")
                    break

        # Extract duration
        if not session.get("duration"):
            duration_patterns = [
                r'(\d+)\s*day',
                r'(\d+)-day',
            ]
            for pattern in duration_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    session["duration"] = int(match.group(1))
                    logger.info(f"Extracted duration: {session['duration']} days")
                    break

        # Extract start date (simplified - use today + 1 week if not specified)
        if not session.get("start_date") and session.get("duration"):
            session["start_date"] = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            logger.info(f"Set default start date: {session['start_date']}")

    def _should_transition_to_planning(self, session: dict, agent_response: str) -> bool:
        """Check if we have enough information to start planning."""
        # Check if agent signals readiness
        if "let me create" in agent_response.lower() or "i have everything" in agent_response.lower():
            return True

        # Check if we have minimum required info
        has_destination = bool(session.get("destination"))
        has_duration = bool(session.get("duration"))
        questions_asked = session.get("clarifying_questions_asked", 0)

        if has_destination and has_duration and questions_asked >= 2:
            return True

        return False

    async def _generate_itinerary(self, websocket: WebSocket, session: dict, agent):
        """
        Automatically generate itinerary after transitioning to PLANNING phase.

        Args:
            websocket: WebSocket connection
            session: Session data
            agent: Agent instance
        """
        try:
            logger.info("Starting automatic itinerary generation")

            # Get planning prompt
            planning_prompt = get_planning_prompt(
                session.get("destination", "the destination"),
                session.get("duration", 3),
                session.get("start_date", "your travel dates"),
                session.get("interests", [])
            )

            # Create system message and trigger message
            system_msg = SystemMessage(content=planning_prompt)
            trigger_msg = ("user", "Please create the itinerary now.")

            # Configure with higher recursion limit for planning
            config = session["config"].copy()
            config["recursion_limit"] = 12
            logger.info(f"Set recursion limit to {config['recursion_limit']} for itinerary generation")

            # Stream agent response
            agent_response_parts = []

            async for event in agent.astream(
                {"messages": [system_msg, trigger_msg]},
                config=config,
                stream_mode="updates"
            ):
                for node, values in event.items():
                    if node == "chatbot":
                        last_msg = values["messages"][-1]

                        # Handle tool calls
                        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                            tool_names = [tc['name'] for tc in last_msg.tool_calls]
                            logger.info(f"Agent calling tools: {tool_names}")
                            await websocket.send_json({
                                "type": "agent_thinking",
                                "message": "Searching for information..."
                            })

                        # Handle text response
                        elif hasattr(last_msg, 'content') and last_msg.content:
                            agent_text = last_msg.content
                            agent_response_parts.append(agent_text)

                            logger.info(f"=== ITINERARY GENERATION RESPONSE ({len(agent_text)} chars) ===")
                            logger.info(agent_text[:500])

                            # Check if itinerary is included
                            if "---ITINERARY---" in agent_text:
                                # Split into spoken summary and detailed itinerary
                                parts = agent_text.split("---ITINERARY---", 1)
                                spoken_summary = parts[0].strip()
                                detailed_itinerary = parts[1].strip() if len(parts) > 1 else ""

                                # Save itinerary to session
                                session["current_itinerary"] = detailed_itinerary
                                session["phase"] = "REVIEWING"
                                logger.info("Saved itinerary and transitioned to REVIEWING phase")

                                # Send spoken summary as transcript
                                await websocket.send_json({
                                    "type": "transcript",
                                    "source": "agent",
                                    "text": spoken_summary,
                                    "is_final": True
                                })
                                logger.info(f"Agent summary: {spoken_summary[:100]}...")

                                # Send detailed itinerary for visual display
                                if detailed_itinerary:
                                    await websocket.send_json({
                                        "type": "itinerary_display",
                                        "content": detailed_itinerary
                                    })
                                    logger.info("Sent detailed itinerary for visual display")

                                # Convert ONLY the summary to speech
                                logger.info("Generating audio for spoken summary")
                                async for audio_chunk in self.tts_service.synthesize_stream(spoken_summary):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": audio_chunk
                                    })
                            else:
                                # Response without itinerary separator - just send it
                                await websocket.send_json({
                                    "type": "transcript",
                                    "source": "agent",
                                    "text": agent_text,
                                    "is_final": True
                                })
                                logger.info(f"Agent response: {agent_text[:100]}...")

                                # Convert to speech
                                async for audio_chunk in self.tts_service.synthesize_stream(agent_text):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": audio_chunk
                                    })

                    elif node == "tools":
                        logger.info("Tool execution completed")
                        await websocket.send_json({
                            "type": "agent_thinking",
                            "message": "Processing results..."
                        })

            # Send completion signal
            await websocket.send_json({
                "type": "agent_complete"
            })

            # Update session stats
            session["conversation_turns"] += 1
            logger.info(f"Itinerary generation completed. Total turns: {session['conversation_turns']}")

        except Exception as e:
            logger.error(f"Error generating itinerary: {e}", exc_info=True)
            await websocket.send_json({
                "type": "error",
                "message": "I'm sorry, I encountered an error creating your itinerary. Please try again."
            })

    async def handle_connection(self, websocket: WebSocket):
        """
        Main WebSocket connection handler.

        Args:
            websocket: FastAPI WebSocket connection
        """
        await websocket.accept()
        websocket_id = str(id(websocket))

        # Create session
        session = self.session_manager.create_session(websocket_id)
        logger.info(f"WebSocket connection accepted: {websocket_id}")

        try:
            await self._conversation_loop(websocket, session, websocket_id)
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {websocket_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket connection {websocket_id}: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Server error: {str(e)}"
                })
            except:
                pass
        finally:
            self.session_manager.remove_session(websocket_id)
            logger.info(f"WebSocket connection closed: {websocket_id}")

    async def _conversation_loop(
        self, websocket: WebSocket, session: dict, websocket_id: str
    ):
        """
        Main conversation processing loop.

        Args:
            websocket: WebSocket connection
            session: Session data
            websocket_id: WebSocket ID
        """
        audio_buffer = []

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            message_type = message.get("type")

            if message_type == "audio_chunk":
                # Accumulate audio chunk
                audio_data = base64.b64decode(message["data"])
                audio_buffer.append(audio_data)
                logger.debug(f"Received audio chunk: {len(audio_data)} bytes")

            elif message_type == "stop_recording":
                # User finished speaking - process complete utterance
                logger.info("Processing complete user utterance")
                await self._process_user_utterance(
                    websocket, audio_buffer, session
                )
                audio_buffer.clear()

            elif message_type == "interrupt":
                # User interrupted - stop current processing
                logger.info("User interrupted current processing")
                audio_buffer.clear()
                await websocket.send_json({
                    "type": "agent_interrupted",
                    "message": "Processing interrupted"
                })

            else:
                logger.warning(f"Unknown message type: {message_type}")

    async def _process_user_utterance(
        self, websocket: WebSocket, audio_buffer: list, session: dict
    ):
        """
        Process complete user utterance through the agent.

        Args:
            websocket: WebSocket connection
            audio_buffer: List of audio chunks
            session: Session data
        """
        if not audio_buffer:
            logger.warning("Empty audio buffer")
            return

        try:
            # 1. Transcribe audio to text
            full_audio = b''.join(audio_buffer)
            logger.info(f"Transcribing audio: {len(full_audio)} bytes")

            user_text = await self.stt_service.transcribe_file(full_audio)

            if not user_text or not user_text.strip():
                logger.warning("Empty transcription result")
                await websocket.send_json({
                    "type": "error",
                    "message": "Could not understand audio. Please try again."
                })
                return

            # Send user transcript to client
            await websocket.send_json({
                "type": "transcript",
                "source": "user",
                "text": user_text,
                "is_final": True
            })
            logger.info(f"User said: {user_text}")

            # 2. Get agent and process query
            agent = await self.agent_factory.get_agent()

            # Get phase-appropriate system message
            phase = session.get("phase", "CLARIFYING")
            logger.info(f"Current phase: {phase}")

            if phase == "CLARIFYING":
                system_prompt = get_clarifying_prompt()
            elif phase == "PLANNING":
                system_prompt = get_planning_prompt(
                    session.get("destination", "the destination"),
                    session.get("duration", 3),
                    session.get("start_date", "your travel dates"),
                    session.get("interests", [])
                )
            else:  # REVIEWING
                system_prompt = get_reviewing_prompt(
                    session.get("destination", "the destination"),
                    session.get("current_itinerary", "")
                )

            # Build messages - include phase-appropriate system message
            system_msg = SystemMessage(content=system_prompt)
            if session["conversation_turns"] == 0:
                input_messages = [system_msg, ("user", user_text)]
            else:
                # For subsequent turns, only add system message if phase changed
                input_messages = [system_msg, ("user", user_text)]

            # Configure with recursion limit
            config = session["config"].copy()
            if phase == "CLARIFYING":
                config["recursion_limit"] = 4  # No tools needed for clarifying
            else:
                config["recursion_limit"] = 12  # Allow more for planning/reviewing
            logger.info(f"Set recursion limit to {config['recursion_limit']}")

            # 3. Stream agent response
            agent_response_parts = []

            async for event in agent.astream(
                {"messages": input_messages},
                config=config,
                stream_mode="updates"
            ):
                for node, values in event.items():
                    if node == "chatbot":
                        last_msg = values["messages"][-1]

                        # Handle tool calls
                        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                            tool_names = [tc['name'] for tc in last_msg.tool_calls]
                            logger.info(f"Agent calling tools: {tool_names}")
                            await websocket.send_json({
                                "type": "agent_thinking",
                                "message": "Searching for information..."
                            })

                        # Handle text response
                        elif hasattr(last_msg, 'content') and last_msg.content:
                            agent_text = last_msg.content
                            agent_response_parts.append(agent_text)

                            # Log full response for debugging
                            logger.info(f"=== AGENT RESPONSE (Phase: {session.get('phase')}, {len(agent_text)} chars) ===")
                            logger.info(agent_text[:500])

                            # Extract trip details from conversation
                            self._extract_trip_details(user_text, agent_text, session)

                            # Check for phase transitions
                            current_phase = session.get("phase", "CLARIFYING")

                            if current_phase == "CLARIFYING":
                                session["clarifying_questions_asked"] = session.get("clarifying_questions_asked", 0) + 1

                                # Check if ready to plan
                                if self._should_transition_to_planning(session, agent_text):
                                    logger.info("Transitioning to PLANNING phase")
                                    session["phase"] = "PLANNING"

                                    # Send transition message to user
                                    await websocket.send_json({
                                        "type": "transcript",
                                        "source": "agent",
                                        "text": agent_text,
                                        "is_final": True
                                    })
                                    # Convert to speech
                                    async for audio_chunk in self.tts_service.synthesize_stream(agent_text):
                                        await websocket.send_json({
                                            "type": "audio_chunk",
                                            "data": audio_chunk
                                        })

                                    # Update session stats for this turn
                                    session["conversation_turns"] += 1
                                    logger.info(f"Conversation turn completed. Total turns: {session['conversation_turns']}")

                                    # Send completion signal for transition message
                                    await websocket.send_json({
                                        "type": "agent_complete"
                                    })

                                    # Now automatically invoke agent to generate the itinerary
                                    logger.info("Automatically invoking agent to generate itinerary")
                                    await self._generate_itinerary(websocket, session, agent)
                                    return  # Exit after generating itinerary

                                # Still clarifying - just send the question
                                await websocket.send_json({
                                    "type": "transcript",
                                    "source": "agent",
                                    "text": agent_text,
                                    "is_final": True
                                })
                                logger.info(f"Agent clarifying question: {agent_text[:100]}...")

                                # Convert to speech
                                async for audio_chunk in self.tts_service.synthesize_stream(agent_text):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": audio_chunk
                                    })

                            elif "---ITINERARY---" in agent_text:
                                # PLANNING or REVIEWING phase - display itinerary
                                # Split into spoken summary and detailed itinerary
                                parts = agent_text.split("---ITINERARY---", 1)
                                spoken_summary = parts[0].strip()
                                detailed_itinerary = parts[1].strip() if len(parts) > 1 else ""

                                # Save itinerary to session
                                session["current_itinerary"] = detailed_itinerary
                                session["phase"] = "REVIEWING"  # Move to reviewing after showing itinerary
                                logger.info("Saved itinerary and transitioned to REVIEWING phase")

                                # Send spoken summary as transcript
                                await websocket.send_json({
                                    "type": "transcript",
                                    "source": "agent",
                                    "text": spoken_summary,
                                    "is_final": True
                                })
                                logger.info(f"Agent summary: {spoken_summary[:100]}...")

                                # Send detailed itinerary for visual display only
                                if detailed_itinerary:
                                    await websocket.send_json({
                                        "type": "itinerary_display",
                                        "content": detailed_itinerary
                                    })
                                    logger.info("Sent detailed itinerary for visual display")

                                # Convert ONLY the summary to speech (not the full itinerary)
                                logger.info("Generating audio for spoken summary")
                                async for audio_chunk in self.tts_service.synthesize_stream(spoken_summary):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": audio_chunk
                                    })
                            else:
                                # Normal response without itinerary
                                await websocket.send_json({
                                    "type": "transcript",
                                    "source": "agent",
                                    "text": agent_text,
                                    "is_final": True
                                })
                                logger.info(f"Agent responded: {agent_text[:100]}...")

                                # Convert to speech and stream audio
                                logger.info("Generating audio for agent response")
                                async for audio_chunk in self.tts_service.synthesize_stream(agent_text):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": audio_chunk
                                    })

                    elif node == "tools":
                        logger.info("Tool execution completed")
                        await websocket.send_json({
                            "type": "agent_thinking",
                            "message": "Processing results..."
                        })

            # Send completion signal
            await websocket.send_json({
                "type": "agent_complete"
            })

            # Update session stats
            session["conversation_turns"] += 1
            logger.info(f"Conversation turn completed. Total turns: {session['conversation_turns']}")

        except Exception as e:
            logger.error(f"Error processing user utterance: {e}", exc_info=True)
            await websocket.send_json({
                "type": "error",
                "message": "I'm sorry, I encountered an error processing your request. Please try again."
            })
