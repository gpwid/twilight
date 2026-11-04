import sys
import os
import io
import threading
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
import torch
import soundfile as sf
from pathlib import Path

# Set optimal PyTorch threads for CPU inference (Ryzen 5 5500U)
torch.set_num_threads(min(8, os.cpu_count() or 4))

BASE_DIR = Path(__file__).resolve().parent
ENGINE_DIR = BASE_DIR / "rvc_engine"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

os.environ.setdefault("weight_root", str(BASE_DIR / "weights"))
os.environ.setdefault("rmvpe_root", str(ENGINE_DIR / "assets" / "rmvpe"))

class VoiceConverter:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        from configs.config import Config
        from infer.vc.modules import VC
        
        self.config = Config()
        self.vc = VC(self.config)
        self.model_name = "TwilightSparkle_Talking_Singing_e240_s5040.pth"
        self.index_path = str(BASE_DIR / "weights" / "added_IVF565_Flat_nprobe_1_TwilightSparkle_Talking_Singing_v2.index")
        
        print(f"[VoiceConverter] Preloading RVC v2 model: {self.model_name}...")
        self.vc.get_vc(self.model_name)
        print("[VoiceConverter] Model loaded and ready.")

    def convert_wav(self, input_wav_bytes: bytes, pitch_shift: int = 0, index_rate: float = 0.75, f0_method: str = "rmvpe") -> bytes:
        """Takes input WAV bytes from Edge-TTS, runs RVC inference, returns converted WAV bytes."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as in_f:
            in_f.write(input_wav_bytes)
            in_path = in_f.name

        try:
            status, result = self.vc.vc_single(
                0,               # speaker_id
                in_path,
                pitch_shift,     # pitch shift
                f0_method,       # rmvpe (clean pitch, zero buzz) or pm
                self.index_path,
                index_rate,      # 0.65 retrieves high-fidelity Twilight timbre without locking pitch
                0,               # resample_sr
                0.9,             # rms_mix_rate (preserves human volume dynamics & emotional peaks)
                0.5              # protect (preserves natural breath, whispers & clean consonants)
            )
            if not result or result[0] is None or result[1] is None:
                print(f"[VoiceConverter] Conversion failed, status: {status}")
                return input_wav_bytes

            sr, audio_data = result
            out_buf = io.BytesIO()
            sf.write(out_buf, audio_data, sr, format="WAV")
            return out_buf.getvalue()
        except Exception as e:
            print(f"[VoiceConverter] Error during conversion: {e}")
            return input_wav_bytes
        finally:
            if os.path.exists(in_path):
                try:
                    os.remove(in_path)
                except Exception:
                    pass
