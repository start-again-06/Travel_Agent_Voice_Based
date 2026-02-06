
"""Text-to-Speech service using ElevenLabs API."""
import logging
import base64
from typing import AsyncIterator, Iterator
import asyncio

from elevenlabs.client import ElevenLabs

logger = logging.getLogger("tts-service")


class TTSService:
    """ElevenLabs Text-to-Speech service."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",  # Bella voice
        model_id: str = "eleven_turbo_v2_5",  # Fastest model
    ):
        """
        Initialize TTS service.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID to use (default: Bella)
            model_id: Model ID to use (default: eleven_turbo_v2_5 for low latency)
        """
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id
        logger.info(f"TTS service initialized with voice: {voice_id}, model: {model_id}")

    def set_voice(self, voice_id: str):
        """Change the voice ID for speech synthesis."""
        self.voice_id = voice_id
        logger.info(f"Voice changed to: {voice_id}")

    async def synthesize_stream(self, text: str) -> AsyncIterator[str]:
        """
        Convert text to speech and stream audio chunks.

        Args:
            text: Text to convert to speech

        Yields:
            Base64-encoded audio chunks suitable for WebSocket transmission
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for TTS")
            return

        try:
            logger.info(f"Synthesizing speech for text: {text[:100]}...")

            # Run streaming TTS in executor to avoid blocking
            loop = asyncio.get_event_loop()

            # Generate audio stream
            def generate_audio():
                return self.client.text_to_speech.convert(
                    text=text,
                    voice_id=self.voice_id,
                    model_id=self.model_id,
                    output_format="mp3_44100_128",  # Good quality, reasonable size
                )

            audio_stream = await loop.run_in_executor(None, generate_audio)

            # Stream audio chunks
            chunk_count = 0
            for chunk in audio_stream:
                if isinstance(chunk, bytes) and len(chunk) > 0:
                    # Encode as base64 for JSON transmission
                    base64_chunk = base64.b64encode(chunk).decode('utf-8')
                    chunk_count += 1
                    yield base64_chunk

            logger.info(f"TTS complete: streamed {chunk_count} audio chunks")

        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise

    async def synthesize_file(self, text: str) -> bytes:
        """
        Convert text to speech and return complete audio file.

        Args:
            text: Text to convert to speech

        Returns:
            Complete audio data as bytes
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for TTS")
            return b""

        try:
            logger.info(f"Synthesizing audio file for text: {text[:100]}...")

            loop = asyncio.get_event_loop()

            def generate_audio():
                audio_stream = self.client.text_to_speech.convert(
                    text=text,
                    voice_id=self.voice_id,
                    model_id=self.model_id,
                    output_format="mp3_44100_128",
                )
                # Collect all chunks
                return b''.join(chunk for chunk in audio_stream if isinstance(chunk, bytes))

            audio_data = await loop.run_in_executor(None, generate_audio)
            logger.info(f"TTS complete: generated {len(audio_data)} bytes")
            return audio_data

        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise
