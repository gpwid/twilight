import glob
import math
import os
import random
import re
import time
import threading
import ctypes
import win32api
import win32con
import win32gui
import pygame

# Enable Per-Monitor High-DPI awareness on Windows to eliminate bilinear blur
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Transparent colorkey (dark charcoal slate keys out 100% cleanly on Windows without pink fringes)
COLORKEY = (10, 10, 16)

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

class CelestialParticle:
    """Crisp geometric starlight sparkle, diamond glint, or floating music note."""
    def __init__(self, cx, cy):
        self.reset(cx, cy)

    def reset(self, cx, cy, state="idle"):
        self.cx = cx
        self.cy = cy
        angle = random.uniform(0, math.tau)
        rx = random.uniform(15, 60)
        ry = random.uniform(6, 22)
        self.x = cx + rx * math.cos(angle)
        self.y = cy + ry * math.sin(angle)
        self.vx = random.uniform(-10, 10)
        self.vy = random.uniform(-22, -42)
        self.size = random.uniform(2.5, 6.0)
        self.max_life = random.uniform(1.2, 2.2)
        self.life = self.max_life
        self.phase = random.uniform(0, math.tau)

        if state == "music":
            self.kind = random.choice(["note", "star", "diamond"])
            self.color = random.choice([
                (56, 189, 248),   # Electric Cyan
                (244, 114, 182),  # Hot Pink
                (255, 255, 255),  # White
                (192, 132, 252)   # Lavender
            ])
        elif state == "thinking":
            self.kind = random.choice(["star", "cross", "diamond"])
            self.color = random.choice([
                (56, 189, 248),   # Electric Cyan
                (14, 165, 233),   # Sky Blue
                (255, 255, 255)
            ])
        elif state == "speaking":
            self.kind = random.choice(["star", "diamond"])
            self.color = random.choice([
                (244, 114, 182),  # Magenta
                (216, 180, 254),  # Violet
                (255, 255, 255)
            ])
        else:  # idle / input
            self.kind = random.choice(["star", "cross", "diamond"])
            self.color = random.choice([
                (192, 132, 252),  # Lavender
                (216, 180, 254),  # Orchid
                (255, 255, 255),  # Starlight White
                (56, 189, 248)    # Cyan spark
            ])

    def update(self, dt, cx, cy, state="idle", speed_mult=1.0):
        self.life -= dt * speed_mult
        self.phase += dt * 3.0
        self.x += (self.vx + math.sin(self.phase) * 8.0) * dt
        self.y += self.vy * dt * speed_mult
        if self.life <= 0:
            self.reset(cx, cy, state=state)

    def draw(self, surface):
        if self.life <= 0:
            return
        ix, iy = int(self.x), int(self.y)
        s = max(1, int(self.size * (self.life / self.max_life)))

        if self.kind == "star" and s >= 2:
            pts = [
                (ix, iy - s), (ix + max(1, s // 3), iy),
                (ix + s, iy), (ix + max(1, s // 3), iy + max(1, s // 3)),
                (ix, iy + s), (ix - max(1, s // 3), iy + max(1, s // 3)),
                (ix - s, iy), (ix - max(1, s // 3), iy)
            ]
            pygame.draw.polygon(surface, self.color, pts)
            surface.set_at((ix, iy), (255, 255, 255))
        elif self.kind == "cross" and s >= 2:
            pygame.draw.line(surface, self.color, (ix - s, iy), (ix + s, iy), 1)
            pygame.draw.line(surface, self.color, (ix, iy - s), (ix, iy + s), 1)
            surface.set_at((ix, iy), (255, 255, 255))
        elif self.kind == "note" and s >= 2:
            pygame.draw.circle(surface, self.color, (ix, iy), max(2, s // 2))
            pygame.draw.line(surface, self.color, (ix + max(1, s // 2), iy), (ix + max(1, s // 2), iy - s - 2), 1)
            pygame.draw.line(surface, self.color, (ix + max(1, s // 2), iy - s - 2), (ix + max(1, s // 2) + 2, iy - s - 1), 1)
        else:  # diamond
            pts = [(ix, iy - s), (ix + s, iy), (ix, iy + s), (ix - s, iy)]
            pygame.draw.polygon(surface, self.color, pts)

_star_font = None

def draw_six_pointed_star(surface, cx: int, cy: int, color=(216, 180, 254), size: float = 6.5):
    """Render the exact Unicode ✶ (U+2736) six-pointed black star glyph."""
    global _star_font
    if _star_font is None:
        try:
            _star_font = pygame.font.SysFont("segoeuisymbol", 17)
        except Exception:
            try:
                _star_font = pygame.font.SysFont("segoeui", 17)
            except Exception:
                _star_font = pygame.font.Font(None, 17)
    
    star_surf = _star_font.render("\u2736", True, color)
    rect = star_surf.get_rect(center=(cx, cy))
    surface.blit(star_surf, rect)

class SciTwiOverlay:
    def __init__(self, config, on_submit_callback):
        self.config = config
        self.on_submit = on_submit_callback

        # Canvas padding to ensure floating effects, halos, and cards never clip
        self.pad_top = 80
        self.pad_bottom = 45
        self.pad_left = 75
        self.pad_right = 75

        # Window dimensions - spacious canvas for companion sprite, halo, effects, and snug cards
        self.win_w = 780
        self.win_h = 560

        # Companion sprite dimensions & positioning
        self.sprite_w = 160
        self.sprite_h = 160
        self.halo_radius = 56

        # Calculate position on screen
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

        # Loaded positions are Twilight's screen coordinates
        if config.initial_x > 0 and config.initial_y > 0:
            twilight_screen_x = max(self.pad_left + 10, min(screen_w - self.sprite_w - self.pad_right - 10, config.initial_x))
            twilight_screen_y = max(self.pad_top + 12, min(screen_h - self.sprite_h - self.pad_bottom - 45, config.initial_y))
        else:
            twilight_screen_x = screen_w - self.sprite_w - self.pad_right - 20
            twilight_screen_y = screen_h - self.sprite_h - self.pad_bottom - 55

        self.side_h = "left" if (twilight_screen_x < screen_w // 2) else "right"
        self.side_v = "top" if (twilight_screen_y < screen_h // 2) else "bottom"

        self.sprite_x = self.pad_left if self.side_h == "left" else (self.win_w - self.sprite_w - self.pad_right)
        self.sprite_y = self.pad_top if self.side_v == "top" else (self.win_h - self.sprite_h - self.pad_bottom)
        self.win_x = twilight_screen_x - self.sprite_x
        self.win_y = twilight_screen_y - self.sprite_y

        self.pedestal_cx = self.sprite_x + self.sprite_w // 2
        self.pedestal_cy = self.sprite_y + self.sprite_h - 14

        # Initialize pygame & fonts
        pygame.init()
        pygame.font.init()
        pygame.key.set_repeat(300, 30)

        # Fonts
        self.font_title = pygame.font.SysFont("segoeui", 14, bold=True)
        self.font_input = pygame.font.SysFont("segoeui", 15)
        self.font_body = pygame.font.SysFont("segoeui", 13)
        self.font_code = pygame.font.SysFont("consolas", 12)
        self.font_hint = pygame.font.SysFont("segoeui", 11)

        # Pygame surface setup with initial colorkey fill to prevent black square flash
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.NOFRAME)
        self.screen.fill(COLORKEY)
        pygame.display.flip()
        pygame.display.set_caption("Twilight Desktop Companion")

        # Win32 transparent layered window hooks
        self.hwnd = pygame.display.get_wm_info()["window"]
        self._setup_win32_window()

        # State management
        self.state = "idle"  # "idle", "input", "thinking", "speaking", "music"
        self.current_emotion = "idle"
        self.status_message = "Ready"
        self.anim_time = 0.0
        self.state_change_time = time.time()
        self.current_bob_y = 0.0

        # Load expression sprites
        self.expressions = {}
        self._load_expressions()

        # Load anime iconography effect stickers
        self.effects = {}
        self._load_effects()

        # Capri features: Perching & Quiet Study Mode (Manual positioning by default; toggle with Ctrl+Shift+P)
        self.perch_enabled = getattr(config, "perch_enabled", False)
        self.is_perched = False
        self.study_mode = False
        self.study_dwell_seconds = 0.0
        self.study_session_start = 0.0
        self.non_study_dwell_seconds = 0.0
        self.last_user_activity = time.time()

        # Celestial Starlight Particles
        self.particles = [CelestialParticle(self.pedestal_cx, self.pedestal_cy) for _ in range(24)]

        # Text input state
        self.show_input = False
        self.input_text = ""
        self.cursor_pos = 0
        self.selection_active = False
        self.input_scroll_x = 0
        self.cursor_visible = True
        self.last_cursor_toggle = time.time()
        self.last_input_activity = time.time()

        # In-UI Response Display (Speech Bubble)
        self.show_response = False
        self.is_processing = False
        self.response_text = ""
        self.response_lines = []
        self.response_query = ""
        self.response_start_time = 0.0
        self.speech_scroll_y = 0

        # Voice Command / Speech-to-Text State
        self.voice_state = "idle"  # "idle", "listening", "recording", "processing"
        self.voice_details = ""
        self.voice_audio_level = 0.0
        self.voice_input_mgr = None
        self._mic_btn_rect = None
        self._ui_lock = threading.Lock()

        # Dragging & physics tilt state
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.initial_press_x = 0
        self.initial_press_y = 0
        self.prev_drag_x = 0
        self.drag_tilt = 0.0
        self.mouse_down_time = 0

        # Render clean initial frame before revealing window to completely eliminate the black startup box
        self.update_and_render(0.016)
        if win32gui and win32con:
            try:
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    self.win_x,
                    self.win_y,
                    self.win_w,
                    self.win_h,
                    win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED
                )
                self._ensure_transparency(force=True)
            except Exception:
                pass

    def _setup_win32_window(self):
        """Set window as transparent layered top-most window (hidden until assets are ready)."""
        if not win32gui or not win32con:
            return
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
        win32gui.SetWindowPos(
            self.hwnd,
            win32con.HWND_TOPMOST,
            self.win_x,
            self.win_y,
            self.win_w,
            self.win_h,
            win32con.SWP_NOACTIVATE | win32con.SWP_HIDEWINDOW | win32con.SWP_FRAMECHANGED
        )

    def _ensure_transparency(self, force: bool = False):
        """Continuously re-assert Win32 layered colorkey attributes to prevent black box glitch."""
        if not win32gui or not win32con:
            return
        try:
            ex_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
            if force or not (ex_style & win32con.WS_EX_LAYERED):
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
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED
                )
        except Exception:
            pass

    def _load_expressions(self):
        """Load and cache smoothly scaled expression sprites."""
        dirs_to_try = [
            os.path.join(os.path.dirname(__file__), getattr(self.config, "expressions_dir", "assets/expressions")),
            os.path.abspath(getattr(self.config, "expressions_dir", "assets/expressions")),
            r"assets\expressions",
            r"C:\Users\azisk\Downloads\expressions"
        ]

        found_dir = None
        for d in dirs_to_try:
            if os.path.isdir(d):
                found_dir = d
                break

        if not found_dir:
            print("[Overlay] Warning: No expressions directory found.")
            return

        print(f"[Overlay] Loading expression sprites from: {found_dir}")
        for p in glob.glob(os.path.join(found_dir, "*.png")):
            emo = os.path.splitext(os.path.basename(p))[0]
            try:
                img = pygame.image.load(p).convert_alpha()
                scaled = pygame.transform.smoothscale(img, (self.sprite_w, self.sprite_h))
                
                alpha = pygame.surfarray.pixels_alpha(scaled)
                alpha[alpha < 85] = 0
                alpha[alpha >= 85] = 255
                del alpha

                self.expressions[emo] = scaled
            except Exception as e:
                print(f"[Overlay] Error loading {emo}.png: {e}")

        # Setup standard aliases
        if "sleep" in self.expressions and "sleepy" not in self.expressions:
            self.expressions["sleepy"] = self.expressions["sleep"]
        if "dragged" in self.expressions and "when_dragged" not in self.expressions:
            self.expressions["when_dragged"] = self.expressions["dragged"]
        if "analyzing" in self.expressions:
            self.expressions["analyzing_or_angry"] = self.expressions["analyzing"]
            self.expressions["angry"] = self.expressions["analyzing"]

        print(f"[Overlay] Successfully loaded {len(self.expressions)} expression sprites: {list(self.expressions.keys())}")

    def _load_effects(self):
        """Load and cache smoothly cropped & scaled anime iconography effect stickers."""
        eff_dir = os.path.join(os.path.dirname(__file__), "assets", "effects")
        if not os.path.isdir(eff_dir):
            eff_dir = r"assets\effects"
        if not os.path.isdir(eff_dir):
            return

        target_sizes = {
            "thinking_effect1": 38,
            "interrupted_mark_effect": 44,
            "music_note1": 34,
            "music_note2": 40,
            "sleep_z_one_letter": 38,
            "tired_breath_effect": 44,
            "flustered_squiqly_shaking_effect": 36,
            "flustered_effect": 28,
            "happy_or_talking_effects1": 42,
            "happy_or_talking_effects2": 38,
            "talking_effect1": 36,
            "dragged_effects1": 44,
            "dragged_effects2": 44,
        }

        for p in glob.glob(os.path.join(eff_dir, "*.png")):
            k = os.path.splitext(os.path.basename(p))[0]
            try:
                surf = pygame.image.load(p).convert_alpha()
                w, h = surf.get_size()
                if w > 0 and h > 0:
                    max_dim = float(target_sizes.get(k, 45))
                    scale = min(max_dim / w, max_dim / h)
                    sw = max(1, int(w * scale))
                    sh = max(1, int(h * scale))
                    scaled = pygame.transform.smoothscale(surf, (sw, sh))
                    self.effects[k] = scaled
            except Exception as e:
                print(f"[Overlay] Error loading effect {k}: {e}")
        print(f"[Overlay] Successfully loaded {len(self.effects)} anime iconography effects: {list(self.effects.keys())}")

    def toggle_perch(self):
        """Toggle active window perching on/off."""
        self.perch_enabled = not self.perch_enabled
        state_str = "enabled" if self.perch_enabled else "disabled"
        print(f"[Overlay] Window perching {state_str}.")
        self.status_message = f"Perch {state_str}"

    def toggle_study_mode(self):
        """Toggle quiet study mode on/off."""
        self.study_mode = not getattr(self, "study_mode", False)
        if self.study_mode:
            self.current_emotion = "reading"
            self.status_message = "Studying"
            print("[Overlay] Quiet Study Mode ON.")
        else:
            self.current_emotion = "idle"
            self.status_message = "Ready"
            print("[Overlay] Quiet Study Mode OFF.")

    def _check_window_perch(self, dt: float):
        """Active Window Perching: magnetically seat companion on top-right bar of active app."""
        if not self.perch_enabled or self.is_dragging:
            self.is_perched = False
            return

        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd or not win32gui.IsWindow(fg_hwnd) or not win32gui.IsWindowVisible(fg_hwnd):
                return
            if fg_hwnd == self.hwnd:
                return

            title = win32gui.GetWindowText(fg_hwnd)
            class_name = win32gui.GetClassName(fg_hwnd)
            if not title or class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
                return

            rect = win32gui.GetWindowRect(fg_hwnd)
            l, t, r, b = rect
            win_w = r - l
            win_h = b - t
            if win_w < 320 or win_h < 240:
                return

            screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

            is_maximized = (l <= 0 and t <= 0 and r >= screen_w - 10)

            if is_maximized:
                # On maximized apps (Chrome, Spotify), perch in top-right gutter below tabs
                target_twilight_x = screen_w - self.sprite_w - self.pad_right - 14
                target_twilight_y = max(self.pad_top + 12, 56)
            else:
                target_twilight_x = max(self.pad_left + 10, min(screen_w - self.sprite_w - self.pad_right - 10, r - self.sprite_w + 14))
                target_twilight_y = max(self.pad_top + 12, min(screen_h - self.sprite_h - self.pad_bottom - 45, t - 14))

            new_side_h = "left" if target_twilight_x < screen_w // 2 else "right"
            new_side_v = "top" if target_twilight_y < screen_h // 2 else "bottom"
            if new_side_h != self.side_h or new_side_v != self.side_v:
                self.side_h = new_side_h
                self.side_v = new_side_v
                self.sprite_x = self.pad_left if self.side_h == "left" else (self.win_w - self.sprite_w - self.pad_right)
                self.sprite_y = self.pad_top if self.side_v == "top" else (self.win_h - self.sprite_h - self.pad_bottom)
                self.pedestal_cx = self.sprite_x + self.sprite_w // 2
                self.pedestal_cy = self.sprite_y + self.sprite_h - 14
                for p in self.particles:
                    p.reset(self.pedestal_cx, self.pedestal_cy, state=self.state)

            target_win_x = target_twilight_x - self.sprite_x
            target_win_y = target_twilight_y - self.sprite_y

            dist = math.hypot(target_win_x - self.win_x, target_win_y - self.win_y)
            if dist > 4.0:
                lerp = min(1.0, dt * 5.0)
                self.win_x += int((target_win_x - self.win_x) * lerp)
                self.win_y += int((target_win_y - self.win_y) * lerp)
                try:
                    win32gui.SetWindowPos(
                        self.hwnd,
                        win32con.HWND_TOPMOST,
                        self.win_x,
                        self.win_y,
                        self.win_w,
                        self.win_h,
                        win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE
                    )
                except Exception:
                    pass
            self.is_perched = True
        except Exception:
            pass

    def _detect_media_playback_kind(self) -> str:
        """Return 'music' if music is playing, 'video' if a non-music video/stream is playing, or '' if silent."""
        if getattr(self, "is_tts_speaking_fn", None) and self.is_tts_speaking_fn():
            return "music" if self.state == "music" else ""

        media_kind_candidate = ""
        if win32gui:
            def _enum_media(hwnd, _):
                nonlocal media_kind_candidate
                try:
                    if not win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
                        return True
                    cls = win32gui.GetClassName(hwnd)
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if not title:
                        return True
                    t_low = title.lower()
                    if cls == "Chrome_WidgetWin_1":
                        # 1. Active Spotify Desktop track: candidate only if " - " in title and not another app
                        if " - " in title and not t_low.startswith("spotify") and not any(
                            b in t_low for b in ("google chrome", "microsoft edge", "brave", "visual studio", "discord", "youtube")
                        ):
                            media_kind_candidate = "music"
                        # 2. Dedicated music web players
                        elif any(k in t_low for k in ("youtube music", "soundcloud", "spotify", "apple music", "bandcamp")):
                            media_kind_candidate = "music"
                        # 3. YouTube / Twitch / Netflix / VLC: check if title looks like a song or a normal video
                        elif any(k in t_low for k in ("youtube", "twitch", "netflix", "vlc", "stremio")):
                            music_title_hints = (
                                "official video", "official music video", "official audio", "lyric", "lyrics",
                                "audio)", "(audio", "mv)", "[mv]", "feat.", "ft.", "remix", "cover",
                                "soundtrack", "ost", "lofi", "lo-fi", "playlist", "full album", "tiny desk"
                            )
                            if any(mh in t_low for mh in music_title_hints):
                                media_kind_candidate = "music"
                            elif not media_kind_candidate:
                                media_kind_candidate = "video"
                except Exception:
                    pass
                return True
            try:
                win32gui.EnumWindows(_enum_media, None)
            except Exception:
                pass

        # Check Windows Core Audio Peak Meter to verify audio is actually playing (not paused or stopped)
        if media_kind_candidate in ("music", "video"):
            try:
                if not hasattr(self, "_audio_meter"):
                    import comtypes.client
                    from comtypes import GUID, IUnknown, COMMETHOD, HRESULT, CLSCTX_ALL
                    from ctypes import c_float, POINTER, c_int, c_uint, byref

                    class IAudioMeterInformation(IUnknown):
                        _iid_ = GUID('{C02216F6-8C67-4B5B-9D00-D008E73E0064}')
                        _methods_ = [
                            COMMETHOD([], HRESULT, 'GetPeakValue', (['out'], POINTER(c_float), 'pfPeak')),
                        ]

                    class IMMDevice(IUnknown):
                        _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
                        _methods_ = [
                            COMMETHOD([], HRESULT, 'Activate',
                                      (['in'], POINTER(GUID), 'iid'),
                                      (['in'], c_uint, 'dwClsCtx'),
                                      (['in'], POINTER(c_int), 'pActivationParams'),
                                      (['out'], POINTER(POINTER(IUnknown)), 'ppInterface')),
                        ]

                    class IMMDeviceEnumerator(IUnknown):
                        _iid_ = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
                        _methods_ = [
                            COMMETHOD([], HRESULT, 'EnumAudioEndpoints'),
                            COMMETHOD([], HRESULT, 'GetDefaultAudioEndpoint',
                                      (['in'], c_int, 'dataFlow'),
                                      (['in'], c_int, 'role'),
                                      (['out'], POINTER(POINTER(IMMDevice)), 'ppEndpoint')),
                        ]

                    CLSID_MMDeviceEnumerator = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
                    enumerator = comtypes.client.CreateObject(CLSID_MMDeviceEnumerator, interface=IMMDeviceEnumerator)
                    endpoint = enumerator.GetDefaultAudioEndpoint(0, 1)
                    iface = endpoint.Activate(byref(IAudioMeterInformation._iid_), CLSCTX_ALL, None)
                    self._audio_meter = iface.QueryInterface(IAudioMeterInformation)

                if self._audio_meter:
                    peak = float(self._audio_meter.GetPeakValue())
                    if peak > 0.003:
                        self._last_audio_peak_time = time.time()
                        return media_kind_candidate
                    if time.time() - getattr(self, "_last_audio_peak_time", 0.0) < 1.0:
                        return media_kind_candidate
                    # Audio peak is too low: paused, stopped, or silent
                    return ""
            except Exception:
                self._audio_meter = None

        return ""

    def _get_ambient_context(self) -> tuple[str, str, str]:
        """Determine (state, emotion, status_msg) dynamically from live music, video, active window, and user AFK time."""
        media_kind = self._detect_media_playback_kind()
        if media_kind == "music":
            return "music", "music", "Playing music"
        elif media_kind == "video":
            return "idle", "analyzing", "Watching with you"

        # Check user AFK time via Win32 GetLastInputInfo
        try:
            idle_ms = (win32api.GetTickCount() - win32api.GetLastInputInfo()) & 0xFFFFFFFF
            idle_secs = idle_ms / 1000.0
            if idle_secs >= 480.0:
                return "idle", "sleep", "Sleeping..."
            elif idle_secs >= 240.0:
                return "idle", "tired", "Getting sleepy..."
        except Exception:
            pass

        # Inspect active foreground window to match what the user is doing
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if fg_hwnd and fg_hwnd != self.hwnd and win32gui.IsWindowVisible(fg_hwnd):
                title_lower = (win32gui.GetWindowText(fg_hwnd) or "").lower()
                study_keywords = (
                    "arxiv", "scholar", "overleaf", "colab", "jupyter", "docs.", ".pdf",
                    "leetcode", "canvas", "blackboard", "moodle", "coursera", "edx",
                    "wikipedia", "visual studio", "code -", "cursor -", "pycharm", "sublime", "notepad", "obsidian"
                )
                creative_or_tech_keywords = (
                    "photoshop", "affinity", "figma", "gimp", "blender", "illustrator",
                    "premiere", "davinci", "after effects", "aseprite", "task manager", "powershell", "terminal"
                )
                if any(k in title_lower for k in study_keywords) or getattr(self, "study_mode", False):
                    return "idle", "reading", "Studying"
                if any(k in title_lower for k in creative_or_tech_keywords):
                    return "idle", "analyzing", "Co-piloting"
        except Exception:
            pass

        return "idle", "idle", "Listening"

    def restore_ambient_state(self):
        """Transition smoothly to whatever ambient state matches the user's live desktop & audio."""
        st, emo, msg = self._get_ambient_context()
        self.set_state(st, status_msg=msg, emotion=emo)

    def set_voice_input_manager(self, mgr):
        """Bind the VoiceInputManager instance for voice recognition controls."""
        self.voice_input_mgr = mgr

    def toggle_voice_input(self):
        """Toggle voice capture on or off."""
        if self.voice_input_mgr:
            self.voice_input_mgr.toggle_listening()

    def _update_dynamic_study_state(self, dt: float):
        """Poll live music, video, active app, and AFK state every 1.0s when not actively in input/thinking/speaking."""
        now = time.time()
        if now - getattr(self, "_last_ambient_poll", 0.0) < 1.0:
            return
        self._last_ambient_poll = now

        if self.show_input or self.state == "thinking" or self.show_response:
            return
        if getattr(self, "is_tts_speaking_fn", None) and self.is_tts_speaking_fn():
            return

        st, emo, msg = self._get_ambient_context()
        self.study_mode = (emo == "reading")
        if st != self.state or emo != self.current_emotion:
            self.set_state(st, status_msg=msg, emotion=emo)

    def set_state(self, state: str, status_msg: str = "", emotion: str = "", query: str = ""):
        """Update companion state, status message, and facial expression."""
        if query:
            self.response_query = query
        if state == "thinking":
            if not getattr(self, "is_trailer", False):
                self.show_response = False
                self.speech_scroll_y = 0

        if state != getattr(self, "state", "") or (emotion and emotion != getattr(self, "current_emotion", "")):
            self.state_change_time = time.time()

        self.state = state
        if status_msg:
            self.status_message = status_msg
        elif state == "idle":
            self.status_message = "Listening"
        elif state == "thinking":
            self.status_message = "Thinking..."
        elif state == "speaking":
            self.status_message = "Twilight speaking..."
        elif state == "music":
            self.status_message = "Playing music"

        if emotion and emotion in self.expressions:
            self.current_emotion = emotion
        elif state == "thinking":
            self.current_emotion = "thinking"
        elif state == "speaking":
            self.current_emotion = "talking"
        elif state == "music":
            self.current_emotion = "music"
        else:
            self.current_emotion = "idle"

    def show_response_card(self, text: str, user_query: str = "", emotion: str = "", is_trailer: bool = False):
        """Display an on-screen speech bubble card showing Twilight's full response or status trailer."""
        self.is_trailer = is_trailer
        if not is_trailer:
            self.is_processing = False

        m = re.search(r'\[(?:emotion|mood):\s*(\w+)\]', text, re.IGNORECASE)
        if m:
            tag_emo = m.group(1).lower()
            text = re.sub(r'\[(?:emotion|mood):\s*\w+\]\s*', '', text, flags=re.IGNORECASE).strip()
            if not emotion and tag_emo in self.expressions:
                if tag_emo == "music" and any(pw in text.lower() for pw in ("paused", "stopped", "pause", "stop", "quiet")):
                    tag_emo = "happy"
                emotion = tag_emo

        sub_map = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉', '+': '⁺', '-': '⁻'}
        def _clean_latex(m):
            s = m.group(1)
            return re.sub(r'_([0-9\+\-])', lambda sub: sub_map.get(sub.group(1), sub.group(1)), s)
        text = re.sub(r'\$([^\$]+)\$', _clean_latex, text).replace('$', '')

        self.response_text = text
        if user_query:
            self.response_query = user_query
        self.response_start_time = time.time()
        self.show_response = True
        self.show_input = False
        self.speech_scroll_y = 0
        
        self.response_lines = self._wrap_text(self.font_body, text, max_width=360)

        if not emotion:
            lower = text.lower()
            if any(w in lower for w in ("blush", "sunset", "sciset", "tease", "stupid boys", "crush", "flustered")):
                emotion = "flustered"
            elif any(w in lower for w in ("closed", "closing", "terminated", "killed", "process", "code", "physics", "calculate")):
                emotion = "analyzing"
            elif re.search(r'\b(?:playing|shuffling|started)\s+(?:playlist|track|song|album|spotify)\b', lower) and not any(w in lower for w in ("paused", "stopped")):
                emotion = "music"
            elif any(w in lower for w in ("error", "sorry", "whoops", "failed", "couldn't")):
                emotion = "sad"

        self.set_state("speaking", status_msg="Twilight speaking...", emotion=emotion)

    def dismiss_response(self):
        """Dismiss the on-screen speech bubble and transition to live ambient state (music, reading, analyzing, or idle)."""
        if getattr(self, "is_processing", False) and not getattr(self, "is_trailer", False):
            return
        self.is_trailer = False
        self.show_response = False
        self.restore_ambient_state()

    def summon(self):
        """Summon companion window to top and open input box immediately."""
        self.show_input = True
        self.cursor_pos = len(self.input_text)
        self.selection_active = False
        self.show_response = False
        self.state = "input"
        self.status_message = "Ready"
        self.last_input_activity = time.time()
        self._ensure_transparency()
        try:
            if win32gui and win32con:
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    self.win_x,
                    self.win_y,
                    self.win_w,
                    self.win_h,
                    win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW
                )
                win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass

    def _wrap_text(self, font, text: str, max_width: int) -> list[str]:
        """Wrap multiline or long text to fit inside max_width."""
        lines = []
        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split(" ")
            current_line = []
            for word in words:
                test_line = " ".join(current_line + [word])
                w, _ = font.size(test_line)
                if w <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)
                        current_line = []
            if current_line:
                lines.append(" ".join(current_line))
        return lines

    def _check_companion_click(self, mx, my) -> bool:
        """Check if mouse coordinate (mx, my) is within companion sprite hitbox or pedestal."""
        cur_bob = getattr(self, "current_bob_y", 0.0)
        top_y = self.sprite_y + cur_bob - 22
        bottom_y = self.sprite_y + self.sprite_h + cur_bob + 24
        left_x = self.sprite_x - 20
        right_x = self.sprite_x + self.sprite_w + 20
        if left_x <= mx <= right_x and top_y <= my <= bottom_y:
            return True
        base_cx = self.sprite_x + self.sprite_w // 2
        base_cy = self.sprite_y + self.sprite_h - 14 + cur_bob
        dx = (mx - base_cx) / 84.0
        dy = (my - base_cy) / 32.0
        return (dx * dx + dy * dy) <= 1.35

    def _calculate_card_rect(self, card_w: int, card_h: int) -> pygame.Rect:
        """Calculate snug, unclipped card rectangle positioned beside Twilight with hair cushion."""
        gap = 18  # Comfortable cushion so card never touches or underlaps companion hair
        
        # Horizontal placement:
        # If Twilight is on the right side of the screen, place card to her left
        # If Twilight is on the left side of the screen, place card to her right
        if self.side_h == "left":
            cx = self.sprite_x + self.sprite_w + gap
        else:
            cx = self.sprite_x - card_w - gap

        # Vertical placement:
        # Align card comfortably with Twilight's face/chin level (sprite_y + 16)
        # If Twilight is near bottom of canvas, align card bottom with her feet
        if self.side_v == "bottom":
            cy = self.sprite_y + self.sprite_h - card_h - 8
        else:
            cy = self.sprite_y + 16

        # Absolute safety clamp: ensure card is 100% inside window canvas bounds
        cx = max(10, min(self.win_w - card_w - 10, cx))
        cy = max(10, min(self.win_h - card_h - 10, cy))
        
        return pygame.Rect(cx, cy, card_w, card_h)

    def _finish_drag(self):
        """Finalize drag drop: user manually positioned Twilight. Keeps her in place."""
        self.perch_enabled = False  # User manual drag takes priority over auto-perch
        self.is_perched = False
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

        twilight_screen_x = self.win_x + self.sprite_x
        twilight_screen_y = self.win_y + self.sprite_y

        twilight_screen_x = max(self.pad_left + 10, min(screen_w - self.sprite_w - self.pad_right - 10, twilight_screen_x))
        twilight_screen_y = max(self.pad_top + 12, min(screen_h - self.sprite_h - self.pad_bottom - 45, twilight_screen_y))

        self.side_h = "left" if (twilight_screen_x < screen_w // 2) else "right"
        self.side_v = "top" if (twilight_screen_y < screen_h // 2) else "bottom"

        new_sprite_x = self.pad_left if self.side_h == "left" else (self.win_w - self.sprite_w - self.pad_right)
        new_sprite_y = self.pad_top if self.side_v == "top" else (self.win_h - self.sprite_h - self.pad_bottom)

        self.win_x = twilight_screen_x - new_sprite_x
        self.win_y = twilight_screen_y - new_sprite_y
        self.sprite_x = new_sprite_x
        self.sprite_y = new_sprite_y

        self.pedestal_cx = self.sprite_x + self.sprite_w // 2
        self.pedestal_cy = self.sprite_y + self.sprite_h - 14

        for p in self.particles:
            p.reset(self.pedestal_cx, self.pedestal_cy, state=self.state)

        try:
            win32gui.SetWindowPos(
                self.hwnd,
                win32con.HWND_TOPMOST,
                self.win_x,
                self.win_y,
                self.win_w,
                self.win_h,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE
            )
        except Exception:
            pass

        if abs(twilight_screen_x - self.config.initial_x) > 12 or abs(twilight_screen_y - self.config.initial_y) > 12:
            self.config.initial_x = twilight_screen_x
            self.config.initial_y = twilight_screen_y
            self.config.save()

    def update_and_render(self, dt: float) -> bool:
        """Process events and render frame. Returns False when application quits."""
        self.anim_time += dt
        if int(self.anim_time) != int(self.anim_time - dt):
            self._ensure_transparency()

        self._check_window_perch(dt)
        self._update_dynamic_study_state(dt)

        # Auto-close idle input box after timeout (12s if empty, 30s if text typed)
        if self.show_input:
            idle_limit = 12.0 if not self.input_text.strip() else 30.0
            if time.time() - self.last_input_activity > idle_limit:
                self.show_input = False
                self.input_text = ""
                self.cursor_pos = 0
                self.selection_active = False
                self.restore_ambient_state()
                self.status_message = "Ready"

        if time.time() - self.last_cursor_toggle > 0.5:
            self.cursor_visible = not self.cursor_visible
            self.last_cursor_toggle = time.time()

        # Dynamic snug card bounding rects based on current anchors
        input_w = 440
        input_h = 108
        input_card_rect = self._calculate_card_rect(input_w, input_h)
        voice_card_rect = self._calculate_card_rect(340, 96)

        line_height = 20
        num_lines = max(1, len(self.response_lines))
        max_card_h = min(420, self.win_h - 40)
        resp_h = max(80, min(max_card_h, 48 + num_lines * line_height + 16))
        
        max_line_w = 0
        if self.response_lines:
            for line in self.response_lines:
                w = self.font_body.size(line)[0]
                if w > max_line_w:
                    max_line_w = w
        resp_w = max(290, min(440, max_line_w + 42))
        resp_card_rect = self._calculate_card_rect(resp_w, resp_h)

        think_w = 400
        think_h = 70
        think_card_rect = self._calculate_card_rect(think_w, think_h)

        # Auto-close speech bubble after reading duration (scaled by length, pause while hovering/scrolling)
        if self.show_response:
            words = len(self.response_text.split())
            read_duration = max(4.0, min(14.0, 2.0 + words * 0.16))
            self._current_read_duration = read_duration
            mx, my = pygame.mouse.get_pos()
            is_hovering = resp_card_rect.collidepoint(mx, my)
            if is_hovering:
                self.last_response_hover_time = time.time()
            hover_cushion = time.time() - getattr(self, "last_response_hover_time", 0.0) < 2.0

            # Never count down or close while Twilight is actively speaking through TTS
            is_speaking = bool(getattr(self, "is_tts_speaking_fn", None) and self.is_tts_speaking_fn())
            if is_speaking:
                self.response_start_time = time.time()

            time_open = time.time() - self.response_start_time

            if getattr(self, "is_trailer", False):
                # Safety cap: auto-dismiss trailer bubble after 15s if background tool hangs
                if time_open > 15.0:
                    self.dismiss_response()
            else:
                # Normal dialogue bubble dismissal: close only after speech finishes, reading duration elapsed, and user is not hovering
                if not is_speaking and (not is_hovering and not hover_cushion) and (time_open > read_duration):
                    self.dismiss_response()
                elif not is_speaking and not is_hovering and (time_open > read_duration + 8.0):
                    # Hard safety ceiling: always close after read_duration + 8s if user isn't actively hovering
                    self.dismiss_response()

        # Safety: if user released mouse button anywhere in Windows while dragging, release drag
        if self.is_dragging and (time.time() - self.mouse_down_time > 0.15) and not (win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000):
            self.is_dragging = False
            self.drag_tilt = 0.0
            try:
                win32gui.ReleaseCapture()
            except Exception:
                pass
            self._finish_drag()

        # Pygame event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.MOUSEWHEEL:
                if self.show_response:
                    content_h = len(self.response_lines) * line_height
                    visible_h = resp_card_rect.height - 52
                    max_scroll = max(0, content_h - visible_h)
                    self.speech_scroll_y = max(0, min(max_scroll, self.speech_scroll_y - event.y * 24))

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mx, my = event.pos
                    if self._check_companion_click(mx, my):
                        self.is_dragging = True
                        self.mouse_down_time = time.time()
                        cur_x, cur_y = win32gui.GetCursorPos()
                        self.drag_offset_x = cur_x - self.win_x
                        self.drag_offset_y = cur_y - self.win_y
                        self.initial_press_x = cur_x
                        self.initial_press_y = cur_y
                        self.prev_drag_x = cur_x
                        self.drag_tilt = 0.0
                        try:
                            win32gui.SetCapture(self.hwnd)
                        except Exception:
                            pass
                    else:
                        if self.show_input:
                            if self._mic_btn_rect and self._mic_btn_rect.collidepoint(mx, my):
                                self.toggle_voice_input()
                            elif input_card_rect.collidepoint(mx, my):
                                well_x = input_card_rect.x + 20 - getattr(self, "input_scroll_x", 0)
                                rel_x = mx - well_x
                                best_pos = len(self.input_text)
                                for idx in range(len(self.input_text) + 1):
                                    if self.font_input.size(self.input_text[:idx])[0] >= rel_x:
                                        best_pos = idx
                                        break
                                self.cursor_pos = best_pos
                                self.selection_active = False
                                self.cursor_visible = True
                                self.last_cursor_toggle = time.time()
                            else:
                                self.show_input = False
                                self.selection_active = False
                                self.restore_ambient_state()
                        elif self.voice_state in ("listening", "recording", "processing") and not self.show_response:
                            if not voice_card_rect.collidepoint(mx, my):
                                if self.voice_input_mgr:
                                    self.voice_input_mgr.cancel()
                                self.voice_state = "idle"
                                self.restore_ambient_state()
                        elif self.show_response and not resp_card_rect.collidepoint(mx, my):
                            if not getattr(self, "is_processing", False):
                                self.dismiss_response()

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self.is_dragging:
                    self.is_dragging = False
                    self.drag_tilt = 0.0
                    try:
                        win32gui.ReleaseCapture()
                    except Exception:
                        pass
                    cur_x, cur_y = win32gui.GetCursorPos()
                    total_moved = math.hypot(cur_x - self.initial_press_x, cur_y - self.initial_press_y)
                    if (time.time() - self.mouse_down_time) < 0.40 and total_moved < 12:
                        if self.show_response:
                            self.dismiss_response()
                        else:
                            self.show_input = not self.show_input
                            self.state = "input" if self.show_input else "idle"
                            self.last_input_activity = time.time()
                            if self.show_input:
                                self.cursor_pos = len(self.input_text)
                                self.selection_active = False
                    else:
                        self._finish_drag()

            elif event.type == pygame.MOUSEMOTION:
                pass

            elif event.type == pygame.KEYDOWN:
                if self.voice_state in ("listening", "recording", "processing") and event.key == pygame.K_ESCAPE:
                    if self.voice_input_mgr:
                        self.voice_input_mgr.cancel()
                    self.voice_state = "idle"
                    self.restore_ambient_state()
                    continue

                if self.show_input:
                    self.last_input_activity = time.time()
                    self.cursor_visible = True
                    self.last_cursor_toggle = time.time()
                    if (event.key == pygame.K_v) and (event.mod & pygame.KMOD_CTRL) and (event.mod & pygame.KMOD_SHIFT):
                        self.toggle_voice_input()
                    elif event.key == pygame.K_ESCAPE:
                        self.show_input = False
                        self.selection_active = False
                        self.restore_ambient_state()
                    elif event.key == pygame.K_RETURN:
                        if self.input_text.strip():
                            submitted = self.input_text.strip()
                            self.response_query = submitted
                            self.input_text = ""
                            self.cursor_pos = 0
                            self.selection_active = False
                            self.show_input = False
                            self.set_state("thinking", "Formulating a reply...")
                            if self.on_submit:
                                self.on_submit(submitted)
                    elif event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL):
                        set_clipboard_text(self.input_text)
                    elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                        p_txt = get_clipboard_text().replace('\r', '').replace('\n', ' ')
                        if p_txt:
                            if getattr(self, "selection_active", False):
                                self.input_text = p_txt
                                self.cursor_pos = len(p_txt)
                                self.selection_active = False
                            else:
                                self.input_text = self.input_text[:self.cursor_pos] + p_txt + self.input_text[self.cursor_pos:]
                                self.cursor_pos += len(p_txt)
                    elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL):
                        self.selection_active = True
                    elif event.key == pygame.K_HOME:
                        self.cursor_pos = 0
                        self.selection_active = False
                    elif event.key == pygame.K_END:
                        self.cursor_pos = len(self.input_text)
                        self.selection_active = False
                    elif event.key == pygame.K_LEFT:
                        self.selection_active = False
                        if event.mod & pygame.KMOD_CTRL:
                            pos = self.cursor_pos
                            while pos > 0 and self.input_text[pos - 1] == ' ':
                                pos -= 1
                            while pos > 0 and self.input_text[pos - 1] != ' ':
                                pos -= 1
                            self.cursor_pos = pos
                        else:
                            self.cursor_pos = max(0, self.cursor_pos - 1)
                    elif event.key == pygame.K_RIGHT:
                        self.selection_active = False
                        if event.mod & pygame.KMOD_CTRL:
                            pos = self.cursor_pos
                            while pos < len(self.input_text) and self.input_text[pos] != ' ':
                                pos += 1
                            while pos < len(self.input_text) and self.input_text[pos] == ' ':
                                pos += 1
                            self.cursor_pos = pos
                        else:
                            self.cursor_pos = min(len(self.input_text), self.cursor_pos + 1)
                    elif event.key == pygame.K_BACKSPACE:
                        if getattr(self, "selection_active", False):
                            self.input_text = ""
                            self.cursor_pos = 0
                            self.selection_active = False
                        elif self.cursor_pos > 0:
                            if event.mod & pygame.KMOD_CTRL:
                                pos = self.cursor_pos
                                while pos > 0 and self.input_text[pos - 1] == ' ':
                                    pos -= 1
                                while pos > 0 and self.input_text[pos - 1] != ' ':
                                    pos -= 1
                                self.input_text = self.input_text[:pos] + self.input_text[self.cursor_pos:]
                                self.cursor_pos = pos
                            else:
                                self.input_text = self.input_text[:self.cursor_pos - 1] + self.input_text[self.cursor_pos:]
                                self.cursor_pos -= 1
                    elif event.key == pygame.K_DELETE:
                        if getattr(self, "selection_active", False):
                            self.input_text = ""
                            self.cursor_pos = 0
                            self.selection_active = False
                        elif self.cursor_pos < len(self.input_text):
                            self.input_text = self.input_text[:self.cursor_pos] + self.input_text[self.cursor_pos + 1:]
                    else:
                        if event.unicode and ord(event.unicode[0]) >= 32:
                            if getattr(self, "selection_active", False):
                                self.input_text = event.unicode
                                self.cursor_pos = len(event.unicode)
                                self.selection_active = False
                            else:
                                self.input_text = self.input_text[:self.cursor_pos] + event.unicode + self.input_text[self.cursor_pos:]
                                self.cursor_pos += len(event.unicode)
                elif self.show_response:
                    if event.key in (pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                        self.dismiss_response()

        # Smooth, hardware-synced 60 FPS window dragging with momentum tilt & zero frame drops
        if self.is_dragging and win32gui and win32con:
            cur_x, cur_y = win32gui.GetCursorPos()
            target_x = cur_x - getattr(self, "drag_offset_x", 0)
            target_y = cur_y - getattr(self, "drag_offset_y", 0)
            if target_x != self.win_x or target_y != self.win_y:
                vx = cur_x - getattr(self, "prev_drag_x", cur_x)
                target_tilt = max(-14.0, min(14.0, -vx * 0.45))
                self.drag_tilt += (target_tilt - self.drag_tilt) * min(1.0, dt * 16.0)
                self.prev_drag_x = cur_x
                self.win_x = target_x
                self.win_y = target_y
                try:
                    win32gui.SetWindowPos(
                        self.hwnd,
                        win32con.HWND_TOPMOST,
                        self.win_x,
                        self.win_y,
                        self.win_w,
                        self.win_h,
                        win32con.SWP_NOACTIVATE | win32con.SWP_NOSIZE
                    )
                except Exception:
                    pass
            else:
                self.drag_tilt += (0.0 - self.drag_tilt) * min(1.0, dt * 10.0)
                self.prev_drag_x = cur_x

        # Render background (invisible colorkey)
        self.screen.fill(COLORKEY)

        # 1. Render Floating Halo & Companion Sprite
        self._render_halo_and_sprite(dt)

        # 2. Render Thinking Indicator if waiting for Gemini (and not in voice input)
        if self.state == "thinking" and not self.show_input and not self.show_response and self.voice_state == "idle":
            self._render_thinking_card(think_card_rect)

        # 3. Render Voice Listening Card if active
        if self.voice_state in ("listening", "recording", "processing") and not self.show_response:
            self._render_voice_card(voice_card_rect)

        # 4. Render Speech Bubble / Response Card if dialogue is active
        if self.show_response:
            self._render_response_card(resp_card_rect)

        # 5. Render Input Card if typing (and voice card is not active)
        if self.show_input and self.voice_state == "idle":
            self._render_input_box(input_card_rect)

        pygame.display.update()
        return True

    def _render_halo_and_sprite(self, dt: float):
        """Draw animated celestial starlight pedestal with floating companion character sprite."""
        base_cx = self.sprite_x + self.sprite_w // 2
        base_cy = self.sprite_y + self.sprite_h - 14

        is_music = (self.state == "music" or self.current_emotion == "music")
        if is_music:
            bob_y = math.sin(self.anim_time * 5.2) * 6.5
            pedestal_col = (34, 211, 238)    # Neon Cyan
            accent_col = (244, 114, 182)
            speed_mult = 1.8
        elif self.is_dragging:
            bob_y = math.sin(self.anim_time * 2.8) * 3.5
            pedestal_col = (244, 114, 182)   # Hot Pink
            accent_col = (255, 255, 255)
            speed_mult = 2.5
        elif self.voice_state in ("listening", "recording", "processing"):
            bob_y = math.sin(self.anim_time * 3.6) * 4.0
            # Active starlight pulse between electric cyan and glowing purple
            pulse_t = (math.sin(self.anim_time * 6.0) + 1.0) * 0.5
            r = int(56 * (1.0 - pulse_t) + 168 * pulse_t)
            g = int(189 * (1.0 - pulse_t) + 85 * pulse_t)
            b = int(248 * (1.0 - pulse_t) + 247 * pulse_t)
            pedestal_col = (r, g, b)
            accent_col = (255, 255, 255)
            speed_mult = 2.4
        elif self.state == "thinking":
            bob_y = math.sin(self.anim_time * 2.8) * 3.5
            pedestal_col = (56, 189, 248)    # Electric Cyan
            accent_col = (255, 255, 255)
            speed_mult = 2.8
        elif self.state == "speaking":
            bob_y = math.sin(self.anim_time * 3.6) * 4.5
            pedestal_col = (244, 114, 182)   # Orchid / Magenta
            accent_col = (216, 180, 254)
            speed_mult = 1.8
        else:  # idle / input
            bob_y = math.sin(self.anim_time * 2.8) * 3.5
            pedestal_col = (168, 85, 247)    # SciTwi Purple
            accent_col = (216, 180, 254)
            speed_mult = 1.0

        self.current_bob_y = bob_y

        # Layer 1: Geometric Celestial Magic Ring (Perspective Ellipse beneath companion)
        if getattr(self, "is_perched", False):
            # Perched on active window: draw clean snug contact shadow on window ledge, no floating space ring
            shadow_rect = pygame.Rect(int(base_cx - 36), int(self.sprite_y + self.sprite_h - 12 + bob_y * 0.3), 72, 8)
            pygame.draw.ellipse(self.screen, (20, 20, 30), shadow_rect)
        else:
            rx = 62 + math.sin(self.anim_time * 3.0) * 2.0
            ry = 20 + math.sin(self.anim_time * 3.0) * 0.8
            ring_rect = pygame.Rect(int(base_cx - rx), int(base_cy - ry + bob_y), int(rx * 2), int(ry * 2))

            pygame.draw.ellipse(self.screen, pedestal_col, ring_rect, width=2)
            
            inner_rx = rx * 0.72
            inner_ry = ry * 0.72
            inner_rect = pygame.Rect(int(base_cx - inner_rx), int(base_cy - inner_ry + bob_y), int(inner_rx * 2), int(inner_ry * 2))
            pygame.draw.ellipse(self.screen, accent_col, inner_rect, width=1)

            rot_angle = self.anim_time * (1.2 * speed_mult)
            for i in range(4):
                ang = rot_angle + i * (math.tau / 4.0)
                tx = base_cx + rx * math.cos(ang)
                ty = base_cy + ry * math.sin(ang) + bob_y
                pts = [(int(tx), int(ty - 3)), (int(tx + 3), int(ty)), (int(tx), int(ty + 3)), (int(tx - 3), int(ty))]
                pygame.draw.polygon(self.screen, (255, 255, 255), pts)

            # Layer 2: Celestial Starlight Particles (only when free-floating)
            for p in self.particles:
                p.update(dt, base_cx, base_cy, state=self.state, speed_mult=speed_mult)
                p.draw(self.screen)

        # Layer 3: Dragging panic particles (sweatdrops / surprise sparks)
        if self.is_dragging:
            sweat_t = (self.anim_time * 6.0) % 1.0
            sx = self.sprite_x + self.sprite_w - 25
            sy = self.sprite_y + 20 + bob_y + sweat_t * 15
            pygame.draw.line(self.screen, (56, 189, 248), (int(sx), int(sy)), (int(sx + 3), int(sy - 6)), 2)

        # Layer 4: Companion Character Sprite with Dynamic Emotion & Tilt
        if self.is_dragging:
            sprite_key = "when_dragged" if "when_dragged" in self.expressions else "flustered"
        elif self.voice_state in ("listening", "recording"):
            sprite_key = "idle"  # Twilight is listening attentively to user speech—never talking
        elif self.voice_state == "processing":
            sprite_key = "thinking"
        elif self.state == "thinking":
            sprite_key = "thinking"
        elif self.state == "music":
            sprite_key = "music"
        elif self.current_emotion in self.expressions:
            sprite_key = self.current_emotion
        else:
            sprite_key = "idle"

        sprite_surf = self.expressions.get(sprite_key) or self.expressions.get("idle")
        if sprite_surf:
            if self.is_dragging and abs(self.drag_tilt) > 0.5:
                rotated = pygame.transform.rotate(sprite_surf, self.drag_tilt)
                rot_rect = rotated.get_rect(center=(self.sprite_x + self.sprite_w // 2, int(self.sprite_y + self.sprite_h // 2 + bob_y)))
                self.screen.blit(rotated, rot_rect)
            else:
                self.screen.blit(sprite_surf, (self.sprite_x, int(self.sprite_y + bob_y)))

        # Layer 5: Dynamic Anime Iconography Effects
        self._render_anime_effects(bob_y)

    def _render_anime_effects(self, bob_y: float):
        """Render active anime iconography stickers with authentic anime comedic timing & animations."""
        if not getattr(self, "effects", None):
            return

        now = time.time()
        time_in_state = now - getattr(self, "state_change_time", now)

        # 1. Dragging effect: anime panic marks floating above head (never blocking avatar)
        if self.is_dragging:
            drag_eff = self.effects.get("dragged_effects1")
            if drag_eff:
                dx = self.sprite_x + self.sprite_w // 2 - drag_eff.get_width() // 2 + 12
                dy = self.sprite_y - drag_eff.get_height() + 10 + bob_y
                self.screen.blit(drag_eff, (int(dx), int(dy)))
            return

        # 2. Thinking effect: Question Mark '?' hovering above left bangs snug to sprite
        if self.state == "thinking":
            q_eff = self.effects.get("thinking_effect1")
            if q_eff:
                if time_in_state < 0.22:
                    p = time_in_state / 0.22
                    scale = min(1.35, p * 1.5) if p < 0.7 else (1.35 - (p - 0.7) / 0.3 * 0.35)
                else:
                    scale = 1.0

                wobble_deg = math.sin(self.anim_time * 4.2) * 6.5
                float_y = math.sin(self.anim_time * 2.8) * 1.8
                
                rot_surf = pygame.transform.rotozoom(q_eff, wobble_deg, scale)
                rx = self.sprite_x + 42 - rot_surf.get_width() // 2
                ry = self.sprite_y - 2 - rot_surf.get_height() // 2 + bob_y + float_y
                self.screen.blit(rot_surf, (int(rx), int(ry)))
            return

        # 3. Interrupted effect: Pink shock slashes radiating upper-left + sweat drops
        if self.current_emotion == "interrupted":
            bang_eff = self.effects.get("interrupted_mark_effect")
            sweat_eff = self.effects.get("flustered_effect")
            if bang_eff:
                if time_in_state < 0.16:
                    scale = 0.5 + (time_in_state / 0.16) * 0.8
                else:
                    scale = 1.0
                shudder = random.uniform(-2.0, 2.0) if time_in_state < 0.28 else 0.0
                rot_surf = pygame.transform.rotozoom(bang_eff, 0, scale)
                rx = self.sprite_x - 14 + shudder
                ry = self.sprite_y - 8 + bob_y
                self.screen.blit(rot_surf, (int(rx), int(ry)))
            if sweat_eff:
                self.screen.blit(sweat_eff, (int(self.sprite_x - 22), int(self.sprite_y + 44 + bob_y)))
            return

        # 4. Music effect: Smooth continuous floating notes with zero snappy reset at loop boundary
        if self.state == "music" or self.current_emotion == "music":
            n1 = self.effects.get("music_note1")
            n2 = self.effects.get("music_note2")
            if n1:
                t1 = (self.anim_time * 0.40) % 1.0
                y1 = self.sprite_y + 14 - (t1 * 46.0)
                x1 = self.sprite_x + self.sprite_w - 20 + math.sin(t1 * math.tau) * 7.0
                deg1 = math.sin(t1 * math.tau) * 10.0
                alpha1 = int(255 * (math.sin(t1 * math.pi) ** 1.5)) if (0.03 < t1 < 0.97) else 0
                rot_s1 = pygame.transform.rotozoom(n1, deg1, 1.0)
                rot_s1.set_alpha(max(0, min(255, alpha1)))
                self.screen.blit(rot_s1, (int(x1), int(y1)))
            if n2:
                t2 = (self.anim_time * 0.40 + 0.5) % 1.0
                y2 = self.sprite_y + 14 - (t2 * 46.0)
                x2 = self.sprite_x + self.sprite_w + 8 - math.cos(t2 * math.tau) * 8.0
                deg2 = -math.cos(t2 * math.tau) * 9.0
                alpha2 = int(255 * (math.sin(t2 * math.pi) ** 1.5)) if (0.03 < t2 < 0.97) else 0
                rot_s2 = pygame.transform.rotozoom(n2, deg2, 1.0)
                rot_s2.set_alpha(max(0, min(255, alpha2)))
                self.screen.blit(rot_s2, (int(x2), int(y2)))
            return

        # 5. Sleeping effect: Rising zigzag Z with scale expansion & fade
        if self.current_emotion in ("sleep", "sleepy"):
            z_eff = self.effects.get("sleep_z_one_letter")
            if z_eff:
                zt = (self.anim_time * 0.5) % 1.0
                zx = self.sprite_x + self.sprite_w // 2 - 8 + math.sin(zt * 6.28) * 9.0
                zy = self.sprite_y + 10 + bob_y - (zt * 42.0)
                z_scale = 0.65 + zt * 0.45
                alpha_z = max(0, min(255, int(255 * math.sin(zt * math.pi))))
                rot_z = pygame.transform.rotozoom(z_eff, math.sin(zt * 3.14) * 8.0, z_scale)
                rot_z.set_alpha(alpha_z)
                self.screen.blit(rot_z, (int(zx), int(zy)))
            return

        # 6. Tired effect: Anime breath puff cloud expanding and drifting from mouth corner (tired_sigh_reference.jpg)
        if self.current_emotion == "tired":
            puff = self.effects.get("tired_breath_effect")
            if puff:
                pt = (self.anim_time * 0.55) % 1.0
                px = self.sprite_x - 18 - (pt * 22.0)
                py = self.sprite_y + 92 + bob_y + math.sin(pt * math.pi) * 2.5
                p_scale = 0.65 + pt * 0.5
                alpha_p = max(0, min(255, int(255 * math.sin(pt * math.pi))))
                rot_p = pygame.transform.rotozoom(puff, 0, p_scale)
                rot_p.set_alpha(alpha_p)
                self.screen.blit(rot_p, (int(px), int(py)))
            return

        # 7. Flustered effect: vibration arcs flanking cheeks & stress marks (mirrored & separated)
        if self.current_emotion == "flustered":
            squig = self.effects.get("flustered_squiqly_shaking_effect")
            sweat = self.effects.get("flustered_effect")
            jitter_x = math.sin(self.anim_time * 42.0) * 2.0
            jitter_y = math.cos(self.anim_time * 32.0) * 1.2
            if squig:
                # Left cheek vibration
                self.screen.blit(squig, (int(self.sprite_x - 22 + jitter_x), int(self.sprite_y + 64 + bob_y + jitter_y)))
                # Right cheek vibration (flipped horizontally for symmetry)
                squig_r = pygame.transform.flip(squig, True, False)
                self.screen.blit(squig_r, (int(self.sprite_x + self.sprite_w + 4 + jitter_x), int(self.sprite_y + 64 + bob_y + jitter_y)))
            if sweat:
                # Placed higher on upper-left temple/bangs to avoid overlapping cheek squiggly
                self.screen.blit(sweat, (int(self.sprite_x - 18), int(self.sprite_y + 20 + bob_y)))
            return

        # 8. Happy / Smug / Speaking sparkles: Top-Left 3-rays and Lower-Right 2-rays snug to hair
        if self.current_emotion in ("happy", "smug") or self.state == "speaking":
            r1 = self.effects.get("happy_or_talking_effects1")
            r2 = self.effects.get("happy_or_talking_effects2")
            sp_pulse = 0.90 + 0.16 * math.sin(self.anim_time * 4.0)
            if r1:
                sp_deg1 = math.sin(self.anim_time * 2.5) * 8.0
                rot_r1 = pygame.transform.rotozoom(r1, sp_deg1, sp_pulse)
                self.screen.blit(rot_r1, (int(self.sprite_x - 10), int(self.sprite_y + 4 + bob_y)))
            if r2:
                sp_deg2 = -math.sin(self.anim_time * 2.5) * 8.0
                rot_r2 = pygame.transform.rotozoom(r2, sp_deg2, sp_pulse)
                self.screen.blit(rot_r2, (int(self.sprite_x + self.sprite_w - 12), int(self.sprite_y + self.sprite_h - 34 + bob_y)))

    def _render_input_box(self, card_rect: pygame.Rect):
        """Draw sleek, modern dark-glass input card with text clipping & horizontal scrolling."""
        card_x, card_y, card_w, card_h = card_rect

        pygame.draw.rect(self.screen, (24, 24, 37), card_rect, border_radius=12)
        pygame.draw.rect(self.screen, (168, 85, 247), card_rect, width=2, border_radius=12)

        draw_six_pointed_star(self.screen, card_x + 22, card_y + 20, (216, 180, 254), size=6.5)
        title_surf = self.font_title.render("Twilight", True, (216, 180, 254))
        self.screen.blit(title_surf, (card_x + 34, card_y + 10))

        badge_surf = self.font_hint.render(f"[{self.status_message}]", True, (148, 163, 184))
        self.screen.blit(badge_surf, (card_x + card_w - badge_surf.get_width() - 14, card_y + 12))

        well_rect = pygame.Rect(card_x + 12, card_y + 36, card_w - 24, 34)
        pygame.draw.rect(self.screen, (17, 17, 27), well_rect, border_radius=8)
        pygame.draw.rect(self.screen, (76, 79, 105), well_rect, width=1, border_radius=8)

        # Microphone Action Button (right end of input well)
        mic_btn_rect = pygame.Rect(well_rect.right - 30, well_rect.y + 3, 26, 28)
        self._mic_btn_rect = mic_btn_rect
        is_voice_active = self.voice_state in ("listening", "recording", "processing")
        if is_voice_active:
            mic_bg = (88, 28, 135)
            mic_border = (56, 189, 248)
            mic_col = (56, 189, 248) if int(self.anim_time * 6) % 2 == 0 else (255, 255, 255)
        else:
            mic_bg = (30, 30, 46)
            mic_border = (76, 79, 105)
            mic_col = (192, 132, 252)

        pygame.draw.rect(self.screen, mic_bg, mic_btn_rect, border_radius=6)
        pygame.draw.rect(self.screen, mic_border, mic_btn_rect, width=1, border_radius=6)

        # Vector Microphone Icon
        mcx = mic_btn_rect.centerx
        mcy = mic_btn_rect.centery - 2
        pygame.draw.rect(self.screen, mic_col, (mcx - 3, mcy - 5, 6, 9), border_radius=3)
        pygame.draw.arc(self.screen, mic_col, (mcx - 6, mcy - 3, 12, 9), 3.1415, 0.0, 1)
        pygame.draw.line(self.screen, mic_col, (mcx, mcy + 6), (mcx, mcy + 9), 1)
        pygame.draw.line(self.screen, mic_col, (mcx - 4, mcy + 9), (mcx + 4, mcy + 9), 1)

        inner_text_rect = pygame.Rect(well_rect.x + 8, well_rect.y + 4, well_rect.width - 42, well_rect.height - 8)
        self.screen.set_clip(inner_text_rect)

        if self.input_text:
            text_w = self.font_input.size(self.input_text)[0]
            cursor_offset = self.font_input.size(self.input_text[:self.cursor_pos])[0]

            if not hasattr(self, "input_scroll_x"):
                self.input_scroll_x = 0
            max_scroll = max(0, text_w - (inner_text_rect.width - 24))
            if cursor_offset - self.input_scroll_x > inner_text_rect.width - 24:
                self.input_scroll_x = cursor_offset - (inner_text_rect.width - 24)
            elif cursor_offset - self.input_scroll_x < 0:
                self.input_scroll_x = cursor_offset
            self.input_scroll_x = max(0, min(self.input_scroll_x, max_scroll))

            draw_x = inner_text_rect.x - self.input_scroll_x
            draw_y = inner_text_rect.y + 2

            if getattr(self, "selection_active", False):
                pygame.draw.rect(self.screen, (88, 48, 120), (draw_x, draw_y, text_w, 20), border_radius=3)

            text_surf = self.font_input.render(self.input_text, True, (245, 245, 247))
            self.screen.blit(text_surf, (draw_x, draw_y))

            if self.cursor_visible and not getattr(self, "selection_active", False):
                caret_x = draw_x + cursor_offset + 1
                pygame.draw.line(self.screen, (192, 132, 252), (caret_x, draw_y), (caret_x, draw_y + 20), 2)
        else:
            if is_voice_active:
                if self.voice_state == "processing":
                    v_txt = "Processing voice command..."
                elif self.voice_state == "recording":
                    v_txt = "Listening to your request..."
                else:
                    v_txt = "I'm listening... Speak now!"
                placeholder_surf = self.font_input.render(v_txt, True, (56, 189, 248))
            else:
                placeholder_surf = self.font_input.render("Ask Twilight anything... (or press Ctrl+Shift+V to talk)", True, (108, 112, 134))
            self.screen.blit(placeholder_surf, (inner_text_rect.x, inner_text_rect.y + 2))
            if self.cursor_visible:
                pygame.draw.line(self.screen, (192, 132, 252), (inner_text_rect.x, inner_text_rect.y + 2), (inner_text_rect.x, inner_text_rect.y + 22), 2)

        self.screen.set_clip(None)

        hint_surf = self.font_hint.render("Press [Enter] send  •  [Ctrl+Shift+V] voice  •  [Esc] close", True, (148, 163, 184))
        self.screen.blit(hint_surf, (card_x + 14, card_y + card_h - 22))

    def _render_voice_card(self, card_rect: pygame.Rect):
        """Draw sleek, illuminated listening card with animated soundwave audio meter."""
        card_x, card_y, card_w, card_h = card_rect

        # Semi-transparent dark glass container
        pygame.draw.rect(self.screen, (24, 24, 37), card_rect, border_radius=12)
        border_col = (56, 189, 248) if self.voice_state in ("recording", "processing") else (168, 85, 247)
        pygame.draw.rect(self.screen, border_col, card_rect, width=2, border_radius=12)

        # Title & Starlight Star
        draw_six_pointed_star(self.screen, card_x + 22, card_y + 18, (56, 189, 248), size=6.5)
        title_text = "Twilight - Listening" if self.voice_state != "processing" else "Twilight - Processing"
        title_surf = self.font_title.render(title_text, True, (216, 180, 254))
        self.screen.blit(title_surf, (card_x + 34, card_y + 10))

        # Dynamic Soundwave Visualizer Bars (7 bars centered)
        wave_cx = card_x + card_w // 2
        wave_base_y = card_y + 40
        bar_w = 4
        bar_gap = 4
        num_bars = 7
        total_w = num_bars * bar_w + (num_bars - 1) * bar_gap
        start_x = wave_cx - total_w // 2

        for i in range(num_bars):
            dist_from_center = abs(i - 3)
            center_weight = 1.0 - (dist_from_center * 0.18)

            if self.voice_state == "processing":
                # Rolling loading sparkle wave
                wave_t = math.sin(self.anim_time * 8.0 + i * 0.8)
                bar_h = int(6 + 12 * max(0.0, wave_t))
                col = (56, 189, 248)
            elif self.voice_state == "recording":
                # Audio-reactive wave based on real-time microphone RMS level
                wave_t = 0.5 + 0.5 * math.sin(self.anim_time * 14.0 + i * 1.1)
                audio_amp = max(0.15, self.voice_audio_level)
                bar_h = int(5 + 24 * audio_amp * center_weight * wave_t)
                col = (244, 114, 182) if i % 2 == 0 else (56, 189, 248)
            else:  # listening / waiting for voice
                wave_t = 0.5 + 0.5 * math.sin(self.anim_time * 4.0 + i * 0.9)
                bar_h = int(4 + 8 * wave_t * center_weight)
                col = (168, 85, 247)

            bx = start_x + i * (bar_w + bar_gap)
            by = wave_base_y - bar_h // 2
            pygame.draw.rect(self.screen, col, (bx, by, bar_w, bar_h), border_radius=2)

        # Status subtitle line
        if self.voice_state == "processing":
            sub_text = "Transcribing audio..."
            sub_col = (56, 189, 248)
        elif self.voice_state == "recording":
            sub_text = "Listening to your request..."
            sub_col = (244, 114, 182)
        else:
            sub_text = "I'm listening... Speak now!"
            sub_col = (148, 163, 184)

        sub_surf = self.font_body.render(sub_text, True, sub_col)
        self.screen.blit(sub_surf, (card_x + (card_w - sub_surf.get_width()) // 2, card_y + 54))

        # Bottom hint
        hint_surf = self.font_hint.render("[Esc] cancel  •  [Ctrl+Shift+V] finish", True, (108, 112, 134))
        self.screen.blit(hint_surf, (card_x + (card_w - hint_surf.get_width()) // 2, card_y + card_h - 18))

    def _render_thinking_card(self, card_rect: pygame.Rect):
        """Draw an animated thinking / formulating reply card above or below the companion."""
        card_x, card_y, card_w, card_h = card_rect

        pygame.draw.rect(self.screen, (24, 24, 37), card_rect, border_radius=12)
        pygame.draw.rect(self.screen, (56, 189, 248), card_rect, width=2, border_radius=12)

        dot_count = int(self.anim_time * 3.0) % 4
        dots = "." * dot_count
        draw_six_pointed_star(self.screen, card_x + 22, card_y + 22, (56, 189, 248), size=6.5)
        title_surf = self.font_title.render(f"Formulating a reply{dots}", True, (56, 189, 248))
        self.screen.blit(title_surf, (card_x + 34, card_y + 12))

        if self.response_query:
            query_preview = f'"{self.response_query[:56]}{"..." if len(self.response_query) > 56 else ""}"'
            query_surf = self.font_body.render(query_preview, True, (203, 213, 225))
            self.screen.blit(query_surf, (card_x + 16, card_y + 40))

    def _render_response_card(self, card_rect: pygame.Rect):
        """Draw on-screen speech bubble card displaying what Twilight says with scroll support."""
        card_x, card_y, card_w, card_h = card_rect

        pygame.draw.rect(self.screen, (24, 24, 37), card_rect, border_radius=12)
        pygame.draw.rect(self.screen, (168, 85, 247), card_rect, width=2, border_radius=12)

        draw_six_pointed_star(self.screen, card_x + 22, card_y + 22, (216, 180, 254), size=6.5)
        title_surf = self.font_title.render("Twilight", True, (216, 180, 254))
        self.screen.blit(title_surf, (card_x + 34, card_y + 12))

        dismiss_surf = self.font_hint.render("[Esc to close]", True, (148, 163, 184))
        self.screen.blit(dismiss_surf, (card_x + card_w - dismiss_surf.get_width() - 16, card_y + 14))

        # Set clip rect to protect card borders from any text overflow
        inner_rect = pygame.Rect(card_x + 14, card_y + 38, card_w - 28, card_h - 46)
        self.screen.set_clip(inner_rect)

        line_y = card_y + 40 - getattr(self, "speech_scroll_y", 0)
        line_height = 20
        for line in self.response_lines:
            if line_y + line_height >= card_y + 36 and line_y <= card_y + card_h:
                if line.startswith("```") or line.startswith("    "):
                    line_surf = self.font_code.render(line, True, (125, 211, 252))
                else:
                    line_surf = self.font_body.render(line, True, (241, 245, 249))
                self.screen.blit(line_surf, (card_x + 18, line_y))
            line_y += line_height

        self.screen.set_clip(None)

        # Subtle scrollbar indicator if text exceeds visible card area
        content_h = len(self.response_lines) * line_height
        visible_h = card_h - 52
        if content_h > visible_h:
            track_h = visible_h
            thumb_h = max(16, int(track_h * (visible_h / content_h)))
            scroll_pct = getattr(self, "speech_scroll_y", 0) / max(1, content_h - visible_h)
            thumb_y = card_y + 42 + int(scroll_pct * (track_h - thumb_h))
            thumb_rect = pygame.Rect(card_x + card_w - 7, thumb_y, 3, thumb_h)
            pygame.draw.rect(self.screen, (168, 85, 247), thumb_rect, border_radius=2)
