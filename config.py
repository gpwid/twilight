import json
import os
from dataclasses import dataclass, field, asdict

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

@dataclass
class Config:
    # Providers: "google", "groq", "openai", "claude"
    provider: str = "google"
    api_key: str = ""  # Google Gemini API key
    groq_api_key: str = ""
    openai_api_key: str = ""
    claude_api_key: str = ""

    model: str = "gemini-3.5-flash-lite"
    deep_model: str = "gemini-3.6-flash"
    model_cascade: list = field(default_factory=lambda: [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.6-flash"
    ])
    model_cascade_google: list = field(default_factory=list)
    model_cascade_groq: list = field(default_factory=list)
    model_cascade_openai: list = field(default_factory=list)
    model_cascade_claude: list = field(default_factory=list)
    
    # Audio Engines: "fish_audio", "elevenlabs", "local_rvc", "edge_tts"
    tts_engine: str = "fish_audio"
    fish_audio_api_key: str = ""
    fish_audio_model_id: str = "16fb9e5787c94f3ea110207e3d1673b8"
    fish_audio_backend: str = "s2.1-pro-free"  # "s2.1-pro-free" or "s2.1-pro"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    
    # Local RVC fallback settings
    use_rvc: bool = True
    rvc_pitch: int = 0
    rvc_index_rate: float = 0.65
    rvc_f0_method: str = "rmvpe"
    tts_voice: str = "en-US-AvaNeural"
    tts_rate: str = "+6%"
    tts_pitch: str = "+0Hz"
    
    # Voice Command / Speech-to-Text (STT) Settings
    voice_input_enabled: bool = True
    voice_input_hotkey: str = "ctrl+shift+v"
    stt_engine: str = "groq_whisper"  # "groq_whisper" | "gemini"
    mic_silence_timeout: float = 1.2
    mic_energy_threshold: int = 30
    mic_device_index: int | None = None

    # Wake Word Settings
    wake_word_enabled: bool = True
    wake_words: list[str] = field(default_factory=lambda: ["hey twi", "hey twilight", "twilight"])

    # Overlay UI settings
    halo_size: int = 70
    initial_x: int = -1
    initial_y: int = -1
    expressions_dir: str = "assets/expressions"
    summon_hotkey: str = "ctrl+shift+space"
    ui_scale: float = 1.0

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        if "GEMINI_API_KEY" in os.environ:
            cfg.api_key = os.environ["GEMINI_API_KEY"]
        if "GROQ_API_KEY" in os.environ:
            cfg.groq_api_key = os.environ["GROQ_API_KEY"]
        if "OPENAI_API_KEY" in os.environ:
            cfg.openai_api_key = os.environ["OPENAI_API_KEY"]
        if "ANTHROPIC_API_KEY" in os.environ:
            cfg.claude_api_key = os.environ["ANTHROPIC_API_KEY"]
        if "FISH_API_KEY" in os.environ:
            cfg.fish_audio_api_key = os.environ["FISH_API_KEY"]
        if "ELEVENLABS_API_KEY" in os.environ:
            cfg.elevenlabs_api_key = os.environ["ELEVENLABS_API_KEY"]
            
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(cfg, k):
                            setattr(cfg, k, v)
            except Exception as e:
                print(f"Warning: Could not read config.json: {e}")
        else:
            cfg.save()
        return cfg

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            print(f"Warning: Could not save config.json: {e}")
