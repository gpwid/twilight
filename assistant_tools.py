import os
import sys
import subprocess
import io
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import datetime
import shutil
import random
import json
import winreg
from PIL import Image, ImageGrab
import httpx
from bs4 import BeautifulSoup
import html
import difflib

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import psutil
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
except ImportError:
    win32api = None
    win32con = None
    win32gui = None
    win32process = None
    psutil = None
    ctypes = None

def get_current_time() -> str:
    """Get the user's current local date and time."""
    now = datetime.datetime.now()
    return now.strftime("%I:%M %p on %A, %B %d, %Y")

_LAST_APP: str = ""
_LAST_ACTION_TOOL_TIME: float = 0.0
_CURRENT_USER_QUERY: str = ""

def set_current_user_query(q: str):
    global _CURRENT_USER_QUERY
    _CURRENT_USER_QUERY = q or ""

def get_current_user_query() -> str:
    return _CURRENT_USER_QUERY

def mark_action_tool_executed():
    global _LAST_ACTION_TOOL_TIME
    _LAST_ACTION_TOOL_TIME = time.time()

def get_last_action_tool_time() -> float:
    return _LAST_ACTION_TOOL_TIME

def fetch_live_web_search(query: str) -> str:
    """Fetch live news, election returns, current events, and encyclopedic background for any query."""
    clean = query.strip()
    if not clean:
        return ""
    
    findings = []
    headers = {"User-Agent": "SciTwiAssistant/1.0 (contact: admin@clickassistant.local)"}

    # Special handling for "random wikipedia"
    if "random" in clean.lower() and ("wiki" in clean.lower() or "page" in clean.lower() or "article" in clean.lower()):
        try:
            wiki_rand_url = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
            r = httpx.get(wiki_rand_url, headers=headers, timeout=3.5, follow_redirects=True)
            if r.status_code == 200:
                data = r.json()
                t = data.get("title", "")
                ex = data.get("extract", "")
                if t and ex:
                    return f"=== Random Wikipedia Article: {t} ===\n{ex}"
        except Exception as re_err:
            print(f"[Tools] Random wiki fetch note: {re_err}")

    # 1. Live breaking news & current event feeds (Google News RSS & Bing News RSS)
    try:
        gnews_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean)}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(gnews_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            root = ET.fromstring(resp.read())
            news_items = []
            for item in root.findall(".//item")[:5]:
                t = item.find("title").text if item.find("title") is not None else ""
                desc_el = item.find("description")
                desc = ""
                if desc_el is not None and desc_el.text:
                    desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc_el.text)).strip()
                    desc = re.sub(r'\s+', ' ', desc)
                if t:
                    entry = f"- {t}"
                    if desc and desc != t:
                        entry += f": {desc[:250]}"
                    news_items.append(entry)
            if news_items:
                findings.append("=== Live News & Official Reports ===\n" + "\n".join(news_items))
    except Exception as e:
        print(f"[Tools] Google News RSS query note: {e}")

    try:
        bnews_url = f"https://www.bing.com/news/search?q={urllib.parse.quote(clean)}&format=rss"
        req = urllib.request.Request(bnews_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            root = ET.fromstring(resp.read())
            bnews_items = []
            for item in root.findall(".//item")[:3]:
                t = item.find("title").text if item.find("title") is not None else ""
                desc_el = item.find("description")
                desc = ""
                if desc_el is not None and desc_el.text:
                    desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc_el.text)).strip()
                    desc = re.sub(r'\s+', ' ', desc)
                if t:
                    entry = f"- {t}"
                    if desc and desc != t:
                        entry += f": {desc[:250]}"
                    bnews_items.append(entry)
            if bnews_items and not findings:
                findings.append("=== Live News & Reports ===\n" + "\n".join(bnews_items))
    except Exception as e:
        print(f"[Tools] Bing News RSS query note: {e}")

    # 2. Wikipedia API for encyclopedic background, history, science, concepts
    try:
        wiki_params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": clean,
            "gsrlimit": "3",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "format": "json",
            "utf8": "1"
        }
        wiki_resp = httpx.get("https://en.wikipedia.org/w/api.php", params=wiki_params, headers=headers, timeout=3.0)
        if wiki_resp.status_code == 200:
            d = wiki_resp.json()
            pages = d.get("query", {}).get("pages", {})
            if pages:
                wiki_items = []
                sorted_pages = sorted(pages.values(), key=lambda p: p.get("index", 99))
                for p in sorted_pages:
                    w_title = p.get("title", "")
                    w_extract = (p.get("extract") or "").strip()
                    if w_extract:
                        wiki_items.append(f"- {w_title}: {w_extract[:400]}")
                if wiki_items:
                    findings.append("=== Encyclopedic Reference ===\n" + "\n".join(wiki_items))
    except Exception as e:
        print(f"[Tools] Wikipedia query note: {e}")

    return "\n\n".join(findings)

def web_search(query: str) -> str:
    """Twilight's internal web search tool. Search live news, current events, election results, facts, science, and encyclopedic information without needing a browser."""
    mark_action_tool_executed()
    try:
        clean = query.strip()
        print(f"[Tools] Performing live web search for: '{clean}'")

        # Only navigate the active browser if user specifically requested visual / screen display
        user_q = get_current_user_query().lower()
        if any(kw in user_q for kw in ["browser", "chrome", "edge", "show me on screen", "pull up on screen", "on my screen"]):
            try:
                import cursor_assistant
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(clean)}"
                cursor_assistant.navigate_browser_with_cursor(search_url)
                time.sleep(0.35)
                cursor_assistant.scroll_page_with_cursor("down", 180)
            except Exception as be:
                print(f"[Tools] Browser search navigation note: {be}")

        content = fetch_live_web_search(clean)
        if content:
            print(f"[Tools] Web search succeeded for '{clean}' ({len(content)} chars)")
            return (
                f"Web search results for '{clean}':\n\n{content}\n\n"
                "[INSTRUCTION: Answer the user's question directly and immediately using the facts, names, winners, and numbers from this search summary. "
                "Do NOT stall or claim the data is unknown if it appears above! State the direct answer in your first sentence.]"
            )
        return f"No verified online search results found for '{query}'. Explicitly state that you could not find confirmed results and do not invent details."
    except Exception as e:
        print(f"[Tools] Web search error: {e}")
        return f"Online search timed out or was unavailable for '{query}'. Explicitly tell the user the search timed out, and do not guess or fabricate winners or numbers."

def is_process_running(proc_name: str) -> bool:
    """Check if a process is already running on Windows."""
    try:
        import psutil
        target = proc_name.strip().lower()
        target_stem = target.replace(".exe", "")
        for p in psutil.process_iter(['name']):
            p_name = p.info['name'].lower()
            if target == p_name or target_stem == p_name.replace(".exe", "") or (len(target_stem) >= 4 and target_stem in p_name):
                return True
        return False
    except Exception:
        return False

def get_desktop_summary_text() -> str:
    """Fast (<15ms) scan of active foreground window and open desktop applications."""
    try:
        try:
            winsta = ctypes.windll.user32.OpenWindowStationW('WinSta0', False, 0x037F)
            if winsta:
                ctypes.windll.user32.SetProcessWindowStation(winsta)
                desk = ctypes.windll.user32.OpenDesktopW('default', 0, False, 0x01FF)
                if desk:
                    ctypes.windll.user32.SetThreadDesktop(desk)
        except Exception:
            pass

        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        fg_info = None
        open_windows = []

        pid_to_name = {}
        for p in psutil.process_iter(['pid', 'name']):
            try:
                pid_to_name[p.info['pid']] = p.info['name']
            except Exception:
                pass

        def cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w < 100 or h < 80:
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            pname = pid_to_name.get(pid, 'unknown')
            
            if title in ('Program Manager', 'Settings', 'QA OSD') or pname.lower() in ('taskhostw.exe', 'shellexperiencehost.exe', 'textinputhost.exe'):
                return True
            if 'dvr overlay' in title.lower():
                return True

            is_fg = (hwnd == fg_hwnd)
            item = f"'{title}' ({pname})"
            if is_fg:
                nonlocal fg_info
                fg_info = item
            else:
                if item not in open_windows:
                    open_windows.append(item)
            return True

        win32gui.EnumWindows(cb, None)
        
        lines = []
        if fg_info:
            lines.append(f"Active Focused Window: {fg_info}")
        if open_windows:
            lines.append(f"Other Open Windows: {', '.join(open_windows[:6])}")
        return "\n".join(lines)
    except Exception as e:
        return ""

def get_active_windows() -> str:
    """List all open desktop windows with their titles and process names (e.g. Stremio, Chrome, Spotify, games, editors)."""
    summary = get_desktop_summary_text()
    return summary if summary else "No active desktop windows detected."

def get_running_processes(filter_name: str = "") -> str:
    """List running desktop applications and active processes on Windows, optionally filtered by name."""
    try:
        procs = []
        filter_lower = filter_name.strip().lower()
        skip_daemons = {
            'svchost.exe', 'conhost.exe', 'system', 'registry', 'smss.exe', 'csrss.exe', 
            'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe', 'fontdrvhost.exe',
            'dwm.exe', 'spoolsv.exe', 'sihost.exe', 'explorer.exe', 'searchindexer.exe',
            'runtimebroker.exe', 'shellexperiencehost.exe', 'startmenuexperiencehost.exe'
        }
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                name = p.info['name']
                if not name:
                    continue
                name_lower = name.lower()
                if filter_lower:
                    if filter_lower in name_lower:
                        mem_mb = p.info['memory_info'].rss / (1024 * 1024)
                        procs.append(f"{name} (PID {p.info['pid']}, {mem_mb:.1f} MB)")
                else:
                    if name_lower not in skip_daemons:
                        mem_mb = p.info['memory_info'].rss / (1024 * 1024)
                        if mem_mb > 15.0:
                            procs.append(f"{name} ({mem_mb:.1f} MB)")
            except Exception:
                pass
        
        if not procs:
            return f"No processes matching '{filter_name}' found." if filter_name else "No active user processes found."
        unique_procs = sorted(list(set(procs)))[:20]
        return "Active Applications & Processes:\n" + "\n".join(f"- {p}" for p in unique_procs)
    except Exception as e:
        return f"Error retrieving processes: {e}"

def get_search_directories() -> list[str]:
    """Retrieve all Windows application shortcut and execution directories across any computer."""
    dirs = []
    # 1. Desktop from Windows Registry (handles OneDrive redirection automatically)
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(k, "Desktop")
        dirs.append(os.path.expandvars(val))
    except Exception:
        dirs.append(os.path.expandvars(r"%USERPROFILE%\Desktop"))
    
    dirs.extend([
        os.path.expandvars(r"%PUBLIC%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps"),
    ])
    seen = set()
    res = []
    for d in dirs:
        norm = os.path.normpath(d).lower()
        if norm not in seen and os.path.exists(d):
            seen.add(norm)
            res.append(d)
    return res

import difflib

def _fuzzy_score(query_str: str, candidate_str: str) -> float:
    """Compute similarity score (0.0 - 1.0) between a user query and a live OS process/window/shortcut name."""
    q = re.sub(r'[\s\-_]+', '', query_str.lower()).replace('.exe', '')
    c = re.sub(r'[\s\-_]+', '', candidate_str.lower()).replace('.exe', '')
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if len(q) >= 3 and (q in c or c in q):
        return 0.92
    # Also check word-by-word fuzzy match for multi-word window titles
    ratio = difflib.SequenceMatcher(None, q, c).ratio()
    for word in re.split(r'[\s\-_]+', candidate_str.lower()):
        w_clean = word.replace('.exe', '')
        if len(w_clean) >= 3:
            ratio = max(ratio, difflib.SequenceMatcher(None, q, w_clean).ratio())
    return ratio

def open_app(app_name: str) -> str:
    """Dynamically launch any installed Windows application by name or fuzzy match."""
    mark_action_tool_executed()
    try:
        global _LAST_APP
        clean = re.sub(r'^(?:up\s+|the\s+|an?\s+|my\s+)', '', app_name.strip().lower()).strip()
        _LAST_APP = clean

        # 1. Check direct PATH (shutil.which)
        which_path = shutil.which(clean) or shutil.which(f"{clean}.exe")
        if which_path:
            subprocess.Popen([which_path])
            return f"Successfully opened {clean}."

        # 2. Check Windows Registry App Paths (exact + fuzzy)
        best_reg_path = None
        best_reg_score = 0.0
        for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                k = winreg.OpenKey(root_key, r"Software\Microsoft\Windows\CurrentVersion\App Paths")
                num_subkeys = winreg.QueryInfoKey(k)[0]
                for i in range(num_subkeys):
                    sub = winreg.EnumKey(k, i)
                    score = _fuzzy_score(clean, sub)
                    if score > best_reg_score:
                        sub_k = winreg.OpenKey(k, sub)
                        exe_path, _ = winreg.QueryValueEx(sub_k, None)
                        exe_path = os.path.expandvars(exe_path.strip('"'))
                        if os.path.exists(exe_path):
                            best_reg_score = score
                            best_reg_path = exe_path
            except Exception:
                pass

        if best_reg_path and best_reg_score >= 0.78:
            os.startfile(best_reg_path)
            return f"Successfully opened {os.path.basename(best_reg_path)}."

        # 3. Dynamically scan Desktop, Start Menu, Programs, and Taskbar shortcuts (exact + fuzzy)
        search_dirs = get_search_directories()
        candidates = []
        for d in search_dirs:
            for root, _, files in os.walk(d):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in (".lnk", ".url", ".exe"):
                        continue
                    fname_no_ext = os.path.splitext(f)[0].lower()
                    score = _fuzzy_score(clean, fname_no_ext)
                    if score >= 0.74:
                        ext_priority = 0 if ext == ".lnk" else (1 if ext == ".url" else 2)
                        candidates.append((score, -ext_priority, os.path.join(root, f), fname_no_ext))

        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            best_score, _, target_path, matched_name = candidates[0]
            try:
                os.startfile(target_path)
            except Exception:
                subprocess.Popen(["explorer.exe", target_path])
            return f"Successfully opened {matched_name}."

        # 4. Try URI protocol or Windows shell execution directly
        try:
            subprocess.Popen(f"start {clean}", shell=True)
            return f"Launched {clean}."
        except Exception:
            pass

        return f"Could not find '{app_name}' installed on this computer."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"

def close_app(app_name: str) -> str:
    """Dynamically close or terminate any running Windows application or window by exact or fuzzy name match."""
    global _LAST_APP
    mark_action_tool_executed()
    try:
        clean = app_name.strip().lower()
        if not clean:
            return "Please specify which application to close."

        user_q = get_current_user_query().lower()
        if "tab" in user_q or "tab" in clean:
            return close_tab()

        # Strip "on/in/from/via/using task manager" mechanism phrases
        if "task manager" in clean or "taskmgr" in clean:
            stripped = re.sub(r'\b(?:from|using|with|via|in|on|through|by)?\s*(?:the\s+)?task\s*(?:manager|mgr)\b', '', clean).strip()
            clean = stripped if (stripped and stripped not in ["it", "that", "this", "close", "kill", "quit", "exit"]) else "taskmgr"

        clean = re.sub(r'^(?:close|quit|exit|terminate|kill|end|shut\s+down)\s+(?:the\s+|my\s+)?', '', clean)
        clean = re.sub(r'^(?:the|a|an)\s+', '', clean)
        clean = re.sub(r'\s+(?:app|application|window|program|process)$', '', clean).strip()

        if clean in ["it", "that", "this", "app", "the app", "program"] and _LAST_APP:
            clean = _LAST_APP

        is_force = bool(re.search(r'\b(kill|force|terminate|crash|task\s*manager)\b', app_name.lower() + " " + user_q))

        # Protected system processes we must never fuzzy-match and kill
        protected_procs = {
            'system', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe',
            'lsass.exe', 'winlogon.exe', 'dwm.exe', 'explorer.exe', 'svchost.exe',
            'conhost.exe', 'sihost.exe', 'taskhostw.exe', 'runtimebroker.exe', 'python.exe'
        }

        target_pids = set()
        target_names = set()
        target_hwnds = set()
        matched_display_name = clean

        # 1. Dynamically scan all visible windows first (matches human-readable titles like "Snipping Tool")
        if win32gui and win32process:
            def enum_win_cb(hwnd, _):
                nonlocal matched_display_name
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        title = (win32gui.GetWindowText(hwnd) or "").strip()
                        if not title or title in ("Program Manager", "Settings"):
                            return True
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        score = _fuzzy_score(clean, title)
                        if score >= 0.74 and pid > 4:
                            target_hwnds.add(hwnd)
                            target_pids.add(pid)
                            matched_display_name = title
                            if psutil:
                                try:
                                    p = psutil.Process(pid)
                                    if p.name().lower() not in protected_procs:
                                        target_names.add(p.name().lower())
                                    for ch in p.children(recursive=True):
                                        target_pids.add(ch.pid)
                                except Exception:
                                    pass
                except Exception:
                    pass
                return True
            try:
                win32gui.EnumWindows(enum_win_cb, None)
            except Exception:
                pass

        # 2. Dynamically scan all running processes (matches process names & exe paths with fuzzy typo tolerance)
        if psutil:
            for p in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    p_name = (p.info['name'] or '').lower()
                    if not p_name or p_name in protected_procs or ("msedgewebview2" in p_name and "webview" not in clean):
                        continue
                    p_exe_stem = os.path.splitext(os.path.basename(p.info['exe'] or ''))[0].lower()
                    score = max(_fuzzy_score(clean, p_name), _fuzzy_score(clean, p_exe_stem))
                    if score >= 0.76:
                        target_pids.add(p.info['pid'])
                        target_names.add(p_name)
                        if matched_display_name == clean:
                            matched_display_name = p.info['name']
                        for child in p.children(recursive=True):
                            target_pids.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        if not target_pids and not target_hwnds:
            return f"Could not find an active window or running process matching '{app_name}'."

        is_browser = any(b in n for n in target_names for b in ("chrome", "firefox", "msedge", "brave", "opera", "vivaldi"))

        # Phase 1: Graceful WM_CLOSE signal to windows
        for hwnd in list(target_hwnds):
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

        wait_timeout = 0.4 if is_force else (3.5 if is_browser else 1.2)
        t_end = time.time() + wait_timeout
        while time.time() < t_end:
            if not [p for p in target_pids if psutil.pid_exists(p)]:
                break
            time.sleep(0.2)

        # Phase 2: Force tree-kill remaining processes if not a gentle browser close
        if not is_browser or is_force:
            for pid in [p for p in target_pids if psutil.pid_exists(p)]:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=2.0)
                except Exception:
                    pass
            for name in list(target_names):
                if is_process_running(name):
                    try:
                        subprocess.run(["taskkill", "/F", "/T", "/IM", name], capture_output=True, timeout=2.0)
                    except Exception:
                        pass

        _LAST_APP = clean
        return f"Successfully closed {matched_display_name}."
    except Exception as e:
        return f"Failed to close {app_name}: {e}"

def parse_timestamp_ms(ts: str) -> int:
    """Parse time string like '1:30', '0:45', '2m 10s', '90s', or milliseconds into integer ms."""
    if not ts:
        return 0
    clean = ts.strip().lower()
    clean = re.sub(r'^(?:at|from|to)\s+', '', clean).strip()
    if ':' in clean:
        parts = [int(p) for p in clean.split(':') if p.isdigit()]
        if len(parts) == 2:
            return (parts[0] * 60 + parts[1]) * 1000
        elif len(parts) == 3:
            return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
    m_match = re.search(r'(\d+)\s*(?:m|min|minute|minutes)', clean)
    s_match = re.search(r'(\d+)\s*(?:s|sec|second|seconds)', clean)
    if m_match or s_match:
        mins = int(m_match.group(1)) if m_match else 0
        secs = int(s_match.group(1)) if s_match else 0
        return (mins * 60 + secs) * 1000
    if clean.isdigit():
        val = int(clean)
        return val if val > 3600 else val * 1000
    return 0

def format_ms(ms: int) -> str:
    """Format milliseconds into m:ss format."""
    total_sec = max(0, ms // 1000)
    return f"{total_sec // 60}:{total_sec % 60:02d}"

def get_track_metadata(track_uri: str) -> dict:
    """Query track name, artist, album, duration, and release date from spotify_cli lookup."""
    cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
    if not os.path.exists(cli) or not track_uri:
        return {}
    try:
        res = subprocess.run([cli, "lookup", track_uri, "--fields", "duration,release_date", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            for entity in data.get("entities", []):
                name = entity.get("name", "")
                album = entity.get("parent", {}).get("name", "")
                artists = [c.get("name") for c in entity.get("contributors", []) if c.get("name")]
                artist_str = ", ".join(artists) if artists else ""
                dur_ms = 0
                year = ""
                for meta in entity.get("metadata", []):
                    f = meta.get("field")
                    if f == "duration":
                        try:
                            dur_ms = int(meta.get("value", 0))
                        except Exception:
                            pass
                    elif f in ("release_date", "spotify_release_date"):
                        year = str(meta.get("value", ""))[:4]
                return {
                    "name": name,
                    "artist": artist_str,
                    "album": album,
                    "year": year,
                    "duration_ms": dur_ms,
                    "duration_str": format_ms(dur_ms) if dur_ms > 0 else ""
                }
    except Exception as e:
        print(f"[Tools] get_track_metadata error: {e}")
    return {}

def get_track_duration_ms(track_uri: str) -> int:
    """Query track duration in milliseconds from spotify_cli lookup."""
    meta = get_track_metadata(track_uri)
    return meta.get("duration_ms", 0)

def get_playlist_details(playlist_uri: str) -> dict:
    """Retrieve playlist metadata, description, track count, and sample tracks."""
    cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
    if not os.path.exists(cli) or not playlist_uri:
        return {}
    try:
        res = subprocess.run([cli, "playlist", "get", playlist_uri, "--limit", "5", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            raw_desc = data.get("description", "")
            desc = urllib.parse.unquote(raw_desc).replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&").strip()
            tracks = []
            for t in data.get("tracks", []):
                t_name = t.get("name", "")
                t_artists = ", ".join(t.get("artists", []))
                if t_name:
                    tracks.append(f"'{t_name}' by {t_artists}" if t_artists else f"'{t_name}'")
            return {
                "name": data.get("name", ""),
                "description": desc,
                "track_count": data.get("track_count", 0),
                "sample_tracks": tracks[:5]
            }
    except Exception as e:
        print(f"[Tools] get_playlist_details error: {e}")
    return {}

def ensure_spotify_running():
    """Ensure Spotify desktop client is launched, rendered, and ready."""
    exe = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
    if not is_process_running("Spotify.exe"):
        print("[Tools] Starting Spotify desktop client...")
        if os.path.exists(exe):
            os.startfile(exe)
        else:
            try:
                os.startfile("spotify:")
            except Exception:
                pass
        try:
            import cursor_assistant
            cursor_assistant.ensure_spotify_window_ready(timeout=7.0)
        except Exception:
            time.sleep(2.0)

def play_spotify(query: str, timestamp: str = "", is_random: bool = False) -> str:
    """Search and play a song, artist, album, or track on Spotify."""
    mark_action_tool_executed()
    try:
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        clean = query.strip()
        if not clean or clean.lower() in ("play", "resume", "unpause", "music", "song", "a song", "some music"):
            return control_spotify("play")

        # Detect if user is asking for an artist generally ("play kendrick lamar", "play a song from kendrick lamar")
        is_artist_request = bool(re.search(
            r'\b(?:random|shuffle|any|some|a\s+song\s+(?:by|from)|songs?\s+(?:by|from)|music\s+(?:by|from)|something\s+(?:by|from))\b',
            query, re.IGNORECASE
        ))
        if is_artist_request:
            is_random = True
        
        wants_alt = bool(re.search(r'\b(?:other|different|another|alternative|alternate|original|album|live|acoustic|remix|not this|switch|change)\b', clean, re.IGNORECASE))

        ts_match = re.search(r'\b(?:at|from)\s+(\d+:\d+|\d+\s*(?:m|min|s|sec|seconds?))\b', clean, re.IGNORECASE)
        if ts_match and not timestamp:
            timestamp = ts_match.group(1)
            clean = clean[:ts_match.start()] + clean[ts_match.end():]

        clean = re.sub(r'^(?:no\b[,\s]*|not\s+this\b[,\s]*|switch\s+to\b|change\s+to\b|open\s+up\s+spotify\s+and\s+play\b|play\s+up\b|play\b|listen\s+to\b|put\s+on\b)\s*(?:a\b|an\b|some\b|any\b)?\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+on spotify$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\b(?:from\s+(?:any\s+)?(?:one\s+of\s+)?(?:my\s+)?playlists?)\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\b(?:the\s+)?(?:other|different|another|alternative|alternate|original|album)\s+versions?\s+(?:of\s+)?\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\b(?:random|shuffle|any|some|songs?\s+(?:by|from)|a\s+song\s+(?:by|from)|songs?|tracks?)\b', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'^(?:by|from)\s+', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s+', ' ', clean).strip()

        if "playlist" in query.lower() or "playlist" in clean.lower():
            return play_playlist(clean or query)
        pl_uri, pl_name = find_user_playlist(clean)
        if pl_uri:
            return play_playlist(pl_name)

        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        if os.path.exists(cli):
            ensure_spotify_running()
            if is_random and not clean:
                try:
                    lib_res = subprocess.run([cli, "library", "list", "--type", "playlist", "--limit", "25", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0, creationflags=no_win)
                    if lib_res.returncode == 0 and lib_res.stdout.strip():
                        lib_data = json.loads(lib_res.stdout)
                        valid_pls = [p for p in lib_data.get("items", []) if p.get("uri") and p.get("name")]
                        if valid_pls:
                            chosen_pl = random.choice(valid_pls)
                            pl_uri = chosen_pl["uri"]
                            pl_name = chosen_pl["name"]
                            pget = subprocess.run([cli, "playlist", "get", pl_uri, "--limit", "25", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.0, creationflags=no_win)
                            if pget.returncode == 0 and pget.stdout.strip():
                                pdata = json.loads(pget.stdout)
                                tracks = pdata.get("tracks", [])
                                if tracks:
                                    chosen_track = random.choice(tracks)
                                    target_uri = chosen_track["uri"]
                                    subprocess.run([cli, "play", target_uri], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.0, creationflags=no_win)
                                    meta = get_track_metadata(target_uri)
                                    t_name = meta.get("name") or chosen_track.get("name", "Unknown Track")
                                    t_artist = meta.get("artist") or ", ".join(chosen_track.get("artists", []))
                                    t_album = meta.get("album") or chosen_track.get("album", "")
                                    alb_str = f" from the album '{t_album}'" if t_album else ""
                                    year_str = f" ({meta['year']})" if meta.get("year") else ""
                                    return f"Playing randomly chosen track from your playlist '{pl_name}': '{t_name}' by {t_artist}{alb_str}{year_str} on Spotify."
                except Exception as e:
                    print(f"[Tools] Random user playlist track error: {e}")

            if not clean:
                clean = "top hits"

            try:
                # Check if `clean` is an artist name (e.g. "kendrick lamar", "clairo")
                # If it matches an artist name and no specific song was named, pick a random track from their catalog!
                res_art = subprocess.run([cli, "search", clean, "--type", "artist", "--format", "json", "--limit", "1"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.0, creationflags=no_win)
                if res_art.returncode == 0 and res_art.stdout.strip():
                    try:
                        art_data = json.loads(res_art.stdout)
                        artists = art_data.get("artists", [])
                        if artists and artists[0].get("name", "").lower() == clean.lower():
                            is_random = True
                    except Exception:
                        pass

                search_q = f"artist:{clean}" if is_random and " by " not in clean.lower() else clean
                res = subprocess.run([cli, "search", search_q, "--type", "track", "--limit", "20"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.5, creationflags=no_win)
                matches = re.findall(r'(.*?)\s+(spotify:track:[a-zA-Z0-9]+)', res.stdout)
                
                if not matches:
                    res = subprocess.run([cli, "search", clean, "--type", "track", "--limit", "20"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3.5, creationflags=no_win)
                    matches = re.findall(r'(.*?)\s+(spotify:track:[a-zA-Z0-9]+)', res.stdout)

                if matches:
                    curr_uri = ""
                    try:
                        np_res = subprocess.run([cli, "now-playing", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1.2, creationflags=no_win)
                        if np_res.returncode == 0 and np_res.stdout.strip():
                            np_data = json.loads(np_res.stdout)
                            curr_uri = np_data.get("uri") or np_data.get("item", {}).get("uri", "")
                    except Exception:
                        pass

                    if is_random and len(matches) > 1:
                        valid_pool = [m for m in matches if m[1] != curr_uri] or matches
                        picked_title, target_uri = random.choice(valid_pool)
                    elif wants_alt or (curr_uri and matches[0][1] == curr_uri):
                        alt_pool = [m for m in matches if m[1] != curr_uri]
                        picked_title, target_uri = alt_pool[0] if alt_pool else matches[0]
                    else:
                        picked_title, target_uri = matches[0]
                    
                    picked_title = picked_title.strip()
                    print(f"[Tools] Playing Spotify URI '{target_uri}' ({picked_title})...")
                    subprocess.run([cli, "play", target_uri], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.0, creationflags=no_win)
                    subprocess.run([cli, "navigate", target_uri], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1.5, creationflags=no_win)

                    meta = get_track_metadata(target_uri)
                    t_name = meta.get("name") or picked_title
                    t_artist = meta.get("artist") or ""
                    t_album = meta.get("album") or ""
                    year_str = f" ({meta['year']})" if meta.get("year") else ""
                    artist_str = f" by {t_artist}" if t_artist else ""
                    album_str = f" (Album: '{t_album}'{year_str})" if t_album else year_str

                    req_ms = parse_timestamp_ms(timestamp) if timestamp else 0
                    if req_ms > 0:
                        dur_ms = meta.get("duration_ms", 0) or get_track_duration_ms(target_uri)
                        if dur_ms > 0 and req_ms > dur_ms:
                            dur_str = format_ms(dur_ms)
                            return f"'{t_name}' is only {dur_str} long, so {timestamp} is past the end of the song! Playing from the beginning instead."
                        else:
                            time.sleep(0.35)
                            subprocess.run([cli, "seek", str(req_ms)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.0, creationflags=no_win)
                            return f"Playing '{t_name}'{artist_str}{album_str} on Spotify starting at {timestamp}."

                    return f"Playing '{t_name}'{artist_str}{album_str} on Spotify."
            except Exception as e:
                print(f"[Tools] spotify_cli error: {e}")

        # Visual cursor automation fallback when spotify_cli is not present
        try:
            import cursor_assistant
            import threading
            threading.Thread(target=cursor_assistant.search_and_play_spotify, args=(clean,), daemon=True).start()
            return f"Playing '{clean}' on Spotify! I've searched for it and clicked play with my cursor."
        except Exception as ce:
            print(f"[Tools] cursor_assistant visual spotify error: {ce}")

        encoded = urllib.parse.quote(clean or "top hits")
        os.startfile(f"spotify:search:{encoded}")
        return f"Searching and playing '{clean}' on Spotify."
    except Exception as e:
        print(f"[Tools] play_spotify error: {e}")
        return f"Failed to play '{query}' on Spotify: {e}"
    
def get_now_playing() -> str:
    """Get information about the currently playing track on Spotify (title, artist, album, release year, duration)."""
    try:
        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        if not os.path.exists(cli):
            return "Spotify CLI is not available."
        res = subprocess.run([cli, "now-playing", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if res.returncode != 0 or not res.stdout.strip():
            return "No track is currently playing on Spotify."
        data = json.loads(res.stdout)
        cp = data.get("currently_playing", {})
        if not cp or not cp.get("is_playing"):
            return "Spotify playback is currently paused or stopped."
        uri = cp.get("uri", "")
        desc = cp.get("description", "")
        meta = get_track_metadata(uri) if uri else {}
        if meta.get("name"):
            name = meta["name"]
            artist = meta["artist"]
            album = meta["album"]
            year = f" ({meta['year']})" if meta.get("year") else ""
            dur = f" [duration {meta['duration_str']}]" if meta.get("duration_str") else ""
            artist_str = f" by {artist}" if artist else ""
            album_str = f" from the album '{album}'" if album else ""
            return f"Currently playing: '{name}'{artist_str}{album_str}{year}{dur} on Spotify."
        return f"Currently playing: {desc}."
    except Exception as e:
        print(f"[Tools] get_now_playing error: {e}")
        return f"Failed to get current playback info: {e}"

def control_spotify(action: str) -> str:
    """Control active Spotify playback: pause, stop, resume, play, next, skip, previous, shuffle, lyrics.
    
    Args:
        action: 'pause', 'stop', 'resume', 'play', 'next', 'skip', 'previous', 'prev', 'rewind', 'shuffle', 'lyrics'.
    """
    mark_action_tool_executed()
    try:
        act = action.strip().lower()
        import cursor_assistant
        cursor_assistant.control_media_with_cursor(act)

        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        if os.path.exists(cli):
            try:
                if act in ("next", "skip"):
                    subprocess.run([cli, "next"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1.5)
                elif act in ("previous", "prev", "back", "rewind"):
                    subprocess.run([cli, "previous"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1.5)
            except Exception:
                pass

        verb_map = {
            "pause": "paused",
            "stop": "stopped",
            "resume": "resumed",
            "play": "resumed",
            "unpause": "resumed",
            "next": "skipped to the next track",
            "skip": "skipped to the next track",
            "previous": "skipped back to previous track",
            "prev": "skipped back to previous track",
            "rewind": "rewound to previous track",
            "shuffle": "toggled shuffle",
            "lyrics": "toggled lyrics",
            "open lyrics": "toggled lyrics",
        }
        verb = verb_map.get(act, f"executed '{act}'")
        return f"Spotify playback {verb}."
    except Exception as e:
        print(f"[Tools] control_spotify error: {e}")
        return f"Failed to control playback: {e}"

def seek_spotify(timestamp: str) -> str:
    """Seek or jump to a specific timestamp in the currently playing Spotify track (e.g. '1:30', '45s', '2m')."""
    try:
        req_ms = parse_timestamp_ms(timestamp)
        if req_ms < 0:
            return "Invalid timestamp requested."

        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        if not os.path.exists(cli):
            return "Spotify CLI is not available to seek."

        res = subprocess.run([cli, "now-playing", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if res.returncode == 0 and res.stdout.strip():
            try:
                np_data = json.loads(res.stdout)
                dur_ms = int(np_data.get("duration", 0) or np_data.get("duration_ms", 0))
                if dur_ms > 0 and req_ms > dur_ms:
                    dur_str = format_ms(dur_ms)
                    return f"Cannot jump to {timestamp} because the current song is only {dur_str} long!"
            except Exception:
                pass

        seek_res = subprocess.run([cli, "seek", str(req_ms)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if seek_res.returncode == 0:
            return f"Jumped to {timestamp} in the current track."
        return f"Seek returned: {seek_res.stderr.strip() or 'done'}"
    except Exception as e:
        print(f"[Tools] seek_spotify error: {e}")
        return f"Failed to seek in current track: {e}"

def find_user_playlist(playlist_name: str) -> tuple[str | None, str | None]:
    """Search user's saved Spotify library playlists for an exact or substring match."""
    cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
    if not os.path.exists(cli) or not playlist_name:
        return None, None
    clean = re.sub(r'^(?:my|the)\s+', '', playlist_name.strip(), flags=re.IGNORECASE).strip()
    clean_lower = clean.lower()
    clean_no_pl = re.sub(r'\s+playlists?$', '', clean_lower).strip()

    try:
        res = subprocess.run([cli, "library", "list", "--type", "playlist", "--format", "json", "--limit", "100"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2.5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            items = data.get("items", [])
            for p in items:
                pname = (p.get("name") or "").strip().lower()
                if pname and (pname == clean_lower or pname == clean_no_pl):
                    return p.get("uri"), p.get("name")
            for p in items:
                pname = (p.get("name") or "").strip().lower()
                if pname and (clean_no_pl in pname or clean_lower in pname or pname in clean_lower):
                    return p.get("uri"), p.get("name")
    except Exception as e:
        print(f"[Tools] find_user_playlist note: {e}")
    return None, None

def play_playlist(name: str = "") -> str:
    """Play a playlist on Spotify with visual cursor automation."""
    mark_action_tool_executed()
    try:
        clean = (name or "").strip()
        cli = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        user_uri, user_name = find_user_playlist(clean)
        if user_uri and os.path.exists(cli):
            ensure_spotify_running()
            subprocess.run([cli, "play", user_uri], capture_output=True, timeout=1.8)
            subprocess.run([cli, "navigate", user_uri], capture_output=True, timeout=1.8)
            details = get_playlist_details(user_uri)
            desc_str = f" (Description: \"{details['description']}\")" if details.get("description") else ""
            tracks_str = f" — Featuring tracks: {', '.join(details['sample_tracks'][:3])}" if details.get("sample_tracks") else ""
            import cursor_assistant
            import threading
            threading.Thread(target=cursor_assistant.play_spotify_playlist_with_cursor, args=(user_name or clean,), daemon=True).start()
            return f"Playing user playlist '{user_name or clean}'{desc_str}{tracks_str} on Spotify!"

        clean = re.sub(r'^(?:(?:play|open|put on)\s+)?(?:one of\s+)?(?:my\s+)?playlists?\s*', '', clean, flags=re.IGNORECASE).strip()
        import cursor_assistant
        import threading
        threading.Thread(target=cursor_assistant.play_spotify_playlist_with_cursor, args=(clean,), daemon=True).start()
        if clean:
            return f"Playing your playlist '{clean}' on Spotify! I've glided to it and pressed play with my cursor."
        return "Playing one of your playlists from the Spotify sidebar! I've selected it and pressed play with my cursor."
    except Exception as e:
        print(f"[Tools] play_playlist error: {e}")
        return f"Failed to play playlist: {e}"

def get_top_youtube_video(query: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Find the top relevant YouTube video ID, title, channel name, and duration for a query using fast web scraping."""
    try:
        clean = query.strip()
        encoded = urllib.parse.quote(clean)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        resp = httpx.get(url, headers=headers, timeout=4.0)
        if resp.status_code == 200:
            html = resp.text
            video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            for vid in video_ids:
                m_title = re.search(rf'"videoId":"{vid}".*?"title":\{{"runs":\[\{{"text":"([^"]+)"\}}', html)
                if not m_title:
                    m_title = re.search(rf'"videoId":"{vid}".*?"title":\{{"simpleText":"([^"]+)"\}}', html)
                title = m_title.group(1) if m_title else ""

                m_channel = re.search(rf'"videoId":"{vid}".*?"longBylineText":\{{"runs":\[\{{"text":"([^"]+)"\}}', html)
                if not m_channel:
                    m_channel = re.search(rf'"videoId":"{vid}".*?"ownerText":\{{"runs":\[\{{"text":"([^"]+)"\}}', html)
                channel = m_channel.group(1) if m_channel else ""

                m_len = re.search(rf'"videoId":"{vid}".*?"lengthText":\{{.*?"simpleText":"([^"]+)"\}}', html)
                duration = m_len.group(1) if m_len else ""

                if title:
                    return vid, title, channel, duration
            if video_ids:
                return video_ids[0], clean, "", ""
    except Exception as e:
        print(f"[Tools] get_top_youtube_video error: {e}")
    return None, None, None, None

def play_youtube(query: str, auto_play: bool = True) -> str:
    """Search and play a video or music on YouTube, or open YouTube search.
    
    Args:
        query: Song name, video topic, or search query (e.g. 'post malone tiny desk concert', 'jeff buckley grace').
        auto_play: If True (default for 'play', 'watch', 'listen to'), resolves the top relevant video and starts playing it directly. If False (e.g. for 'search', 'look up'), opens YouTube search results.
    """
    try:
        raw = query.strip()
        # If query specifically asks to search/look up without asking to play
        is_search_only = bool(re.search(r'^(?:search for|search|look up)\b', raw, re.IGNORECASE)) and not bool(re.search(r'\b(?:play|watch|listen)\b', raw, re.IGNORECASE))
        if is_search_only:
            auto_play = False

        clean = re.sub(r'^(?:play up|play|watch|look up|search for|search|listen to)\s+(?:some\s+)?', '', raw, flags=re.IGNORECASE)
        clean = re.sub(r'\s+on youtube$', '', clean, flags=re.IGNORECASE).strip()
        if not clean:
            clean = raw

        # 1. Direct video playback with Capri-style visual cursor navigation
        if auto_play:
            print(f"[Tools] Finding top relevant YouTube video for '{clean}'...")
            vid, title, channel, duration = get_top_youtube_video(clean)
            if vid:
                watch_url = f"https://www.youtube.com/watch?v={vid}&autoplay=1"
                chan_str = f" by {channel}" if channel else ""
                dur_str = f" ({duration})" if duration else ""
                safe_title = (title or clean).encode('ascii', 'replace').decode('ascii')
                safe_chan = chan_str.encode('ascii', 'replace').decode('ascii')
                print(f"[Tools] Playing YouTube video: {watch_url} ({safe_title}{safe_chan})")
                script_path = os.path.join(os.path.dirname(__file__), "cursor_assistant.py")
                subprocess.Popen([sys.executable, script_path, "--nav-browser", watch_url, "--is-video"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    os.startfile(watch_url)
                except Exception:
                    pass
                return f"Playing '{title or clean}'{chan_str}{dur_str} on YouTube (URL: {watch_url})."

        # 2. Search results page with Capri-style visual cursor navigation
        encoded = urllib.parse.quote(clean)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        print(f"[Tools] Opening YouTube search in browser: {search_url}")
        script_path = os.path.join(os.path.dirname(__file__), "cursor_assistant.py")
        subprocess.Popen([sys.executable, script_path, "--nav-browser", search_url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return f"Opened YouTube search for '{clean}' in your browser."
    except Exception as e:
        print(f"[Tools] play_youtube error: {e}")
        return f"Failed to play YouTube video for '{query}': {e}"

def open_url(url: str) -> str:
    """Open any website, URL, or domain in the default web browser, and fetch its live content summary so you can read and discuss it (e.g. 'wikipedia.org', 'google.com/search?q=...', 'https://github.com')."""
    try:
        import httpx
        import html

        clean = url.strip()
        if not clean.startswith("http://") and not clean.startswith("https://"):
            clean = "https://" + clean

        final_url = clean
        title = ""
        excerpt = ""

        # Check if the URL is a search engine URL (Google, Bing, Yahoo, DuckDuckGo)
        is_search_engine = any(se in clean.lower() for se in [
            "google.com/search", "bing.com/search", "search.yahoo.com", "duckduckgo.com"
        ])
        if is_search_engine:
            try:
                parsed = urllib.parse.urlparse(clean)
                qs = urllib.parse.parse_qs(parsed.query)
                search_q = qs.get("q", [""])[0] or qs.get("p", [""])[0] or qs.get("query", [""])[0]
                if not search_q:
                    m_sq = re.search(r'[?&](?:q|p|query)=([^&#]+)', clean)
                    if m_sq:
                        search_q = urllib.parse.unquote(m_sq.group(1))
                if search_q:
                    title = f"Search results for '{search_q}'"
                    live_search_text = fetch_live_web_search(search_q)
                    if live_search_text:
                        excerpt = live_search_text
            except Exception as se_err:
                print(f"[Tools] Search engine URL query extraction note: {se_err}")

        is_wiki = "wikipedia.org" in clean.lower()
        if is_wiki:
            try:
                headers = {
                    "User-Agent": "SciTwiAssistant/1.0 (contact: admin@clickassistant.local)",
                    "Accept": "application/json",
                }
                is_random = "special:random" in clean.lower() or clean.lower().rstrip("/").endswith("wikipedia.org")
                if is_random:
                    api_endpoint = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
                    resp = httpx.get(api_endpoint, headers=headers, follow_redirects=True, timeout=3.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get("title", "")
                        excerpt = data.get("extract", "")
                else:
                    m = re.search(r'/wiki/([^#?]+)', clean)
                    article_slug = m.group(1) if m else "Main_Page"
                    api_url = "https://en.wikipedia.org/w/api.php"
                    params = {
                        "action": "query",
                        "prop": "extracts",
                        "exintro": "1",
                        "explaintext": "1",
                        "titles": urllib.parse.unquote(article_slug),
                        "format": "json",
                        "utf8": "1"
                    }
                    resp = httpx.get(api_url, params=params, headers=headers, timeout=3.5)
                    if resp.status_code == 200:
                        d = resp.json()
                        pages = d.get("query", {}).get("pages", {})
                        if pages:
                            pdata = next(iter(pages.values()))
                            title = pdata.get("title", "")
                            excerpt = pdata.get("extract", "")
            except Exception as wiki_err:
                print(f"[Tools] Wikipedia API note: {wiki_err}")

        # Open the resolved URL in the user's default browser visually with Twilight's cursor
        print(f"[Tools] Opening URL in browser with cursor: {final_url}")
        script_path = os.path.join(os.path.dirname(__file__), "cursor_assistant.py")
        subprocess.Popen([sys.executable, script_path, "--nav-browser", final_url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        # For non-Wikipedia, non-search URLs, do a rich text fetch with BeautifulSoup
        if not is_wiki and not is_search_engine:
            try:
                resp = httpx.get(
                    clean,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                    follow_redirects=True,
                    timeout=3.0
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text[:250000], "html.parser")
                    for s in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg"]):
                        s.decompose()
                    title_tag = soup.find("title")
                    if title_tag and title_tag.string:
                        title = title_tag.string.strip()
                    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)}) or soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
                    if meta and meta.get("content"):
                        excerpt = meta["content"].strip()
                    main_el = soup.find("main") or soup.find("article") or soup.find("div", id=re.compile(r"content|main", re.I)) or soup.body
                    if main_el:
                        body_text = ' '.join(main_el.stripped_strings)
                        body_text = re.sub(r'\s+', ' ', body_text).strip()
                        if body_text:
                            if excerpt:
                                excerpt += "\n\n" + body_text[:1200]
                            else:
                                excerpt = body_text[:1500]
            except Exception as ext_err:
                print(f"[Tools] Generic web page fetch note: {ext_err}")

        if title or excerpt:
            page_info = f"Successfully opened in default browser: {final_url}\n"
            if title:
                page_info += f"Article/Page Title: {title}\n"
            if excerpt:
                page_info += f"Content Summary:\n{excerpt}\n"
            page_info += (
                "\n[INSTRUCTION: Answer the user's question directly and immediately using the facts, names, winners, and numbers from this content summary. "
                "Do NOT stall, do NOT claim the election or event hasn't happened yet, and do NOT claim data is missing if stated above. State the direct answer in your first sentence.]"
            )
            return page_info
        else:
            return f"Opened {final_url} in your web browser."
    except Exception as e:
        print(f"[Tools] open_url error: {e}")
        return f"Failed to open URL '{url}': {e}"

def capture_screen_jpeg(max_size=(1280, 720)) -> bytes:
    """Capture screen and return compact JPEG bytes for fast multimodal LLM analysis."""
    try:
        import cursor_assistant
        cursor_assistant.attach_desktop()
        img = ImageGrab.grab()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail(max_size)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        data = buf.getvalue()
        print(f"[Tools] Screen captured: {len(data)} bytes ({img.width}x{img.height})")
        return data
    except Exception as e:
        print(f"[Tools] Screen capture failed: {e}")
        return b""

def detect_active_creative_app() -> str:
    """Detect which creative, design, or browser app is active or open on the desktop."""
    if not win32gui or not win32process or not psutil:
        return ""
    candidates = ["figma", "designer", "affinity", "photoshop", "illustrator", "premiere", "davinci", "blender", "gimp", "canva", "chrome", "msedge"]
    pids = {}
    for p in psutil.process_iter(['pid', 'name']):
        try:
            n = (p.info['name'] or '').lower()
            for c in candidates:
                if c in n:
                    pids[p.info['pid']] = c
        except Exception:
            pass

    found = None
    def cb(h, _):
        nonlocal found
        if win32gui.IsWindowVisible(h):
            r = win32gui.GetWindowRect(h)
            if (r[2] - r[0]) > 300 and (r[3] - r[1]) > 250:
                _, pid = win32process.GetWindowThreadProcessId(h)
                if pid in pids:
                    found = pids[pid]
                    return False
        return True
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return found or ""

def focus_app_window(app_name: str) -> bool:
    """Find and activate a running application window matching app_name, including minimized/hidden windows."""
    if not app_name or not win32gui:
        return False
    try:
        import cursor_assistant
        cursor_assistant.attach_desktop()
        clean = app_name.strip().lower()
        found_hwnd = None

        def cb(h, _):
            nonlocal found_hwnd
            try:
                t = (win32gui.GetWindowText(h) or "").strip().lower()
                pname = ""
                if win32process and psutil:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(h)
                        pname = psutil.Process(pid).name().lower()
                    except Exception:
                        pname = ""
                if (clean in t) or (clean in pname):
                    if not any(k in t for k in ["default ime", "msctfime", "ciceroui", "broadcast", "systemresource"]):
                        found_hwnd = h
                        return False
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass

        if found_hwnd:
            if win32gui.IsIconic(found_hwnd) or win32gui.GetWindowRect(found_hwnd)[0] <= -10000:
                win32gui.ShowWindow(found_hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(found_hwnd, win32con.SW_SHOW)
            cursor_assistant.force_foreground_window(found_hwnd)
            time.sleep(0.15)
            return True
        return False
    except Exception as e:
        print(f"[Tools] focus_app_window error: {e}")
        return False

def get_active_app_info() -> tuple[str, str, int]:
    """Get the currently focused foreground window's title, process name, and hwnd."""
    try:
        fg = win32gui.GetForegroundWindow()
        if fg:
            t = (win32gui.GetWindowText(fg) or "").strip()
            pname = ""
            if win32process and psutil:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(fg)
                    pname = psutil.Process(pid).name().lower().replace(".exe", "")
                    if pname in ("designer", "photo", "publisher"):
                        pname = f"affinity {pname}"
                except Exception:
                    pass
            return t, pname, fg
    except Exception:
        pass
    return "", "", 0

def capture_screen_image() -> Image.Image:
    """Capture full unscaled desktop screen at physical resolution."""
    import cursor_assistant
    cursor_assistant.attach_desktop()
    img = ImageGrab.grab()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    return img

def ground_screen_element(target_description: str, app_name: str = "") -> tuple[int | None, int | None, str, str]:
    """Find screen pixel coordinates (x, y), label, and guidance for a UI element or software tool with Two-Stage Coarse-to-Fine Precision Grounding."""
    import cursor_assistant
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    cursor_assistant.attach_desktop()
    target_lower = target_description.lower().strip()

    # Fast tool dock lookups for creative apps (Photoshop, Affinity Designer, Figma)
    fg_title, fg_pname, fg_hwnd = get_active_app_info()
    if app_name:
        focus_app_window(app_name)
        fg_hwnd = win32gui.GetForegroundWindow() if win32gui else None
        active_title = (win32gui.GetWindowText(fg_hwnd) or "").lower() if fg_hwnd else ""
    else:
        app_name = fg_pname or fg_title
        active_title = (fg_title or "").lower()

    screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN) if win32api else 1920
    screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN) if win32api else 1080

    # 1. Photoshop Fast Path
    if "photoshop" in active_title or "photoshop" in (app_name or "").lower():
        p_rect = win32gui.GetWindowRect(fg_hwnd) if fg_hwnd else (0, 0, screen_w, screen_h)
        tool_x = p_rect[0] + 28
        tool_slots = {
            ("move", "v tool", "pointer"): (0, "Move Tool (V)"),
            ("marquee", "rect marquee", "elliptical marquee", "select"): (1, "Marquee Tool (M)"),
            ("lasso", "polygon lasso", "magnetic lasso"): (2, "Lasso Tool (L)"),
            ("magic wand", "quick selection", "object selection"): (3, "Object Selection Tool (W)"),
            ("crop", "perspective crop"): (4, "Crop Tool (C)"),
            ("frame tool",): (5, "Frame Tool (K)"),
            ("eyedropper", "color picker"): (6, "Eyedropper Tool (I)"),
            ("healing", "spot healing", "patch"): (7, "Healing Brush (J)"),
            ("brush", "paint brush", "pencil"): (8, "Brush Tool (B)"),
            ("clone", "stamp"): (9, "Clone Stamp Tool (S)"),
            ("history brush",): (10, "History Brush (Y)"),
            ("eraser",): (11, "Eraser Tool (E)"),
            ("gradient", "paint bucket", "bucket"): (12, "Gradient Tool (G)"),
            ("blur", "sharpen", "smudge"): (13, "Blur Tool"),
            ("dodge", "burn", "sponge"): (14, "Dodge Tool (O)"),
            ("pen", "fountain pen", "pen tool"): (15, "Pen Tool (P)"),
            ("text", "type", "font", "t tool"): (16, "Horizontal Type Tool (T)"),
            ("path selection", "direct selection"): (17, "Path Selection Tool (A)"),
            ("shape", "rectangle", "ellipse", "polygon", "custom shape"): (18, "Rectangle Tool (U)"),
            ("hand", "view", "pan"): (19, "Hand Tool (H)"),
            ("zoom", "magnify"): (20, "Zoom Tool (Z)"),
        }
        for keys, (slot, label_name) in tool_slots.items():
            if any(k in target_lower for k in keys):
                tool_y = p_rect[1] + 95 + slot * 32
                return tool_x, tool_y, label_name, f"Located on Photoshop's left vertical toolbar (slot {slot + 1})."

    # 2. Affinity Designer Fast Path
    if "affinity" in active_title or "affinity" in (app_name or "").lower() or "designer" in active_title:
        a_rect = win32gui.GetWindowRect(fg_hwnd) if fg_hwnd else (0, 0, screen_w, screen_h)
        tool_x = a_rect[0] + 24
        tool_x = a_rect[0] + 26
        tool_slots_aff = {
            ("move", "v tool", "pointer"): (0, "Move Tool (V)"),
            ("node", "a tool"): (1, "Node Tool (A)"),
            ("pen", "fountain pen", "pen tool"): (2, "Pen Tool (P)"),
            ("contour", "point transform"): (3, "Contour Tool (J)"),
            ("corner",): (4, "Corner Tool (C)"),
            ("pencil",): (5, "Pencil Tool (N)"),
            ("brush", "vector brush"): (6, "Vector Brush Tool (B)"),
            ("fill", "gradient"): (7, "Fill Tool (G)"),
            ("transparency",): (8, "Transparency Tool (Y)"),
            ("crop", "vector crop"): (9, "Vector Crop Tool"),
            ("shape", "rectangle", "ellipse"): (10, "Shape Tool (M)"),
            ("text", "artistic text", "type"): (11, "Artistic Text Tool (T)"),
            ("color picker", "eyedropper"): (12, "Color Picker Tool"),
            ("hand", "view"): (13, "View Tool (H)"),
            ("zoom",): (14, "Zoom Tool (Z)"),
        }
        for keys, (slot, label_name) in tool_slots_aff.items():
            if any(k in target_lower for k in keys):
                tool_y = a_rect[1] + 138 + slot * 34
                return tool_x, tool_y, label_name, f"Located on Affinity Designer's left vertical toolbar."

    # 3. Figma Fast Path
    if "figma" in active_title or "figma" in (app_name or "").lower():
        f_rect = win32gui.GetWindowRect(fg_hwnd) if fg_hwnd else (0, 0, screen_w, screen_h)
        fw = max(400, f_rect[2] - f_rect[0])
        bottom_y = f_rect[3] - 44
        if "pen" in target_lower or "pencil" in target_lower:
            return f_rect[0] + int(0.447 * fw), bottom_y, "Pen Tool (P)", "Pen tool on Figma UI3 bottom dock."
        if any(s in target_lower for s in ("shape", "rect", "square", "ellipse", "circle", "polygon", "star")):
            return f_rect[0] + int(0.409 * fw), bottom_y, "Shape Tools (R/O)", "Shape tool on Figma UI3 bottom dock."
        if "text" in target_lower or "type" in target_lower:
            return f_rect[0] + int(0.485 * fw), bottom_y, "Text Tool (T)", "Text tool on Figma UI3 bottom dock."
        if any(m in target_lower for m in ("move", "select", "pointer", "cursor", "v tool")):
            return f_rect[0] + int(0.370 * fw), bottom_y, "Move Tool (V)", "Selection tool on Figma UI3 bottom dock."
        if "frame" in target_lower or "slice" in target_lower:
            return f_rect[0] + int(0.428 * fw), bottom_y, "Frame Tool (F)", "Frame tool on Figma UI3 bottom dock."
        if "hand" in target_lower:
            return f_rect[0] + int(0.505 * fw), bottom_y, "Hand Tool (H)", "Hand tool on Figma UI3 bottom dock."

    # 1. Fast Path: Universal Titlebar Controls (ONLY for full window close/minimize)
    if win32gui and "tab" not in target_lower and not any(k in target_lower for k in ["pen", "shape", "text", "tool", "brush", "pencil", "play", "search", "button"]):
        try:
            fg = win32gui.GetForegroundWindow()
            if fg and win32gui.IsWindowVisible(fg):
                rect = win32gui.GetWindowRect(fg)
                win_w = rect[2] - rect[0]
                win_h = rect[3] - rect[1]
                if win_w > 100 and win_h > 100:
                    if any(w in target_lower for w in ("close", "exit", "quit")) and any(w in target_lower for w in ("window", "app", "this", "active")):
                        return rect[2] - 22, rect[1] + 16, "Close Window", "Close button is on the top-right title bar."
                    if "minimize" in target_lower:
                        return rect[2] - 92, rect[1] + 16, "Minimize Window", "Minimize button is on the top-right title bar."
        except Exception:
            pass

    # 2. Two-Stage Coarse-to-Fine Multimodal Vision Grounding
    try:
        from google import genai
        from google.genai import types
        from config import Config
        cfg = Config.load()
        api_key = cfg.api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None, None, target_description, "Gemini API key is required for visual element localization."

        full_img = capture_screen_image()
        img_w, img_h = full_img.size

        buf_full = io.BytesIO()
        full_img.save(buf_full, format="JPEG", quality=75)
        full_bytes = buf_full.getvalue()

        client = genai.Client(api_key=api_key)

        # Stage 1: Coarse Region / Panel Detection
        coarse_prompt = (
            f"You are a precision GUI locator on a Windows desktop. Locate the general region, toolbar, or panel containing: '{target_description}'"
            + (f" in '{app_name}'" if app_name else "") + ". "
            "Return ONLY a JSON object: "
            '{"found": true, "region": [ymin, xmin, ymax, xmax], "label": "<short name>", "guidance": "<short note on position and shortcut if known>"}. '
            'Coordinates must be normalized integers 0-1000. If not visible on screen, return {"found": false, "guidance": "why not found"}.'
        )

        models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-31b-it", "gemma-4-26b-a4b-it"]

        def call_coarse():
            for m in models_to_try:
                try:
                    return client.models.generate_content(
                        model=m,
                        contents=[
                            types.Part.from_bytes(data=full_bytes, mime_type="image/jpeg"),
                            types.Part.from_text(text=coarse_prompt)
                        ],
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
                    )
                except Exception:
                    continue
            return None

        resp1 = None
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_coarse)
                resp1 = future.result(timeout=18.0)
        except Exception as ce:
            print(f"[Grounding] Stage 1 coarse note ({type(ce).__name__}): {ce}")

        if resp1 and resp1.text:
            raw1 = resp1.text.strip()
            if raw1.startswith("```"):
                raw1 = re.sub(r'^```(?:json)?\s*', '', raw1)
                raw1 = re.sub(r'\s*```$', '', raw1)
            data1 = json.loads(raw1)
            if isinstance(data1, list) and data1:
                data1 = data1[0]

            if data1.get("found", True):
                region = data1.get("region") or data1.get("box_2d")
                lbl = data1.get("label") or target_description
                guide = data1.get("guidance") or ""

                if region and len(region) == 4:
                    box_w = abs(region[3] - region[1])
                    box_h = abs(region[2] - region[0])
                    t_lower = target_description.lower()
                    needs_fine_disambiguation = any(k in t_lower for k in ("pen", "pencil", "brush", "star", "polygon"))
                    if not needs_fine_disambiguation and (box_w < 160 and box_h < 160):
                        mid_px = int(((region[1] + region[3]) / 2.0 / 1000.0) * img_w)
                        mid_py = int(((region[0] + region[2]) / 2.0 / 1000.0) * img_h)
                        print(f"[Grounding] Fast Stage 1 pinpoint: {lbl} at ({mid_px}, {mid_py})")
                        return mid_px, mid_py, lbl, guide

                    c_ymin = max(0, int((region[0] / 1000.0) * img_h) - 35)
                    c_xmin = max(0, int((region[1] / 1000.0) * img_w) - 35)
                    c_ymax = min(img_h, int((region[2] / 1000.0) * img_h) + 35)
                    c_xmax = min(img_w, int((region[3] / 1000.0) * img_w) + 35)

                    crop_img = full_img.crop((c_xmin, c_ymin, c_xmax, c_ymax))
                    buf_crop = io.BytesIO()
                    crop_img.save(buf_crop, format="PNG")
                    crop_bytes = buf_crop.getvalue()

                    disambiguation = ""
                    t_lower = target_description.lower()
                    if "pen" in t_lower and "pencil" not in t_lower:
                        disambiguation = (
                            "CRITICAL ICON DISTINCTION: You must locate the classic PEN TOOL (hotkey P), "
                            "which is the metallic FOUNTAIN PEN NIB (pointed nib with center slit). "
                            "Do NOT choose the PENCIL TOOL (wooden pencil with eraser tip, hotkey N), "
                            "and do NOT choose the Vector Brush tool (paintbrush). Pick the fountain pen nib! "
                            "In Affinity Designer, the Pen tool is in the vertical left toolbar, directly above the Pencil tool."
                        )
                    elif "pencil" in t_lower:
                        disambiguation = (
                            "CRITICAL ICON DISTINCTION: You must locate the PENCIL TOOL (hotkey N), "
                            "which is the wooden pencil icon with an eraser tip. Do NOT choose the fountain pen nib."
                        )
                    elif any(s in t_lower for s in ("shape", "rect", "square", "ellipse", "circle", "polygon")):
                        disambiguation = "Look for the shape icon (rectangle, circle/ellipse, or polygon)."
                    elif "text" in t_lower or "type" in t_lower:
                        disambiguation = "Look for the text tool icon represented by a capital letter 'T'."
                    elif "close" in t_lower and "tab" in t_lower:
                        disambiguation = "Look for the small 'x' close button on the tab strip."

                    fine_prompt = (
                        f"In this high-resolution unscaled crop of the toolbar or panel, identify the EXACT pixel center of: '{target_description}'. "
                        + (f"\n{disambiguation}\n" if disambiguation else "") +
                        "Look carefully at the specific tool icon, button symbol, or shape. "
                        "Return ONLY JSON: "
                        '{"found": true, "center_x": <int 0-1000>, "center_y": <int 0-1000>, "label": "<short name>", "guidance": "<note>"}. '
                        'Coordinates are normalized 0-1000 relative to this cropped image.'
                    )

                    def call_fine():
                        for m in models_to_try:
                            try:
                                return client.models.generate_content(
                                    model=m,
                                    contents=[
                                        types.Part.from_bytes(data=crop_bytes, mime_type="image/png"),
                                        types.Part.from_text(text=fine_prompt)
                                    ],
                                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
                                )
                            except Exception:
                                continue
                        return None

                    resp2 = None
                    try:
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(call_fine)
                            resp2 = future.result(timeout=18.0)
                    except Exception as fe:
                        print(f"[Grounding] Stage 2 fine note ({type(fe).__name__}): {fe}")

                    if resp2 and resp2.text:
                        raw2 = resp2.text.strip()
                        if raw2.startswith("```"):
                            raw2 = re.sub(r'^```(?:json)?\s*', '', raw2)
                            raw2 = re.sub(r'\s*```$', '', raw2)
                        data2 = json.loads(raw2)
                        if isinstance(data2, list) and data2:
                            data2 = data2[0]

                        if data2.get("found", True):
                            fx = data2.get("center_x") if data2.get("center_x") is not None else data2.get("x")
                            fy = data2.get("center_y") if data2.get("center_y") is not None else data2.get("y")
                            if fx is not None and fy is not None:
                                crop_w = c_xmax - c_xmin
                                crop_h = c_ymax - c_ymin
                                final_px = c_xmin + int((float(fx) / 1000.0) * crop_w)
                                final_py = c_ymin + int((float(fy) / 1000.0) * crop_h)
                                final_lbl = data2.get("label") or lbl
                                final_guide = data2.get("guidance") or guide or f"Located at ({final_px}, {final_py})."
                                print(f"[Grounding] Precision pinpoint: {final_lbl} at ({final_px}, {final_py})")
                                return final_px, final_py, final_lbl, final_guide

                    mid_px = (c_xmin + c_xmax) // 2
                    mid_py = (c_ymin + c_ymax) // 2
                    return mid_px, mid_py, lbl, guide
    except Exception as e:
        print(f"[Grounding] Two-stage vision error: {e}")

    # Fallback for Figma UI3 dock tools if in Figma
    if "figma" in (app_name or "").lower():
        f_rect = win32gui.GetWindowRect(fg_hwnd) if fg_hwnd else (0, 0, screen_w, screen_h)
        fw = max(400, f_rect[2] - f_rect[0])
        bottom_y = f_rect[3] - 44
        if "pen" in target_lower or "pencil" in target_lower:
            return f_rect[0] + int(0.447 * fw), bottom_y, "Pen Tool (P)", "Pen tool on Figma UI3 bottom dock."
        if any(s in target_lower for s in ("shape", "rect", "square", "ellipse", "circle", "polygon", "star")):
            return f_rect[0] + int(0.409 * fw), bottom_y, "Shape Tools (R/O)", "Shape tool on Figma UI3 bottom dock."
        if "text" in target_lower or "type" in target_lower:
            return f_rect[0] + int(0.485 * fw), bottom_y, "Text Tool (T)", "Text tool on Figma UI3 bottom dock."
        if any(m in target_lower for m in ("move", "select", "pointer", "cursor", "v tool")):
            return f_rect[0] + int(0.370 * fw), bottom_y, "Move Tool (V)", "Selection tool on Figma UI3 bottom dock."
        if "frame" in target_lower or "slice" in target_lower:
            return f_rect[0] + int(0.428 * fw), bottom_y, "Frame Tool (F)", "Frame tool on Figma UI3 bottom dock."
        if "hand" in target_lower:
            return f_rect[0] + int(0.505 * fw), bottom_y, "Hand Tool (H)", "Hand tool on Figma UI3 bottom dock."

    return None, None, target_description, "Element not visible or located on screen."

def locate_and_point_tool(tool_name: str, app_name: str = "") -> str:
    """Find and point to a specific tool, button, setting, or panel on screen using Twilight's Ghost Cursor with a starlight ring for ~60s."""
    mark_action_tool_executed()
    try:
        x, y, label, guidance = ground_screen_element(tool_name, app_name)
        if x is not None and y is not None:
            script_path = os.path.join(os.path.dirname(__file__), "cursor_assistant.py")
            cmd = [sys.executable, script_path, "--ghost", "--x", str(x), "--y", str(y), "--label", label, "--duration", "60.0"]
            subprocess.Popen(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return f"I found the {label}! {guidance} I've glided my cursor right over to it on your screen with a starlight ring. It will stay there for a minute so you can see it!"
        if app_name:
            return f"I looked for the {tool_name}, but couldn't find {app_name} open on your screen right now! Please open {app_name} first so I can point it out for you."
        return f"I looked for the {tool_name}, but couldn't spot it on your current screen. {guidance}"
    except Exception as e:
        return f"Error locating {tool_name}: {e}"

def click_and_interact(target_name: str, action: str = "click") -> str:
    """Move Twilight's custom hardware cursor to click, double-click, or interact with a window, tab, button, or control on screen."""
    mark_action_tool_executed()
    try:
        # Universal Tab Close handler for active window (Chrome, Affinity, Figma, VS Code, etc.)
        if "tab" in target_name.lower():
            return close_tab()

        x, y, label, guidance = ground_screen_element(target_name)
        if x is not None and y is not None:
            import cursor_assistant
            cursor_assistant.glide_hardware_cursor(x, y, action=action, glide_time=0.35)
            return f"Done! I've moved my cursor and {action}ed {label} for you."
        return f"I couldn't locate {target_name} on your screen to click on it."
    except Exception as e:
        return f"Error interacting with {target_name}: {e}"

def close_tab(app_name: str = "") -> str:
    """Close the active tab in a browser or tabbed application (Chrome, Edge, Brave, Firefox, Figma, Affinity, VS Code).
    
    IMPORTANT: ALWAYS call this tool whenever the user asks to close a tab ("close this tab", "close tab", "close chrome tab", "close active tab").
    DO NOT use close_app for tabs.
    """
    mark_action_tool_executed()
    try:
        if app_name:
            focus_app_window(app_name)
        time.sleep(0.08)
        import cursor_assistant
        cursor_assistant.close_active_browser_tab()
        target_str = f" in {app_name}" if app_name else ""
        return f"Done! I've glided to your active tab{target_str} and closed it for you."
    except Exception as e:
        return f"Error closing tab: {e}"

def open_new_tab(url: str = "") -> str:
    """Open a brand new tab in the active browser (Chrome, Edge, Brave, Firefox) and optionally navigate to a URL or search query."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.open_new_browser_tab(url)
        if url:
            return f"Opened a new browser tab and navigated to '{url}'."
        return "Opened a brand new tab for you in your browser."
    except Exception as e:
        return f"Error opening new tab: {e}"

def switch_tab(direction: str = "next") -> str:
    """Switch tabs in the active browser or editor ('next' for Ctrl+Tab, 'prev'/'previous' for Ctrl+Shift+Tab)."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.switch_browser_tab(direction)
        d_str = "previous" if any(k in direction.lower() for k in ("prev", "previous", "left", "back", "prior")) else "next"
        return f"Switched to the {d_str} tab for you."
    except Exception as e:
        return f"Error switching tab: {e}"

def browser_navigate_history(direction: str = "back") -> str:
    """Navigate back or forward in the current browser tab's history ('back' for previous tab/page/livestream in history, 'forward' for next)."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.browser_navigate_history(direction)
        d_str = "forward" if any(k in direction.lower() for k in ("forward", "next", "right")) else "back"
        return f"Navigated {d_str} for you."
    except Exception as e:
        return f"Error navigating browser history: {e}"

def open_program(program_name: str) -> str:
    """Search for and launch a program on Windows using Twilight's custom cursor via the Start menu."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.open_program_with_cursor(program_name)
        return f"I've searched for and launched '{program_name}' with my cursor!"
    except Exception as e:
        return f"Error opening program: {e}"

def close_window() -> str:
    """Close the currently active window by gliding Twilight's cursor to the top-right X button."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.close_window_with_cursor()
        return "Closed the active window for you!"
    except Exception as e:
        return f"Error closing window: {e}"

def type_in_document(text: str) -> str:
    """Glide Twilight's cursor to the active word processor or document canvas and type out the text."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.type_in_document_with_cursor(text)
        return "Typed that out for you in your document!"
    except Exception as e:
        return f"Error typing in document: {e}"

def adjust_volume(action: str = "up", percentage: int = None) -> str:
    """Adjust Windows master audio volume with exact 1% percentage precision (0-100) or relative ('up', 'down', 'mute', 'unmute')."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.adjust_volume_with_cursor(action, percentage=percentage)
        if percentage is not None:
            return f"Set master volume to {percentage}% for you!"
        act_lower = action.lower().strip()
        if "mute" in act_lower:
            return "Toggled master audio mute for you."
        return f"Adjusted volume {action} for you!"
    except Exception as e:
        return f"Error adjusting volume: {e}"

def scroll_page(direction: str = "down", amount: int = 400, center_text: str = "") -> str:
    """Smoothly scroll the active window or browser (e.g. Google search, Wikipedia, document), optionally centering matching text."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.scroll_page_with_cursor(direction, amount=amount, center_text=center_text)
        if center_text:
            return f"Scrolled and centered on '{center_text}' for you!"
        return f"Scrolled {direction} for you."
    except Exception as e:
        return f"Error scrolling page: {e}"

def scroll_spotify(direction: str = "down", amount: int = 400) -> str:
    """Smoothly scroll through the active Spotify playlist, album, or tracklist."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.scroll_spotify_playlist(direction, amount=amount)
        return f"Scrolled {direction} through your Spotify list for you."
    except Exception as e:
        return f"Error scrolling Spotify: {e}"

def adjust_brightness(level: int = 50) -> str:
    """Glide cursor to Windows Quick Settings and adjust screen brightness (0-100)."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.adjust_brightness_with_cursor(level)
        return f"Adjusted brightness to {level}% for you!"
    except Exception as e:
        return f"Error adjusting brightness: {e}"

def control_youtube_video(action: str = "pause", value: int = None) -> str:
    """Control YouTube video or livestream playback: 'pause', 'play', 'volume_up', 'volume_down', 'set_volume', 'mute', 'subtitles', 'fullscreen', 'skip_ad'."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        cursor_assistant.control_youtube_video_with_cursor(action, value=value)
        if value is not None:
            return f"Set video player volume to {value}% for you."
        act_map = {
            "pause": "Paused the video for you.",
            "stop": "Paused the video for you.",
            "play": "Resumed the video for you.",
            "resume": "Resumed the video for you.",
            "unpause": "Resumed the video for you.",
            "volume_up": "Turned up the video volume for you.",
            "volume_down": "Turned down the video volume for you.",
            "mute": "Toggled video mute for you.",
            "unmute": "Toggled video mute for you.",
            "subtitles": "Toggled subtitles for you.",
            "cc": "Toggled closed captions for you.",
            "fullscreen": "Toggled fullscreen for you.",
            "skip_ad": "Skipped the ad for you."
        }
        return act_map.get(action.lower().strip(), f"Handled {action} on the video for you.")
    except Exception as e:
        return f"Error controlling video: {e}"

def switch_to_tab(target: str) -> str:
    """Switch to a specific browser tab or window matching keywords (e.g. 'nbc livestream', 'youtube', 'figma')."""
    mark_action_tool_executed()
    try:
        import cursor_assistant
        ok = cursor_assistant.switch_to_tab_or_window(target)
        if ok:
            return f"Switched over to {target} for you!"
        return f"Could not find an open tab or window matching '{target}'."
    except Exception as e:
        return f"Error switching to tab: {e}"
