import io
import json
import logging
import math
import os
import re
import threading
import time
from typing import Callable, Optional

import httpx
import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("VoiceInput")


class VoiceInputManager:
    """
    Ultra-responsive Voice Command & Speech-to-Text Manager for Twilight Sparkle.
    Captures 16kHz mono audio via sounddevice with real-time RMS Voice Activity Detection (VAD),
    and transcribes speech in ~200ms using Groq Whisper (with automatic Google Gemini fallback).
    """

    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_RECORDING = "recording"
    STATE_PROCESSING = "processing"

    def __init__(
        self,
        config,
        is_speaking_fn: Optional[Callable[[], bool]] = None,
        on_state_change: Optional[Callable[[str, str], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None,
        on_transcription_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.is_speaking_fn = is_speaking_fn
        self.on_state_change = on_state_change
        self.on_audio_level = on_audio_level
        self.on_transcription_complete = on_transcription_complete
        self.on_error = on_error

        self.state = self.STATE_IDLE
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.sample_rate = 16000
        self.block_size = 640  # 40ms at 16kHz
        self.silence_timeout = getattr(config, "mic_silence_timeout", 1.2)
        self.energy_threshold = getattr(config, "mic_energy_threshold", 400)
        self.stt_engine = getattr(config, "stt_engine", "groq_whisper")

    def _set_state(self, new_state: str, details: str = ""):
        self.state = new_state
        if self.on_state_change:
            try:
                self.on_state_change(new_state, details)
            except Exception as e:
                logger.error(f"Error in on_state_change callback: {e}")

    def is_active(self) -> bool:
        return self.state in (self.STATE_LISTENING, self.STATE_RECORDING, self.STATE_PROCESSING)

    def toggle_listening(self):
        """Toggle voice capture on or off. If already recording, stops and transcribes immediately."""
        with self._lock:
            if self.is_active():
                self.stop_listening(force_transcribe=True)
            else:
                self.start_listening()

    def start_listening(self):
        """Begin non-blocking microphone capture with Voice Activity Detection."""
        with self._lock:
            # If Twilight's own TTS is currently speaking, wait or abort to prevent audio feedback
            if self.is_speaking_fn and self.is_speaking_fn():
                print("[VoiceInput] Twilight is currently speaking. Waiting for speech to finish before listening.")
                return

            if self.is_active():
                return

            self._stop_event.clear()
            self._cancel_event.clear()
            self._set_state(self.STATE_LISTENING, "I'm listening... Speak now!")
            self._worker_thread = threading.Thread(target=self._capture_and_process_loop, daemon=True)
            self._worker_thread.start()

    def stop_listening(self, force_transcribe: bool = True):
        """Stop active microphone recording and process captured audio."""
        self._stop_event.set()

    def cancel(self):
        """Cancel voice input without transcribing or triggering callbacks."""
        self._cancel_event.set()
        self._stop_event.set()
        self._set_state(self.STATE_IDLE, "")
        if self.on_audio_level:
            try:
                self.on_audio_level(0.0)
            except Exception:
                pass

    def _capture_and_process_loop(self):
        """Continuous background audio capture and VAD loop."""
        recorded_chunks = []
        speech_started = False
        silence_start_time = None
        start_time = time.time()
        baseline_samples = []
        dynamic_threshold = self.energy_threshold

        device_idx = getattr(self.config, "mic_device_index", None)

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.block_size,
                device=device_idx,
            ) as stream:
                while not self._stop_event.is_set():
                    data, overflowed = stream.read(self.block_size)
                    chunk = data.flatten()
                    
                    # Compute chunk RMS for volume level and VAD
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    norm_level = min(1.0, max(0.0, rms / 1400.0))
                    
                    if self.on_audio_level:
                        try:
                            self.on_audio_level(norm_level)
                        except Exception:
                            pass

                    # Calibrate ambient noise floor over first 250ms
                    if len(baseline_samples) < 6:
                        baseline_samples.append(rms)
                        dynamic_threshold = max(self.energy_threshold, int(np.mean(baseline_samples) * 1.85))
                        continue

                    # Speech Detection Logic
                    if rms >= dynamic_threshold:
                        if not speech_started:
                            speech_started = True
                            self._set_state(self.STATE_RECORDING, "Listening to your request...")
                        silence_start_time = None
                        recorded_chunks.append(chunk)
                    elif speech_started:
                        recorded_chunks.append(chunk)
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time >= self.silence_timeout:
                            # User finished speaking: trigger transcription
                            break
                    else:
                        # Keep a small rolling pre-speech buffer (last 240ms) so the first syllable isn't cut off
                        recorded_chunks.append(chunk)
                        if len(recorded_chunks) > 6:
                            recorded_chunks.pop(0)

                    # Safety timeout: stop if user leaves mic open for >20 seconds
                    if time.time() - start_time > 20.0:
                        break

        except Exception as e:
            print(f"[VoiceInput] Microphone stream error: {e}")
            if self.on_error:
                self.on_error(f"Microphone error: {e}")
            self._set_state(self.STATE_IDLE, "")
            return

        # Reset audio level indicator
        if self.on_audio_level:
            try:
                self.on_audio_level(0.0)
            except Exception:
                pass

        if self._cancel_event.is_set():
            print("[VoiceInput] Recording was cancelled by user.")
            self._set_state(self.STATE_IDLE, "")
            return

        # If user manually stopped and we have recorded chunks, allow transcription even if threshold was borderline
        if not recorded_chunks or (not speech_started and not self._stop_event.is_set()):
            print("[VoiceInput] No speech detected or recording was aborted.")
            self._set_state(self.STATE_IDLE, "")
            return

        # Process and Transcribe
        self._set_state(self.STATE_PROCESSING, "Processing voice command...")
        try:
            full_audio = np.concatenate(recorded_chunks, axis=0)
            # Must have at least 0.4s of audio to be valid speech
            if len(full_audio) < int(self.sample_rate * 0.4):
                print("[VoiceInput] Speech sample too brief (<0.4s). Dropping.")
                self._set_state(self.STATE_IDLE, "")
                return

            wav_buf = io.BytesIO()
            sf.write(wav_buf, full_audio, self.sample_rate, format="WAV", subtype="PCM_16")
            wav_bytes = wav_buf.getvalue()

            text = self.transcribe(wav_bytes)
            if text and text.strip():
                clean_text = self._clean_transcription(text)
                print(f"[VoiceInput] Recognized: '{clean_text}'")
                self._set_state(self.STATE_IDLE, "")
                if self.on_transcription_complete:
                    self.on_transcription_complete(clean_text)
            else:
                print("[VoiceInput] Transcription returned empty text.")
                self._set_state(self.STATE_IDLE, "")
        except Exception as e:
            print(f"[VoiceInput] Transcription error: {e}")
            if self.on_error:
                self.on_error(f"Transcription error: {e}")
            self._set_state(self.STATE_IDLE, "")

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV bytes using the configured STT engine with automatic fallback."""
        engine = getattr(self.config, "stt_engine", "groq_whisper").lower()

        if engine == "groq_whisper":
            try:
                text = self._transcribe_groq(wav_bytes)
                if text:
                    return text
            except Exception as e:
                print(f"[VoiceInput] Groq Whisper failed ({e}). Attempting Gemini fallback...")

        # Fallback or primary Gemini transcription
        try:
            return self._transcribe_gemini(wav_bytes)
        except Exception as e:
            print(f"[VoiceInput] Gemini transcription failed: {e}")
            raise RuntimeError(f"All STT providers failed: {e}")

    def _transcribe_groq(self, wav_bytes: bytes) -> str:
        """Execute ultra-fast transcription via Groq Cloud Whisper API (~200ms latency) with network retry."""
        key = getattr(self.config, "groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise ValueError("Groq API Key is not configured.")

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {key}"
        }
        files = {
            "file": ("voice_command.wav", wav_bytes, "audio/wav")
        }
        data = {
            "model": "whisper-large-v3-turbo",
            "language": "en",
            "prompt": "Twilight, Sci-Twi, Spotify, Radiohead, Clairo, play, pause, search, tab, browser, volume"
        }

        last_err = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.post(url, headers=headers, data=data, files=files)
                    if resp.status_code != 200:
                        raise RuntimeError(f"Groq API error ({resp.status_code}): {resp.text[:120]}")
                    result = resp.json()
                    return result.get("text", "").strip()
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, OSError) as e:
                last_err = e
                time.sleep(0.35)

        raise RuntimeError(f"Groq Whisper network error after retry: {last_err}")

    def _transcribe_gemini(self, wav_bytes: bytes) -> str:
        """Execute multimodal audio transcription via Google Gemini 3.5 Flash-Lite."""
        key = getattr(self.config, "api_key", "") or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("Google Gemini API Key is not configured.")

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
        prompt = (
            "You are a Speech-to-Text transcription tool. "
            "Listen to the audio and transcribe the user's spoken words exactly as spoken. "
            "Output ONLY the plain transcription text. "
            "Do not include quotes, explanations, markdown, or timestamps. "
            "If the audio is silence or unintelligible, output nothing."
        )

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[audio_part, prompt],
        )

        out = (response.text or "").strip()
        if out.upper() in ("SILENCE", "NOTHING", "[SILENCE]", "EMPTY"):
            return ""
        return out

    def _clean_transcription(self, text: str) -> str:
        """Remove common hallucinated Whisper artifacts on trailing silence."""
        cleaned = text.strip()
        cleaned = re.sub(r'^(?:\[.*?\]|\(.*?\))\s*', '', cleaned)
        cleaned = re.sub(r'\s*(?:\[.*?\]|\(.*?\))$', '', cleaned)
        # Filter typical Whisper phantom phrases on quiet breath
        phantom_phrases = (
            "Thank you.", "Thanks for watching!", "Subtitles by",
            "MBC", "Please subscribe", "Bye.", "See you next time."
        )
        for ph in phantom_phrases:
            if cleaned.lower() == ph.lower():
                return ""
        return cleaned
