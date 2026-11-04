import asyncio
import io
import queue
import re
import threading
import time
import edge_tts
import pygame
from fish_audio_client import FishAudioClient, FishAudioQuotaError, FishAudioAuthError, FishAudioError, sanitize_wav_header

def normalize_speech_text(text: str) -> str:
    """Normalize acronyms, symbols, and special pronunciations for natural TTS rendering."""
    if not text:
        return ""
    text = text.replace("bôa", "boa").replace("bÃ´a", "boa")
    text = re.sub(r'(\d+)%', r'\1 percent', text)
    text = text.replace('&', ' and ')
    text = text.replace('@', ' at ')
    text = re.sub(r'\bvs\.?\b', 'versus', text, flags=re.IGNORECASE)
    text = re.sub(r'\be\.g\.?\b', 'for example', text, flags=re.IGNORECASE)
    text = re.sub(r'\bi\.e\.?\b', 'that is', text, flags=re.IGNORECASE)
    
    acronyms = {
        r'\bCAS\b': 'C.A.S.',
        r'\bURL\b': 'U.R.L.',
        r'\bURLs\b': 'U.R.L.s',
        r'\bPID\b': 'P.I.D.',
        r'\bAPI\b': 'A.P.I.',
        r'\bAPIs\b': 'A.P.I.s',
        r'\bUI\b': 'U.I.',
        r'\bTTS\b': 'T.T.S.',
        r'\bRVC\b': 'R.V.C.',
        r'\bCLI\b': 'C.L.I.',
        r'\bGUI\b': 'G.U.I.',
        r'\bSDK\b': 'S.D.K.',
        r'\bGIMP\b': 'gimp',
    }
    for pat, rep in acronyms.items():
        text = re.sub(pat, rep, text)
    return text

def split_into_speech_chunks(text: str) -> list[str]:
    """Splits text into coherent spoken sections (~20-30 words) to avoid mid-sentence stutter."""
    if not text:
        return []
    
    # 0. Replace fenced code blocks so TTS never reads raw code syntax aloud
    text = re.sub(r'```[\s\S]*?```', ', as shown in the code on your screen, ', text)

    # 1. Phonetic & acronym normalization
    text = normalize_speech_text(text)

    # 2. Clean markdown formatting
    text = re.sub(r'[*_#`]', '', text).strip()
    
    # 3. Strip bracket action tags so TTS doesn't speak "bracket chuckle bracket"
    text = re.sub(r'\[.*?\]', '', text)
    
    # 4. Strip awkward literal text laughter ("haha", "hahaha", "heh", "lol") that TTS reads robotically
    text = re.sub(r'[,.\s]*\b(?:haha+|hehe+|heh+|lol)\b[,.!?]*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s{2,}', ' ', text).strip()

    raw = [s.strip() for s in re.split(r'(?<=[.!?\n])\s+', text) if s.strip()]
    if not raw:
        return [text]
    
    chunks = []
    curr = ""
    for s in raw:
        if not curr:
            curr = s
            # Ultra-fast time-to-first-voice: emit first complete sentence immediately
            if not chunks and len(curr) >= 20:
                chunks.append(curr)
                curr = ""
        elif len(curr) + len(s) + 1 <= 140:
            curr += " " + s
        else:
            chunks.append(curr)
            curr = s
    if curr:
        chunks.append(curr)
    return chunks if chunks else [text]

class AudioManager:
    def __init__(
        self,
        voice="en-US-AvaNeural",
        rate="+6%",
        pitch="+0Hz",
        use_rvc=True,
        rvc_pitch=0,
        rvc_index_rate=0.65,
        rvc_f0_method="rmvpe",
        tts_engine="fish_audio",
        fish_audio_api_key="",
        fish_audio_model_id="16fb9e5787c94f3ea110207e3d1673b8",
        fish_audio_backend="s2.1-pro-free",
        elevenlabs_api_key="",
        elevenlabs_voice_id=""
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.use_rvc = use_rvc
        self.rvc_pitch = rvc_pitch
        self.rvc_index_rate = rvc_index_rate
        self.rvc_f0_method = rvc_f0_method
        self.tts_engine = tts_engine
        self.fish_audio_api_key = fish_audio_api_key
        self.fish_audio_model_id = fish_audio_model_id
        self.fish_audio_backend = fish_audio_backend
        self.elevenlabs_api_key = elevenlabs_api_key
        self.elevenlabs_voice_id = elevenlabs_voice_id
        
        self.fish_client = FishAudioClient(
            api_key=fish_audio_api_key,
            model_id=fish_audio_model_id,
            backend_model=fish_audio_backend
        )
        
        # 2-Stage Streaming Pipelining:
        # Stage 1: Synthesis & RVC conversion worker
        # Stage 2: Audio playback worker
        self._synthesis_queue = queue.Queue()
        self._playback_queue = queue.Queue()
        
        self._is_speaking = False
        self._stop_event = threading.Event()
        self._current_channel = None
        
        # Initialize mixer at standard 44.1kHz with 2048 buffer
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            except Exception as e:
                print(f"pygame.mixer init error: {e}")
                pygame.mixer.init()

        # Preload RVC in background if enabled
        if self.use_rvc:
            threading.Thread(target=self._preload_rvc, daemon=True).start()

        # Start background workers
        self._converter_thread = threading.Thread(target=self._converter_loop, daemon=True)
        self._converter_thread.start()

        self._player_thread = threading.Thread(target=self._player_loop, daemon=True)
        self._player_thread.start()

    def _preload_rvc(self):
        try:
            from voice_converter import VoiceConverter
            VoiceConverter.get_instance()
        except Exception as e:
            print(f"[AudioManager] RVC preload warning: {e}")

    def speak(self, text: str, on_start=None, on_done=None):
        """Enqueue text for rapid pipelined conversion and playback."""
        if not text or not text.strip():
            if on_start:
                try:
                    on_start()
                except Exception:
                    pass
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return

        if self.tts_engine == "off":
            if on_start:
                try:
                    on_start()
                except Exception:
                    pass
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return
        
        # Extract emotion tag before chunks are stripped
        em_match = re.search(r'\[emotion:\s*([a-zA-Z0-9_\-]+)\]', text)
        emotion = em_match.group(1).lower() if em_match else "neutral"

        chunks = split_into_speech_chunks(text)
        if not chunks:
            return

        total = len(chunks)
        for i, chunk in enumerate(chunks):
            is_first = (i == 0)
            is_last = (i == total - 1)
            self._synthesis_queue.put({
                "text": chunk,
                "emotion": emotion,
                "is_first": is_first,
                "is_last": is_last,
                "on_start": on_start if is_first else None,
                "on_done": on_done if is_last else None
            })

    def is_speaking(self) -> bool:
        return self._is_speaking or (self._current_channel.get_busy() if self._current_channel else False)

    def stop(self):
        """Interrupt and clear all active speech immediately."""
        self._stop_event.set()
        while not self._synthesis_queue.empty():
            try:
                self._synthesis_queue.get_nowait()
            except queue.Empty:
                break
        while not self._playback_queue.empty():
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                break
        
        if self._current_channel:
            self._current_channel.stop()
        if pygame.mixer.get_init():
            pygame.mixer.stop()
            
        self._is_speaking = False
        time.sleep(0.05)
        self._stop_event.clear()

    def _converter_loop(self):
        """Stage 1: Converts text chunks one-by-one and forwards audio immediately to player."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            try:
                item = self._synthesis_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._stop_event.is_set():
                continue

            chunk_text = item["text"]
            emotion = item.get("emotion", "neutral")
            final_wav_bytes = None

            # 1. Try Fish Audio cloud API if configured
            if self.tts_engine == "fish_audio" and self.fish_client.is_configured():
                try:
                    final_wav_bytes = self.fish_client.synthesize(chunk_text)
                except FishAudioQuotaError as e:
                    print(f"[AudioManager] Fish Audio quota exhausted ({e}). Falling back to local RVC.")
                except FishAudioAuthError as e:
                    print(f"[AudioManager] Fish Audio auth error ({e}). Falling back to local RVC.")
                except Exception as e:
                    print(f"[AudioManager] Fish Audio error ({e}). Falling back to local RVC.")

            # 2. Try ElevenLabs cloud API if configured
            elif self.tts_engine == "elevenlabs" and self.elevenlabs_api_key and self.elevenlabs_voice_id:
                try:
                    final_wav_bytes = self._synthesize_elevenlabs(chunk_text)
                except Exception as e:
                    print(f"[AudioManager] ElevenLabs error ({e}). Falling back to local RVC.")

            # 3. Local fallback via Edge-TTS + RVC if cloud was not used or failed
            if not final_wav_bytes:
                try:
                    base_wav_bytes = loop.run_until_complete(self._synthesize(chunk_text, emotion=emotion))
                    final_wav_bytes = base_wav_bytes

                    if self.use_rvc and base_wav_bytes:
                        try:
                            from voice_converter import VoiceConverter
                            converter = VoiceConverter.get_instance()
                            final_wav_bytes = converter.convert_wav(
                                base_wav_bytes,
                                pitch_shift=self.rvc_pitch,
                                index_rate=self.rvc_index_rate,
                                f0_method=self.rvc_f0_method
                            )
                        except Exception as e:
                            print(f"[AudioManager] RVC conversion fallback: {e}")
                except Exception as e:
                    print(f"[AudioManager] Local synthesis error: {e}")

            if final_wav_bytes and not self._stop_event.is_set():
                self._playback_queue.put({
                    "audio_bytes": final_wav_bytes,
                    "is_first": item["is_first"],
                    "is_last": item["is_last"],
                    "on_start": item["on_start"],
                    "on_done": item["on_done"]
                })
            else:
                if item["is_first"] and item.get("on_start"):
                    try:
                        item["on_start"]()
                    except Exception:
                        pass
                if item["is_last"] and item.get("on_done"):
                    try:
                        item["on_done"]()
                    except Exception:
                        pass

    def _create_sound(self, audio_bytes: bytes) -> pygame.mixer.Sound:
        """Robustly decodes audio bytes into pygame.mixer.Sound with multi-tier fallback."""
        # 1. Direct load with sanitized header
        try:
            clean = sanitize_wav_header(audio_bytes)
            return pygame.mixer.Sound(io.BytesIO(clean))
        except Exception:
            pass

        # 2. Raw unedited bytes (in case sanitize altered a valid stream)
        try:
            return pygame.mixer.Sound(io.BytesIO(audio_bytes))
        except Exception:
            pass

        # 3. Libsndfile / soundfile re-encode into clean 16-bit PCM WAV
        try:
            import soundfile as sf
            data, sr = sf.read(io.BytesIO(audio_bytes))
            buf = io.BytesIO()
            sf.write(buf, data, sr, format="WAV", subtype="PCM_16")
            return pygame.mixer.Sound(io.BytesIO(buf.getvalue()))
        except Exception:
            pass

        # 4. Disk file fallback
        import os
        import tempfile
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_name = f.name
            return pygame.mixer.Sound(tmp_name)
        except Exception:
            return None
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except Exception:
                    pass

    def _player_loop(self):
        """Stage 2: Plays converted audio chunks sequentially with zero lag between sentences."""
        while True:
            try:
                item = self._playback_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._stop_event.is_set():
                continue

            audio_bytes = item["audio_bytes"]
            is_first = item["is_first"]
            is_last = item["is_last"]
            on_start = item["on_start"]
            on_done = item["on_done"]

            if is_first:
                self._is_speaking = True
                if on_start:
                    try:
                        on_start()
                    except Exception as e:
                        print(f"on_start error: {e}")

            if audio_bytes and len(audio_bytes) > 0 and not self._stop_event.is_set():
                try:
                    sound = self._create_sound(audio_bytes)
                    if sound:
                        self._current_channel = sound.play()
                        if self._current_channel:
                            while self._current_channel.get_busy() and not self._stop_event.is_set():
                                time.sleep(0.02)
                except Exception as e:
                    print(f"[AudioManager] Playback error: {e}")

            if is_last:
                self._is_speaking = False
                if on_done:
                    try:
                        on_done()
                    except Exception as e:
                        print(f"on_done error: {e}")

    async def _synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """Fetch WAV bytes from Edge TTS asynchronously with dynamic emotion-mapped prosody."""
        prosody_map = {
            "excited": {"rate": "+12%", "pitch": "+10Hz"},
            "cheerful": {"rate": "+8%", "pitch": "+6Hz"},
            "happy": {"rate": "+8%", "pitch": "+6Hz"},
            "analyzing": {"rate": "+4%", "pitch": "+2Hz"},
            "curious": {"rate": "+6%", "pitch": "+8Hz"},
            "surprised": {"rate": "+10%", "pitch": "+12Hz"},
            "music": {"rate": "+4%", "pitch": "+4Hz"},
            "sad": {"rate": "-6%", "pitch": "-6Hz"},
            "gentle": {"rate": "-4%", "pitch": "-2Hz"},
            "thinking": {"rate": "+2%", "pitch": "+2Hz"},
        }
        params = prosody_map.get(emotion, {"rate": self.rate, "pitch": self.pitch})

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=params["rate"],
            pitch=params["pitch"]
        )
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def _synthesize_elevenlabs(self, text: str) -> bytes:
        """Synthesize speech using ElevenLabs API."""
        if not self.elevenlabs_api_key or not self.elevenlabs_voice_id:
            raise ValueError("ElevenLabs API Key and Voice ID are required.")
        import httpx
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}?output_format=mp3_44100_128"
        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        resp = httpx.post(url, headers=headers, json=payload, timeout=12.0)
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs error ({resp.status_code}): {resp.text[:100]}")
        return resp.content

    def reload_config(self, cfg):
        """Dynamically reload audio engine settings from updated Config."""
        self.tts_engine = getattr(cfg, "tts_engine", self.tts_engine)
        self.fish_audio_api_key = getattr(cfg, "fish_audio_api_key", self.fish_audio_api_key)
        self.fish_audio_model_id = getattr(cfg, "fish_audio_model_id", self.fish_audio_model_id)
        self.fish_audio_backend = getattr(cfg, "fish_audio_backend", self.fish_audio_backend)
        self.elevenlabs_api_key = getattr(cfg, "elevenlabs_api_key", self.elevenlabs_api_key)
        self.elevenlabs_voice_id = getattr(cfg, "elevenlabs_voice_id", self.elevenlabs_voice_id)
        self.use_rvc = getattr(cfg, "use_rvc", self.use_rvc)
        self.rvc_pitch = getattr(cfg, "rvc_pitch", self.rvc_pitch)
        self.rvc_index_rate = getattr(cfg, "rvc_index_rate", self.rvc_index_rate)
        self.fish_client = FishAudioClient(
            api_key=self.fish_audio_api_key,
            model_id=self.fish_audio_model_id,
            backend_model=self.fish_audio_backend
        )
        print(f"[AudioManager] Settings reloaded: engine={self.tts_engine}, rvc={self.use_rvc}")
