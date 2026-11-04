"""
Sci-Twi Desktop Companion - Settings & Model Cascade Terminal
A sleek, HD floating dialogue card matching Twilight's exact purple & obsidian glass theming.
Features full multi-provider support (Google, Groq, OpenAI, Claude), live model fetching,
interactive cascade reordering (▲ Up, ▼ Down, ★ Primary, ✕ Remove, ＋ Add), and voice engines.
"""
import os
import sys

# High-DPI awareness MUST be declared before Pygame/SDL to prevent Windows bitmap blur
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import json
import time
import threading
import pygame
import httpx
from config import Config, CONFIG_FILE

try:
    import win32api
    import win32con
    import win32gui
except ImportError:
    win32api = None
    win32con = None
    win32gui = None

# =============================================================================
# THEME COLORS - 1:1 Matched to Twilight Companion Overlay
# =============================================================================
COLORKEY = (1, 1, 1)            # Colorkey for transparent rounded corners
C_BG = (24, 24, 37)             # Deep cosmic dark glass (#181825)
C_BORDER = (168, 85, 247)       # Twilight Sparkle purple (#a855f7)
C_WELL = (17, 17, 27)           # Inset well background (#11111b)
C_WELL_BORDER = (76, 79, 105)   # Inset well border (#4c4f69)
C_STAR = (216, 180, 254)        # Starlight lilac (#d8b4fe)
C_TEXT = (248, 250, 252)        # Crisp white
C_MUTED = (148, 163, 184)       # Secondary slate (#94a3b8)
C_DIM = (108, 112, 134)         # Dim text (#6c7086)
C_CYAN = (56, 189, 248)         # Electric magic blue (#38bdf8)
C_MAGENTA = (244, 114, 182)     # Sci-Twi magenta (#f472b6)
C_SEL_BG = (55, 38, 85)         # Selected cascade item background
C_SUCCESS = (74, 222, 128)      # Confirmation green
C_ERR = (248, 113, 113)         # Alert red

WIN_W = 520
WIN_H = 480

def get_clipboard_text() -> str:
    """Read plain text from clipboard using pygame.scrap with win32clipboard fallback."""
    try:
        txt = pygame.scrap.get_text()
        if txt:
            return txt
    except Exception:
        pass
    try:
        import win32clipboard, win32con
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return ""

def set_clipboard_text(text: str):
    """Write plain text to clipboard using pygame.scrap with win32clipboard fallback."""
    if not text:
        return
    try:
        pygame.scrap.put_text(text)
    except Exception:
        pass
    try:
        import win32clipboard, win32con
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass

def draw_star(surface, cx: int, cy: int, color=(216, 180, 254)):
    """Render the exact six-pointed star glyph matching Twilight's cards."""
    global _star_font
    if "_star_font" not in globals() or _star_font is None:
        try:
            _star_font = pygame.font.SysFont("segoeuisymbol", 17)
        except Exception:
            _star_font = pygame.font.SysFont("segoeui", 17)
    star_surf = _star_font.render("\u2736", True, color)
    rect = star_surf.get_rect(center=(cx, cy))
    surface.blit(star_surf, rect)

class SciTwiSettingsCard:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.key.set_repeat(300, 35)

        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME)
        pygame.display.set_caption("Twilight Settings")

        self.hwnd = pygame.display.get_wm_info()["window"]
        self._setup_win32()

        # HD Anti-aliased Fonts
        self.font_title = pygame.font.SysFont("segoeui", 15, bold=True)
        self.font_tab = pygame.font.SysFont("segoeui", 12, bold=True)
        self.font_body = pygame.font.SysFont("segoeui", 12)
        self.font_bold = pygame.font.SysFont("segoeui", 12, bold=True)
        self.font_code = pygame.font.SysFont("consolas", 12)
        self.font_hint = pygame.font.SysFont("segoeui", 11)

        # Config state
        self.cfg = Config.load()
        self.provider = getattr(self.cfg, "provider", "google").lower()
        if self.provider not in ("google", "groq", "openai", "claude"):
            self.provider = "google"

        # Active Cascades per provider
        self.model_cascades = {
            "google": getattr(self.cfg, "model_cascade_google", None) or [
                "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash-lite",
                "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.6-flash"
            ],
            "groq": getattr(self.cfg, "model_cascade_groq", None) or [
                "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768",
                "llama-3.2-11b-vision-preview"
            ],
            "openai": getattr(self.cfg, "model_cascade_openai", None) or [
                "gpt-4o-mini", "gpt-4o", "o3-mini"
            ],
            "claude": getattr(self.cfg, "model_cascade_claude", None) or [
                "claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"
            ]
        }

        # All available models fetched from the API (full catalog of 28+ models)
        self.all_available_models = {
            "google": list(self.model_cascades["google"]),
            "groq": list(self.model_cascades["groq"]),
            "openai": list(self.model_cascades["openai"]),
            "claude": list(self.model_cascades["claude"])
        }

        self.keys = {
            "google": getattr(self.cfg, "api_key", ""),
            "groq": getattr(self.cfg, "groq_api_key", ""),
            "openai": getattr(self.cfg, "openai_api_key", ""),
            "claude": getattr(self.cfg, "claude_api_key", "")
        }

        # Voice values
        self.tts_engine = getattr(self.cfg, "tts_engine", "fish_audio")
        self.fish_key = getattr(self.cfg, "fish_audio_api_key", "")
        self.fish_model = getattr(self.cfg, "fish_audio_model_id", "16fb9e5787c94f3ea110207e3d1673b8")
        self.eleven_key = getattr(self.cfg, "elevenlabs_api_key", "")
        self.eleven_voice = getattr(self.cfg, "elevenlabs_voice_id", "")
        self.use_rvc = getattr(self.cfg, "use_rvc", True)
        self.rvc_pitch = getattr(self.cfg, "rvc_pitch", 0)
        self.rvc_index = getattr(self.cfg, "rvc_index_rate", 0.65)

        # Tab navigation: 0 = Brain & Models, 1 = Voice & Audio, 2 = Shortcuts
        self.current_tab = 0

        # Cascade selection & scroll
        self.selected_cascade_idx = 0
        self.cascade_scroll = 0

        # Dropdown selection for adding new models
        self.selected_available_idx = 0
        self.show_dropdown = False
        self.dropdown_scroll = 0

        # Input box state
        self.active_input = None
        self.input_cursor_pos = 0
        self.input_selected_all = False
        self.show_keys = False
        self.cursor_timer = 0.0
        self.status_msg = "Ready. Configure providers, cascade order & voice."
        self.status_col = C_MUTED
        self.is_verifying = False

        # Window Dragging state
        self.is_dragging = False
        self.drag_offset = (0, 0)

    def _setup_win32(self):
        """Configure top-most rounded colorkey window on Windows."""
        if not win32gui or not win32con:
            return
        sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        self.win_x = max(20, (sw - WIN_W) // 2)
        self.win_y = max(20, (sh - WIN_H) // 2)

        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            self.win_x,
            self.win_y,
            WIN_W,
            WIN_H,
            win32con.SWP_SHOWWINDOW
        )
        ex_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            self.hwnd,
            win32con.GWL_EXSTYLE,
            ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST
        )
        win32gui.SetLayeredWindowAttributes(
            self.hwnd,
            win32api.RGB(*COLORKEY),
            0,
            win32con.LWA_COLORKEY
        )

    # =========================================================================
    # CASCADE REORDERING & MANAGEMENT
    # =========================================================================
    def move_cascade_up(self):
        cascade = self.model_cascades.get(self.provider, [])
        idx = self.selected_cascade_idx
        if idx > 0 and idx < len(cascade):
            cascade[idx - 1], cascade[idx] = cascade[idx], cascade[idx - 1]
            self.selected_cascade_idx = idx - 1
            self.status_msg = f"Moved '{cascade[idx - 1]}' up to priority #{idx}."
            self.status_col = C_CYAN

    def move_cascade_down(self):
        cascade = self.model_cascades.get(self.provider, [])
        idx = self.selected_cascade_idx
        if idx >= 0 and idx < len(cascade) - 1:
            cascade[idx + 1], cascade[idx] = cascade[idx], cascade[idx + 1]
            self.selected_cascade_idx = idx + 1
            self.status_msg = f"Moved '{cascade[idx + 1]}' down to priority #{idx + 2}."
            self.status_col = C_CYAN

    def set_cascade_primary(self):
        cascade = self.model_cascades.get(self.provider, [])
        idx = self.selected_cascade_idx
        if idx > 0 and idx < len(cascade):
            item = cascade.pop(idx)
            cascade.insert(0, item)
            self.selected_cascade_idx = 0
            self.status_msg = f"Promoted '{item}' to Primary (#1)."
            self.status_col = C_SUCCESS

    def remove_cascade_item(self):
        cascade = self.model_cascades.get(self.provider, [])
        if len(cascade) <= 1:
            self.status_msg = "Cannot remove last remaining model."
            self.status_col = C_ERR
            return
        idx = self.selected_cascade_idx
        if 0 <= idx < len(cascade):
            removed = cascade.pop(idx)
            self.selected_cascade_idx = max(0, min(idx, len(cascade) - 1))
            self.status_msg = f"Removed '{removed}' from cascade."
            self.status_col = C_MUTED

    def add_selected_to_cascade(self):
        avail = self.all_available_models.get(self.provider, [])
        if not avail:
            return
        model = avail[self.selected_available_idx]
        cascade = self.model_cascades.get(self.provider, [])
        if model in cascade:
            self.status_msg = f"'{model}' is already in your cascade."
            self.status_col = C_ERR
            return
        cascade.append(model)
        self.selected_cascade_idx = len(cascade) - 1
        self.status_msg = f"Added '{model}' to cascade (Priority #{len(cascade)})."
        self.status_col = C_SUCCESS

    # =========================================================================
    # LIVE VERIFICATION & FULL CATALOG FETCHING
    # =========================================================================
    def verify_active_provider(self):
        if self.is_verifying:
            return
        p = self.provider
        key = self.keys.get(p, "").strip()
        if not key:
            self.status_msg = f"Enter your {p.capitalize()} API key first."
            self.status_col = C_ERR
            return

        self.is_verifying = True
        self.status_msg = f"Connecting to {p.capitalize()} API..."
        self.status_col = C_CYAN

        def worker():
            try:
                if p == "google":
                    from google import genai
                    client = genai.Client(api_key=key)
                    models = []
                    for m in client.models.list():
                        name = m.name.replace("models/", "")
                        if any(k in name for k in ("flash", "lite", "pro", "gemma")):
                            models.append(name)
                    def _rank(m):
                        if "3.1-flash-lite" in m: return 0
                        if "3-flash-preview" in m: return 1
                        if "3.5-flash-lite" in m: return 2
                        if "flash-lite-latest" in m: return 3
                        if "3.5-flash" in m: return 4
                        if "3.6-flash" in m: return 5
                        return 10
                    models = sorted(models, key=_rank)
                    self.all_available_models["google"] = models
                    self.status_msg = f"Verified Google API! Loaded {len(models)} models."
                    self.status_col = C_SUCCESS

                elif p == "groq":
                    with httpx.Client(timeout=8.0) as client:
                        resp = client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
                        if resp.status_code != 200:
                            raise RuntimeError(f"HTTP {resp.status_code}")
                        data = resp.json().get("data", [])
                        models = [m["id"] for m in data if "whisper" not in m["id"] and "distil" not in m["id"]]
                        def _groq_rank(m):
                            if "llama-3.3-70b" in m: return 0
                            if "llama-3.1-8b" in m: return 1
                            if "mixtral" in m: return 2
                            if "vision" in m: return 3
                            return 10
                        models = sorted(models, key=_groq_rank)
                        self.all_available_models["groq"] = models
                        self.status_msg = f"Verified Groq API! Loaded {len(models)} models."
                        self.status_col = C_SUCCESS

                elif p == "openai":
                    with httpx.Client(timeout=8.0) as client:
                        resp = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
                        if resp.status_code != 200:
                            raise RuntimeError(f"HTTP {resp.status_code}")
                        data = resp.json().get("data", [])
                        targets = ("gpt-4o", "gpt-4", "o3", "o1")
                        models = [m["id"] for m in data if any(m["id"].startswith(pre) for pre in targets)]
                        self.all_available_models["openai"] = sorted(list(set(models)))
                        self.status_msg = f"Verified OpenAI! Loaded {len(models)} models."
                        self.status_col = C_SUCCESS

                elif p == "claude":
                    with httpx.Client(timeout=8.0) as client:
                        resp = client.get("https://api.anthropic.com/v1/models", headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
                        if resp.status_code == 200:
                            models = [m["id"] for m in resp.json().get("data", [])]
                        else:
                            models = ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]
                        self.all_available_models["claude"] = models
                        self.status_msg = f"Verified Claude! Loaded {len(models)} models."
                        self.status_col = C_SUCCESS
            except Exception as e:
                self.status_msg = f"Verification failed: {str(e)[:32]}"
                self.status_col = C_ERR
            finally:
                self.is_verifying = False

        threading.Thread(target=worker, daemon=True).start()

    def test_voice(self):
        self.status_msg = "Synthesizing tongue twister preview..."
        self.status_col = C_CYAN
        def worker():
            try:
                from audio_manager import AudioManager
                mgr = AudioManager(
                    tts_engine=self.tts_engine,
                    fish_audio_api_key=self.fish_key,
                    fish_audio_model_id=self.fish_model,
                    elevenlabs_api_key=self.eleven_key,
                    elevenlabs_voice_id=self.eleven_voice,
                    use_rvc=self.use_rvc,
                    rvc_pitch=self.rvc_pitch,
                    rvc_index_rate=self.rvc_index
                )
                twister = "Can a canner can a can as an uncanny canner can can a can? ...Wait! Which wristwatches are Swiss wristwatches?! Phew, my speech synthesizer is definitely keeping up!"
                mgr.speak(twister)
                self.status_msg = "Tongue twister preview complete!"
                self.status_col = C_SUCCESS
            except Exception as e:
                self.status_msg = f"Voice error: {str(e)[:30]}"
                self.status_col = C_ERR
        threading.Thread(target=worker, daemon=True).start()

    def save_settings(self):
        try:
            cascade = self.model_cascades.get(self.provider, [])
            primary_model = cascade[0] if cascade else "gemini-3.1-flash-lite"

            self.cfg.provider = self.provider
            self.cfg.api_key = self.keys.get("google", "").strip()
            self.cfg.groq_api_key = self.keys.get("groq", "").strip()
            self.cfg.openai_api_key = self.keys.get("openai", "").strip()
            self.cfg.claude_api_key = self.keys.get("claude", "").strip()

            self.cfg.model = primary_model
            self.cfg.model_cascade = cascade
            self.cfg.model_cascade_google = self.model_cascades.get("google", [])
            self.cfg.model_cascade_groq = self.model_cascades.get("groq", [])
            self.cfg.model_cascade_openai = self.model_cascades.get("openai", [])
            self.cfg.model_cascade_claude = self.model_cascades.get("claude", [])

            self.cfg.tts_engine = self.tts_engine
            self.cfg.fish_audio_api_key = self.fish_key.strip()
            self.cfg.fish_audio_model_id = self.fish_model.strip()
            self.cfg.elevenlabs_api_key = self.eleven_key.strip()
            self.cfg.elevenlabs_voice_id = self.eleven_voice.strip()
            self.cfg.use_rvc = self.use_rvc
            self.cfg.rvc_pitch = int(self.rvc_pitch)
            self.cfg.rvc_index_rate = float(self.rvc_index)

            self.cfg.save()
            self.status_msg = f"Settings saved! Primary: {primary_model}"
            self.status_col = C_SUCCESS
        except Exception as e:
            self.status_msg = f"Save failed: {e}"
            self.status_col = C_ERR

    # =========================================================================
    # RENDER ENGINE
    # =========================================================================
    def render(self, dt: float):
        self.cursor_timer = (self.cursor_timer + dt) % 1.0
        self.screen.fill(COLORKEY)

        # 1. Main Rounded Glass Card Shell
        card_rect = pygame.Rect(0, 0, WIN_W, WIN_H)
        pygame.draw.rect(self.screen, C_BG, card_rect, border_radius=12)
        pygame.draw.rect(self.screen, C_BORDER, card_rect, width=2, border_radius=12)

        # 2. Header Bar
        draw_star(self.screen, 24, 20, C_STAR)
        title_surf = self.font_title.render("Twilight", True, C_STAR)
        self.screen.blit(title_surf, (36, 9))

        dismiss_surf = self.font_hint.render("[Esc close]", True, C_MUTED)
        self.rect_close_btn = pygame.Rect(WIN_W - dismiss_surf.get_width() - 16, 12, dismiss_surf.get_width(), 18)
        self.screen.blit(dismiss_surf, (self.rect_close_btn.x, self.rect_close_btn.y))

        # 3. Tab Navigation Pills
        tabs = [("Brain & Models", 0), ("Voice & Audio", 1), ("Shortcuts", 2)]
        self.tab_rects = {}
        tx = 12
        ty = 38
        tw = 158
        th = 28
        for tname, tid in tabs:
            tr = pygame.Rect(tx, ty, tw, th)
            self.tab_rects[tid] = tr
            is_active = (self.current_tab == tid)
            bg = C_BORDER if is_active else C_WELL
            border = C_STAR if is_active else C_WELL_BORDER
            fg = (255, 255, 255) if is_active else C_MUTED
            pygame.draw.rect(self.screen, bg, tr, border_radius=8)
            pygame.draw.rect(self.screen, border, tr, width=1, border_radius=8)
            t_surf = self.font_tab.render(tname, True, fg)
            self.screen.blit(t_surf, (tr.x + (tw - t_surf.get_width()) // 2, tr.y + 5))
            tx += tw + 8

        # 4. Inset Well Container
        well_rect = pygame.Rect(12, 74, WIN_W - 24, 346)
        pygame.draw.rect(self.screen, C_WELL, well_rect, border_radius=8)
        pygame.draw.rect(self.screen, C_WELL_BORDER, well_rect, width=1, border_radius=8)

        if self.current_tab == 0:
            self._render_tab_brain(well_rect)
        elif self.current_tab == 1:
            self._render_tab_voice(well_rect)
        else:
            self._render_tab_system(well_rect)

        # 5. Footer Bar
        self.rect_save_btn = pygame.Rect(WIN_W - 146, WIN_H - 46, 134, 34)
        pygame.draw.rect(self.screen, C_BORDER, self.rect_save_btn, border_radius=8)
        s_lbl = self.font_bold.render("Save & Apply", True, (255, 255, 255))
        self.screen.blit(s_lbl, (self.rect_save_btn.x + (self.rect_save_btn.width - s_lbl.get_width()) // 2, self.rect_save_btn.y + 8))

        st_surf = self.font_hint.render(self.status_msg[:60], True, self.status_col)
        self.screen.blit(st_surf, (16, WIN_H - 36))

        # Render Dropdown on top if open
        if self.current_tab == 0 and self.show_dropdown:
            self._render_dropdown(well_rect)

        pygame.display.update()

    def _get_active_text(self) -> str:
        if self.active_input == "api_key":
            return self.keys.get(self.provider, "")
        elif self.active_input == "fish_key":
            return self.fish_key
        elif self.active_input == "fish_model":
            return self.fish_model
        elif self.active_input == "eleven_key":
            return self.eleven_key
        elif self.active_input == "eleven_voice":
            return self.eleven_voice
        return ""

    def _set_active_text(self, val: str):
        if self.active_input == "api_key":
            self.keys[self.provider] = val
        elif self.active_input == "fish_key":
            self.fish_key = val
        elif self.active_input == "fish_model":
            self.fish_model = val
        elif self.active_input == "eleven_key":
            self.eleven_key = val
        elif self.active_input == "eleven_voice":
            self.eleven_voice = val

    def _render_text_input_content(self, rect: pygame.Rect, text: str, is_active: bool, is_masked: bool = False, font = None, text_color = C_TEXT):
        if font is None:
            font = self.font_code
        inner_rect = pygame.Rect(rect.x + 6, rect.y + 2, rect.width - 12, rect.height - 4)
        self.screen.set_clip(inner_rect)

        disp = ("•" * len(text)) if is_masked else text
        cursor_pos = self.input_cursor_pos if is_active else len(text)
        cursor_pos = max(0, min(len(disp), cursor_pos))

        text_w = font.size(disp)[0]
        cursor_w = font.size(disp[:cursor_pos])[0]

        scroll_x = 0
        if is_active:
            if cursor_w > inner_rect.width - 16:
                scroll_x = cursor_w - (inner_rect.width - 16)
        else:
            if text_w > inner_rect.width - 10:
                scroll_x = text_w - (inner_rect.width - 10)

        draw_x = inner_rect.x - scroll_x
        draw_y = inner_rect.y + 3

        if is_active and self.input_selected_all and disp:
            pygame.draw.rect(self.screen, (88, 48, 120), (draw_x, draw_y - 1, text_w + 2, inner_rect.height - 2), border_radius=3)

        if disp:
            t_surf = font.render(disp, True, text_color)
            self.screen.blit(t_surf, (draw_x, draw_y))

        if is_active and self.cursor_timer < 0.5 and not self.input_selected_all:
            caret_x = draw_x + cursor_w + 1
            pygame.draw.line(self.screen, C_BORDER, (caret_x, rect.y + 4), (caret_x, rect.y + rect.height - 4), 2)

        self.screen.set_clip(None)

    # =========================================================================
    # TAB 0: BRAIN & MODELS (Cascade Reordering & Full 28-Model Picker)
    # =========================================================================
    def _render_tab_brain(self, well: pygame.Rect):
        # Row 1: Provider selection
        lbl1 = self.font_bold.render("Provider:", True, C_TEXT)
        self.screen.blit(lbl1, (well.x + 12, well.y + 12))

        providers = ["google", "groq", "openai", "claude"]
        self.provider_rects = {}
        px = well.x + 84
        for p in providers:
            pr = pygame.Rect(px, well.y + 9, 88, 24)
            self.provider_rects[p] = pr
            is_p = (self.provider == p)
            bg = C_BORDER if is_p else C_BG
            border = C_STAR if is_p else C_WELL_BORDER
            fg = (255, 255, 255) if is_p else C_MUTED
            pygame.draw.rect(self.screen, bg, pr, border_radius=6)
            pygame.draw.rect(self.screen, border, pr, width=1, border_radius=6)
            p_surf = self.font_bold.render(p.capitalize(), True, fg)
            self.screen.blit(p_surf, (pr.x + (pr.width - p_surf.get_width()) // 2, pr.y + 3))
            px += 94

        # Row 2: API Key input & Verify Button
        lbl2 = self.font_bold.render("API Key:", True, C_TEXT)
        self.screen.blit(lbl2, (well.x + 12, well.y + 44))

        self.rect_api_box = pygame.Rect(well.x + 84, well.y + 40, 200, 26)
        pygame.draw.rect(self.screen, (10, 10, 16), self.rect_api_box, border_radius=6)
        border_col = C_BORDER if self.active_input == "api_key" else C_WELL_BORDER
        pygame.draw.rect(self.screen, border_col, self.rect_api_box, width=1, border_radius=6)

        k = self.keys.get(self.provider, "")
        self._render_text_input_content(self.rect_api_box, k, is_active=(self.active_input == "api_key"), is_masked=(not self.show_keys))

        self.rect_show_btn = pygame.Rect(well.x + 288, well.y + 40, 44, 26)
        self.rect_paste_btn = pygame.Rect(well.x + 336, well.y + 40, 48, 26)
        pygame.draw.rect(self.screen, C_BG, self.rect_show_btn, border_radius=6)
        pygame.draw.rect(self.screen, C_BG, self.rect_paste_btn, border_radius=6)
        pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_show_btn, width=1, border_radius=6)
        pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_paste_btn, width=1, border_radius=6)
        sh_txt = self.font_hint.render("Hide" if self.show_keys else "Show", True, C_CYAN)
        pa_txt = self.font_hint.render("Paste", True, C_MUTED)
        self.screen.blit(sh_txt, (self.rect_show_btn.x + 8, self.rect_show_btn.y + 5))
        self.screen.blit(pa_txt, (self.rect_paste_btn.x + 9, self.rect_paste_btn.y + 5))

        # Verify & Fetch Button
        self.rect_verify_btn = pygame.Rect(well.x + 388, well.y + 40, 96, 26)
        v_bg = (38, 38, 58) if not self.is_verifying else (50, 50, 75)
        pygame.draw.rect(self.screen, v_bg, self.rect_verify_btn, border_radius=6)
        pygame.draw.rect(self.screen, C_CYAN, self.rect_verify_btn, width=1, border_radius=6)
        v_txt = "..." if self.is_verifying else "Fetch"
        v_surf = self.font_bold.render(v_txt, True, C_CYAN)
        self.screen.blit(v_surf, (self.rect_verify_btn.x + (self.rect_verify_btn.width - v_surf.get_width()) // 2, self.rect_verify_btn.y + 4))

        # Row 3: Model Cascade Order Header
        lbl_cas = self.font_bold.render("Model Cascade Order (Tries #1 first, then falls back):", True, C_STAR)
        self.screen.blit(lbl_cas, (well.x + 12, well.y + 74))

        # Row 4: Cascade List Box & Order Controls
        cascade = self.model_cascades.get(self.provider, [])
        list_rect = pygame.Rect(well.x + 12, well.y + 96, 380, 160)
        pygame.draw.rect(self.screen, (13, 13, 20), list_rect, border_radius=6)
        pygame.draw.rect(self.screen, C_WELL_BORDER, list_rect, width=1, border_radius=6)

        # Draw visible cascade items
        self.cascade_item_rects = []
        item_h = 26
        max_visible = 6
        start_idx = max(0, min(self.cascade_scroll, max(0, len(cascade) - max_visible)))
        visible_items = cascade[start_idx:start_idx + max_visible]

        for i, model_name in enumerate(visible_items):
            actual_idx = start_idx + i
            iy = list_rect.y + 4 + i * item_h
            ir = pygame.Rect(list_rect.x + 4, iy, list_rect.width - 8, item_h - 2)
            self.cascade_item_rects.append((ir, actual_idx))

            is_sel = (actual_idx == self.selected_cascade_idx)
            if is_sel:
                pygame.draw.rect(self.screen, C_SEL_BG, ir, border_radius=4)
                pygame.draw.rect(self.screen, C_BORDER, ir, width=1, border_radius=4)

            # Badge: #1 Primary vs #2, #3
            if actual_idx == 0:
                num_txt = f"#1 [PRIMARY]"
                num_col = C_CYAN
            else:
                num_txt = f"#{actual_idx + 1}"
                num_col = C_MUTED

            num_surf = self.font_code.render(num_txt, True, num_col)
            name_surf = self.font_code.render(model_name[:28], True, C_TEXT)
            self.screen.blit(num_surf, (ir.x + 8, ir.y + 4))
            self.screen.blit(name_surf, (ir.x + 104, ir.y + 4))

        # Vertical Cascade Controls column (Up, Down, Primary, Remove)
        btn_x = well.x + 398
        bw = 86
        bh = 26

        self.rect_up_btn = pygame.Rect(btn_x, well.y + 96, bw, bh)
        self.rect_down_btn = pygame.Rect(btn_x, well.y + 126, bw, bh)
        self.rect_primary_btn = pygame.Rect(btn_x, well.y + 156, bw, bh)
        self.rect_remove_btn = pygame.Rect(btn_x, well.y + 186, bw, bh)

        for btn_r, b_txt, col in [
            (self.rect_up_btn, "▲ Up", C_TEXT),
            (self.rect_down_btn, "▼ Down", C_TEXT),
            (self.rect_primary_btn, "★ Primary", C_CYAN),
            (self.rect_remove_btn, "✕ Remove", C_ERR)
        ]:
            pygame.draw.rect(self.screen, C_BG, btn_r, border_radius=5)
            pygame.draw.rect(self.screen, C_WELL_BORDER, btn_r, width=1, border_radius=5)
            b_surf = self.font_bold.render(b_txt, True, col)
            self.screen.blit(b_surf, (btn_r.x + (bw - b_surf.get_width()) // 2, btn_r.y + 5))

        # Row 5: Add Model from Full Fetched List
        avail = self.all_available_models.get(self.provider, [])
        lbl_add = self.font_body.render(f"Add Model to Cascade ({len(avail)} fetched):", True, C_MUTED)
        self.screen.blit(lbl_add, (well.x + 12, well.y + 266))

        # Dropdown Box
        self.rect_dropdown_box = pygame.Rect(well.x + 12, well.y + 288, 380, 26)
        pygame.draw.rect(self.screen, (10, 10, 16), self.rect_dropdown_box, border_radius=6)
        pygame.draw.rect(self.screen, C_BORDER if self.show_dropdown else C_WELL_BORDER, self.rect_dropdown_box, width=1, border_radius=6)

        current_choice = avail[self.selected_available_idx] if avail else "None available"
        c_surf = self.font_code.render(current_choice[:36], True, C_CYAN)
        arrow_surf = self.font_bold.render("▼", True, C_MUTED)
        self.screen.blit(c_surf, (self.rect_dropdown_box.x + 8, self.rect_dropdown_box.y + 5))
        self.screen.blit(arrow_surf, (self.rect_dropdown_box.x + self.rect_dropdown_box.width - 20, self.rect_dropdown_box.y + 5))

        # [＋ Add] Button
        self.rect_add_btn = pygame.Rect(well.x + 398, well.y + 288, bw, 26)
        pygame.draw.rect(self.screen, C_BG, self.rect_add_btn, border_radius=5)
        pygame.draw.rect(self.screen, C_STAR, self.rect_add_btn, width=1, border_radius=5)
        add_surf = self.font_bold.render("＋ Add", True, C_STAR)
        self.screen.blit(add_surf, (self.rect_add_btn.x + (bw - add_surf.get_width()) // 2, self.rect_add_btn.y + 5))

    def _render_dropdown(self, well: pygame.Rect):
        """Draw floating popup menu showing all 28+ fetched models with scroll support."""
        avail = self.all_available_models.get(self.provider, [])
        if not avail:
            return

        menu_w = 380
        menu_h = 160
        menu_x = well.x + 12
        menu_y = well.y + 128
        self.rect_menu = pygame.Rect(menu_x, menu_y, menu_w, menu_h)

        pygame.draw.rect(self.screen, (18, 18, 28), self.rect_menu, border_radius=8)
        pygame.draw.rect(self.screen, C_BORDER, self.rect_menu, width=2, border_radius=8)

        item_h = 24
        max_vis = 6
        start = max(0, min(self.dropdown_scroll, max(0, len(avail) - max_vis)))
        visible = avail[start:start + max_vis]

        self.dropdown_item_rects = []
        for i, m_name in enumerate(visible):
            actual_idx = start + i
            iy = menu_y + 6 + i * item_h
            ir = pygame.Rect(menu_x + 4, iy, menu_w - 8, item_h - 2)
            self.dropdown_item_rects.append((ir, actual_idx))

            is_sel = (actual_idx == self.selected_available_idx)
            if is_sel:
                pygame.draw.rect(self.screen, C_SEL_BG, ir, border_radius=4)

            m_surf = self.font_code.render(m_name[:36], True, C_STAR if is_sel else C_TEXT)
            self.screen.blit(m_surf, (ir.x + 8, ir.y + 3))

    # =========================================================================
    # TAB 1: VOICE & AUDIO
    # =========================================================================
    def _render_tab_voice(self, well: pygame.Rect):
        lbl1 = self.font_bold.render("TTS Engine:", True, C_TEXT)
        self.screen.blit(lbl1, (well.x + 12, well.y + 14))

        engines = [("fish_audio", "Fish Audio"), ("elevenlabs", "ElevenLabs"), ("local_rvc", "Local RVC"), ("off", "Mute")]
        self.engine_rects = {}
        ex = well.x + 94
        for eid, ename in engines:
            er = pygame.Rect(ex, well.y + 10, 88, 26)
            self.engine_rects[eid] = er
            is_e = (self.tts_engine == eid)
            bg = C_BORDER if is_e else C_BG
            border = C_STAR if is_e else C_WELL_BORDER
            fg = (255, 255, 255) if is_e else C_MUTED
            pygame.draw.rect(self.screen, bg, er, border_radius=6)
            pygame.draw.rect(self.screen, border, er, width=1, border_radius=6)
            e_surf = self.font_bold.render(ename, True, fg)
            self.screen.blit(e_surf, (er.x + (er.width - e_surf.get_width()) // 2, er.y + 4))
            ex += 96

        if self.tts_engine == "fish_audio":
            lbl_k = self.font_body.render("Fish Audio Key:", True, C_MUTED)
            self.screen.blit(lbl_k, (well.x + 12, well.y + 54))
            self.rect_fish_key = pygame.Rect(well.x + 120, well.y + 50, 260, 26)
            pygame.draw.rect(self.screen, (10, 10, 16), self.rect_fish_key, border_radius=6)
            border_col = C_BORDER if self.active_input == "fish_key" else C_WELL_BORDER
            pygame.draw.rect(self.screen, border_col, self.rect_fish_key, width=1, border_radius=6)
            self._render_text_input_content(self.rect_fish_key, self.fish_key, is_active=(self.active_input == "fish_key"), is_masked=(not self.show_keys))

            self.rect_paste_fish_key = pygame.Rect(well.x + 388, well.y + 50, 48, 26)
            pygame.draw.rect(self.screen, C_BG, self.rect_paste_fish_key, border_radius=6)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_paste_fish_key, width=1, border_radius=6)
            pk_txt = self.font_hint.render("Paste", True, C_MUTED)
            self.screen.blit(pk_txt, (self.rect_paste_fish_key.x + 9, self.rect_paste_fish_key.y + 5))

            lbl_m = self.font_body.render("Model ID:", True, C_MUTED)
            self.screen.blit(lbl_m, (well.x + 12, well.y + 94))
            self.rect_fish_model = pygame.Rect(well.x + 120, well.y + 90, 260, 26)
            pygame.draw.rect(self.screen, (10, 10, 16), self.rect_fish_model, border_radius=6)
            border_m_col = C_BORDER if self.active_input == "fish_model" else C_WELL_BORDER
            pygame.draw.rect(self.screen, border_m_col, self.rect_fish_model, width=1, border_radius=6)
            self._render_text_input_content(self.rect_fish_model, self.fish_model, is_active=(self.active_input == "fish_model"), is_masked=False, text_color=C_CYAN)

            self.rect_paste_fish_model = pygame.Rect(well.x + 388, well.y + 90, 48, 26)
            pygame.draw.rect(self.screen, C_BG, self.rect_paste_fish_model, border_radius=6)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_paste_fish_model, width=1, border_radius=6)
            pm_txt = self.font_hint.render("Paste", True, C_MUTED)
            self.screen.blit(pm_txt, (self.rect_paste_fish_model.x + 9, self.rect_paste_fish_model.y + 5))

        elif self.tts_engine == "elevenlabs":
            lbl_ek = self.font_body.render("ElevenLabs Key:", True, C_MUTED)
            self.screen.blit(lbl_ek, (well.x + 12, well.y + 54))
            self.rect_eleven_key = pygame.Rect(well.x + 120, well.y + 50, 260, 26)
            pygame.draw.rect(self.screen, (10, 10, 16), self.rect_eleven_key, border_radius=6)
            border_col = C_BORDER if self.active_input == "eleven_key" else C_WELL_BORDER
            pygame.draw.rect(self.screen, border_col, self.rect_eleven_key, width=1, border_radius=6)
            self._render_text_input_content(self.rect_eleven_key, self.eleven_key, is_active=(self.active_input == "eleven_key"), is_masked=(not self.show_keys))

            self.rect_paste_eleven_key = pygame.Rect(well.x + 388, well.y + 50, 48, 26)
            pygame.draw.rect(self.screen, C_BG, self.rect_paste_eleven_key, border_radius=6)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_paste_eleven_key, width=1, border_radius=6)
            pk_txt = self.font_hint.render("Paste", True, C_MUTED)
            self.screen.blit(pk_txt, (self.rect_paste_eleven_key.x + 9, self.rect_paste_eleven_key.y + 5))

            lbl_ev = self.font_body.render("Voice ID:", True, C_MUTED)
            self.screen.blit(lbl_ev, (well.x + 12, well.y + 94))
            self.rect_eleven_voice = pygame.Rect(well.x + 120, well.y + 90, 260, 26)
            pygame.draw.rect(self.screen, (10, 10, 16), self.rect_eleven_voice, border_radius=6)
            border_v_col = C_BORDER if self.active_input == "eleven_voice" else C_WELL_BORDER
            pygame.draw.rect(self.screen, border_v_col, self.rect_eleven_voice, width=1, border_radius=6)
            self._render_text_input_content(self.rect_eleven_voice, self.eleven_voice, is_active=(self.active_input == "eleven_voice"), is_masked=False, text_color=C_CYAN)

            self.rect_paste_eleven_voice = pygame.Rect(well.x + 388, well.y + 90, 48, 26)
            pygame.draw.rect(self.screen, C_BG, self.rect_paste_eleven_voice, border_radius=6)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_paste_eleven_voice, width=1, border_radius=6)
            pv_txt = self.font_hint.render("Paste", True, C_MUTED)
            self.screen.blit(pv_txt, (self.rect_paste_eleven_voice.x + 9, self.rect_paste_eleven_voice.y + 5))

        elif self.tts_engine == "local_rvc":
            lbl_p = self.font_body.render(f"RVC Pitch Shift: {self.rvc_pitch:+d} semitones", True, C_TEXT)
            self.screen.blit(lbl_p, (well.x + 12, well.y + 54))
            self.rect_pitch_down = pygame.Rect(well.x + 240, well.y + 50, 36, 26)
            self.rect_pitch_up = pygame.Rect(well.x + 284, well.y + 50, 36, 26)
            pygame.draw.rect(self.screen, C_BG, self.rect_pitch_down, border_radius=5)
            pygame.draw.rect(self.screen, C_BG, self.rect_pitch_up, border_radius=5)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_pitch_down, width=1, border_radius=5)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_pitch_up, width=1, border_radius=5)
            pd_t = self.font_bold.render("-", True, C_TEXT)
            pu_t = self.font_bold.render("+", True, C_TEXT)
            self.screen.blit(pd_t, (self.rect_pitch_down.x + 13, self.rect_pitch_down.y + 3))
            self.screen.blit(pu_t, (self.rect_pitch_up.x + 12, self.rect_pitch_up.y + 3))

            lbl_i = self.font_body.render(f"Timbre Accuracy (Index Rate): {int(self.rvc_index * 100)}%", True, C_TEXT)
            self.screen.blit(lbl_i, (well.x + 12, well.y + 94))
            self.rect_timbre_bar = pygame.Rect(well.x + 12, well.y + 120, 320, 10)
            pygame.draw.rect(self.screen, (10, 10, 16), self.rect_timbre_bar, border_radius=5)
            pygame.draw.rect(self.screen, C_WELL_BORDER, self.rect_timbre_bar, width=1, border_radius=5)
            fill_w = int(self.rect_timbre_bar.width * max(0.0, min(1.0, self.rvc_index)))
            pygame.draw.rect(self.screen, C_BORDER, (self.rect_timbre_bar.x, self.rect_timbre_bar.y, fill_w, 10), border_radius=5)

        else:
            off_msg = self.font_body.render("Voice output is muted. Twilight speaks via response cards.", True, C_MUTED)
            self.screen.blit(off_msg, (well.x + 12, well.y + 60))

        # Test Voice Button
        self.rect_test_btn = pygame.Rect(well.x + 12, well.y + 160, 150, 30)
        pygame.draw.rect(self.screen, C_BG, self.rect_test_btn, border_radius=6)
        pygame.draw.rect(self.screen, C_CYAN, self.rect_test_btn, width=1, border_radius=6)
        t_surf = self.font_bold.render("▶ Test Voice", True, C_CYAN)
        self.screen.blit(t_surf, (self.rect_test_btn.x + (self.rect_test_btn.width - t_surf.get_width()) // 2, self.rect_test_btn.y + 6))

    # =========================================================================
    # TAB 2: SHORTCUTS & SYSTEM
    # =========================================================================
    def _render_tab_system(self, well: pygame.Rect):
        lbl_h = self.font_bold.render("Desktop Companion Shortcuts:", True, C_STAR)
        self.screen.blit(lbl_h, (well.x + 12, well.y + 14))

        shortcuts = [
            ("Ctrl + Shift + Space", "Summon Twilight input card immediately"),
            ("Ctrl + Shift + P", "Toggle perching on active window ledge"),
            ("Ctrl + Shift + Q", "Toggle quiet study / research mode")
        ]
        sy = well.y + 44
        for key_combo, desc in shortcuts:
            k_surf = self.font_bold.render(f"• {key_combo}:", True, C_CYAN)
            d_surf = self.font_body.render(desc, True, C_MUTED)
            self.screen.blit(k_surf, (well.x + 16, sy))
            self.screen.blit(d_surf, (well.x + 174, sy))
            sy += 28

        sy += 14
        lbl_sub = self.font_bold.render("Active Intelligence Subsystems:", True, C_STAR)
        self.screen.blit(lbl_sub, (well.x + 12, sy))
        sy += 26
        s1 = self.font_hint.render("• Research Journal: Persisting facts and preferences to memories.md", True, C_MUTED)
        s2 = self.font_hint.render("• Process Grounding: Live active window & media context enabled", True, C_MUTED)
        self.screen.blit(s1, (well.x + 16, sy))
        self.screen.blit(s2, (well.x + 16, sy + 20))

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================
    def handle_event(self, event) -> bool:
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # If dropdown was open, check click on items
            if self.current_tab == 0 and self.show_dropdown:
                if hasattr(self, "rect_menu") and self.rect_menu.collidepoint(mx, my):
                    for ir, actual_idx in getattr(self, "dropdown_item_rects", []):
                        if ir.collidepoint(mx, my):
                            self.selected_available_idx = actual_idx
                            self.show_dropdown = False
                            return True
                    return True
                else:
                    self.show_dropdown = False

            # Check close button
            if hasattr(self, "rect_close_btn") and self.rect_close_btn.collidepoint(mx, my):
                return False

            # Header & Background Dragging: Move settings window smoothly via OS caption drag
            if my < 38 or (my > WIN_H - 42 and not (hasattr(self, "rect_save_btn") and self.rect_save_btn.collidepoint(mx, my))):
                if win32gui and win32con:
                    try:
                        win32gui.ReleaseCapture()
                        win32gui.SendMessage(self.hwnd, win32con.WM_NCLBUTTONDOWN, win32con.HTCAPTION, 0)
                        r = win32gui.GetWindowRect(self.hwnd)
                        self.win_x, self.win_y = r[0], r[1]
                        return True
                    except Exception:
                        pass
                self.is_dragging = True
                cur_x, cur_y = win32gui.GetCursorPos() if win32gui else (0, 0)
                self.drag_offset = (cur_x - self.win_x, cur_y - self.win_y)
                return True

            # Tab Switching
            for tid, tr in self.tab_rects.items():
                if tr.collidepoint(mx, my):
                    self.current_tab = tid
                    self.show_dropdown = False
                    return True

            if self.rect_save_btn.collidepoint(mx, my):
                self.save_settings()
                return True

            # Tab 0: Brain & Cascade interactions
            if self.current_tab == 0:
                for p, pr in getattr(self, "provider_rects", {}).items():
                    if pr.collidepoint(mx, my):
                        self.provider = p
                        self.selected_cascade_idx = 0
                        self.selected_available_idx = 0
                        self.status_msg = f"Switched to {p.capitalize()}."
                        self.status_col = C_CYAN
                        return True

                if hasattr(self, "rect_verify_btn") and self.rect_verify_btn.collidepoint(mx, my):
                    self.verify_active_provider()
                    return True

                if hasattr(self, "rect_api_box") and self.rect_api_box.collidepoint(mx, my):
                    self.active_input = "api_key"
                    self.input_cursor_pos = len(self._get_active_text())
                    self.input_selected_all = False
                    return True

                if hasattr(self, "rect_show_btn") and self.rect_show_btn.collidepoint(mx, my):
                    self.show_keys = not self.show_keys
                    return True

                if hasattr(self, "rect_paste_btn") and self.rect_paste_btn.collidepoint(mx, my):
                    p_txt = get_clipboard_text().strip()
                    if p_txt:
                        self.keys[self.provider] = p_txt
                        self.active_input = "api_key"
                        self.input_cursor_pos = len(p_txt)
                        self.input_selected_all = False
                        self.status_msg = f"Pasted {self.provider.capitalize()} API key."
                        self.status_col = C_SUCCESS
                    return True

                # Cascade items selection
                for ir, actual_idx in getattr(self, "cascade_item_rects", []):
                    if ir.collidepoint(mx, my):
                        self.selected_cascade_idx = actual_idx
                        return True

                # Cascade Controls (Up, Down, Primary, Remove)
                if hasattr(self, "rect_up_btn") and self.rect_up_btn.collidepoint(mx, my):
                    self.move_cascade_up()
                    return True
                if hasattr(self, "rect_down_btn") and self.rect_down_btn.collidepoint(mx, my):
                    self.move_cascade_down()
                    return True
                if hasattr(self, "rect_primary_btn") and self.rect_primary_btn.collidepoint(mx, my):
                    self.set_cascade_primary()
                    return True
                if hasattr(self, "rect_remove_btn") and self.rect_remove_btn.collidepoint(mx, my):
                    self.remove_cascade_item()
                    return True

                # Add Model Dropdown & Add Button
                if hasattr(self, "rect_dropdown_box") and self.rect_dropdown_box.collidepoint(mx, my):
                    self.show_dropdown = not self.show_dropdown
                    return True
                if hasattr(self, "rect_add_btn") and self.rect_add_btn.collidepoint(mx, my):
                    self.add_selected_to_cascade()
                    return True

            # Tab 1: Voice interactions
            elif self.current_tab == 1:
                for eid, er in getattr(self, "engine_rects", {}).items():
                    if er.collidepoint(mx, my):
                        self.tts_engine = eid
                        self.status_msg = f"Engine: {eid.replace('_', ' ').capitalize()}"
                        self.status_col = C_CYAN
                        return True

                if hasattr(self, "rect_test_btn") and self.rect_test_btn.collidepoint(mx, my):
                    self.test_voice()
                    return True

                if self.tts_engine == "fish_audio":
                    if hasattr(self, "rect_paste_fish_key") and self.rect_paste_fish_key.collidepoint(mx, my):
                        txt = get_clipboard_text().strip()
                        if txt:
                            self.fish_key = txt
                            self.active_input = "fish_key"
                            self.input_cursor_pos = len(txt)
                            self.input_selected_all = False
                            self.status_msg = "Pasted Fish Audio Key."
                            self.status_col = C_SUCCESS
                        return True
                    if hasattr(self, "rect_paste_fish_model") and self.rect_paste_fish_model.collidepoint(mx, my):
                        txt = get_clipboard_text().strip()
                        if txt:
                            self.fish_model = txt
                            self.active_input = "fish_model"
                            self.input_cursor_pos = len(txt)
                            self.input_selected_all = False
                            self.status_msg = "Pasted Model ID."
                            self.status_col = C_SUCCESS
                        return True
                    if hasattr(self, "rect_fish_key") and self.rect_fish_key.collidepoint(mx, my):
                        self.active_input = "fish_key"
                        self.input_cursor_pos = len(self._get_active_text())
                        self.input_selected_all = False
                        return True
                    if hasattr(self, "rect_fish_model") and self.rect_fish_model.collidepoint(mx, my):
                        self.active_input = "fish_model"
                        self.input_cursor_pos = len(self._get_active_text())
                        self.input_selected_all = False
                        return True
                elif self.tts_engine == "elevenlabs":
                    if hasattr(self, "rect_paste_eleven_key") and self.rect_paste_eleven_key.collidepoint(mx, my):
                        txt = get_clipboard_text().strip()
                        if txt:
                            self.eleven_key = txt
                            self.active_input = "eleven_key"
                            self.input_cursor_pos = len(txt)
                            self.input_selected_all = False
                            self.status_msg = "Pasted ElevenLabs Key."
                            self.status_col = C_SUCCESS
                        return True
                    if hasattr(self, "rect_paste_eleven_voice") and self.rect_paste_eleven_voice.collidepoint(mx, my):
                        txt = get_clipboard_text().strip()
                        if txt:
                            self.eleven_voice = txt
                            self.active_input = "eleven_voice"
                            self.input_cursor_pos = len(txt)
                            self.input_selected_all = False
                            self.status_msg = "Pasted Voice ID."
                            self.status_col = C_SUCCESS
                        return True
                    if hasattr(self, "rect_eleven_key") and self.rect_eleven_key.collidepoint(mx, my):
                        self.active_input = "eleven_key"
                        self.input_cursor_pos = len(self._get_active_text())
                        self.input_selected_all = False
                        return True
                    if hasattr(self, "rect_eleven_voice") and self.rect_eleven_voice.collidepoint(mx, my):
                        self.active_input = "eleven_voice"
                        self.input_cursor_pos = len(self._get_active_text())
                        self.input_selected_all = False
                        return True
                elif self.tts_engine == "local_rvc":
                    if hasattr(self, "rect_pitch_down") and self.rect_pitch_down.collidepoint(mx, my):
                        self.rvc_pitch = max(-12, self.rvc_pitch - 1)
                        return True
                    if hasattr(self, "rect_pitch_up") and self.rect_pitch_up.collidepoint(mx, my):
                        self.rvc_pitch = min(12, self.rvc_pitch + 1)
                        return True
                    if hasattr(self, "rect_timbre_bar") and self.rect_timbre_bar.collidepoint(mx, my):
                        frac = (mx - self.rect_timbre_bar.x) / float(self.rect_timbre_bar.width)
                        self.rvc_index = round(max(0.0, min(1.0, frac)), 2)
                        return True

            self.active_input = None
            self.input_selected_all = False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            # Mouse wheel scroll
            if self.current_tab == 0:
                if self.show_dropdown:
                    if event.button == 4:
                        self.dropdown_scroll = max(0, self.dropdown_scroll - 1)
                    else:
                        avail = self.all_available_models.get(self.provider, [])
                        self.dropdown_scroll = min(max(0, len(avail) - 6), self.dropdown_scroll + 1)
                else:
                    if event.button == 4:
                        self.cascade_scroll = max(0, self.cascade_scroll - 1)
                    else:
                        cascade = self.model_cascades.get(self.provider, [])
                        self.cascade_scroll = min(max(0, len(cascade) - 6), self.cascade_scroll + 1)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.is_dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging and win32gui and win32con:
                cur_x, cur_y = win32gui.GetCursorPos()
                self.win_x = cur_x - self.drag_offset[0]
                self.win_y = cur_y - self.drag_offset[1]
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    self.win_x,
                    self.win_y,
                    WIN_W,
                    WIN_H,
                    win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.show_dropdown:
                    self.show_dropdown = False
                    return True
                return False
            elif event.key == pygame.K_RETURN and not self.active_input:
                self.save_settings()
                return True

            if self.active_input:
                text = self._get_active_text()
                self.cursor_timer = 0.0

                if event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL):
                    set_clipboard_text(text)
                    self.status_msg = "Copied to clipboard."
                    self.status_col = C_CYAN
                    return True
                elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                    p_txt = get_clipboard_text().strip()
                    if p_txt:
                        if self.input_selected_all:
                            self._set_active_text(p_txt)
                            self.input_cursor_pos = len(p_txt)
                            self.input_selected_all = False
                        else:
                            new_text = text[:self.input_cursor_pos] + p_txt + text[self.input_cursor_pos:]
                            self._set_active_text(new_text)
                            self.input_cursor_pos += len(p_txt)
                        self.status_msg = "Pasted from clipboard."
                        self.status_col = C_SUCCESS
                    return True
                elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL):
                    self.input_selected_all = True
                    return True
                elif event.key == pygame.K_HOME:
                    self.input_cursor_pos = 0
                    self.input_selected_all = False
                    return True
                elif event.key == pygame.K_END:
                    self.input_cursor_pos = len(text)
                    self.input_selected_all = False
                    return True
                elif event.key == pygame.K_LEFT:
                    self.input_selected_all = False
                    if event.mod & pygame.KMOD_CTRL:
                        pos = self.input_cursor_pos
                        while pos > 0 and text[pos - 1] in ' -_:': pos -= 1
                        while pos > 0 and text[pos - 1] not in ' -_:': pos -= 1
                        self.input_cursor_pos = pos
                    else:
                        self.input_cursor_pos = max(0, self.input_cursor_pos - 1)
                    return True
                elif event.key == pygame.K_RIGHT:
                    self.input_selected_all = False
                    if event.mod & pygame.KMOD_CTRL:
                        pos = self.input_cursor_pos
                        while pos < len(text) and text[pos] not in ' -_:': pos += 1
                        while pos < len(text) and text[pos] in ' -_:': pos += 1
                        self.input_cursor_pos = pos
                    else:
                        self.input_cursor_pos = min(len(text), self.input_cursor_pos + 1)
                    return True
                elif event.key == pygame.K_BACKSPACE:
                    if self.input_selected_all:
                        self._set_active_text("")
                        self.input_cursor_pos = 0
                        self.input_selected_all = False
                    elif self.input_cursor_pos > 0:
                        new_text = text[:self.input_cursor_pos - 1] + text[self.input_cursor_pos:]
                        self._set_active_text(new_text)
                        self.input_cursor_pos -= 1
                    return True
                elif event.key == pygame.K_DELETE:
                    if self.input_selected_all:
                        self._set_active_text("")
                        self.input_cursor_pos = 0
                        self.input_selected_all = False
                    elif self.input_cursor_pos < len(text):
                        new_text = text[:self.input_cursor_pos] + text[self.input_cursor_pos + 1:]
                        self._set_active_text(new_text)
                    return True
                elif event.key == pygame.K_RETURN:
                    self.active_input = None
                    self.input_selected_all = False
                    return True
                else:
                    if event.unicode and ord(event.unicode[0]) >= 32:
                        if self.input_selected_all:
                            self._set_active_text(event.unicode)
                            self.input_cursor_pos = len(event.unicode)
                            self.input_selected_all = False
                        else:
                            new_text = text[:self.input_cursor_pos] + event.unicode + text[self.input_cursor_pos:]
                            self._set_active_text(new_text)
                            self.input_cursor_pos += len(event.unicode)
                    return True

        return True

    def run(self):
        clock = pygame.time.Clock()
        running = True
        try:
            while running:
                dt = clock.tick(60) / 1000.0
                for event in pygame.event.get():
                    if not self.handle_event(event):
                        running = False
                        break
                self.render(dt)
        finally:
            pygame.quit()

if __name__ == "__main__":
    app = SciTwiSettingsCard()
    app.run()
