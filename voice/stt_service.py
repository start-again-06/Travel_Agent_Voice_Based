
"""Speech-to-Text service using ElevenLabs API."""
import logging
from typing import AsyncIterator, Dict, Optional
import asyncio
from io import BytesIO

from elevenlabs.client import ElevenLabs

logger = logging.getLogger("stt-service")


class STTService:
    """ElevenLabs Speech-to-Text service."""

    def __init__(self, api_key: str):
        """Initialize STT service with API key."""
        self.client = ElevenLabs(api_key=api_key)
        logger.info("STT service initialized")

    async def transcribe_file(self, audio_data: bytes) -> str:
        try:
            logger.debug(f"Transcribing audio file ({len(audio_data)} bytes)")

            audio_file = BytesIO(audio_data)
            audio_file.name = "audio.webm"

            result = await asyncio.to_thread(
                self.client.speech_to_text.convert,
                file=audio_file,
                model_id="scribe_v2",
            )

            transcript = result.text if hasattr(result, "text") else str(result)
            logger.info(f"Transcription complete: {transcript[:100]}...")
            return transcript

        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            raise

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[Dict[str, any]]:
        """
        Stream audio chunks and yield transcription results.

        Args:
            audio_chunks: Async iterator of audio data chunks

        Yields:
            Dictionary with:
                - text: Partial or final transcript
                - is_final: Whether this is the final result
                - timestamp: Current timestamp
        """
        # Buffer for accumulating audio chunks
        audio_buffer = []
        buffer_duration = 0

        try:
            async for chunk in audio_chunks:
                audio_buffer.append(chunk)
                buffer_duration += len(chunk) / 16000  # Assuming 16kHz sample rate

                # Process buffer when we have ~1 second of audio
                if buffer_duration >= 1.0:
                    full_audio = b''.join(audio_buffer)

                    # Transcribe accumulated audio
                    try:
                        transcript = await self.transcribe_file(full_audio)

                        if transcript and transcript.strip():
                            yield {
                                "text": transcript,
                                "is_final": False,
                                "timestamp": asyncio.get_event_loop().time()
                            }
                    except Exception as e:
                        logger.error(f"Error transcribing chunk: {e}")

                    # Keep last 0.5s for context overlap
                    overlap_bytes = int(16000 * 0.5 * 2)  # 0.5s at 16kHz, 16-bit
                    audio_buffer = [full_audio[-overlap_bytes:]]
                    buffer_duration = 0.5

        except Exception as e:
            logger.error(f"STT streaming failed: {e}")
            raise

    async def finalize_transcription(self, audio_buffer: list) -> str:
        """
        Finalize transcription of remaining audio in buffer.

        Args:
            audio_buffer: List of audio chunks

        Returns:
            Final transcript
        """
        if not audio_buffer:
            return ""

        full_audio = b''.join(audio_buffer)
        return await self.transcribe_file(full_audio)
