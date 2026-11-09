import json
import logging
import re
import threading
import time
from typing import Callable, List, Optional

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

logger = logging.getLogger("WakeWord")

# Suppress verbose Kaldi C++ engine logs
SetLogLevel(-1)


class WakeWordDetector:
    """
    Ultra-lightweight, 100% offline acoustic wake-word detector.
    Runs continuous background keyword spotting with Kaldi grammar FST (<1% CPU).
    Defaults to ["hey twi", "hey twilight", "twilight"], fully user-configurable.
    """

    DEFAULT_WAKE_WORDS = ["hey twi", "hey twilight", "twilight"]

    def __init__(
        self,
        config,
        on_wake: Callable[[str], None],
        is_speaking_fn: Optional[Callable[[], bool]] = None,
        is_voice_active_fn: Optional[Callable[[], bool]] = None,
        is_processing_fn: Optional[Callable[[], bool]] = None,
    ):
        self.config = config
        self.on_wake = on_wake
        self.is_speaking_fn = is_speaking_fn
        self.is_voice_active_fn = is_voice_active_fn
        self.is_processing_fn = is_processing_fn

        self.enabled = getattr(config, "wake_word_enabled", True)
        self.wake_words = self._clean_phrases(getattr(config, "wake_words", None) or self.DEFAULT_WAKE_WORDS)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.last_suppressed_time = time.time()
        self.last_wake_time = 0.0

        self.model = None
        self.recognizer = None
        self._is_ready = False

        # Asynchronously load model to keep startup instant (<0.1s)
        threading.Thread(target=self._init_model_and_start, daemon=True).start()

    def _clean_phrases(self, phrases: List[str]) -> List[str]:
        cleaned = []
        for p in phrases:
            # Lowercase and keep letters, numbers, spaces
            c = re.sub(r'[^a-zA-Z0-9\s]', '', str(p).lower()).strip()
            if c and c not in cleaned:
                cleaned.append(c)
        # Sort descending by length so longer phrases ("hey twilight") match before shorter sub-phrases ("twilight")
        cleaned.sort(key=lambda s: len(s), reverse=True)
        return cleaned or list(self.DEFAULT_WAKE_WORDS)

    def _init_model_and_start(self):
        try:
            # Load local cached small English model (~39MB)
            self.model = Model(model_name="vosk-model-small-en-us-0.15")
            self._update_grammar()
            self._is_ready = True
            print(f"[WakeWord] Engine active! Listening for wake phrases: {self.wake_words}")
            if self.enabled:
                self.start()
        except Exception as e:
            print(f"[WakeWord] Failed to initialize model: {e}")

    def _update_grammar(self):
        if not self.model:
            return
        interrupt_phrases = ["stop", "wait", "hold on", "quiet", "nevermind"]
        grammar = list(self.wake_words) + interrupt_phrases + ["[unk]"]
        self.recognizer = KaldiRecognizer(self.model, 16000, json.dumps(grammar))

    def reload_config(self, new_config):
        """Update enabled state and wake words dynamically when config changes on disk."""
        with self._lock:
            self.config = new_config
            new_enabled = getattr(new_config, "wake_word_enabled", True)
            new_phrases = self._clean_phrases(getattr(new_config, "wake_words", None) or self.DEFAULT_WAKE_WORDS)

            phrases_changed = (new_phrases != self.wake_words)
            self.wake_words = new_phrases
            self.enabled = new_enabled

            if phrases_changed and self.model:
                try:
                    self._update_grammar()
                    print(f"[WakeWord] Updated wake phrases: {self.wake_words}")
                except Exception as e:
                    print(f"[WakeWord] Error updating grammar: {e}")

            if not self.enabled and self.is_running():
                self.stop()
            elif self.enabled and not self.is_running() and self._is_ready:
                self.start()

    def is_running(self) -> bool:
        return self._worker_thread is not None and self._worker_thread.is_alive()

    def start(self):
        with self._lock:
            if not self.enabled or not self._is_ready:
                return
            if self.is_running():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._worker_thread.start()

    def stop(self):
        with self._lock:
            self._stop_event.set()

    def _is_suppressed(self) -> bool:
        """Check if wake word detection should be temporarily paused to prevent acoustic loops."""
        now = time.time()
        # Suppress if voice input manager is listening/recording/transcribing
        if self.is_voice_active_fn and self.is_voice_active_fn():
            self.last_suppressed_time = now
            return True
        # Suppress if brain is actively formulating a reply
        if self.is_processing_fn and self.is_processing_fn():
            self.last_suppressed_time = now
            return True
        # Post-suppression acoustic cooldown (1.0s to clear room echo and driver buffers)
        if now - self.last_suppressed_time < 1.0:
            return True
        # Minimum debounce interval between wake events (1.5s)
        if now - self.last_wake_time < 1.5:
            return True
        return False

    def _listen_loop(self):
        """Continuous background audio stream and keyword spotter."""
        device_idx = getattr(self.config, "mic_device_index", None)
        block_size = 4000  # 250ms at 16kHz

        while not self._stop_event.is_set() and self.enabled:
            if self._is_suppressed():
                time.sleep(0.1)
                continue

            try:
                with sd.RawInputStream(
                    samplerate=16000,
                    blocksize=block_size,
                    dtype="int16",
                    channels=1,
                    device=device_idx,
                ) as stream:
                    if self.recognizer:
                        self.recognizer.Reset()

                    while not self._stop_event.is_set() and self.enabled:
                        if self._is_suppressed():
                            # Flush all pending stream audio and reset Kaldi grammar state
                            try:
                                while stream.read_available >= block_size:
                                    stream.read(block_size)
                            except Exception:
                                pass
                            if self.recognizer:
                                self.recognizer.Reset()
                            time.sleep(0.1)
                            continue

                        data, overflowed = stream.read(block_size)
                        if not data or len(data) == 0:
                            continue

                        matched = False
                        if self.recognizer.AcceptWaveform(bytes(data)):
                            res = json.loads(self.recognizer.Result())
                            text = res.get("text", "").strip().lower()
                            if self._match_wake_word(text):
                                matched = True
                        else:
                            partial = json.loads(self.recognizer.PartialResult())
                            p_text = partial.get("partial", "").strip().lower()
                            if self._match_wake_word(p_text):
                                matched = True

                        if matched:
                            now = time.time()
                            self.last_wake_time = now
                            self.last_suppressed_time = now
                            # Drain residual audio so VoiceInputManager gets a fresh stream
                            try:
                                while stream.read_available > 0:
                                    stream.read(min(block_size, stream.read_available))
                            except Exception:
                                pass
                            if self.recognizer:
                                self.recognizer.Reset()
                            break

            except Exception as e:
                # Silently back off on device busy / disconnection
                time.sleep(0.5)

    def _match_wake_word(self, detected_text: str) -> bool:
        if not detected_text:
            return False

        targets = list(self.wake_words)
        # If Twilight is actively speaking, also allow quick voice interruption keywords
        if self.is_speaking_fn and self.is_speaking_fn():
            targets += ["stop", "wait", "hold on", "quiet", "nevermind"]

        for target in targets:
            if target in detected_text:
                print(f"[WakeWord] Detected wake/interrupt phrase: '{target}' in '{detected_text}'")
                if self.recognizer:
                    self.recognizer.Reset()
                if self.on_wake:
                    try:
                        self.on_wake(target)
                    except Exception as e:
                        print(f"[WakeWord] Error in on_wake callback: {e}")
                return True
        return False
