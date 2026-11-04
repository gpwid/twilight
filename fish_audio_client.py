import httpx
import time
import struct
import threading

def sanitize_wav_header(wav_bytes: bytes) -> bytes:
    """Fix streaming WAV headers where total size is set to 0xFFFFFFFF (4.2GB), preventing SDL malloc OOM crashes."""
    if not wav_bytes or len(wav_bytes) < 44 or not wav_bytes.startswith(b"RIFF"):
        return wav_bytes
    try:
        data = bytearray(wav_bytes)
        total_len = len(data)
        struct.pack_into("<I", data, 4, total_len - 8)
        data_idx = data.find(b"data")
        if data_idx != -1:
            struct.pack_into("<I", data, data_idx + 4, total_len - (data_idx + 8))
        return bytes(data)
    except Exception:
        return wav_bytes

class FishAudioError(Exception):
    """Base exception for Fish Audio API errors."""
    pass

class FishAudioQuotaError(FishAudioError):
    """Raised when Fish Audio credits are exhausted (402/429)."""
    pass

class FishAudioAuthError(FishAudioError):
    """Raised when API key is missing or invalid (401)."""
    pass

class FishAudioClient:
    API_URL = "https://api.fish.audio/v1/tts"

    def __init__(
        self,
        api_key: str,
        model_id: str = "16fb9e5787c94f3ea110207e3d1673b8",
        backend_model: str = "s2.1-pro-free"
    ):
        self.api_key = (api_key or "").strip()
        self.model_id = (model_id or "").strip()
        self.backend_model = (backend_model or "s2.1-pro-free").strip()
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        with self._lock:
            if self._client is None or self._client.is_closed:
                http_timeout = httpx.Timeout(connect=10.0, read=28.0, write=10.0, pool=10.0)
                limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
                self._client = httpx.Client(timeout=http_timeout, limits=limits)
            return self._client

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, text: str, timeout: float = 28.0) -> bytes:
        """
        Synthesize speech using Fish Audio API with persistent HTTP keep-alive pooling.
        Uses the free S2.1 Pro tier by default (works with $0 credit balance).
        Returns WAV bytes on success.
        Raises FishAudioQuotaError, FishAudioAuthError, or FishAudioError on failure.
        """
        if not self.is_configured():
            raise FishAudioAuthError("Fish Audio API key is not configured.")

        payload = {
            "text": text.strip(),
            "format": "wav",
            "temperature": 0.85,
            "top_p": 0.85,
            "normalize": True,
        }
        if self.model_id:
            payload["reference_id"] = self.model_id

        client = self._get_client()

        def make_request(model_name: str):
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "model": model_name,
            }
            return client.post(self.API_URL, json=payload, headers=headers)

        for attempt in range(2):
            try:
                resp = make_request(self.backend_model)

                # If a paid model was specified but balance is $0, retry with s2.1-pro-free
                if resp.status_code == 402 and self.backend_model != "s2.1-pro-free":
                    print("[FishAudio] Paid tier returned 402. Retrying with free tier (s2.1-pro-free)...")
                    resp = make_request("s2.1-pro-free")

                if resp.status_code == 200:
                    return sanitize_wav_header(resp.content)
                elif resp.status_code == 401:
                    raise FishAudioAuthError("Fish Audio 401 Unauthorized: Invalid API key.")
                elif resp.status_code in (402, 429):
                    raise FishAudioQuotaError(f"Fish Audio credits exhausted or rate limited ({resp.status_code}).")
                else:
                    raise FishAudioError(f"Fish Audio API returned status {resp.status_code}: {resp.text[:120]}")
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                with self._lock:
                    if self._client:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                        self._client = None
                if attempt == 0:
                    print(f"[FishAudio] Cloud network delay on attempt 1 ({e}). Retrying once...")
                    time.sleep(0.8)
                    client = self._get_client()
                    continue
                raise FishAudioError(f"Fish Audio network connection error: {e}")
