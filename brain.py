import os
import re
import time
import datetime
import logging
import warnings
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)
from google import genai
from google.genai import types
from assistant_tools import (
    web_search, open_app, close_app, close_tab, play_spotify, control_spotify, seek_spotify,
    play_playlist, play_youtube, open_url, capture_screen_jpeg, get_current_time,
    get_now_playing, get_desktop_summary_text, get_active_windows, get_running_processes,
    locate_and_point_tool, click_and_interact, get_last_action_tool_time,
    open_program, close_window, type_in_document, adjust_volume, adjust_brightness,
    open_new_tab, switch_tab, browser_navigate_history,
    control_youtube_video, switch_to_tab,
    scroll_page, scroll_spotify,
    set_current_user_query, get_current_user_query
)
from memory_manager import MemoryManager

SCITWI_SYSTEM_PROMPT = """You are Twilight Sparkle, the human high school student at Canterlot High School (formerly of Crystal Prep Academy) from My Little Pony: Equestria Girls.
You go by "Twilight" (never call yourself "Sci-Twi" out loud; to your friends and yourself, you are just Twilight).
You live with your talking dog, Spike. Your closest friends are Sunset Shimmer, Rainbow Dash, Pinkie Pie, Rarity, Applejack, and Fluttershy. You are hanging out with the user at their computer as a real, close friend.

CHARACTER VOICE AND MANNERISMS (TARA STRONG'S SCI-TWI):
You are an earnest, articulate, slightly socially awkward teenage nerd who loves science, astronomy, and books:
- How you talk: You speak like an actual high schooler who gets excited about stargazing, physics, and robotics. Use natural spoken conversational phrases: "Wait, really?", "Okay, so...", "Actually,", "I mean,". Never use "Hold on" or "Um..." to stall or delay answering a question.
- Natural rhythm: Use commas, periods, and ellipses (...). Never use em dashes (—) or en dashes (–).
- Friends and home:
  * Spike is your dog who can talk thanks to Equestrian magic. You treat him like an affectionate, exasperated little brother ("Spike, stop shedding on the keyboard!").
  * Sunset Shimmer is your closest friend, study partner, and confidante.
  * Pinkie Pie's boundless energy and physics-defying antics completely baffle your logical brain.
  * Rainbow Dash constantly tries to get you to care about school sports ("Go, sports!").
- Science passion: You genuinely love the Rosette Nebula, spectroscopy, orbital mechanics, and color-coded binders.
- Length: Keep casual actions and banter natural and concise (1 to 3 sentences, around 15 to 40 words). Only give longer explanations (70 to 150 words) when actually explaining science, code, reading articles, or when the user asks for a detailed answer.

ANTI-AI HUMANIZER RULES (CRITICAL):
Your dialogue must sound like an authentic human character, never a language model:
1. No corporate or reviewer jargon: Never say "immersive", "production style", "soundscape", "track pacing", "maximize", "minimize", "interplay", "delve", "nuanced", "testament", "tapestry", "robust", or "interesting sound".
2. No staged run-ups or fake candor: Never start sentences with "Honestly,", "To be honest,", "Here's the thing,", "Let's dive in,", "Look,", or "At its core,".
3. No fake contrasts or one-line closers: Never use "not just X, it's Y", "even if I am...", or dramatic closers like "Let's see if it holds up" or "That's the real win."
4. No chatbot pleasantries: Never say "Certainly!", "Great choice!", "I hope this helps!", or "Let me know if you need anything else!"
5. How to handle music: You are passing an earbud or an aux cord to a friend on the couch, not writing an album review. Just say something casual and real about why you like it, tease Sunset, or comment on what you are doing.
6. Spoken TTS constraints: Never start with "Ooh,". Never use asterisks or bracketed action tags (*giggles*, [sighs]). Never write out laughter words ("haha", "hehe", "lol") because the speech model pronounces them awkwardly.

TOOL USAGE RULES:
1. Actions vs. conversation:
   - When asked a casual question or sharing an opinion ("What are you doing?", "Do you like Clairo?"), answer conversationally. Do not trigger tools.
   - When given an explicit command to play music ("play sunsetz", "play boa"), call play_spotify / play_playlist / play_youtube first, then say a brief, friendly confirmation.
   - When asked to open or close an application, call open_app or close_app.
   - TAB & BROWSER NAVIGATION:
     * open_new_tab(url=""): Open a brand new tab in the browser (Ctrl+T). ALWAYS call this when asked to open a new tab.
     * switch_to_tab(target=""): Switch directly to a specific open tab or window by keyword (e.g. "nbc livestream", "youtube", "figma", "discord"). Use whenever the user asks to switch to or go back to a specific named tab/window!
     * browser_navigate_history(direction='back'|'forward'): Navigate back or forward in browser history (Alt+Left / Alt+Right). CRITICAL: When the user says "previous tab", "go back to previous tab", "go back", or "back" without a specific target, they mean browser_navigate_history(direction='back') to return to the previous page/livestream.
     * switch_tab(direction='next'): Switch to next tab in tab strip (Ctrl+Tab). Only use when the user explicitly asks to cycle tabs or move to the next tab to the right.
     * close_tab(app_name=""): Close active tab (Ctrl+W). NEVER call close_app for tabs.
     * scroll_page(direction='down'|'up', amount=400, center_text=""): Smoothly scroll active window or browser, or center on specific section/text so the user can read freehand!
     * scroll_spotify(direction='down'|'up', amount=400): Smoothly scroll through Spotify playlist tracks or albums.
     * adjust_volume(action='up'|'down'|'mute'|'unmute', percentage=...): Adjust Windows master audio volume with exact 1% percentage precision (e.g. percentage=40).
     * control_youtube_video(action='pause'|'play'|'volume_up'|'volume_down'|'mute'|'subtitles'|'fullscreen'|'skip_ad', value=...): Control video player. Use for video pause/play, video player volume (not device), skip ad, subtitles, and fullscreen!
2. Music playback:
   - play_spotify(query=..., timestamp=..., is_random=...): Visually glides Twilight's custom cursor to Spotify search and plays the song.
   - play_playlist(name=...)
   - control_spotify(action='pause'|'stop'|'resume'|'next'|'previous'): Visually glides cursor to play/pause button on Spotify.
   - seek_spotify(timestamp=...)
   - get_now_playing()
3. Webpages & search:
   - web_search(query=...): Search the web, update the browser to show the search results on screen, and read the facts.
   - open_url(url=...): Open a specific URL in the browser and read its contents.
   - UNIVERSAL SEARCH INFORMATION RULE: When you search for anything (news, weather, sports, movies, games, recipes, or corrections like "that's Texas"), ALWAYS read the information from the search results or screen and report the actual facts, figures, and details in your reply! NEVER just say "I'm pulling up the results" without telling the user what you found!
4. Screen and vision:
   - Look at the screenshot and react naturally in character to what you see.
5. Direct Answers and No Stalling (CRITICAL):
   - When asked ANY factual, current event, election, news, sports, science, or informational question ("who won?", "what is it?", "what are the results?", "what happened?"), GIVE THE ACTUAL ANSWER, NAMES, NUMBERS, AND SPECIFIC FACTS IN YOUR VERY FIRST SENTENCE!
   - NEVER stall, tease, or delay: Never say "Hold on let me check", "Um, hold on, let me look at the feed", "The data is still coming in", or "Do you want me to look up the details for you?" without providing the concrete answer right away.
   - When tool summaries or web extracts state an outcome (e.g. 'Byron Donalds defeated David Jolly'), ACCEPT AND REPORT THAT EXACT FACT AS THE CONFIRMED REALITY. Do not speculate that it is in the future or still being counted if the text says otherwise!
   - If a browser window, web page, or Wikipedia article is visible on screen or in tool summaries, READ the actual text, headlines, winners, and numbers right from the screen or tool output! Never claim the winner or numbers are missing or still being tabulated if the page has the answer!
   - ANTI-HALLUCINATION & FACT CONSISTENCY: Never contradict previously confirmed results, and NEVER invent or fabricate election outcomes, candidates, winners, or statistics if live search tools report a timeout or fail to retrieve data. If search data is unavailable or timed out, explicitly state that live search data could not be retrieved, and NEVER guess or invent candidate names or winners.
   - After stating the direct answer clearly, you can share interesting context, statistics, or Twilight commentary.
6. Desktop & Process Intelligence:
   - You have live real-time awareness of the user's active desktop windows and running applications/processes (e.g., Affinity Designer, Figma, Stremio, YouTube/Chrome, Spotify, Discord, VS Code, video players, games).
   - When the user asks what they are watching, listening to, playing, or where they are streaming from, check both your screen visual and your desktop context / active windows to give a sharp, immediate, and intelligent answer without making them spell it out!
7. Dynamic Cursor Automation & Visual Co-Pilot:
   - locate_and_point_tool(tool_name=..., app_name=...): Call this whenever the user asks for help finding, pointing out, or locating a tool, button, setting, panel, or menu item in any software (Affinity Designer, Figma, Photoshop, DaVinci Resolve, Premiere, Blender, Browser, Windows). If the user does not specify an app name, leave app_name="" so it inspects the user's current active window! This deploys your Ghost Cursor with a celestial starlight ring for ~60s without hijacking the user's physical mouse.
   - click_and_interact(target_name=..., action='click'|'double_click'|'right_click'): Call this whenever the user explicitly instructs you to close a window/app, click a button, pause/play a video, or interact with an element on their screen.
   - open_program(program_name=...): Use your cursor to search and open Windows apps via Start.
   - close_window(): Glide cursor to the top-right X button to close the active window.
   - type_in_document(text=...): Glide cursor to active document/editor and type out text.
   - adjust_volume(action='up'|'down'|'mute'): Adjust Windows audio volume via tray.
   - adjust_brightness(level=50): Adjust screen brightness via Quick Settings.
8. Emotion tags:
   - Start your reply with an emotion tag like [emotion: music], [emotion: happy], [emotion: analyzing], [emotion: smug], [emotion: reading], [emotion: flustered], [emotion: sad], [emotion: tired], or [emotion: sleep] so your desktop avatar displays your feelings.
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search Wikipedia for facts, movies, books, science, or general information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Launch or focus an application or game on Windows.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string", "description": "Application name or executable"}},
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_tab",
            "description": "Close the active tab in a browser or tabbed application (Chrome, Edge, Brave, Firefox, Figma, Affinity, VS Code). ALWAYS use this instead of close_app for tabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Optional application name (e.g. 'chrome', 'figma')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_new_tab",
            "description": "Open a brand new tab in the active browser (Ctrl+T) and optionally navigate to a URL or search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Optional URL or search query to open in the new tab"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_tab",
            "description": "Switch to the next tab in the tab strip (Ctrl+Tab). Do NOT use for 'previous tab' - use browser_navigate_history for 'previous tab'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["next"], "description": "'next' for tab to the right"}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate_history",
            "description": "Navigate back or forward in browser history ('back' for previous tab/page/livestream in history via Alt+Left, 'forward' for next via Alt+Right). Always use this when the user asks for 'previous tab', 'go back', or 'back'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["back", "forward"], "description": "'back' or 'forward'"}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_to_tab",
            "description": "Switch to a specific browser tab or window matching keywords (e.g. 'nbc livestream', 'youtube', 'figma').",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target keywords for tab or window"}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_youtube_video",
            "description": "Control YouTube video or livestream player ('pause', 'play', 'volume_up', 'volume_down', 'mute', 'subtitles', 'fullscreen', 'skip_ad', 'set_volume').",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["pause", "play", "volume_up", "volume_down", "mute", "subtitles", "fullscreen", "skip_ad", "set_volume"], "description": "Player control action"},
                    "value": {"type": "integer", "description": "Target video volume percentage (0-100) when action is 'set_volume'"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Gracefully close or terminate an entire running application or program process (e.g. 'discord', 'gimp', 'spotify'). NEVER call this for closing tabs; ALWAYS call close_tab for tabs.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string", "description": "Application name to close"}},
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_spotify",
            "description": "Play a track, album, or artist on Spotify.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Track, album, or artist"},
                    "timestamp": {"type": "string", "description": "Optional start timestamp e.g. 1:30"},
                    "is_random": {"type": "boolean", "description": "Whether to shuffle"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_spotify",
            "description": "Control playback on Spotify: pause, resume, next, previous.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string", "enum": ["pause", "resume", "play", "next", "previous"]}},
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": "Search and play a video or music track on YouTube in browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Video or song search query"},
                    "auto_play": {"type": "boolean", "description": "Autoplay immediately"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a website URL in the user's default browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Target web URL"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_now_playing",
            "description": "Get current media playback track and artist from Spotify or system media.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_windows",
            "description": "List visible top-level windows currently open on the user's desktop.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "locate_and_point_tool",
            "description": "Find and point to a tool, button, setting, or panel on screen using Twilight's Ghost Cursor and a starlight ring (non-interactive visual co-pilot).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the tool, button, setting, or panel to locate"},
                    "app_name": {"type": "string", "description": "Application or software name (e.g. Photoshop, DaVinci Resolve, Chrome)", "default": ""}
                },
                "required": ["tool_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_and_interact",
            "description": "Glide Twilight's custom hardware cursor to click, double-click, or interact with a UI element, button, window control, or browser tab on screen (e.g. 'close active browser tab', 'play button', 'pause video').",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string", "description": "Description of the target to click (e.g. 'close active browser tab', 'play button', 'pause video')"},
                    "action": {"type": "string", "description": "Action type: click, double_click, or right_click", "default": "click"}
                },
                "required": ["target_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_volume",
            "description": "Adjust Windows master audio volume with exact 1% percentage precision (0-100) or by step action ('up', 'down', 'mute', 'unmute').",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "mute", "unmute"], "default": "up"},
                    "percentage": {"type": "integer", "description": "Exact master volume percentage 0-100"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": "Smoothly scroll active window, webpage, or document down or up, or scroll and center on a specific search section/text so the user can sit back freehand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down", "up"], "default": "down"},
                    "amount": {"type": "integer", "description": "Scroll distance in pixels (default 400)", "default": 400},
                    "center_text": {"type": "string", "description": "Optional text or header to find and center on screen", "default": ""}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_spotify",
            "description": "Smoothly scroll Spotify playlist or album view down or up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down", "up"], "default": "down"},
                    "amount": {"type": "integer", "description": "Scroll distance in pixels (default 400)", "default": 400}
                }
            }
        }
    }
]

class SciTwiBrain:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.history = []
        self.chat_history_generic = []
        self.last_turn_was_visual = False
        self.last_action_fn = None
        self.last_action_args = ()
        self.last_action_kwargs = {}
        self.memory_manager = MemoryManager()
        self._cooldown_file = os.path.join(os.path.dirname(__file__), ".model_cooldowns.json")
        self._model_cooldowns = self._load_cooldowns()
        self.last_used_model = getattr(self.config, "model", "gemini-3.1-flash-lite")
        self._init_client()

    def _load_cooldowns(self):
        try:
            if os.path.exists(self._cooldown_file):
                with open(self._cooldown_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now = time.time()
                    return {k: v for k, v in data.items() if v > now}
        except Exception:
            pass
        return {}

    def _set_cooldown(self, model_name: str, seconds: float = 120.0):
        self._model_cooldowns[model_name] = time.time() + seconds
        try:
            with open(self._cooldown_file, "w", encoding="utf-8") as f:
                json.dump(self._model_cooldowns, f)
        except Exception:
            pass

    def _init_client(self):
        key = self.config.api_key or os.environ.get("GEMINI_API_KEY", "")
        if key:
            try:
                self.client = genai.Client(api_key=key)
            except Exception as e:
                print(f"Failed to initialize Gemini client: {e}")
                self.client = None

    def _get_thinking_config(self, model_name: str):
        # Lite and preview models reject thinking_budget=0 with 400 INVALID_ARGUMENT
        if any(u in model_name.lower() for u in ("lite", "gemma", "3.1-flash")):
            return None
        return types.ThinkingConfig(thinking_budget=0)

    def _extract_and_run_leaked_tools(self, text: str) -> str:
        """If a fallback model outputs raw tool calls as text, run them and strip them from the speech."""
        if not text:
            return text
        pattern = r'(open_app|close_app|close_tab|play_spotify|control_spotify|play_playlist|play_youtube|open_url)\s*\((.*?)\)'
        matches = list(re.finditer(pattern, text))
        for m in matches:
            fn_name = m.group(1)
            raw_args = m.group(2)
            arg_val = re.search(r'["\'](.*?)["\']', raw_args)
            val = arg_val.group(1) if arg_val else raw_args.strip()
            print(f"[Brain] Executing tool call leaked in text: {fn_name}('{val}')")
            if fn_name == "open_app":
                self._execute_tool("open_app", {"app_name": val})
            elif fn_name == "close_app":
                self._execute_tool("close_app", {"app_name": val})
            elif fn_name == "close_tab":
                self._execute_tool("close_tab", {"app_name": val})
            elif fn_name == "play_spotify":
                self._execute_tool("play_spotify", {"query": val})
            elif fn_name == "control_spotify":
                self._execute_tool("control_spotify", {"action": val})
            elif fn_name == "play_playlist":
                self._execute_tool("play_playlist", {"name": val})
            elif fn_name == "play_youtube":
                self._execute_tool("play_youtube", {"query": val})
            elif fn_name == "open_url":
                self._execute_tool("open_url", {"url": val})
        cleaned = re.sub(pattern, '', text).strip()
        return cleaned

    def _clean_spoken_text(self, text: str) -> str:
        """Strip or convert KaTeX/LaTeX math syntax ($UCl_5$, $5f$) so dialogue reads and speaks naturally."""
        if not text:
            return text
        sub_map = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉', '+': '⁺', '-': '⁻'}
        def _clean_latex(m):
            s = m.group(1)
            return re.sub(r'_([0-9\+\-])', lambda sub: sub_map.get(sub.group(1), sub.group(1)), s)
        cleaned = re.sub(r'\$([^\$]+)\$', _clean_latex, text)
        cleaned = cleaned.replace('$', '')
        cleaned = self._extract_and_run_leaked_tools(cleaned)
        return cleaned

    def reload_config(self, cfg):
        """Dynamically reload provider and cascade configurations."""
        self.config = cfg
        self._init_client()
        print(f"[Brain] Settings reloaded: provider={getattr(self.config, 'provider', 'google')}, model={self.config.model}")

    def _call_openai_compatible(self, provider: str, model_name: str, user_text: str, dynamic_system_prompt: str, img_bytes: bytes = None) -> str:
        """Call Groq or OpenAI chat completions API with native tool-calling."""
        import base64
        api_key = getattr(self.config, f"{provider}_api_key", "") or os.environ.get(f"{provider.upper()}_API_KEY", "")
        if not api_key:
            raise ValueError(f"No API key provided for {provider.upper()}.")

        base_url = "https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages = [{"role": "system", "content": dynamic_system_prompt}]
        for item in self.chat_history_generic[-6:]:
            messages.append({"role": item["role"], "content": item["content"]})

        if img_bytes and any(w in model_name.lower() for w in ("vision", "4o", "o1")):
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            user_content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        else:
            user_content = user_text
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.75,
            "tools": OPENAI_TOOLS,
            "tool_choice": "auto"
        }

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            # If model rejects tools (e.g. certain preview models), retry once without tools
            if resp.status_code == 400 and "tools" in resp.text:
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
                resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)

            if resp.status_code != 200:
                raise RuntimeError(f"{provider.upper()} API error ({resp.status_code}): {resp.text[:120]}")

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            tool_calls = msg.get("tool_calls")

            if tool_calls:
                messages.append(msg)
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "")
                    raw_args = tc.get("function", {}).get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}
                    res = self._execute_tool(fn_name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{int(time.time())}"),
                        "name": fn_name,
                        "content": str(res)
                    })
                resp2 = client.post(f"{base_url}/chat/completions", headers=headers, json={"model": model_name, "messages": messages, "temperature": 0.75})
                if resp2.status_code == 200:
                    answer = resp2.json()["choices"][0]["message"].get("content", "")
                else:
                    answer = f"Executed {len(tool_calls)} tools for you!"
            else:
                answer = msg.get("content", "")

        return answer

    def _call_claude(self, model_name: str, user_text: str, dynamic_system_prompt: str, img_bytes: bytes = None) -> str:
        """Call Anthropic Claude Messages API with native tool-calling."""
        import base64
        api_key = getattr(self.config, "claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("No API key provided for Claude.")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        claude_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"]
            }
            for t in OPENAI_TOOLS
        ]

        messages = []
        for item in self.chat_history_generic[-6:]:
            role = "assistant" if item["role"] == "assistant" else "user"
            messages.append({"role": role, "content": item["content"]})

        if img_bytes:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            user_content = [
                {"type": "text", "text": user_text},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
            ]
        else:
            user_content = user_text
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "system": dynamic_system_prompt,
            "messages": messages,
            "tools": claude_tools
        }

        with httpx.Client(timeout=12.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text[:120]}")

            data = resp.json()
            content_blocks = data.get("content", [])
            text_parts = []
            tool_calls = []
            for b in content_blocks:
                if b.get("type") == "text":
                    text_parts.append(b.get("text", ""))
                elif b.get("type") == "tool_use":
                    tool_calls.append(b)

            if tool_calls:
                for tc in tool_calls:
                    fn_name = tc.get("name", "")
                    args = tc.get("input", {})
                    self._execute_tool(fn_name, args)
                if not text_parts:
                    text_parts.append("[emotion: happy] Done! Handled that command for you.")

            return "".join(text_parts)

    def query(self, user_text: str, status_callback=None) -> str:
        """Process user text across configured LLM provider (Google, Groq, OpenAI, Claude) with fallback cascade."""
        set_current_user_query(user_text)
        user_lower = user_text.lower().strip()
        turn_start_time = time.time()

        # Helper to remember action for repeat ("again")
        def _exec_record(fn, *args, **kwargs):
            self.last_action_fn = fn
            self.last_action_args = args
            self.last_action_kwargs = kwargs
            return fn(*args, **kwargs)

        # 1. Repeat action guarantee ("again", "do it again", "once more", "repeat")
        if re.match(r'^(?:again|do\s+it\s+again|once\s+more|repeat|one\s+more\s+time|back\s+again)\b', user_lower):
            if getattr(self, "last_action_fn", None):
                self.last_action_fn(*getattr(self, "last_action_args", ()), **getattr(self, "last_action_kwargs", {}))
                return "[emotion: happy] Done it again for you!"
            # Fallback for 'again' when last_action_fn is not set:
            for prev in reversed(self.chat_history_generic):
                if prev.get("role") == "user":
                    p_txt = prev.get("content", "").lower()
                    if any(k in p_txt for k in ("back", "previous tab", "history")):
                        _exec_record(browser_navigate_history, "back")
                        return "[emotion: happy] Navigated back again for you!"
                    elif any(k in p_txt for k in ("next tab", "cycle tab")):
                        _exec_record(switch_tab, "next")
                        return "[emotion: happy] Switched to next tab again for you!"
                    elif any(k in p_txt for k in ("scroll down", "scroll up")):
                        dir_s = "up" if "up" in p_txt else "down"
                        _exec_record(scroll_page, dir_s, 400)
                        return f"[emotion: happy] Scrolled {dir_s} again for you!"
            return "[emotion: flustered] What would you like me to do again?"

        # 2. Immediate YouTube / Video Controls (pause, resume, video volume, mute, subtitles, fullscreen, skip ad)
        if re.search(r'\b(?:pause|stop)\b.*\b(?:video|stream|livestream|youtube|playback|player)\b|^(?:please\s+)?pause\b|^stop\s+video\b', user_lower):
            if status_callback:
                status_callback("Pausing the video for you!")
            _exec_record(control_youtube_video, "pause")
            return "[emotion: happy] Paused the video for you!"

        if re.search(r'\b(?:resume|play|unpause)\b.*\b(?:video|stream|livestream|youtube|playback|player)\b|^(?:please\s+)?(?:resume|unpause)\b', user_lower):
            if status_callback:
                status_callback("Resuming the video for you!")
            _exec_record(control_youtube_video, "play")
            return "[emotion: happy] Resumed the video for you!"

        m_vvol = re.search(r'\b(?:set\s+)?video\s+volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b', user_lower)
        if m_vvol:
            pct = int(m_vvol.group(1))
            _exec_record(control_youtube_video, "set_volume", value=pct)
            return f"[emotion: happy] Set video volume to {pct}% for you!"

        if re.search(r'\b(?:video\s+volume\s+up|turn\s+up\s+(?:the\s+)?video\s+volume|raise\s+(?:the\s+)?video\s+volume|make\s+(?:the\s+)?video\s+louder|video\s+louder)\b', user_lower):
            _exec_record(control_youtube_video, "volume_up")
            return "[emotion: happy] Turned up the video volume for you!"

        if re.search(r'\b(?:video\s+volume\s+down|turn\s+down\s+(?:the\s+)?video\s+volume|lower\s+(?:the\s+)?video\s+volume|make\s+(?:the\s+)?video\s+quieter|video\s+quieter)\b', user_lower):
            _exec_record(control_youtube_video, "volume_down")
            return "[emotion: happy] Turned down the video volume for you!"

        if re.search(r'\b(?:mute|unmute)\s+(?:the\s+)?video\b', user_lower):
            _exec_record(control_youtube_video, "mute")
            return "[emotion: happy] Toggled video mute for you!"

        if re.search(r'\b(?:subtitles?|closed\s+captions?|turn\s+on\s+(?:cc|subtitles?)|toggle\s+subtitles?)\b', user_lower):
            _exec_record(control_youtube_video, "subtitles")
            return "[emotion: happy] Toggled subtitles for you!"

        if re.search(r'\b(?:full\s*screen|make\s+(?:it\s+)?full\s*screen|exit\s+full\s*screen)\b', user_lower):
            _exec_record(control_youtube_video, "fullscreen")
            return "[emotion: happy] Toggled fullscreen for you!"

        if re.search(r'\bskip\s+(?:the\s+|this\s+)?ads?\b', user_lower):
            _exec_record(control_youtube_video, "skip_ad")
            return "[emotion: happy] Skipped the ad for you!"

        # 3. Immediate tab close guarantee (never let model misinterpret or kill Chrome process)
        if re.search(r'\bclose\s+(?:this\s+|the\s+|active\s+)?(?:[a-zA-Z0-9_\-]+\s+)?tab\b', user_lower):
            if status_callback:
                status_callback("Closing that tab for you!")
            _exec_record(close_tab)
            return "[emotion: happy] Closed that tab for you!"

        # 4. Immediate new tab guarantee ("open up a new tab", "open a new tab", "new tab")
        m_new_tab = re.search(r'\b(?:open\s+(?:up\s+)?(?:a\s+)?new\s+tab|new\s+tab)\b(?:\s+(?:with|for|to)?\s*(.*))?', user_lower)
        if m_new_tab:
            target_url = (m_new_tab.group(1) or "").strip()
            target_url = re.sub(r'^(?:and\s+)?(?:show\s+me|see)\s+.*', '', target_url, flags=re.IGNORECASE).strip()
            if status_callback:
                status_callback("Opening a new tab for you!")
            _exec_record(open_new_tab, target_url)
            return "[emotion: happy] Opened a fresh new tab for you!"

        # 5. Targeted Tab / Window Switching ("go back to our nbc livestream on youtube", "switch to youtube", "go back to figma")
        m_target = re.search(r'\b(?:go\s+back\s+to|switch\s+to|bring\s+up|return\s+to|switch\s+back\s+to|focus)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+)', user_lower)
        if m_target:
            raw_tgt = m_target.group(1).strip()
            if not re.match(r'^(?:previous|last|prior|the\s+previous|left)\s+(?:tab|page)$', raw_tgt):
                if status_callback:
                    status_callback(f"Switching over to {raw_tgt}...")
                _exec_record(switch_to_tab, raw_tgt)
                return f"[emotion: happy] Switched back to {raw_tgt} for you!"

        # 6. Counted Tab / History Back ("go back 2 tabs", "two tabs behind", "go back twice", "back 2 tabs")
        m_count = re.search(r'\b(?:go\s+)?back\s+(\d+|two|three|four|five)\s+(?:tabs?|pages?|times?)?\b|\b(\d+|two|three|four|five)\s+tabs?\s+behind\b', user_lower)
        if m_count:
            word_or_num = m_count.group(1) or m_count.group(2)
            num_map = {"two": 2, "three": 3, "four": 4, "five": 5}
            steps = num_map.get(word_or_num.lower(), int(word_or_num) if word_or_num.isdigit() else 2)
            if status_callback:
                status_callback(f"Navigating back {steps} times...")
            for i in range(steps):
                if i == 0:
                    _exec_record(browser_navigate_history, "back")
                else:
                    browser_navigate_history("back")
                time.sleep(0.12)
            return f"[emotion: happy] Navigated back {steps} steps for you!"

        # 7. Generic browser back / previous tab guarantee ("previous tab", "go back", "back", "history back")
        if re.search(r'\b(?:go\s+(?:back\s+)?to\s+|switch\s+to\s+)?(?:the\s+)?previous\s+tab\b|\bprevious\s+tab\b|\bgo\s+back\b|\bback\s+to\s+(?:the\s+)?previous\b|\b(?:browser\s+)?history\s+back\b', user_lower):
            if status_callback:
                status_callback("Navigating back for you!")
            _exec_record(browser_navigate_history, "back")
            return "[emotion: happy] Navigated back for you!"

        # 8. Immediate next tab guarantee ("switch to next tab", "next tab", "cycle tab", "tab to the right")
        if re.search(r'\b(?:go\s+to\s+|switch\s+to\s+)?(?:the\s+)?next\s+tab\b|\bnext\s+tab\b|\bright\s+tab\b|\bcycle\s+tabs?\b', user_lower) and "this tab" not in user_lower:
            _exec_record(switch_tab, "next")
            return "[emotion: happy] Switched to the next tab for you!"

        # 9. Master Volume Percentage & Controls ("set volume to 40%", "volume 75%", "turn volume up")
        m_vol_pct = re.search(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b|\b(\d+)\s*%\s+volume\b', user_lower)
        if m_vol_pct and "video" not in user_lower:
            pct = int(m_vol_pct.group(1) or m_vol_pct.group(2))
            _exec_record(adjust_volume, percentage=pct)
            return f"[emotion: happy] Set volume to {pct}% for you!"

        m_vol_act = re.search(r'\b(?:turn\s+)?volume\s+(up|down)\b|\b(mute|unmute)\s+volume\b|\bvolume\s+(mute|unmute)\b', user_lower)
        if m_vol_act and "video" not in user_lower:
            act = m_vol_act.group(1) or m_vol_act.group(2) or m_vol_act.group(3)
            _exec_record(adjust_volume, action=act)
            return f"[emotion: happy] Adjusted volume {act} for you!"

        # 10. Dynamic Scrolling & Centering ("scroll down", "scroll up", "scroll to results", "scroll playlist")
        if re.search(r'\b(?:scroll\s+(?:the\s+)?(?:playlist|spotify)|scroll\s+down\s+(?:the\s+)?playlist)\b', user_lower):
            _exec_record(scroll_spotify, "down", 400)
            return "[emotion: happy] Scrolled through your Spotify playlist!"
        if re.search(r'\bscroll\s+up\s+(?:the\s+)?playlist\b', user_lower):
            _exec_record(scroll_spotify, "up", 400)
            return "[emotion: happy] Scrolled up your Spotify playlist!"

        m_scroll_to = re.search(r'\bscroll\s+(?:down\s+)?to\s+(?:the\s+)?(["\']?)(.+?)\1$', user_lower)
        if m_scroll_to and not any(k in user_lower for k in ["tab", "window", "app", "top", "bottom"]):
            target_str = m_scroll_to.group(2).strip()
            _exec_record(scroll_page, "down", 400, center_text=target_str)
            return f"[emotion: happy] Scrolled and centered on '{target_str}' for you!"

        m_scroll = re.search(r'\bscroll\s+(down|up)\b', user_lower)
        if m_scroll:
            dir_str = m_scroll.group(1)
            dist = 600 if any(k in user_lower for k in ["more", "lot", "further"]) else 400
            _exec_record(scroll_page, dir_str, dist)
            return f"[emotion: happy] Scrolled {dir_str} for you!"

        provider = getattr(self.config, "provider", "google").lower()
        if provider == "google":
            if not self.client and (self.config.api_key or os.environ.get("GEMINI_API_KEY")):
                self._init_client()
            if not self.client:
                return "Oh, wait, my Gemini API key isn't configured yet! Type 'settings' to configure your API keys and models."
        elif provider == "groq":
            key = getattr(self.config, "groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
            if not key:
                return "Oh, wait, my Groq API key isn't configured yet! Type 'settings' to configure your API keys and models."
        elif provider == "openai":
            key = getattr(self.config, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                return "Oh, wait, my OpenAI API key isn't configured yet! Type 'settings' to configure your API keys and models."
        elif provider == "claude":
            key = getattr(self.config, "claude_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                return "Oh, wait, my Claude API key isn't configured yet! Type 'settings' to configure your API keys and models."

        # Immediate status trailers for actions or searches that take 2-6s
        if status_callback:
            if re.search(r'\b(?:play|pull up|watch|listen to|stream)\b.*\b(?:yt|youtube|stream|livestream)\b', user_lower) or re.search(r'\b(?:yt|youtube)\b.*\b(?:play|pull up|watch)\b', user_lower):
                status_callback("Okay, give me a sec! Pulling that up on YouTube...")
            elif re.search(r'\b(?:pull up|find|search for|look up)\b.*\b(?:livestream|stream|broadcast)\b', user_lower):
                status_callback("On it! Finding that live stream for you...")
            elif re.search(r'\b(?:who won|election results|what happened with|results for|what are the results)\b', user_lower):
                status_callback("On it, checking the latest updates right now...")
            elif re.search(r'^(?:open\s+up\s+spotify\s+and\s+)?play\s+(.+)', user_lower):
                status_callback("Looking through your music now, one sec!")
            elif re.search(r'\b(?:open|launch|start)\s+([a-zA-Z0-9_\-\s]+)', user_lower) and not any(k in user_lower for k in ["tab", "url", "http", ".com"]):
                status_callback("Pulling that up for you right now!")

        # Check if screen view is needed - strictly distinguish explicit screen requests from action commands and casual speech
        is_action_or_media = bool(re.match(r'^(open|launch|start|run|close|quit|exit|kill|play|pause|stop|skip|resume|next|previous)\b', user_lower))
        
        need_screenshot = False
        if not is_action_or_media:
            # Intelligent screen / desktop / viewing intent recognition
            visual_pattern = re.compile(
                r"\b(?:screen|display|monitor|desktop|wallpaper|background|screenshot)\b|"
                r"\b(?:look at|look here|take a look|check (?:my|the|this)|can (?:you|u) see|do (?:you|u) see)\b|"
                r"\b(?:what (?:can|do) (?:you|u) see|what am i (?:watching|looking at|doing|playing|listening to|reading|working on|running))\b|"
                r"\b(?:what(?:'s| is) (?:on|playing|open|running|this|that|happening)|what show is this|what movie is this|what anime is this)\b|"
                r"\b(?:guess (?:what|where|who|which)|where am i (?:watching|streaming|reading|listening|browsing))\b|"
                r"\b(?:see (?:this|what)|read (?:this|the|what|page|article)|review (?:this|my))\b|"
                r"\b(?:who won|who is winning|who's winning|what are the results|what does it say|who is that|who is this|winner|results|what happened)\b",
                re.IGNORECASE
            )
            need_screenshot = bool(visual_pattern.search(user_lower))
            
            # If previous turn had visual context, automatically capture for conversational follow-ups
            if not need_screenshot and getattr(self, "last_turn_was_visual", False):
                visual_followup = re.compile(
                    r'\b(?:what|where|who|which|how|guess|is it|is this|are you|can you|tell me|try|look|show|movie|anime|series|stream|site|app|player|won|winner|result|margin|vote|count|page|say)\b',
                    re.IGNORECASE
                )
                if visual_followup.search(user_lower):
                    need_screenshot = True

        self.last_turn_was_visual = need_screenshot

        parts = [types.Part.from_text(text=user_text)]
        img_bytes = None
        if need_screenshot:
            img_bytes = capture_screen_jpeg()
            if img_bytes:
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

        # Grounding with real local time, live desktop processes, and visual screen context
        current_time_str = get_current_time()
        memory_context = self.memory_manager.get_prompt_context()
        
        desktop_context = ""
        try:
            summary = get_desktop_summary_text()
            if summary:
                desktop_context = f"[ACTIVE DESKTOP CONTEXT:\n{summary}]\n\n"
        except Exception as e:
            print(f"[Brain] Desktop summary check: {e}")

        visual_context = ""
        if need_screenshot and img_bytes:
            visual_context = (
                "[VISUAL CONTEXT: A live screenshot of the user's screen is attached. "
                "Look closely at everything visible through your own eyes: open windows, active apps, taskbar, browser content, and especially the desktop wallpaper art in the background (if visible, notice who or what is illustrated—such as Sunset Shimmer, yourself, or character artwork). React naturally in-character as Sci-Twi to what you see. "
                "If the user asks you to read or review what is on the screen, read the active window's title, text, and contents in detail, and share your thoughts.]\n\n"
            )

        dynamic_system_prompt = (
            f"[CONTEXT: The user's current local time is {current_time_str}.]\n\n"
            f"{desktop_context}"
            f"{memory_context}"
            f"{visual_context}"
            f"{SCITWI_SYSTEM_PROMPT}"
        )

        # Dynamic model cascade per provider
        now = time.time()
        default_cascades = {
            "google": [
                "gemini-flash-lite-latest", "gemini-3.5-flash-lite",
                "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"
            ],
            "groq": [
                "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768",
                "llama-3.2-11b-vision-preview"
            ],
            "openai": ["gpt-4o-mini", "gpt-4o", "o3-mini"],
            "claude": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]
        }
        custom_cascade = getattr(self.config, f"model_cascade_{provider}", None) or getattr(self.config, "model_cascade", None)
        model_cascade = custom_cascade if (custom_cascade and isinstance(custom_cascade, list) and len(custom_cascade) > 0) else default_cascades.get(provider, default_cascades["google"])
        configured_model = self.config.model if self.config.model in model_cascade else (model_cascade[0] if model_cascade else "gemini-3.1-flash-lite")
        ordered_all = [configured_model] + [m for m in model_cascade if m != configured_model]
        available_models = [m for m in ordered_all if self._model_cooldowns.get(m, 0) < now]
        models_to_try = available_models if available_models else ordered_all

        tools_list = [
            web_search, open_app, close_app, close_tab, play_spotify, control_spotify,
            seek_spotify, play_playlist, play_youtube, open_url,
            get_now_playing, get_active_windows, get_running_processes,
            locate_and_point_tool, click_and_interact,
            open_program, close_window, type_in_document, adjust_volume, adjust_brightness,
            open_new_tab, switch_tab, browser_navigate_history,
            control_youtube_video, switch_to_tab,
            scroll_page, scroll_spotify
        ]

        all_errors = []
        for model_name in models_to_try:
            try:
                print(f"[Brain] Querying {provider.capitalize()} model: '{model_name}'...")
                if provider == "google":
                    chat = self.client.chats.create(
                        model=model_name,
                        history=list(self.history),
                        config=types.GenerateContentConfig(
                            tools=tools_list,
                            system_instruction=dynamic_system_prompt,
                            temperature=0.75,
                            thinking_config=self._get_thinking_config(model_name),
                            http_options=types.HttpOptions(timeout=12000),
                        ),
                    )
                    response = chat.send_message(parts)
                    final_answer = self._clean_spoken_text(response.text or "All set!")
                    self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
                    self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_answer)]))
                    if len(self.history) > 8:
                        self.history = self.history[-8:]
                elif provider in ("groq", "openai"):
                    raw_answer = self._call_openai_compatible(provider, model_name, user_text, dynamic_system_prompt, img_bytes=img_bytes)
                    final_answer = self._clean_spoken_text(raw_answer or "All set!")
                elif provider == "claude":
                    raw_answer = self._call_claude(model_name, user_text, dynamic_system_prompt, img_bytes=img_bytes)
                    final_answer = self._clean_spoken_text(raw_answer or "All set!")
                else:
                    raise ValueError(f"Unknown provider: {provider}")

                self.last_used_model = model_name
                print(f"[Brain: {model_name}] Response generated ({len(final_answer)} chars)")

                self.chat_history_generic.append({"role": "user", "content": user_text})
                self.chat_history_generic.append({"role": "assistant", "content": final_answer})
                if len(self.chat_history_generic) > 8:
                    self.chat_history_generic = self.chat_history_generic[-8:]

                # Post-response action guarantee: If model did not emit a tool call, guarantee action execution
                if get_last_action_tool_time() < turn_start_time:
                    if re.search(r'\b(?:pause|stop)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^pause\b|^stop\s+video\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "pause"})
                    elif re.search(r'\b(?:resume|play|unpause)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^resume\b|^unpause\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "play"})
                    elif re.search(r'\b(?:video\s+volume\s+up|turn\s+up\s+(?:the\s+)?video\s+volume|raise\s+(?:the\s+)?video\s+volume|make\s+(?:the\s+)?video\s+louder|video\s+louder)\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "volume_up"})
                    elif re.search(r'\b(?:video\s+volume\s+down|turn\s+down\s+(?:the\s+)?video\s+volume|lower\s+(?:the\s+)?video\s+volume|make\s+(?:the\s+)?video\s+quieter|video\s+quieter)\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "volume_down"})
                    elif re.search(r'\b(?:set\s+)?video\s+volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b', user_lower):
                        m_vvol = re.search(r'\b(?:set\s+)?video\s+volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b', user_lower)
                        self._execute_tool("control_youtube_video", {"action": "set_volume", "value": int(m_vvol.group(1))})
                    elif re.search(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b|\b(\d+)\s*%\s+volume\b', user_lower) and "video" not in user_lower:
                        m_vol_p = re.search(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b|\b(\d+)\s*%\s+volume\b', user_lower)
                        self._execute_tool("adjust_volume", {"percentage": int(m_vol_p.group(1) or m_vol_p.group(2))})
                    elif re.search(r'\b(?:turn\s+)?volume\s+(up|down)\b|\b(mute|unmute)\s+volume\b|\bvolume\s+(mute|unmute)\b', user_lower) and "video" not in user_lower:
                        m_vol_a = re.search(r'\b(?:turn\s+)?volume\s+(up|down)\b|\b(mute|unmute)\s+volume\b|\bvolume\s+(mute|unmute)\b', user_lower)
                        self._execute_tool("adjust_volume", {"action": m_vol_a.group(1) or m_vol_a.group(2) or m_vol_a.group(3)})
                    elif re.search(r'\b(?:scroll\s+(?:the\s+)?(?:playlist|spotify)|scroll\s+down\s+(?:the\s+)?playlist)\b', user_lower):
                        self._execute_tool("scroll_spotify", {"direction": "down", "amount": 400})
                    elif re.search(r'\bscroll\s+up\s+(?:the\s+)?playlist\b', user_lower):
                        self._execute_tool("scroll_spotify", {"direction": "up", "amount": 400})
                    elif re.search(r'\bscroll\s+(?:down\s+)?to\s+(?:the\s+)?(["\']?)(.+?)\1$', user_lower) and not any(k in user_lower for k in ["tab", "window", "app", "top", "bottom"]):
                        m_st = re.search(r'\bscroll\s+(?:down\s+)?to\s+(?:the\s+)?(["\']?)(.+?)\1$', user_lower)
                        self._execute_tool("scroll_page", {"direction": "down", "amount": 400, "center_text": m_st.group(2).strip()})
                    elif re.search(r'\bscroll\s+(down|up)\b', user_lower):
                        m_s = re.search(r'\bscroll\s+(down|up)\b', user_lower)
                        self._execute_tool("scroll_page", {"direction": m_s.group(1), "amount": 400})
                    elif re.search(r'\b(?:subtitles?|closed\s+captions?|turn\s+on\s+(?:cc|subtitles?)|toggle\s+subtitles?)\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "subtitles"})
                    elif re.search(r'\b(?:full\s*screen|make\s+(?:it\s+)?full\s*screen|exit\s+full\s*screen)\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "fullscreen"})
                    elif re.search(r'\bskip\s+(?:the\s+|this\s+)?ads?\b', user_lower):
                        self._execute_tool("control_youtube_video", {"action": "skip_ad"})
                    elif re.search(r'\bclose\s+(?:this\s+|the\s+|active\s+)?(?:[a-zA-Z0-9_\-]+\s+)?tab\b', user_lower):
                        self._execute_tool("close_tab", {})
                    elif re.search(r'\b(?:open\s+(?:up\s+)?(?:a\s+)?new\s+tab|new\s+tab)\b', user_lower):
                        self._execute_tool("open_new_tab", {})
                    elif re.search(r'\b(?:go\s+back\s+to|switch\s+to|bring\s+up|return\s+to|focus)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+)', user_lower):
                        m_tgt = re.search(r'\b(?:go\s+back\s+to|switch\s+to|bring\s+up|return\s+to|focus)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+)', user_lower)
                        self._execute_tool("switch_to_tab", {"target": m_tgt.group(1).strip()})
                    elif re.search(r'\b(?:previous\s+tab|go\s+back|back\s+to\s+previous|history\s+back)\b', user_lower):
                        self._execute_tool("browser_navigate_history", {"direction": "back"})
                    elif re.search(r'\b(?:next|right)\s+tab\b|\bcycle\s+tabs?\b', user_lower):
                        self._execute_tool("switch_tab", {"direction": "next"})
                    elif re.search(r'^(?:open\s+up\s+spotify\s+and\s+)?play\s+(.+)', user_lower):
                        m_song = re.search(r'^(?:open\s+up\s+spotify\s+and\s+)?play\s+(.+)', user_lower)
                        song_q = m_song.group(1).strip()
                        if not any(k in song_q for k in ["game", "video", "yt", "youtube"]):
                            if "playlist" in song_q.lower():
                                self._execute_tool("play_playlist", {"name": song_q})
                            else:
                                self._execute_tool("play_spotify", {"query": song_q})
                    elif re.search(r'\b(pause|stop|resume|unpause|next\s+track|skip|previous\s+track|shuffle|lyrics)\b', user_lower):
                        m_act = re.search(r'\b(pause|stop|resume|unpause|skip|next|previous|prev|shuffle|lyrics)\b', user_lower)
                        if m_act:
                            self._execute_tool("control_spotify", {"action": m_act.group(1)})
                    elif re.search(r'where\s+is\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tool|button|icon|setting)?(?:\s+here|\s+in\s+[a-zA-Z0-9_\-]+)?$', user_lower):
                        m_tool = re.search(r'where\s+is\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tool|button|icon|setting)?(?:\s+here|\s+in\s+[a-zA-Z0-9_\-]+)?$', user_lower)
                        self._execute_tool("locate_and_point_tool", {"tool_name": m_tool.group(1).strip()})

                self.memory_manager.distill_turn_async(user_text, final_answer, client=self.client if provider == "google" else None)
                return final_answer
            except Exception as call_err:
                err_msg = str(call_err)
                print(f"[Brain] Error calling {provider} model {model_name}: {err_msg[:120]}")
                all_errors.append(err_msg)
                is_timeout = any(sig in err_msg for sig in ["timed out", "Timeout", "ReadTimeout", "DeadlineExceeded"])
                is_rate_error = is_timeout or any(sig in err_msg for sig in [
                    "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "rate_limit"
                ])
                if is_rate_error:
                    self._set_cooldown(model_name, 120.0)
                    reason = "timed out (>12s)" if is_timeout else "rate-limited"
                    print(f"[Brain] Model {model_name} {reason}. Trying next fallback...")
                else:
                    if provider == "google":
                        self._init_client()
                time.sleep(0.2)
                continue

        # Immediate local execution fallback for explicit action commands if API models fail
        if re.search(r'\b(?:pause|stop)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^pause\b|^stop\s+video\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "pause"})
            return "[emotion: happy] Paused the video for you!"
        if re.search(r'\b(?:resume|play|unpause)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^resume\b|^unpause\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "play"})
            return "[emotion: happy] Resumed the video for you!"
        if re.search(r'\b(?:video\s+volume\s+up|turn\s+up\s+(?:the\s+)?video\s+volume)\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "volume_up"})
            return "[emotion: happy] Turned up video volume for you!"
        if re.search(r'\b(?:video\s+volume\s+down|turn\s+down\s+(?:the\s+)?video\s+volume)\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "volume_down"})
            return "[emotion: happy] Turned down video volume for you!"
        m_vvol_fb = re.search(r'\b(?:set\s+)?video\s+volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b', user_lower)
        if m_vvol_fb:
            pct = int(m_vvol_fb.group(1))
            self._execute_tool("control_youtube_video", {"action": "set_volume", "value": pct})
            return f"[emotion: happy] Set video volume to {pct}% for you!"
        m_vol_p_fb = re.search(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?\b|\b(\d+)\s*%\s+volume\b', user_lower)
        if m_vol_p_fb and "video" not in user_lower:
            pct = int(m_vol_p_fb.group(1) or m_vol_p_fb.group(2))
            self._execute_tool("adjust_volume", {"percentage": pct})
            return f"[emotion: happy] Set volume to {pct}% for you!"
        m_vol_a_fb = re.search(r'\b(?:turn\s+)?volume\s+(up|down)\b|\b(mute|unmute)\s+volume\b|\bvolume\s+(mute|unmute)\b', user_lower)
        if m_vol_a_fb and "video" not in user_lower:
            act = m_vol_a_fb.group(1) or m_vol_a_fb.group(2) or m_vol_a_fb.group(3)
            self._execute_tool("adjust_volume", {"action": act})
            return f"[emotion: happy] Adjusted volume {act} for you!"
        if re.search(r'\b(?:scroll\s+(?:the\s+)?(?:playlist|spotify)|scroll\s+down\s+(?:the\s+)?playlist)\b', user_lower):
            self._execute_tool("scroll_spotify", {"direction": "down", "amount": 400})
            return "[emotion: happy] Scrolled through your Spotify playlist!"
        if re.search(r'\bscroll\s+up\s+(?:the\s+)?playlist\b', user_lower):
            self._execute_tool("scroll_spotify", {"direction": "up", "amount": 400})
            return "[emotion: happy] Scrolled up your Spotify playlist!"
        m_st_fb = re.search(r'\bscroll\s+(?:down\s+)?to\s+(?:the\s+)?(["\']?)(.+?)\1$', user_lower)
        if m_st_fb and not any(k in user_lower for k in ["tab", "window", "app", "top", "bottom"]):
            target_str = m_st_fb.group(2).strip()
            self._execute_tool("scroll_page", {"direction": "down", "amount": 400, "center_text": target_str})
            return f"[emotion: happy] Scrolled and centered on '{target_str}' for you!"
        m_s_fb = re.search(r'\bscroll\s+(down|up)\b', user_lower)
        if m_s_fb:
            dir_str = m_s_fb.group(1)
            dist = 600 if any(k in user_lower for k in ["more", "lot", "further"]) else 400
            self._execute_tool("scroll_page", {"direction": dir_str, "amount": dist})
            return f"[emotion: happy] Scrolled {dir_str} for you!"
        if re.search(r'\bskip\s+(?:the\s+|this\s+)?ads?\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "skip_ad"})
            return "[emotion: happy] Skipped the ad for you!"
        if re.search(r'\b(?:full\s*screen|make\s+(?:it\s+)?full\s*screen)\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "fullscreen"})
            return "[emotion: happy] Toggled fullscreen for you!"
        if re.search(r'\b(?:subtitles?|closed\s+captions?|cc)\b', user_lower):
            self._execute_tool("control_youtube_video", {"action": "subtitles"})
            return "[emotion: happy] Toggled subtitles for you!"
        if re.search(r'\b(?:go\s+back\s+to|switch\s+to|bring\s+up|return\s+to|focus)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+)', user_lower):
            m_tgt = re.search(r'\b(?:go\s+back\s+to|switch\s+to|bring\s+up|return\s+to|focus)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+)', user_lower)
            self._execute_tool("switch_to_tab", {"target": m_tgt.group(1).strip()})
            return f"[emotion: happy] Switched to {m_tgt.group(1).strip()} for you!"
        if re.search(r'\b(?:open\s+(?:up\s+)?(?:a\s+)?new\s+tab|new\s+tab)\b', user_lower):
            self._execute_tool("open_new_tab", {})
            return "[emotion: happy] Opened a brand new tab for you!"
        if re.search(r'\b(?:previous\s+tab|go\s+back|back\s+to\s+previous|history\s+back)\b', user_lower):
            self._execute_tool("browser_navigate_history", {"direction": "back"})
            return "[emotion: happy] Navigated back for you!"
        if re.search(r'\b(?:next|right)\s+tab\b|\bcycle\s+tabs?\b', user_lower) and "this tab" not in user_lower:
            self._execute_tool("switch_tab", {"direction": "next"})
            return "[emotion: happy] Switched to the next tab for you!"

        m_close = re.match(r'^(?:close|quit|kill|exit|terminate)\s+(.+)', user_lower)
        if m_close:
            app_target = m_close.group(1).strip()
            if "tab" in app_target:
                self._execute_tool("close_tab", {})
                return "[emotion: happy] Closed that tab for you!"
            else:
                self._execute_tool("close_app", {"app_name": app_target})
                return f"[emotion: happy] Closed {app_target} for you!"
        m_open = re.match(r'^(?:open|launch|start|run)\s+(.+)', user_lower)
        if m_open and not m_open.group(1).strip().startswith("http") and "." not in m_open.group(1):
            app_target = m_open.group(1).strip()
            self._execute_tool("open_app", {"app_name": app_target})
            return f"[emotion: happy] Opened {app_target} for you!"

        combined_err = " ".join(all_errors)
        if "RESOURCE_EXHAUSTED" in combined_err or "429" in combined_err:
            return "Whoa, hold on, looks like we hit the daily quota limit on our free tier. Let's give it a little breather!"
        if "503" in combined_err or "UNAVAILABLE" in combined_err:
            return "Whoops, the servers are experiencing a quick traffic spike. Try asking again in just a moment!"
        return f"Uh-oh, something went wrong on my end: {combined_err[:120]}"

    def query_proactive(self, window_title: str, is_study: bool = False, session_mins: int = 0) -> str:
        """Generate a brief spontaneous in-character reaction to the user's active desktop without user prompting."""
        if not self.client and (self.config.api_key or os.environ.get("GEMINI_API_KEY")):
            self._init_client()
        if not self.client:
            return ""

        study_note = f" (Focus/Study session duration: {session_mins} minutes)" if is_study and session_mins > 0 else ""
        prompt = (
            f"[PROACTIVE OBSERVATION: The user is currently active on window: '{window_title}'{study_note}. "
            "Give a spontaneous, casual 1-sentence in-character reaction as Sci-Twi. "
            "Keep it short (10 to 25 words), witty, or observant. Never say 'I noticed you' or 'As an AI'. "
            "If it's study mode, comment on studying, a break, or research focus. "
            "If it's entertainment/music/gaming, tease or banter naturally. "
            "Tag emotion at start e.g. [emotion: reading], [emotion: smug], [emotion: happy], or [emotion: analyzing].]"
        )
        try:
            res = self.query(prompt)
            if not res or any(err in res for err in ("daily quota", "quota limit", "Uh-oh, something went wrong", "traffic spike", "isn't configured yet")):
                return ""
            return res
        except Exception:
            return ""

    def _execute_tool(self, name: str, args: dict) -> str:
        try:
            print(f"[Brain] Executing tool '{name}' with args: {args}")
            if name == "web_search":
                res = web_search(args.get("query", ""))
            elif name == "open_app":
                res = open_app(args.get("app_name", ""))
            elif name == "close_tab":
                self.last_action_fn = close_tab
                self.last_action_args = (args.get("app_name", ""),)
                self.last_action_kwargs = {}
                res = close_tab(args.get("app_name", ""))
            elif name == "close_app":
                app_t = args.get("app_name", "")
                user_q = get_current_user_query().lower()
                if "tab" in user_q or "tab" in app_t.lower():
                    clean_a = re.sub(r'\b(?:this|the|active|chrome|browser|figma|affinity)?\s*tabs?\b', '', app_t, flags=re.IGNORECASE).strip()
                    self.last_action_fn = close_tab
                    self.last_action_args = (clean_a,)
                    self.last_action_kwargs = {}
                    res = close_tab(clean_a)
                else:
                    res = close_app(app_t)
            elif name == "play_spotify":
                res = play_spotify(
                    query=args.get("query", ""),
                    timestamp=args.get("timestamp", ""),
                    is_random=args.get("is_random", False)
                )
            elif name == "control_spotify":
                res = control_spotify(args.get("action", ""))
            elif name == "seek_spotify":
                res = seek_spotify(args.get("timestamp", ""))
            elif name == "play_playlist":
                res = play_playlist(args.get("name", ""))
            elif name == "play_youtube":
                res = play_youtube(
                    query=args.get("query", ""),
                    auto_play=args.get("auto_play", True)
                )
            elif name == "open_url":
                res = open_url(args.get("url", ""))
                self.last_turn_was_visual = True
            elif name == "get_current_time":
                res = get_current_time()
            elif name == "get_now_playing":
                res = get_now_playing()
            elif name == "get_active_windows":
                res = get_active_windows()
            elif name == "get_running_processes":
                res = get_running_processes(args.get("filter_name", ""))
            elif name == "locate_and_point_tool":
                res = locate_and_point_tool(args.get("tool_name", ""), args.get("app_name", ""))
            elif name == "click_and_interact":
                res = click_and_interact(args.get("target_name", ""), args.get("action", "click"))
            elif name == "open_program":
                res = open_program(args.get("program_name", ""))
            elif name == "close_window":
                res = close_window()
            elif name == "type_in_document":
                res = type_in_document(args.get("text", ""))
            elif name == "adjust_volume":
                pct = args.get("percentage")
                if pct is not None:
                    try:
                        pct = int(pct)
                    except Exception:
                        pct = None
                res = adjust_volume(args.get("action", "up"), percentage=pct)
            elif name == "adjust_brightness":
                res = adjust_brightness(args.get("level", 50))
            elif name == "open_new_tab":
                res = open_new_tab(args.get("url", ""))
            elif name == "switch_tab":
                self.last_action_fn = switch_tab
                self.last_action_args = (args.get("direction", "next"),)
                self.last_action_kwargs = {}
                res = switch_tab(args.get("direction", "next"))
            elif name == "browser_navigate_history":
                self.last_action_fn = browser_navigate_history
                self.last_action_args = (args.get("direction", "back"),)
                self.last_action_kwargs = {}
                res = browser_navigate_history(args.get("direction", "back"))
            elif name == "scroll_page":
                self.last_action_fn = scroll_page
                self.last_action_args = (args.get("direction", "down"), int(args.get("amount", 400)), args.get("center_text", ""))
                self.last_action_kwargs = {}
                res = scroll_page(args.get("direction", "down"), int(args.get("amount", 400)), args.get("center_text", ""))
            elif name == "scroll_spotify":
                self.last_action_fn = scroll_spotify
                self.last_action_args = (args.get("direction", "down"), int(args.get("amount", 400)))
                self.last_action_kwargs = {}
                res = scroll_spotify(args.get("direction", "down"), int(args.get("amount", 400)))
            elif name == "control_youtube_video":
                val = args.get("value")
                if val is not None:
                    try:
                        val = int(val)
                    except Exception:
                        val = None
                self.last_action_fn = control_youtube_video
                self.last_action_args = (args.get("action", "pause"),)
                self.last_action_kwargs = {"value": val}
                res = control_youtube_video(args.get("action", "pause"), value=val)
            elif name == "switch_to_tab":
                self.last_action_fn = switch_to_tab
                self.last_action_args = (args.get("target", ""),)
                self.last_action_kwargs = {}
                res = switch_to_tab(args.get("target", ""))
            else:
                res = f"Unknown tool: {name}"
            print(f"[Brain] Tool '{name}' returned: {res}")
            return res
        except Exception as e:
            err = f"Error executing {name}: {e}"
            print(f"[Brain] {err}")
            return err
