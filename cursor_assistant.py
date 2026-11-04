import os
import sys
import time
import math
import struct
import argparse
import ctypes
import atexit
import shutil
import io
import json
import re
from PIL import Image

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import psutil
except ImportError:
    win32api = None
    win32con = None
    win32gui = None
    win32process = None
    psutil = None

CURSOR_PNG = os.path.join(os.path.dirname(__file__), "assets", "cursor.png")
CURSOR_CUR = os.path.join(os.path.dirname(__file__), "assets", "twilight_cursor.cur")
COLORKEY = (10, 10, 16)

SYS_CURSOR_H = 32
SYS_CURSOR_W = 19

def ensure_twilight_cur_exists():
    """Ensure the Windows .cur file with (0,0) hotspot exists from the PNG asset with correct aspect ratio."""
    src_png = CURSOR_PNG
    if not os.path.exists(src_png):
        dl_png = r"C:\Users\azisk\Downloads\cursor.png"
        if os.path.exists(dl_png):
            src_png = dl_png
    if not os.path.exists(src_png):
        return CURSOR_CUR if os.path.exists(CURSOR_CUR) else ""
    try:
        # Check if current CURSOR_CUR is up-to-date and non-stretched (1412 bytes)
        if os.path.exists(CURSOR_CUR) and os.path.getsize(CURSOR_CUR) == 1412:
            return CURSOR_CUR
        os.makedirs(os.path.dirname(CURSOR_CUR), exist_ok=True)
        img = Image.open(src_png).convert("RGBA")
        h = SYS_CURSOR_H
        w = int(round(h * (img.width / img.height)))
        scaled = img.resize((w, h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        canvas.paste(scaled, (0, 0))
        buf = io.BytesIO()
        canvas.save(buf, format="ICO", sizes=[(32, 32)])
        cur_data = bytearray(buf.getvalue())
        struct.pack_into("<H", cur_data, 2, 2)
        struct.pack_into("<H", cur_data, 10, 0)
        struct.pack_into("<H", cur_data, 12, 0)
        with open(CURSOR_CUR, "wb") as f:
            f.write(cur_data)
        return CURSOR_CUR
    except Exception as e:
        print(f"[Cursor] ensure_twilight_cur_exists error: {e}")
        return CURSOR_CUR if os.path.exists(CURSOR_CUR) else ""

_twilight_cursor_active = False

def set_twilight_system_cursor():
    """Temporarily replace Windows system cursors with Twilight's custom cursor."""
    global _twilight_cursor_active
    cur_path = ensure_twilight_cur_exists()
    if not cur_path or not os.path.exists(cur_path):
        return False
    try:
        IMAGE_CURSOR = 2
        LR_LOADFROMFILE = 0x00000010
        hcur = ctypes.windll.user32.LoadImageW(None, cur_path, IMAGE_CURSOR, 32, 32, LR_LOADFROMFILE)
        if hcur:
            for cid in (32512, 32513, 32649):
                hcopy = ctypes.windll.user32.CopyIcon(hcur)
                ctypes.windll.user32.SetSystemCursor(hcopy, cid)
            _twilight_cursor_active = True
            return True
    except Exception as e:
        print(f"[Cursor] set_twilight_system_cursor error: {e}")
    return False

def restore_system_cursor():
    """Restore normal default Windows cursors."""
    global _twilight_cursor_active
    if not _twilight_cursor_active:
        return
    try:
        SPI_SETCURSORS = 0x0057
        ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
        _twilight_cursor_active = False
    except Exception:
        pass

atexit.register(restore_system_cursor)

def attach_desktop():
    """Ensure process and thread are attached to the interactive user desktop."""
    try:
        winsta = ctypes.windll.user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if winsta:
            ctypes.windll.user32.SetProcessWindowStation(winsta)
            desk = ctypes.windll.user32.OpenDesktopW("default", 0, False, 0x01FF)
            if desk:
                ctypes.windll.user32.SetThreadDesktop(desk)
    except Exception:
        pass

def force_foreground_window(hwnd):
    """Force any window into the active foreground even if called from a background thread."""
    if not hwnd or not win32gui:
        return
    attach_desktop()
    try:
        if win32gui.IsIconic(hwnd) or win32gui.GetWindowRect(hwnd)[0] <= -10000:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fore_hwnd = win32gui.GetForegroundWindow()
        if fore_hwnd and win32process:
            fore_tid, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
            target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            if fore_tid != cur_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, fore_tid, True)
            if target_tid != cur_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, target_tid, True)

            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)

            if fore_tid != cur_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, fore_tid, False)
            if target_tid != cur_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, target_tid, False)
        else:
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"[Cursor] force_foreground_window error: {e}")

def get_spotify_window():
    """Locate the main interactive Spotify window handle (Chrome_WidgetWin_1, w>=400, h>=300)."""
    attach_desktop()
    if not win32gui:
        return None

    spotify_candidates = []
    def enum_sp(hwnd, _):
        try:
            c = win32gui.GetClassName(hwnd)
            t = (win32gui.GetWindowText(hwnd) or "").strip()
            pname = ""
            if win32process and psutil:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    pname = psutil.Process(pid).name().lower()
                except Exception:
                    pass
            if "spotify" in pname:
                if not any(k in c.lower() for k in ["ime", "tray", "session", "power", "gdi+"]):
                    rect = win32gui.GetWindowRect(hwnd)
                    spotify_candidates.append((hwnd, c, t, rect))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(enum_sp, None)
    except Exception:
        pass

    chosen_hwnd = None
    for hwnd, c, t, rect in spotify_candidates:
        if c == "Chrome_WidgetWin_1":
            chosen_hwnd = hwnd
            break
        if any(k in t.lower() for k in ["spotify", "free", "premium"]):
            chosen_hwnd = hwnd
            break

    if not chosen_hwnd and spotify_candidates:
        for hwnd, c, t, rect in spotify_candidates:
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w >= 400 and h >= 300:
                chosen_hwnd = hwnd
                break

    if chosen_hwnd:
        try:
            if win32gui.IsIconic(chosen_hwnd) or win32gui.GetWindowRect(chosen_hwnd)[0] <= -10000:
                win32gui.ShowWindow(chosen_hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(chosen_hwnd, win32con.SW_SHOW)
        except Exception:
            pass

    return chosen_hwnd

def wait_for_spotify_ui_ready(hwnd, timeout: float = 3.5) -> bool:
    """Wait until Spotify window is rendered and not blank/black from cold start."""
    from PIL import ImageGrab, ImageStat
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = win32gui.GetWindowRect(hwnd)
            w = r[2] - r[0]
            h = r[3] - r[1]
            if w > 200 and h > 200 and r[0] > -10000:
                cx1 = r[0] + w // 4
                cy1 = r[1] + h // 4
                cx2 = r[0] + (3 * w) // 4
                cy2 = r[1] + (3 * h) // 4
                sample = ImageGrab.grab(bbox=(cx1, cy1, cx2, cy2))
                stat = ImageStat.Stat(sample)
                if any(s > 15 for s in stat.stddev):
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False

def get_browser_window():
    """Locate an active visible browser window (Chrome, Edge, Brave, Firefox)."""
    attach_desktop()
    if not win32gui:
        return None
    browser_hwnd = None
    candidates = ["chrome", "msedge", "brave", "firefox"]
    def cb(h, _):
        nonlocal browser_hwnd
        try:
            t = (win32gui.GetWindowText(h) or "").strip().lower()
            pname = ""
            if win32process and psutil:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(h)
                    pname = psutil.Process(pid).name().lower()
                except Exception:
                    pass
            if any(b in t or b in pname for b in candidates):
                if not any(k in t for k in ["default ime", "msctfime", "ciceroui"]):
                    browser_hwnd = h
                    return False
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return browser_hwnd

def type_text(text: str, delay: float = 0.055):
    """Type text characters via Windows keyboard events with lively one-by-one cadence."""
    if not win32api:
        return
    for ch in text:
        win32api.keybd_event(0, ord(ch), 0x0004, 0)
        time.sleep(0.02)
        win32api.keybd_event(0, ord(ch), 0x0004 | 2, 0)
        time.sleep(delay)
    time.sleep(0.1)

def glide_hardware_cursor(target_x: int, target_y: int, action: str = "click", glide_time: float = 0.35, start_x: int = None, start_y: int = None):
    """Pure Win32 hardware cursor glide using Twilight's custom cursor. Zero Pygame window, zero lag."""
    attach_desktop()
    if not win32api:
        return
    set_twilight_system_cursor()
    try:
        if start_x is None or start_y is None:
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            start_x, start_y = pt.x, pt.y

        steps = max(10, int(glide_time * 60))
        start_t = time.time()
        for i in range(1, steps + 1):
            elapsed = time.time() - start_t
            t = min(1.0, elapsed / glide_time) if glide_time > 0 else 1.0
            ease = t * t * (3.0 - 2.0 * t)
            cx = int(start_x + (target_x - start_x) * ease)
            cy = int(start_y + (target_y - start_y) * ease)
            win32api.SetCursorPos((cx, cy))
            if t >= 1.0:
                break
            time.sleep(max(0.005, (glide_time / steps) * 0.8))

        win32api.SetCursorPos((target_x, target_y))
        time.sleep(0.04)

        if action in ("click", "left_click"):
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
            time.sleep(0.03)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
        elif action == "double_click":
            for _ in range(2):
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
                time.sleep(0.03)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
                time.sleep(0.05)
        elif action == "right_click":
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, target_x, target_y, 0, 0)
            time.sleep(0.03)
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, target_x, target_y, 0, 0)
        time.sleep(0.04)
    finally:
        restore_system_cursor()

def run_ghost_cursor_overlay(target_x: int, target_y: int, label: str = "", start_x: int = None, start_y: int = None, duration: float = 60.0, glide_time: float = 0.45):
    """Ghost cursor overlay with starlight ring and label badge. Window starts HIDDEN to eliminate any black flash."""
    attach_desktop()
    import pygame
    pygame.init()
    pygame.font.init()

    win_size = 200
    screen = pygame.display.set_mode((win_size, win_size), pygame.NOFRAME | pygame.HIDDEN)
    hwnd = pygame.display.get_wm_info()["window"]

    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    ex_style |= (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*COLORKEY), 0, win32con.LWA_COLORKEY)
    screen.fill(COLORKEY)
    pygame.display.flip()

    cursor_surf = None
    if os.path.exists(CURSOR_PNG):
        raw_img = pygame.image.load(CURSOR_PNG).convert_alpha()
        cursor_surf = pygame.transform.smoothscale(raw_img, (SYS_CURSOR_W, SYS_CURSOR_H))

    font_badge = pygame.font.SysFont("segoeui", 12, bold=True)
    clock = pygame.time.Clock()

    screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN) if win32api else 1920
    screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN) if win32api else 1080

    if start_x is None or start_y is None:
        start_x = screen_w - 240
        start_y = screen_h - 220

    start_time = time.time()
    tip_offset_x = 24
    tip_offset_y = 24
    running = True

    try:
        while running:
            clock.tick(60)
            elapsed = time.time() - start_time

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break

            if elapsed > 1.5:
                if win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000 or win32api.GetAsyncKeyState(win32con.VK_ESCAPE) & 0x8000:
                    running = False
                    break
                if elapsed > (glide_time + duration):
                    running = False
                    break

            if elapsed < glide_time:
                t = elapsed / glide_time
                ease = t * t * (3.0 - 2.0 * t)
                cur_x = int(start_x + (target_x - start_x) * ease)
                cur_y = int(start_y + (target_y - start_y) * ease)
            else:
                cur_x = target_x
                cur_y = target_y

            wx = int(cur_x - tip_offset_x)
            wy = int(cur_y - tip_offset_y)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, wx, wy, win_size, win_size, win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)

            screen.fill(COLORKEY)

            if elapsed >= glide_time:
                pulse_t = elapsed - glide_time
                ring_r = 13 + math.sin(pulse_t * 5.0) * 3.5
                pygame.draw.circle(screen, (244, 114, 182), (tip_offset_x, tip_offset_y), int(ring_r), width=2)
                pygame.draw.circle(screen, (56, 189, 248), (tip_offset_x, tip_offset_y), int(ring_r + 5), width=1)
                for ang in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
                    sp_x = tip_offset_x + math.cos(ang + pulse_t * 2.0) * (ring_r + 8)
                    sp_y = tip_offset_y + math.sin(ang + pulse_t * 2.0) * (ring_r + 8)
                    pygame.draw.circle(screen, (255, 255, 255), (int(sp_x), int(sp_y)), 2)

            if cursor_surf:
                screen.blit(cursor_surf, (tip_offset_x, tip_offset_y))

            if label and elapsed >= glide_time:
                badge_txt = font_badge.render(f"\u2736 {label}", True, (255, 255, 255))
                bw, bh = badge_txt.get_width() + 14, 22
                bx, by = tip_offset_x + 24, tip_offset_y + 8
                badge_rect = pygame.Rect(bx, by, bw, bh)
                pygame.draw.rect(screen, (24, 24, 37), badge_rect, border_radius=6)
                pygame.draw.rect(screen, (168, 85, 247), badge_rect, width=1, border_radius=6)
                screen.blit(badge_txt, (bx + 7, by + 3))

            pygame.display.update()
    finally:
        pygame.quit()

def run_custom_cursor_overlay(target_x: int, target_y: int, mode: str = "hardware", action: str = "click", label: str = "", start_x: int = None, start_y: int = None, duration: float = 60.0, glide_time: float = 0.45):
    """Unified Twilight cursor entry point: hardware uses pure Win32; ghost uses transparent pygame overlay."""
    if mode == "hardware":
        glide_hardware_cursor(target_x, target_y, action=action, glide_time=glide_time, start_x=start_x, start_y=start_y)
    else:
        run_ghost_cursor_overlay(target_x, target_y, label=label, start_x=start_x, start_y=start_y, duration=duration, glide_time=glide_time)

def find_spotify_green_play_button(spotify_hwnd):
    """Detect circular green play button on Spotify via fast pixel clustering in <8ms."""
    if not spotify_hwnd or not win32gui:
        return None
    try:
        from PIL import ImageGrab
        import numpy as np
        from scipy.ndimage import label, center_of_mass
        r = win32gui.GetWindowRect(spotify_hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]
        if w < 200 or h < 200:
            return None
        img = ImageGrab.grab(bbox=(r[0], r[1], r[2], r[3])).convert("RGB")
        arr = np.array(img)
        # Spotify signature green: R < 60, G > 180, B < 120
        mask = (arr[:, :, 0] < 60) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 120)
        lbl, num = label(mask)
        best_center = None
        best_area = 0
        for i in range(1, num + 1):
            area = np.sum(lbl == i)
            # Filter out bottom player checkmarks (keep upper 85%)
            if area > 100 and area > best_area:
                cy, cx = center_of_mass(lbl == i)
                if cy < h * 0.85:
                    best_area = area
                    best_center = (r[0] + int(cx), r[1] + int(cy))
        return best_center
    except Exception as e:
        print(f"[Cursor] find_spotify_green_play_button: {e}")
        return None

def play_spotify_playlist_with_cursor(playlist_name: str = ""):
    """Smart visual automation for Spotify playlists: selects sidebar playlist or searches, then clicks the big green play button."""
    attach_desktop()
    if not win32gui or not win32api:
        return False
    spotify_hwnd = get_spotify_window()
    if not spotify_hwnd:
        os.system("start spotify:")
        for _ in range(50):
            time.sleep(0.2)
            sp = get_spotify_window()
            if sp:
                spotify_hwnd = sp
                break
        time.sleep(1.5)
    if not spotify_hwnd:
        return False

    try:
        force_foreground_window(spotify_hwnd)
        wait_for_spotify_ui_ready(spotify_hwnd, timeout=4.0)
        time.sleep(0.15)
        r = win32gui.GetWindowRect(spotify_hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]

        clean = (playlist_name or "").strip()
        clean = re.sub(r'^(?:play|open|put on)\s+(?:up\s+)?(?:spotify\s+and\s+)?(?:some\s+)?', '', clean, flags=re.IGNORECASE).strip()
        is_my_library = (not clean) or any(k in clean.lower() for k in ("one of my playlist", "my playlist", "one of my", "mine", "library", "saved playlist", "random"))

        if is_my_library:
            # 1. Click user's saved playlist on the left sidebar
            pl_x = r[0] + 48
            pl_y = r[1] + 240
            glide_hardware_cursor(pl_x, pl_y, action="click", glide_time=0.35)
            time.sleep(0.35)
        else:
            # 2. Check if already on the playlist page
            t_win = (win32gui.GetWindowText(spotify_hwnd) or "").lower()
            if clean.lower() in t_win:
                pass
            else:
                # Glide to search bar and search playlist
                sx = r[0] + int(w * 0.44)
                sy = r[1] + 36
                glide_hardware_cursor(sx, sy, action="click", glide_time=0.32)
                time.sleep(0.04)
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('A'), 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.03)
                type_text(f"{clean} playlist")
                time.sleep(0.04)
                win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.40)
                # Click the playlist result card
                card_x = r[0] + int(w * 0.32)
                card_y = r[1] + 280
                glide_hardware_cursor(card_x, card_y, action="click", glide_time=0.32)
                time.sleep(0.35)

        # 3. Detect and click the big circular play button on the playlist header
        green_btn = find_spotify_green_play_button(spotify_hwnd)
        if green_btn:
            gx, gy = green_btn
            glide_hardware_cursor(gx, gy, action="click", glide_time=0.35)
        else:
            try:
                from assistant_tools import ground_screen_element
                px, py, _, _ = ground_screen_element("Spotify big circular play button on playlist header", "spotify")
                if px is not None and py is not None:
                    glide_hardware_cursor(px, py, action="click", glide_time=0.35)
                else:
                    fallback_gx = r[0] + 145
                    fallback_gy = r[1] + 330
                    glide_hardware_cursor(fallback_gx, fallback_gy, action="click", glide_time=0.35)
            except Exception:
                fallback_gx = r[0] + 145
                fallback_gy = r[1] + 330
                glide_hardware_cursor(fallback_gx, fallback_gy, action="click", glide_time=0.35)

        time.sleep(0.05)
        win32api.keybd_event(win32con.VK_SPACE, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(win32con.VK_SPACE, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[Cursor] play_spotify_playlist_with_cursor error: {e}")
        return False

def search_and_play_spotify(query: str, search_x: int = None, search_y: int = None):
    """Dynamic automation: activate Spotify, search query, scour tracks visually, and click play."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    spotify_hwnd = get_spotify_window()
    if not spotify_hwnd:
        os.system("start spotify:")
        for _ in range(50):
            time.sleep(0.2)
            sp = get_spotify_window()
            if sp:
                spotify_hwnd = sp
                break
        time.sleep(1.5)

    if not spotify_hwnd:
        return False

    try:
        force_foreground_window(spotify_hwnd)
        wait_for_spotify_ui_ready(spotify_hwnd, timeout=4.0)
        time.sleep(0.15)
        r = win32gui.GetWindowRect(spotify_hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]

        clean_query = (query or "").strip()
        clean_query = re.sub(r'^(?:play|open|put on)\s+(?:up\s+)?(?:spotify\s+and\s+)?(?:some\s+)?', '', clean_query, flags=re.IGNORECASE).strip()
        clean_query = re.sub(r'^(?:any|some)\s+', '', clean_query, flags=re.IGNORECASE)
        clean_query = re.sub(r'\s+songs?$', '', clean_query, flags=re.IGNORECASE).strip()

        is_my_library = (not clean_query) or any(k in clean_query.lower() for k in ("one of my playlist", "my playlist", "one of my", "mine", "library", "saved playlist"))
        if is_my_library:
            return play_spotify_playlist_with_cursor("")

        sx = search_x if (search_x is not None) else (r[0] + int(w * 0.44))
        sy = search_y if (search_y is not None) else (r[1] + 36)

        glide_hardware_cursor(sx, sy, action="click", glide_time=0.32)
        time.sleep(0.04)

        # Clear & type
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord('A'), 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)

        type_text(clean_query)
        time.sleep(0.04)
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.35)

        # Try visual detection for the top search result track or play button
        target_pos = None
        try:
            from assistant_tools import ground_screen_element
            tx, ty, _, _ = ground_screen_element(f"Spotify top song result or play button for '{clean_query}'", "spotify")
            if tx is not None and ty is not None:
                target_pos = (tx, ty)
        except Exception:
            pass

        if target_pos:
            glide_hardware_cursor(target_pos[0], target_pos[1], action="click", glide_time=0.28)
            time.sleep(0.05)
        else:
            # Scour through the songs list visually
            track_col_x = r[0] + int(w * 0.58)
            row1_y = r[1] + 215
            row2_y = r[1] + 270

            glide_hardware_cursor(track_col_x, row1_y, action="none", glide_time=0.20)
            time.sleep(0.08)
            glide_hardware_cursor(track_col_x, row2_y, action="none", glide_time=0.18)
            time.sleep(0.08)

            # Check for visible green play button revealed by hover
            green_btn = find_spotify_green_play_button(spotify_hwnd)
            if green_btn:
                gx, gy = green_btn
                glide_hardware_cursor(gx, gy, action="click", glide_time=0.25)
            else:
                glide_hardware_cursor(track_col_x, row1_y, action="double_click", glide_time=0.25)
                time.sleep(0.04)
                win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

        # Background Spotify CLI sync if available
        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        if os.path.exists(cli) and clean_query:
            try:
                import subprocess
                res = subprocess.run([cli, "search", clean_query, "--type", "track", "--limit", "1"], capture_output=True, text=True, encoding="utf-8", timeout=1.8)
                m = re.search(r'(spotify:track:[a-zA-Z0-9]+)', res.stdout)
                if m:
                    subprocess.run([cli, "play", m.group(1)], capture_output=True, text=True, encoding="utf-8", timeout=1.5)
            except Exception:
                pass

        return True
    except Exception as e:
        print(f"[Cursor] Spotify visual automation error: {e}")
        return False

def control_media_with_cursor(action: str = "pause", target_x: int = None, target_y: int = None):
    """Dynamic media control: glide Twilight's cursor directly to Spotify's playback control button and click."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    act_lower = action.strip().lower()
    spotify_hwnd = get_spotify_window()
    if not spotify_hwnd and act_lower in ("play", "resume"):
        os.system("start spotify:")
        for _ in range(40):
            time.sleep(0.2)
            sp = get_spotify_window()
            if sp:
                spotify_hwnd = sp
                break
        time.sleep(1.5)

    btn_map = {
        "shuffle": 0.42,
        "previous": 0.465,
        "prev": 0.465,
        "back": 0.465,
        "rewind": 0.465,
        "play": 0.501,
        "pause": 0.501,
        "resume": 0.501,
        "stop": 0.501,
        "unpause": 0.501,
        "next": 0.537,
        "skip": 0.537,
        "repeat": 0.58,
        "lyrics": 0.73,
        "open lyrics": 0.73,
        "queue": 0.76,
    }

    if spotify_hwnd:
        try:
            force_foreground_window(spotify_hwnd)
            time.sleep(0.12)
            r = win32gui.GetWindowRect(spotify_hwnd)
            w = r[2] - r[0]

            btn_pos = None
            try:
                from assistant_tools import ground_screen_element
                bx, by, _, _ = ground_screen_element(f"Spotify bottom bar {act_lower} button", "spotify")
                if bx is not None and by is not None:
                    btn_pos = (bx, by)
            except Exception:
                pass

            ratio = btn_map.get(act_lower, 0.501)
            px = target_x if (target_x is not None) else (btn_pos[0] if btn_pos else (r[0] + int(w * ratio)))
            py = target_y if (target_y is not None) else (btn_pos[1] if btn_pos else (r[3] - 65))

            # Visually glide to control button
            glide_hardware_cursor(px, py, action="click", glide_time=0.30)
            time.sleep(0.04)

            # Spotify native shortcuts beat pixel guessing across responsive desktop UI
            if act_lower in ("pause", "stop", "play", "resume", "unpause"):
                win32api.keybd_event(win32con.VK_SPACE, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_SPACE, 0, win32con.KEYEVENTF_KEYUP, 0)
            elif act_lower in ("next", "skip"):
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(win32con.VK_RIGHT, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_RIGHT, 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            elif act_lower in ("previous", "prev", "back"):
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(win32con.VK_LEFT, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_LEFT, 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            elif "volume_up" in act_lower or "louder" in act_lower:
                for _ in range(3):
                    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                    win32api.keybd_event(win32con.VK_UP, 0, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(win32con.VK_UP, 0, win32con.KEYEVENTF_KEYUP, 0)
                    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            elif "volume_down" in act_lower or "quieter" in act_lower:
                for _ in range(3):
                    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                    win32api.keybd_event(win32con.VK_DOWN, 0, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(win32con.VK_DOWN, 0, win32con.KEYEVENTF_KEYUP, 0)
                    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            elif "shuffle" in act_lower:
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('S'), 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('S'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"[Cursor] Media control click error: {e}")

    # Fallback media keys
    if act_lower in ("pause", "stop", "resume", "play", "unpause"):
        win32api.keybd_event(win32con.VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MEDIA_PLAY_PAUSE, 0, 2, 0)
    elif act_lower in ("next", "skip"):
        win32api.keybd_event(win32con.VK_MEDIA_NEXT_TRACK, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MEDIA_NEXT_TRACK, 0, 2, 0)
    elif act_lower in ("previous", "prev", "back", "rewind"):
        win32api.keybd_event(win32con.VK_MEDIA_PREV_TRACK, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MEDIA_PREV_TRACK, 0, 2, 0)
    return True

def scroll_spotify_playlist(direction: str = "down", amount: int = 400):
    """Smoothly scroll through Spotify playlist tracks or search results."""
    attach_desktop()
    if not win32gui or not win32api:
        return False
    sp = get_spotify_window()
    if sp:
        try:
            force_foreground_window(sp)
            time.sleep(0.08)
            r = win32gui.GetWindowRect(sp)
            w = r[2] - r[0]
            h = r[3] - r[1]
            cx = r[0] + int(w * 0.60)
            cy = r[1] + int(h * 0.50)
            glide_hardware_cursor(cx, cy, action="none", glide_time=0.20)
            time.sleep(0.04)

            d_lower = direction.strip().lower()
            is_down = any(k in d_lower for k in ("down", "next", "bottom"))
            clicks = max(1, min(12, int(amount) // 100)) if amount else 4
            notch = -120 if is_down else 120

            for _ in range(clicks):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, cx, cy, notch, 0)
                time.sleep(0.035)
            return True
        except Exception as e:
            print(f"[Cursor] scroll_spotify_playlist error: {e}")
    return False

def is_terminal_or_overlay_hwnd(h):
    if not h or not win32gui:
        return False
    try:
        if win32process and psutil:
            _, pid = win32process.GetWindowThreadProcessId(h)
            pname = psutil.Process(pid).name().lower()
            if any(x in pname for x in ("python", "windowsterminal", "cmd", "powershell", "pwsh")):
                return True
    except Exception:
        pass
    return False

def find_active_browser_tab_close_button(hwnd):
    """Find the exact screen coordinates (x, y) of the active tab's 'x' close button via visual inspection."""
    try:
        from PIL import ImageGrab
        from google import genai
        from google.genai import types
        from config import Config
        cfg = Config.load()
        if not cfg.api_key:
            return None, None
        client = genai.Client(api_key=cfg.api_key)
        r = win32gui.GetWindowRect(hwnd)
        t = (win32gui.GetWindowText(hwnd) or "").strip()
        img = ImageGrab.grab(r)
        strip = img.crop((0, 0, r[2] - r[0], min(80, r[3] - r[1])))
        buf = io.BytesIO()
        strip.save(buf, format="JPEG", quality=80)
        strip_b = buf.getvalue()

        prompt = (
            f"This is the top tab strip of the browser window. The active/current tab has title: '{t}'. "
            "Locate the active tab (the highlighted/light tab), and identify the exact (x, y) coordinates of its close button (the small 'x' icon on that tab). "
            "Return ONLY JSON: {\"found\": true, \"x\": <int pixel_x_in_image>, \"y\": <int pixel_y_in_image>}"
        )
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[types.Part.from_bytes(data=strip_b, mime_type="image/jpeg"), types.Part.from_text(text=prompt)],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        if resp and resp.text:
            raw = resp.text.strip()
            if raw.startswith("```"):
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
            d = json.loads(raw)
            if isinstance(d, list) and d:
                d = d[0]
            if d.get("found", True) and "x" in d and "y" in d:
                px = r[0] + int(d["x"])
                py = r[1] + int(d["y"])
                return px, py
    except Exception as e:
        print(f"[Cursor] find_active_browser_tab_close_button note: {e}")
    return None, None

def close_active_browser_tab(target_x: int = None, target_y: int = None):
    """Visually glide Twilight's cursor to the active tab's close button and click it to close."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    fg = win32gui.GetForegroundWindow()
    if not fg or is_terminal_or_overlay_hwnd(fg) or win32gui.GetWindowRect(fg)[0] <= -10000:
        fg = get_browser_window()

    if fg:
        try:
            force_foreground_window(fg)
            time.sleep(0.08)
            r = win32gui.GetWindowRect(fg)
            w = r[2] - r[0]
            h = r[3] - r[1]

            tab_x, tab_y = target_x, target_y
            if tab_x is None or tab_y is None:
                bx, by = find_active_browser_tab_close_button(fg)
                if bx is not None and by is not None:
                    tab_x, tab_y = bx, by
                else:
                    tab_x = r[0] + min(w - 150, max(200, int(w * 0.25)))
                    tab_y = r[1] + 20

            # 1. Visually glide Twilight's cursor right onto the active tab close button with click!
            glide_hardware_cursor(tab_x, tab_y, action="click", glide_time=0.30)
            time.sleep(0.05)

            # 2. Re-assert foreground and dispatch Ctrl+W safety guarantee in case click was slightly off
            force_foreground_window(fg)
            time.sleep(0.03)
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('W'), 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(ord('W'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"[Cursor] close_active_browser_tab error: {e}")
            return False
    return False

def open_new_browser_tab(url: str = ""):
    """Visually glide Twilight's cursor to the tab strip '+' button and cleanly open with Ctrl+T."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    fg = win32gui.GetForegroundWindow()
    if not fg or is_terminal_or_overlay_hwnd(fg) or win32gui.GetWindowRect(fg)[0] <= -10000:
        fg = get_browser_window()

    if not fg:
        return navigate_browser_with_cursor(url or "https://www.google.com")

    try:
        force_foreground_window(fg)
        time.sleep(0.08)
        r = win32gui.GetWindowRect(fg)
        w = r[2] - r[0]

        tab_x = r[0] + min(w - 120, max(260, int(w * 0.35)))
        tab_y = r[1] + 20
        glide_hardware_cursor(tab_x, tab_y, action="none", glide_time=0.25)
        time.sleep(0.04)

        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord('T'), 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(ord('T'), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.25)

        clean = (url or "").strip()
        if clean:
            if clean.startswith("http://") or clean.startswith("https://") or (("." in clean) and (" " not in clean)):
                target_url = clean if clean.startswith("http") else f"https://{clean}"
            else:
                import urllib.parse
                target_url = f"https://www.google.com/search?q={urllib.parse.quote(clean)}"
            navigate_browser_with_cursor(target_url)
        return True
    except Exception as e:
        print(f"[Cursor] open_new_browser_tab error: {e}")
        return False

def switch_browser_tab(direction: str = "next"):
    """Switch browser tab: previous (browser history back) or next (Ctrl+Tab)."""
    d_lower = (direction or "").strip().lower()
    if any(k in d_lower for k in ("prev", "previous", "back", "prior", "last")):
        return browser_navigate_history("back")
    attach_desktop()
    if not win32gui or not win32api:
        return False
    fg = win32gui.GetForegroundWindow()
    if not fg or is_terminal_or_overlay_hwnd(fg) or win32gui.GetWindowRect(fg)[0] <= -10000:
        fg = get_browser_window()
    if not fg:
        return False
    try:
        force_foreground_window(fg)
        time.sleep(0.08)
        r = win32gui.GetWindowRect(fg)
        w = r[2] - r[0]

        tab_y = r[1] + 20
        tab_x = r[0] + min(w - 150, max(200, int(w * 0.3)))
        glide_hardware_cursor(tab_x, tab_y, action="none", glide_time=0.20)
        time.sleep(0.04)

        d_lower = direction.strip().lower()
        is_prev = any(k in d_lower for k in ("prev", "previous", "left", "back", "last", "prior"))

        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        if is_prev:
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
        win32api.keybd_event(win32con.VK_TAB, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(win32con.VK_TAB, 0, win32con.KEYEVENTF_KEYUP, 0)
        if is_prev:
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[Cursor] switch_browser_tab error: {e}")
        return False

def browser_navigate_history(direction: str = "back"):
    """Navigate browser history: back (Alt+Left) or forward (Alt+Right)."""
    attach_desktop()
    if not win32gui or not win32api:
        return False
    fg = win32gui.GetForegroundWindow()
    if not fg or is_terminal_or_overlay_hwnd(fg) or win32gui.GetWindowRect(fg)[0] <= -10000:
        fg = get_browser_window()
    if not fg:
        return False
    try:
        force_foreground_window(fg)
        time.sleep(0.08)
        r = win32gui.GetWindowRect(fg)
        d_lower = direction.strip().lower()
        is_forward = any(k in d_lower for k in ("forward", "next", "right"))

        # Visually glide to the browser's Back (<-) or Forward (->) button
        btn_x = r[0] + (48 if is_forward else 24)
        btn_y = r[1] + 62
        glide_hardware_cursor(btn_x, btn_y, action="none", glide_time=0.20)
        time.sleep(0.04)

        vk_key = win32con.VK_RIGHT if is_forward else win32con.VK_LEFT

        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0) # Alt
        win32api.keybd_event(vk_key, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(vk_key, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[Cursor] browser_navigate_history error: {e}")
        return False

def switch_to_tab_or_window(target: str):
    """Switch to a specific window or Chrome/Edge tab matching target keywords."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    clean = (target or "").strip().lower()
    clean = re.sub(r'^(?:to\s+|our\s+|the\s+)+', '', clean)
    clean = re.sub(r'\s+(?:tab|window|stream|page)$', '', clean).strip()
    words = [w for w in re.split(r'[\s\-_]+', clean) if len(w) > 1 and w not in ("our", "the", "back", "to", "in", "on", "a", "of")]

    # 1. Search top-level visible windows for matching title
    hwnds = []
    def enum_cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = (win32gui.GetWindowText(h) or "").lower()
            if t and not is_terminal_or_overlay_hwnd(h):
                score = sum(1 for w in words if w in t)
                if score > 0:
                    hwnds.append((h, score, t))
        return True
    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    if hwnds:
        hwnds.sort(key=lambda x: x[1], reverse=True)
        best_hwnd = hwnds[0][0]
        force_foreground_window(best_hwnd)
        return True

    # 2. Search Chrome/Edge tabs via Ctrl+Shift+A
    browser_hwnd = get_browser_window()
    if browser_hwnd:
        try:
            force_foreground_window(browser_hwnd)
            time.sleep(0.08)
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            win32api.keybd_event(ord('A'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.20)

            search_query = " ".join(words[:2]) if words else clean
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(search_query, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()

            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.18)

            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"[Cursor] switch_to_tab_or_window tab search error: {e}")

    return False

def control_youtube_video_with_cursor(action: str = "pause", value: int = None):
    """Control YouTube and video platform playback: pause, play, volume, subtitles, fullscreen, skip_ad."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    act_lower = action.strip().lower()

    # 1. Locate YouTube or active video window
    yt_hwnd = None
    hwnds = []
    def enum_cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = (win32gui.GetWindowText(h) or "").lower()
            if any(k in t for k in ("youtube", "twitch", "netflix", "stremio", "vlc")) and not is_terminal_or_overlay_hwnd(h):
                hwnds.append(h)
        return True
    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    if hwnds:
        yt_hwnd = hwnds[0]
    else:
        yt_hwnd = get_browser_window()

    if not yt_hwnd:
        return False

    try:
        force_foreground_window(yt_hwnd)
        time.sleep(0.08)
        r = win32gui.GetWindowRect(yt_hwnd)
        w = r[2] - r[0]
        h = r[3] - r[1]

        # Visually glide to video player center
        vid_x = r[0] + w // 2
        vid_y = r[1] + int(h * 0.45)
        glide_hardware_cursor(vid_x, vid_y, action="none", glide_time=0.20)
        time.sleep(0.04)

        # Check for exact percentage volume
        target_pct = None
        if value is not None:
            target_pct = max(0, min(100, int(value)))
        else:
            m_pct = re.search(r'(\d+)\s*%', act_lower)
            if m_pct:
                target_pct = max(0, min(100, int(m_pct.group(1))))

        if target_pct is not None or "set_volume" in act_lower:
            pct = target_pct if target_pct is not None else 50
            glide_hardware_cursor(vid_x, vid_y, action="none", glide_time=0.15)
            time.sleep(0.04)
            # Mouse wheel over video player controls player volume natively with zero page scrolling!
            for _ in range(20):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, vid_x, vid_y, -120, 0)
                time.sleep(0.015)
            steps = pct // 5
            for _ in range(steps):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, vid_x, vid_y, 120, 0)
                time.sleep(0.015)
            return True

        if act_lower in ("pause", "stop", "play", "resume", "unpause", "toggle_pause"):
            win32api.keybd_event(ord('K'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('K'), 0, win32con.KEYEVENTF_KEYUP, 0)
        elif act_lower in ("volume_up", "louder", "up", "raise_volume"):
            glide_hardware_cursor(vid_x, vid_y, action="none", glide_time=0.15)
            for _ in range(3):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, vid_x, vid_y, 120, 0)
                time.sleep(0.02)
        elif act_lower in ("volume_down", "quieter", "down", "lower_volume"):
            glide_hardware_cursor(vid_x, vid_y, action="none", glide_time=0.15)
            for _ in range(3):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, vid_x, vid_y, -120, 0)
                time.sleep(0.02)
        elif act_lower in ("mute", "unmute"):
            win32api.keybd_event(ord('M'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('M'), 0, win32con.KEYEVENTF_KEYUP, 0)
        elif act_lower in ("subtitles", "cc", "captions"):
            win32api.keybd_event(ord('C'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('C'), 0, win32con.KEYEVENTF_KEYUP, 0)
        elif act_lower in ("fullscreen", "full_screen", "toggle_fullscreen"):
            win32api.keybd_event(ord('F'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
        elif act_lower in ("skip_ad", "skip_ads", "skip ad"):
            skip_pos = None
            try:
                from assistant_tools import ground_screen_element
                sx, sy, _, _ = ground_screen_element("Skip ad or Skip button on YouTube video player")
                if sx is not None and sy is not None:
                    skip_pos = (sx, sy)
            except Exception:
                pass

            if not skip_pos:
                player_w = int(w * 0.68)
                player_h = int(h * 0.70)
                skip_x = r[0] + int(player_w * 0.88)
                skip_y = r[1] + int(player_h * 0.85)
                skip_pos = (skip_x, skip_y)

            glide_hardware_cursor(skip_pos[0], skip_pos[1], action="click", glide_time=0.30)
            time.sleep(0.05)
        return True
    except Exception as e:
        print(f"[Cursor] control_video_player error: {e}")
        return False

control_video_player_with_cursor = control_youtube_video_with_cursor

def open_program_with_cursor(program_name: str):
    """Visually open a program: glide cursor to Windows Start, click/search, type program, and press Enter."""
    attach_desktop()
    if not win32api or not win32gui:
        return False
    try:
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        # Glide to Start button (bottom left)
        glide_hardware_cursor(24, screen_h - 24, action="click", glide_time=0.30)
        time.sleep(0.05)
        # Send Windows key to ensure Search menu opens
        win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.25)
        type_text(program_name)
        time.sleep(0.30)
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        time.sleep(0.02)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"[Cursor] open_program_with_cursor error: {e}")
        return False

def close_window_with_cursor():
    """Visually close the active foreground window by gliding to the top-right X button."""
    attach_desktop()
    if not win32gui or not win32api:
        return False
    fg = win32gui.GetForegroundWindow()
    if fg:
        try:
            r = win32gui.GetWindowRect(fg)
            close_x = r[2] - 22
            close_y = r[1] + 16
            glide_hardware_cursor(close_x, close_y, action="click", glide_time=0.30)
            return True
        except Exception as e:
            print(f"[Cursor] close_window_with_cursor error: {e}")
    return False

def type_in_document_with_cursor(text: str):
    """Visually click into the active editor/document canvas and type out text."""
    attach_desktop()
    if not win32gui or not win32api:
        return False
    fg = win32gui.GetForegroundWindow()
    if fg:
        try:
            force_foreground_window(fg)
            r = win32gui.GetWindowRect(fg)
            w = r[2] - r[0]
            h = r[3] - r[1]
            cx = r[0] + int(w * 0.5)
            cy = r[1] + int(h * 0.5)
            glide_hardware_cursor(cx, cy, action="click", glide_time=0.30)
            time.sleep(0.1)
            type_text(text)
            return True
        except Exception as e:
            print(f"[Cursor] type_in_document_with_cursor error: {e}")
    return False

def _get_audio_endpoint_volume():
    """Obtain Windows Core Audio IAudioEndpointVolume interface via comtypes."""
    try:
        import comtypes.client
        from comtypes import GUID, IUnknown, COMMETHOD, HRESULT, CLSCTX_ALL
        from ctypes import c_float, POINTER, c_int, c_uint, byref

        class IAudioEndpointVolume(IUnknown):
            _iid_ = GUID('{5CDF2C82-841E-4546-9722-0CF74078229A}')
            _methods_ = [
                COMMETHOD([], HRESULT, 'RegisterControlChangeNotify'),
                COMMETHOD([], HRESULT, 'UnregisterControlChangeNotify'),
                COMMETHOD([], HRESULT, 'GetChannelCount'),
                COMMETHOD([], HRESULT, 'SetMasterVolumeLevel'),
                COMMETHOD([], HRESULT, 'SetMasterVolumeLevelScalar',
                          (['in'], c_float, 'fLevel'),
                          (['in'], POINTER(GUID), 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'GetMasterVolumeLevel'),
                COMMETHOD([], HRESULT, 'GetMasterVolumeLevelScalar',
                          (['out'], POINTER(c_float), 'pfLevel')),
                COMMETHOD([], HRESULT, 'SetChannelVolumeLevel'),
                COMMETHOD([], HRESULT, 'SetChannelVolumeLevelScalar'),
                COMMETHOD([], HRESULT, 'GetChannelVolumeLevel'),
                COMMETHOD([], HRESULT, 'GetChannelVolumeLevelScalar'),
                COMMETHOD([], HRESULT, 'SetMute',
                          (['in'], c_int, 'bMute'),
                          (['in'], POINTER(GUID), 'pguidEventContext')),
                COMMETHOD([], HRESULT, 'GetMute',
                          (['out'], POINTER(c_int), 'pbMute')),
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
        endpoint = enumerator.GetDefaultAudioEndpoint(0, 1) # eRender, eMultimedia
        volume_iface = endpoint.Activate(byref(IAudioEndpointVolume._iid_), CLSCTX_ALL, None)
        return volume_iface.QueryInterface(IAudioEndpointVolume)
    except Exception as e:
        print(f"[Cursor] Core Audio COM error: {e}")
        return None

def get_master_volume_scalar() -> float:
    """Return current Windows master volume as a float between 0.0 and 1.0."""
    vol = _get_audio_endpoint_volume()
    if vol:
        try:
            return float(vol.GetMasterVolumeLevelScalar())
        except Exception:
            pass
    return 0.50

def set_master_volume_scalar(scalar: float) -> bool:
    """Set Windows master volume to an exact scalar between 0.0 and 1.0 (0% - 100%)."""
    val = max(0.0, min(1.0, float(scalar)))
    vol = _get_audio_endpoint_volume()
    if vol:
        try:
            vol.SetMasterVolumeLevelScalar(val, None)
            return True
        except Exception as e:
            print(f"[Cursor] set_master_volume_scalar error: {e}")
    return False

def set_master_volume_mute(mute: bool) -> bool:
    """Mute (True) or unmute (False) Windows master audio."""
    vol = _get_audio_endpoint_volume()
    if vol:
        try:
            vol.SetMute(1 if mute else 0, None)
            return True
        except Exception as e:
            print(f"[Cursor] set_master_volume_mute error: {e}")
    return False

def adjust_volume_with_cursor(action: str = "up", percentage: int = None):
    """Glide to Windows taskbar volume area and adjust system volume with exact percentage precision."""
    attach_desktop()
    try:
        if win32api:
            screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            glide_hardware_cursor(screen_w - 90, screen_h - 24, action="none", glide_time=0.25)
    except Exception:
        pass

    # 1. Exact percentage requested
    if percentage is not None:
        scalar = max(0.0, min(1.0, float(percentage) / 100.0))
        return set_master_volume_scalar(scalar)

    act = (action or "").strip().lower()
    m_pct = re.search(r'(\d+)\s*%', act)
    if m_pct:
        scalar = float(m_pct.group(1)) / 100.0
        return set_master_volume_scalar(scalar)

    if "unmute" in act:
        return set_master_volume_mute(False)
    elif "mute" in act:
        return set_master_volume_mute(True)

    # 2. Relative change based on live Core Audio volume
    cur = get_master_volume_scalar()
    delta = 0.10
    m_diff = re.search(r'(\d+)', act)
    if m_diff:
        delta = float(m_diff.group(1)) / 100.0

    if any(k in act for k in ("down", "lower", "quieter", "decrease", "less")):
        new_vol = max(0.0, cur - delta)
    else:
        new_vol = min(1.0, cur + delta)

    return set_master_volume_scalar(new_vol)

def scroll_page_with_cursor(direction: str = "down", amount: int = 400, center_text: str = ""):
    """Smoothly scroll active window or browser, optionally centering a matching section or text."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    fg = win32gui.GetForegroundWindow()
    if not fg or is_terminal_or_overlay_hwnd(fg) or win32gui.GetWindowRect(fg)[0] <= -10000:
        fg = get_browser_window()

    if not fg:
        return False

    try:
        force_foreground_window(fg)
        time.sleep(0.05)
        r = win32gui.GetWindowRect(fg)
        w = r[2] - r[0]
        h = r[3] - r[1]

        # In-page find centering
        if center_text and len(center_text.strip()) > 1:
            clean_search = center_text.strip()[:60]
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(clean_search, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()

                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('F'), 0, 0, 0)
                time.sleep(0.03)
                win32api.keybd_event(ord('F'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.08)

                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('V'), 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.10)

                win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.08)

                win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
                return True
            except Exception as fe:
                print(f"[Cursor] Center text scroll error: {fe}")

        # Smooth mouse wheel scroll
        cx = r[0] + w // 2
        cy = r[1] + h // 2
        glide_hardware_cursor(cx, cy, action="none", glide_time=0.20)
        time.sleep(0.04)

        d_lower = direction.strip().lower()
        is_down = any(k in d_lower for k in ("down", "bottom", "next", "lower"))

        clicks = max(1, min(12, int(amount) // 100)) if amount else 4
        notch = -120 if is_down else 120

        for _ in range(clicks):
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, cx, cy, notch, 0)
            time.sleep(0.035)

        return True
    except Exception as e:
        print(f"[Cursor] scroll_page_with_cursor error: {e}")
        return False

def adjust_brightness_with_cursor(level: int = 50):
    """Glide to Quick Settings and adjust Windows screen brightness."""
    attach_desktop()
    if not win32api:
        return False
    try:
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        glide_hardware_cursor(screen_w - 60, screen_h - 24, action="none", glide_time=0.30)
        lvl = max(0, min(100, int(level)))
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {lvl})"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=2.5
        )
        return True
    except Exception as e:
        print(f"[Cursor] adjust_brightness_with_cursor error: {e}")
        return False

def navigate_browser_with_cursor(url: str, is_video: bool = False):
    """Capri-style visual browser navigation: focus browser, glide to address bar, type URL, enter, and engage video."""
    attach_desktop()
    if not win32gui or not win32api:
        return False

    browser_hwnd = get_browser_window()
    if not browser_hwnd:
        chrome_exe = shutil.which("chrome.exe") or os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        if os.path.exists(chrome_exe):
            os.startfile(chrome_exe)
        else:
            os.startfile("https://www.google.com")
        for _ in range(30):
            time.sleep(0.2)
            browser_hwnd = get_browser_window()
            if browser_hwnd:
                break
        time.sleep(1.2)

    if browser_hwnd:
        try:
            force_foreground_window(browser_hwnd)
            time.sleep(0.18)
            r = win32gui.GetWindowRect(browser_hwnd)
            w = r[2] - r[0]
            h = r[3] - r[1]

            # Visual glide to address bar with action="none" to prevent accidental misclick in resized windows
            addr_x = r[0] + min(int(w * 0.40), 300)
            addr_y = r[1] + min(int(h * 0.10), 62)
            glide_hardware_cursor(addr_x, addr_y, action="none", glide_time=0.25)
            time.sleep(0.04)

            # Alt+D is universally supported across Chrome, Edge, Brave, and Firefox to focus omnibox
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(ord('D'), 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(ord('D'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.06)

            # Paste URL via clipboard to completely bypass Chrome omnibox history autocompletion
            pasted = False
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(url, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('V'), 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                pasted = True
            except Exception:
                pass
            if not pasted:
                type_text(url)

            time.sleep(0.04)
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.8)

            if is_video:
                vid_x = r[0] + w // 2
                vid_y = r[1] + int(h * 0.48)
                glide_hardware_cursor(vid_x, vid_y, action="click", glide_time=0.38)
            return True
        except Exception as e:
            print(f"[Cursor] navigate_browser_with_cursor error: {e}")
            return False
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twilight Cursor Assistant")
    parser.add_argument("--ghost", action="store_true", help="Launch Ghost Cursor overlay pointing to a tool")
    parser.add_argument("--click", action="store_true", help="Execute hardware glide and click with custom cursor")
    parser.add_argument("--close-tab", action="store_true", help="Visually glide and close current tab")
    parser.add_argument("--new-tab", type=str, default="", help="Visually glide and open a new tab")
    parser.add_argument("--switch-tab", type=str, default="", help="Switch tab left/previous or right/next")
    parser.add_argument("--browser-history", type=str, default="", help="Navigate history back or forward")
    parser.add_argument("--play-spotify", type=str, default="", help="Visually search and play a song on Spotify")
    parser.add_argument("--play-playlist", type=str, default="", help="Visually select and play a Spotify playlist")
    parser.add_argument("--media-action", type=str, default="", help="Visually click play/pause on Spotify")
    parser.add_argument("--nav-browser", type=str, default="", help="Visually navigate browser to URL")
    parser.add_argument("--scroll", type=str, default="", help="Scroll active window: down or up")
    parser.add_argument("--scroll-amount", type=int, default=400, help="Scroll pixel distance")
    parser.add_argument("--center-text", type=str, default="", help="Center matching text in viewport")
    parser.add_argument("--volume-pct", type=int, default=None, help="Set exact volume percentage 0-100")
    parser.add_argument("--youtube-action", type=str, default="", help="Control YouTube video: pause, play, volume_up, volume_down, mute, subtitles, fullscreen, skip_ad")
    parser.add_argument("--switch-to-tab", type=str, default="", help="Switch to tab or window by search query")
    parser.add_argument("--is-video", action="store_true", help="Flag for video playback engagement")
    parser.add_argument("--x", type=int, default=None, help="Target screen X coordinate")
    parser.add_argument("--y", type=int, default=None, help="Target screen Y coordinate")
    parser.add_argument("--label", type=str, default="", help="Label badge text for tool/button")
    parser.add_argument("--action", type=str, default="click", choices=["click", "double_click", "right_click", "none"])
    parser.add_argument("--duration", type=float, default=60.0, help="Ghost cursor dwell duration in seconds (default: 60s)")

    args = parser.parse_args()

    tx = args.x if args.x is not None else 500
    ty = args.y if args.y is not None else 500

    if args.ghost:
        run_custom_cursor_overlay(tx, ty, mode="ghost", label=args.label, duration=args.duration)
    elif args.click:
        run_custom_cursor_overlay(tx, ty, mode="hardware", action=args.action)
    elif args.close_tab:
        close_active_browser_tab(target_x=args.x, target_y=args.y)
    elif args.new_tab is not None and "--new-tab" in sys.argv:
        open_new_browser_tab(args.new_tab)
    elif args.switch_tab:
        switch_browser_tab(args.switch_tab)
    elif args.browser_history:
        browser_navigate_history(args.browser_history)
    elif args.play_spotify:
        search_and_play_spotify(args.play_spotify, search_x=args.x, search_y=args.y)
    elif args.play_playlist:
        play_spotify_playlist_with_cursor(args.play_playlist)
    elif args.media_action:
        control_media_with_cursor(args.media_action, target_x=args.x, target_y=args.y)
    elif args.youtube_action:
        control_youtube_video_with_cursor(args.youtube_action)
    elif args.scroll:
        scroll_page_with_cursor(args.scroll, amount=args.scroll_amount, center_text=args.center_text)
    elif args.volume_pct is not None:
        adjust_volume_with_cursor(percentage=args.volume_pct)
    elif args.switch_to_tab:
        switch_to_tab_or_window(args.switch_to_tab)
    elif args.nav_browser:
        navigate_browser_with_cursor(args.nav_browser, is_video=args.is_video)
