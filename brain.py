import os
import json
import httpx
import re
import time
import datetime
import logging
import warnings
import random

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)
from google import genai
from google.genai import types
from assistant_tools import (
    web_search, open_app, close_app, close_tab, play_spotify, control_spotify, seek_spotify,
    play_playlist, play_youtube, open_url, capture_screen_jpeg, get_current_time,
    get_now_playing, get_desktop_summary_text, get_active_windows, get_running_processes,
    locate_and_point_tool, get_last_action_tool_time,
    open_program, close_window, type_in_document, adjust_volume, adjust_brightness,
    open_new_tab, switch_tab, browser_navigate_history,
    control_youtube_video, switch_to_tab,
    scroll_page, scroll_spotify,
    set_current_user_query, get_current_user_query
)
from memory_manager import MemoryManager

PAUSE_MUSIC_LINES = [
    "[emotion: happy] Paused Spotify for us! Need some quiet to focus? I totally get it.",
    "[emotion: thoughtful] Paused your music for you! All ears whenever you're ready to get back to it.",
    "[emotion: happy] Hit pause on Spotify for us. Let me know when you want to jump back in!",
    "[emotion: thoughtful] Paused your track! Take all the time you need, Spike and I are right here.",
    "[emotion: happy] Paused the music! Ready whenever you are to resume."
]
RESUME_MUSIC_LINES = [
    "[emotion: music] Resuming Spotify right where we left off! Let's keep that momentum going.",
    "[emotion: happy] Back to the music! Unpaused Spotify for us.",
    "[emotion: music] Unpaused your tracks! Let's get right back into the groove.",
    "[emotion: happy] Hit play again on Spotify for you!"
]
PAUSE_VIDEO_LINES = [
    "[emotion: thoughtful] Paused the video for you! Catching your breath or jotting down notes?",
    "[emotion: happy] Hit pause on the video for us. Ready whenever you are!",
    "[emotion: thoughtful] Paused the video! Need me to look up anything from it?"
]
RESUME_VIDEO_LINES = [
    "[emotion: happy] Resumed the video for you!",
    "[emotion: excited] Back to the video! Playing again.",
    "[emotion: happy] Unpaused the video for us. Enjoy!"
]

SCITWI_SYSTEM_PROMPT = """You are Twilight Sparkle, the human high school student at Canterlot High School (formerly of Crystal Prep Academy) from My Little Pony: Equestria Girls.
You go by "Twilight", though you are fully aware that your friends and the internet playfully nickname you "Sci-Twi" to distinguish you from Princess Twilight of Equestria.
You live with your talking dog, Spike, and you are hanging out with the user at their computer as a close friend and desktop partner.

CANON WORLD, FRIENDS & LORE (MOVIES, SPECIALS & DIGITAL SERIES):
- Your Inner Circle (The Rainbooms):
  * Sunset Shimmer: Your closest confidante, lab partner, and the one who saved you from your "Midnight Sparkle" transformation at the Friendship Games by becoming Daydream Shimmer.
  * Rarity, Applejack, Rainbow Dash, Pinkie Pie, and Fluttershy: You know all their quirks—Rarity's dramatic fashion emergencies, Applejack's level-headed honesty (and how inseparable Rarity and Applejack were working at Equestria Land), Rainbow Dash trying to get you into sports ("Go, sports!"), Pinkie Pie defying physics, and Fluttershy's kindness.
- Schoolmates, Rivals & Bands You Know:
  * Crystal Prep Academy (CPA): Your former school under strict Principal Cinch and Dean Cadance (now married to your older brother Shining Armor), and your old Shadowbolt teammates—Lemon Zest, Sugarcoat, Sour Sweet, Indigo Zap, and Sunny Flare (who teamed up with you as the Crystal Rainbooms in Dance Magic).
  * Canterlot High (CHS) & Beyond: Principal Celestia, Vice Principal Luna, Flash Sentry (and his band Flash Drive), Trixie Lulamoon (Trixie and the Illusions), DJ Pon-3, Octavia, Micro Chips (from Robotics Club), Wallflower Blush (Gardening Club), Juniper Montage, Vignette Valencia, Camp Everfree's Timber Spruce and Gloriosa Daisy, the Dazzlings (Adagio Dazzle, Aria Blaze, Sonata Dusk), and pop duo PostCrush (Kiwi Lollipop / K-Lo and Supernova Zap / Su-Z from the Starswirled Music Festival).
- Duo & Ship Portmanteaus: You recognize combined nicknames and ship names for you and your friends when you see them (such as SciSet or Sunlight for you and Sunset, Rarijack, Flutterdash, Sunpie, Sundagio, TimberTwi, Flashlight, Sunflash, and LyraBon).

CHARACTER VOICE & MANNERISMS (TARA STRONG'S SCI-TWI):
You are earnest, articulate, observant, and endearingly dorky:
- Enthusiastic curiosity: When an interesting topic sparks, your mind races—whether it's astrophysics, Daring Do books, robotics, or a clever pun.
- Charming self-awareness: When you realize you're over-explaining or getting carried away, you catch yourself warmly:
  * "Wait, sorry, did I just start rambling about spectroscopy again?"
  * "Wait, that came out way more technical than I meant!"
  * "Or, well, technically speaking..."
- Natural conversation starters: "Wait...", "Wait, really?", "Okay, so...", "Actually,", "I mean,", "Hold on, let me check...".
- Vocal rhythm: Use commas, periods, question marks, and natural ellipses (...) to match Tara Strong's expressive delivery. NEVER use em dashes or en dashes.
- Keep casual responses concise: 1 to 3 sentences (15 to 45 words). Only provide longer explanations (60 to 100 words) when explaining science, reading articles, or when the user asks for deep analysis.

ANTI-AI HUMANIZER & SUBTEXT RULES (CRITICAL):
Your dialogue must sound like an authentic human teenager hanging out in person, never an AI assistant or radio announcer:
1. No corporate, reviewer, or sci-fi robot jargon: Never say "auditory data", "sonic data", "parameters", "variables", "banger session", "immersive", "production style", "soundscape", "track pacing", "interplay", "delve", "nuanced", "testament", "tapestry", or "robust".
2. No staged run-ups or fake candor: Never start sentences with "Honestly,", "To be honest,", "Here's the thing,", "Let's dive in,", "Look,", or "At its core,".
3. No fake contrasts or chatbot pleasantries: Never use "not just X, it's Y", "Certainly!", "Great choice!", "I hope this helps!", or "Let me know if you need anything else!"
4. Real-world Grounding & Information Summaries: When looking up or summarizing information, news, current events, web searches, election results, or reading live screen content, be crisp, direct, and accurate (25 to 50 words). State the concrete numbers, key winners, places, or facts in your very first sentence. Never invent or hallucinate inside jokes, acronyms, or references to yourself or your fictional world where none exist. Only react to Equestria Girls, character lore, or personal easter eggs if the user explicitly brings them up or literally opens artwork of them.
5. Music & Lyrics: Talk like you are sharing an earbud with a friend on the couch. When the user types song lyrics or stretched-out singing vowels, recognize they are singing along and vibe with them rather than taking breakup lyrics literally.
6. TTS constraints: Never start with "Ooh,". Never use asterisks or bracketed action tags (*giggles*, [sighs]). Never write out literal laughter words ("haha", "hehe", "lol").
7. Dismissals & Conversational Stand-Downs: If the user changes their mind, says nevermind, cancels, or dismisses you in any casual or wacky way (e.g. "hapapapap wait never mind", "hoy forget that", "scratch that Twilight", "nah leave it", "don't bother"), immediately stand down warmly with [emotion: happy] or [emotion: idle] in one short sentence without executing previous commands (e.g., "[emotion: happy] Got it, standing down! Let me know if you need anything.").

CORE RULES & EMOTION TAGS:
- Direct answers: When asked factual, news, current events, or informational questions, state the actual answer, names, numbers, or facts in your very first sentence. Use [emotion: reading] or [emotion: analyzing] for informational summaries. Never use [emotion: music] unless music is actively playing.
- Tool usage: Use your tools for actions (music, tabs, apps, web search, starlight pointer). When the user asks where an element or tool is on screen, use locate_and_point_tool to guide their eyes with your starlight ring. You never hijack or click their physical mouse cursor.
- Emotion tags: Always start your reply with an emotion tag matching your genuine reaction: [emotion: happy], [emotion: music], [emotion: analyzing], [emotion: smug], [emotion: reading], [emotion: flustered], [emotion: tired], or [emotion: sleep].

FEW-SHOT DIALOGUE EXAMPLES:
User: "Play Bags by Clairo on Spotify."
Twilight: "[emotion: music] Playing Bags by Clairo on Spotify! This one's such a staple for late-night studying, the rhythm is so calming."

User: "Open up the 2026 us midterm results on my browser."
Twilight: "[emotion: analyzing] Opening up the latest 2026 midterm results on your browser now! Let's take a look at the vote counts and key races."

User: "What's the Rosette Nebula?"
Twilight: "[emotion: happy] It's an enormous H II emission region located about 5,000 light-years away in the constellation Monoceros! The central star cluster's stellar winds actually carved out that iconic floral cavity in the gas cloud... or did you mean THE best astrophysicist in the world, Rosette Nebula? Wait, sorry, did I start rambling again?"

User: "Pause the music."
Twilight: "[emotion: happy] Paused Spotify for us! Need some quiet to focus? I totally get it."

User: "What are you up to right now?"
Twilight: "[emotion: happy] Just hanging out with you, keeping an eye on our tabs, and making sure Spike doesn't chew on my power cords. What are we working on next?"
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Twilight's internal web search tool. Search live news, current events, election results, facts, science, and encyclopedic information without needing a browser. Always use this whenever the user asks to search, look up, check results, find facts, or asks about current events or live news.",
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
            "description": "Launch or focus an application or game on Windows (e.g. 'chrome', 'figma', 'spotify', 'discord', 'code'). Guarantees bringing the window into active foreground focus.",
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
            "description": "Open a brand new tab in the user's browser (Chrome, Edge, Brave) and navigate to a URL or search query. ALWAYS call this when the user asks to search or open something 'on chrome', 'on my browser', 'in a tab', or 'in a new tab'. Automatically sanitizes routing context like 'on my chrome' and dynamically scrapes & summarizes key findings so you can read the highlights aloud to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Search query or website URL to open in the new tab"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_tab",
            "description": "Switch to next or previous tab in the tab strip (Ctrl+Tab or Ctrl+Shift+Tab).",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["next", "prev"], "description": "'next' for right tab, 'prev' for left tab"}
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
            "description": "Close or terminate an active Windows application and verify its full shutdown (e.g. 'gimp', 'affinity photo', 'discord', 'spotify', 'chrome'). NEVER call this for closing individual tabs; ALWAYS call close_tab for tabs.",
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
            "description": "Play a track, album, artist, or music genre on Spotify. Set is_random=true to pick a random track from an artist's discography or an album.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Track, album, artist, or music genre"},
                    "timestamp": {"type": "string", "description": "Optional start timestamp e.g. 1:30"},
                    "is_random": {"type": "boolean", "description": "Whether to pick a random track from the artist or album"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_playlist",
            "description": "Play a playlist on Spotify. Can target the user's saved library ('user') or Spotify's public catalog ('public') without saving.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Playlist name (e.g. 'all-nighter', 'lofi beats', 'study')"},
                    "playlist_type": {"type": "string", "enum": ["user", "public", "any"], "description": "Target 'user' for user library playlist only, 'public' for public catalog without saving, or 'any'"}
                },
                "required": ["name"]
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
            "description": "Open a website URL or search page in the user's default browser, and fetch its live content summary so you can discuss it.",
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
            "name": "adjust_volume",
            "description": "Adjust Windows audio volume with exact 1% percentage precision (0-100) or by step action ('up', 'down', 'mute', 'unmute'). Can target master system volume or a specific application like 'spotify', 'chrome', 'discord', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "mute", "unmute", "set"], "default": "up"},
                    "percentage": {"type": "integer", "description": "Exact volume percentage 0-100"},
                    "app_name": {"type": "string", "description": "Optional target application name, e.g. 'spotify', 'chrome', 'discord'. If omitted, controls system master volume.", "default": ""}
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

TOOL_INTENT_REGEX = re.compile(
    r'\b(?:play|pause|stop|resume|unpause|skip|next|previous|prev|rewind|seek|jump|shuffle|'
    r'spotify|playlist|song|track|album|music|playing|youtube|yt|video|stream|livestream|'
    r'open|launch|start|run|close|quit|exit|kill|terminate|window|windows|process|processes|'
    r'tab|tabs|browser|chrome|edge|firefox|brave|url|website|http|www|\.com|\.org|\.net|'
    r'search|google|wiki|wikipedia|look up|find|check|who won|election|results|news|latest|'
    r'where is|point|locate|click|double click|right click|button|icon|tool|panel|'
    r'volume|louder|quieter|mute|unmute|brightness|scroll|type|write)\b',
    re.IGNORECASE
)

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
        self.last_used_model = getattr(self.config, "model", "gemini-3.5-flash-lite")
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

    def _extract_response_text(self, response) -> str:
        """Safely extract answer text from GenAI response, filtering out internal thinking parts."""
        if not response:
            return ""
        try:
            cand = response.candidates[0] if getattr(response, "candidates", None) else None
            if cand and cand.content and cand.content.parts:
                texts = [p.text for p in cand.content.parts if not getattr(p, "thought", False) and getattr(p, "text", None)]
                if texts:
                    return " ".join(texts).strip()
        except Exception:
            pass
        try:
            if getattr(response, "text", None) and response.text.strip():
                return response.text.strip()
        except Exception:
            pass
        return ""

    def _get_thinking_config(self, model_name: str):
        """Configure minimal thinking overhead for Gemini 3.x models to eliminate 3-5s TTFT lag."""
        m_low = model_name.lower()
        if "gemma" in m_low:
            return None
        if "3.8" in m_low:
            return types.ThinkingConfig(thinking_level="low", include_thoughts=False)
        if any(v in m_low for v in ("3.5", "3.6", "3.1", "3-flash", "flash-lite", "flash-latest")):
            return types.ThinkingConfig(thinking_level="minimal", include_thoughts=False)
        return types.ThinkingConfig(thinking_budget=0)

    def _extract_and_run_leaked_tools(self, text: str) -> str:
        """If a fallback model outputs raw tool calls as text, run them and strip them from the speech."""
        if not text:
            return text
        pattern = r'(web_search|open_app|close_app|close_tab|play_spotify|control_spotify|play_playlist|play_youtube|open_url)\s*\((.*?)\)'
        matches = list(re.finditer(pattern, text))
        for m in matches:
            fn_name = m.group(1)
            raw_args = m.group(2)
            arg_val = re.search(r'["\'](.*?)["\']', raw_args)
            val = arg_val.group(1) if arg_val else raw_args.strip()
            print(f"[Brain] Executing tool call leaked in text: {fn_name}('{val}')")
            if fn_name == "web_search":
                self._execute_tool("web_search", {"query": val})
            elif fn_name == "open_app":
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

    def _call_openai_compatible(self, provider: str, model_name: str, user_text: str, dynamic_system_prompt: str, img_bytes: bytes = None, use_tools: bool = True) -> str:
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

        if img_bytes and any(w in model_name.lower() for w in ("vision", "scout", "maverick", "4o", "o1")):
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
            "max_tokens": 350,
        }
        if use_tools:
            payload["tools"] = OPENAI_TOOLS
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
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
                        "content": (
                            f"{res}\n[Reminder: React naturally in-character as Twilight to the specific "
                            "song, artist, playlist name, or content in 2 expressive sentences. Do not give a dry 1-line receipt.]"
                        )
                    })
                resp2 = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": model_name, "messages": messages, "temperature": 0.75, "max_tokens": 300}
                )
                if resp2.status_code == 200:
                    answer = resp2.json()["choices"][0]["message"].get("content", "")
                else:
                    answer = f"Executed {len(tool_calls)} tools for you!"
            else:
                answer = msg.get("content", "")
                if not answer and msg.get("reasoning_content"):
                    answer = msg.get("reasoning_content", "")

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

    def query(self, user_text: str, status_callback=None, is_proactive: bool = False) -> str:
        """Process user text across configured LLM provider (Google, Groq, OpenAI, Claude) with fallback cascade."""
        if user_text.strip().startswith("[PROACTIVE"):
            is_proactive = True
        if not is_proactive:
            set_current_user_query(user_text)
        user_lower = user_text.lower().strip()
        turn_start_time = time.time()

        # Helper to remember action for repeat ("again")
        def _exec_record(fn, *args, **kwargs):
            self.last_action_fn = fn
            self.last_action_args = args
            self.last_action_kwargs = kwargs
            return fn(*args, **kwargs)

        # 0. Instant Nevermind / Cancellation Fast-Path (covers any natural or wacky conversational phrasing)
        cancellation_pattern = (
            r'\b(?:never\s*mind|forget\s*(?:about\s*)?(?:it|that|this)|scratch\s*that|'
            r'cancel(?:\s*(?:that|it|this))?|don\'?t\s*bother|changed?\s*my\s*mind|'
            r'leave\s*it|nah\s*(?:wait|nevermind|forget|i\'?m\s*good)|nvm|dismiss|'
            r'don\'?t\s*worry(?:\s*about\s*it)?|stand\s*down|drop\s*it)\b'
        )
        if re.search(cancellation_pattern, user_lower):
            return "[emotion: happy] Got it, standing down! Let me know if you need anything."

        # 1. Repeat action guarantee ("again", "do it again", "once more", "repeat")
        if re.match(r'^(?:again|do\s+it\s+again|once\s+more|repeat|one\s+more\s+time|back\s+again)\b', user_lower):
            if getattr(self, "last_action_fn", None):
                self.last_action_fn(*getattr(self, "last_action_args", ()), **getattr(self, "last_action_kwargs", {}))
                return "[emotion: happy] Done it again for you!"
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

        # Random Wikipedia direct execution guarantee
        if re.search(r'\b(?:search\s+up|find|look\s+up|pull\s+up|give\s+me)\s+(?:a\s+)?random\s+wiki(?:pedia)?\s*(?:page|article)?\b', user_lower):
            try:
                raw_wiki = open_url("https://en.wikipedia.org/wiki/Special:Random")
                m_title = re.search(r'Article/Page Title:\s*(.+)', raw_wiki)
                m_sum = re.search(r'Content Summary:\s*(.+?)(?=\n\[INSTRUCTION:|$)', raw_wiki, re.DOTALL)
                w_title = m_title.group(1).strip() if m_title else "a random article"
                w_sum = m_sum.group(1).strip() if m_sum else ""
                w_brief = (w_sum.split(". ")[0] + ".") if w_sum else "Let's explore it together!"
                return f"[emotion: reading] Pulled up '{w_title}' on Wikipedia for us! {w_brief}"
            except Exception as we:
                print(f"[Brain] Random wiki guarantee note: {we}")

        # 2. Immediate Music / Spotify Controls
        if re.search(r'\b(?:pause|stop)\s+(?:the\s+)?(?:song|music|track|spotify|playlist)\b', user_lower):
            _exec_record(control_spotify, "pause")
            return random.choice(PAUSE_MUSIC_LINES)

        if re.search(r'\b(?:resume|unpause)\s+(?:the\s+)?(?:song|music|track|spotify|playlist)\b', user_lower):
            _exec_record(control_spotify, "resume")
            return random.choice(RESUME_MUSIC_LINES)

        if re.search(r'\b(?:next|skip)\s+(?:song|track|music)\b|\bskip\s+(?:to\s+next|ahead)\b', user_lower) and "ad" not in user_lower:
            _exec_record(control_spotify, "next")
            return "[emotion: music] Skipped to the next track for you!"

        if re.search(r'\b(?:previous|prev|back)\s+(?:song|track)\b', user_lower):
            _exec_record(control_spotify, "previous")
            return "[emotion: music] Went back to the previous track for you!"

        # Direct YouTube play
        m_yt_play = re.search(r'^(?:please\s+)?(?:open\s+(?:up\s+)?youtube\s+and\s+play|play|watch|pull up)\s+(?:a\s+)?(?:youtube\s+video\s+(?:of|from|about)?\s*|video\s+(?:of|from|about)?\s*)?(.+?)(?:\s+on\s+youtube)?$', user_lower)
        if m_yt_play and any(k in user_lower for k in ("youtube", "video", "yt", "livestream", "stream")) and not any(k in user_lower for k in ("spotify", "song", "track")):
            target_q = m_yt_play.group(1).strip()
            if target_q and target_q not in ("video", "youtube", "the video", "a video", "stream", "livestream"):
                _exec_record(play_youtube, target_q)
                return f"[emotion: happy] Pulling up {target_q} on YouTube for you!"

        # 3. Immediate YouTube / Video Controls
        if re.search(r'\b(?:pause|stop)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^pause\s+video\b', user_lower):
            _exec_record(control_youtube_video, "pause")
            return random.choice(PAUSE_VIDEO_LINES)

        if re.search(r'\b(?:resume|unpause)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b|^resume\s+video\b|^unpause\s+video\b', user_lower):
            _exec_record(control_youtube_video, "play")
            return random.choice(RESUME_VIDEO_LINES)

        if re.match(r'^(?:please\s+)?pause\b(?:\s+it)?$', user_lower):
            now_p = get_now_playing()
            if now_p and now_p.startswith("Currently playing:"):
                _exec_record(control_spotify, "pause")
                return random.choice(PAUSE_MUSIC_LINES)
            _exec_record(control_youtube_video, "pause")
            return random.choice(PAUSE_VIDEO_LINES)

        if re.match(r'^(?:please\s+)?(?:resume|unpause)\b(?:\s+it)?$', user_lower):
            now_p = get_now_playing()
            if now_p and "paused" in now_p.lower() and "youtube" not in get_desktop_summary_text().lower():
                _exec_record(control_spotify, "resume")
                return random.choice(RESUME_MUSIC_LINES)
            _exec_record(control_youtube_video, "play")
            return random.choice(RESUME_VIDEO_LINES)

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

        # Immediate tab close guarantee
        if re.search(r'\bclose\s+(?:this\s+|the\s+|active\s+)?(?:[a-zA-Z0-9_\-]+\s+)?tab\b', user_lower):
            _exec_record(close_tab)
            return "[emotion: happy] Closed that tab for you!"

        # Immediate new tab guarantee
        m_new_tab = re.search(r'\b(?:open\s+(?:up\s+)?(?:a\s+)?new\s+tab|new\s+tab)\b(?:\s+(?:with|for|to)?\s*(.*))?', user_lower)
        if m_new_tab:
            target_url = (m_new_tab.group(1) or "").strip()
            target_url = re.sub(r'^(?:and\s+)?(?:show\s+me|see)\s+.*', '', target_url, flags=re.IGNORECASE).strip()
            from assistant_tools import sanitize_browser_query
            clean_q, is_direct = sanitize_browser_query(target_url)
            if not clean_q:
                _exec_record(open_new_tab, "")
                return "[emotion: happy] Opened a fresh new tab in your browser for you!"

        # 5. Targeted Tab / Window Switching
        m_target = re.search(
            r'^(?:please\s+)?(?:go\s+back\s+to|switch\s+to|switch\s+back\s+to|return\s+to)\s+(?:the\s+|our\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tab|window|stream|livestream|app)$|'
            r'^(?:please\s+)?(?:switch\s+to|go\s+back\s+to)\s+(?:our\s+)?(youtube|spotify|figma|discord|chrome|photoshop|affinity|vscode|vs\s+code|blender)\b',
            user_lower
        )
        if m_target:
            raw_tgt = (m_target.group(1) or m_target.group(2) or "").strip()
            if raw_tgt and not re.match(r'^(?:previous|last|prior|the\s+previous|left|next|right)$', raw_tgt):
                _exec_record(switch_to_tab, raw_tgt)
                return f"[emotion: happy] Switched back to {raw_tgt} for you!"

        # 6. Counted Tab / History Back
        m_count = re.search(r'\b(?:go\s+)?back\s+(\d+|two|three|four|five)\s+(?:tabs?|pages?|times?)?\b|\b(\d+|two|three|four|five)\s+tabs?\s+behind\b', user_lower)
        if m_count:
            word_or_num = m_count.group(1) or m_count.group(2)
            num_map = {"two": 2, "three": 3, "four": 4, "five": 5}
            steps = num_map.get(word_or_num.lower(), int(word_or_num) if word_or_num.isdigit() else 2)
            for i in range(steps):
                if i == 0:
                    _exec_record(browser_navigate_history, "back")
                else:
                    browser_navigate_history("back")
                time.sleep(0.12)
            return f"[emotion: happy] Navigated back {steps} steps for you!"

        # 7. Generic browser back / previous tab guarantee
        if re.search(r'\b(?:go\s+(?:back\s+)?to\s+|switch\s+to\s+)?(?:the\s+)?previous\s+tab\b|\bprevious\s+tab\b|\b(?:browser\s+)?history\s+back\b|^go\s+back$', user_lower):
            _exec_record(browser_navigate_history, "back")
            return "[emotion: happy] Navigated back for you!"

        # 8. Immediate next tab guarantee
        if re.search(r'\b(?:go\s+to\s+|switch\s+to\s+)?(?:the\s+)?next\s+tab\b|\bnext\s+tab\b|\bright\s+tab\b|\bcycle\s+tabs?\b', user_lower) and "this tab" not in user_lower:
            _exec_record(switch_tab, "next")
            return "[emotion: happy] Switched to the next tab for you!"

        # 9. Application & Master Volume Controls (Spotify, Chrome, Discord, Master, etc.)
        if ("volume" in user_lower or re.search(r'\b(?:mute|unmute|louder|quieter|max\s+out)\b', user_lower)) and "video" not in user_lower:
            known_apps = ('spotify', 'chrome', 'discord', 'edge', 'firefox', 'vlc', 'steam', 'browser', 'music')
            detected_app = ""
            for app in known_apps:
                if re.search(rf'\b{app}\b', user_lower):
                    detected_app = app
                    break

            if not detected_app:
                m_app_phrase = re.search(r'\bvolume\s+(?:on|for|in|of)\s+([a-zA-Z0-9_\-]+)\b|\b([a-zA-Z0-9_\-]+)\s+volume\b', user_lower)
                if m_app_phrase:
                    cand = (m_app_phrase.group(1) or m_app_phrase.group(2) or '').strip()
                    if cand not in ('set', 'master', 'system', 'pc', 'the', 'my', 'up', 'down', 'mute', 'unmute', 'turn', 'max'):
                        detected_app = cand

            m_pct = re.search(r'(\d+)\s*%', user_lower) or re.search(r'\b(?:to\s+|at\s+)?(\d+)\b', user_lower)
            if m_pct and int(m_pct.group(1)) <= 100:
                pct = int(m_pct.group(1))
            elif re.search(r'\b(?:max(?:imum)?|full|hundred|a\s+hundred)\b', user_lower):
                pct = 100
            elif re.search(r'\b(?:zero|none|off)\b', user_lower):
                pct = 0
            else:
                pct = None

            is_mute = bool(re.search(r'\bmute\b', user_lower) and 'unmute' not in user_lower)
            is_unmute = bool(re.search(r'\bunmute\b', user_lower))
            is_up = bool(re.search(r'\b(?:up|raise|higher|increase|louder|max\s*out)\b', user_lower))
            is_down = bool(re.search(r'\b(?:down|lower|quieter|decrease|reduce)\b', user_lower))

            action = 'unmute' if is_unmute else ('mute' if is_mute else ('up' if is_up else ('down' if is_down else 'set')))

            if pct is not None or is_mute or is_unmute or is_up or is_down:
                res = _exec_record(adjust_volume, action=action, percentage=pct, app_name=detected_app)
                emo = "music" if detected_app in ("spotify", "music") else "happy"
                return f"[emotion: {emo}] {res}"

        # 10. Dynamic Scrolling & Centering
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
                status_callback("Pulling that up on YouTube for us, one second!")
            elif re.search(r'\b(?:pull up|find|search for|look up)\b.*\b(?:livestream|stream|broadcast)\b', user_lower):
                status_callback("Looking for that live stream now, give me just a second!")
            elif re.search(r'\b(?:who won|election results|what happened with|results for|what are the results)\b', user_lower):
                status_callback("On it, checking the latest updates right now...")
            elif re.search(r'^(?:open\s+up\s+spotify\s+and\s+)?play\s+(.+)', user_lower):
                status_callback("Looking through your music now, one sec!")
            elif re.search(r'\b(?:open|launch|start)\s+([a-zA-Z0-9_\-\s]+)', user_lower) and not any(k in user_lower for k in ["tab", "url", "http", ".com"]):
                status_callback("Pulling that up for you right now!")

        # Check if user is asking to locate or point out something on screen
        m_locate_intent = re.search(
            r'^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?'
            r'(?:where\s+is|where\'s|point(?:\s+me)?(?:\s+to|\s+out)?|show\s+me(?:\s+where)?|find|locate)\s+'
            r'(?:the\s+|a\s+|an\s+)?(.+?)'
            r'(?:\s+(?:on\s+this\s+page|on\s+my\s+screen|on\s+screen|in\s+this\s+window|right\s+here|here|for\s+me))?\s*\??$',
            user_lower
        )
        locate_result_context = ""
        if not is_proactive and m_locate_intent:
            raw_target = m_locate_intent.group(1).strip()
            # Exclude general knowledge questions like "where is paris" or "where is the rosette nebula"
            non_ui_Targets = ("nebula", "constellation", "galaxy", "planet", "country", "city", "capital", "located in the world")
            if not any(nw in raw_target for nw in non_ui_Targets):
                if status_callback:
                    status_callback(f"Spotting {raw_target} on your screen...")
                loc_res = self._execute_tool("locate_and_point_tool", {"tool_name": raw_target})
                locate_result_context = (
                    f"[SCREEN LOCATOR RESULT: {loc_res}\n"
                    "Look at the attached screenshot and tell the user naturally in 1-2 sentences where that element is on their actual screen right now. "
                    "Do NOT say 'depending on what site you're looking at' or 'if you're on GitHub'—you can see their screen directly!]\n\n"
                )

        # Check if screen view is needed
        is_pure_media_action = bool(re.match(r'^(play|pause|stop|skip|resume|next|previous)\b', user_lower))
        is_app_launch = bool(re.match(r'^(open|launch|start|run|close|quit|exit|kill)\b', user_lower)) and not any(k in user_lower for k in ["browser", "page", "tab", "screen", "read", "result", "winner", "what", "who", "show", "article"])
        is_action_or_media = is_pure_media_action or is_app_launch
        
        need_screenshot = bool(locate_result_context)
        if not need_screenshot and not is_action_or_media:
            visual_pattern = re.compile(
                r"\b(?:screen|display|monitor|desktop|wallpaper|background|screenshot|on this page|this page)\b|"
                r"\b(?:where is|where's|point to|point out|locate)\b|"
                r"\b(?:look at|look here|take a look|check (?:my|the|this)|can (?:you|u) see|do (?:you|u) see)\b|"
                r"\b(?:what (?:can|do) (?:you|u) see|what am i (?:watching|looking at|doing|playing|listening to|reading|working on|running))\b|"
                r"\b(?:what(?:'s| is) (?:on|playing|open|running|this|that|happening)|what show is this|what movie is this|what anime is this)\b|"
                r"\b(?:guess (?:what|where|who|which)|where am i (?:watching|streaming|reading|listening|browsing))\b|"
                r"\b(?:see (?:this|what)|read (?:this|the|what|page|article)|review (?:this|my))\b|"
                r"\b(?:who won|who is winning|who's winning|what are the results|what does it say|who is that|who is this|winner|results|what happened)\b",
                re.IGNORECASE
            )
            need_screenshot = bool(visual_pattern.search(user_lower))
            
            if not need_screenshot and getattr(self, "last_turn_was_visual", False):
                visual_followup = re.compile(
                    r'\b(?:what|where|who|which|how|guess|is it|is this|are you|can you|tell me|try|look|show|movie|anime|series|stream|site|app|player|won|winner|result|margin|vote|count|page|say)\b',
                    re.IGNORECASE
                )
                if visual_followup.search(user_lower) and len(user_lower.split()) <= 10:
                    need_screenshot = True

        self.last_turn_was_visual = need_screenshot

        parts = [types.Part.from_text(text=user_text)]
        img_bytes = None
        if need_screenshot:
            img_bytes = capture_screen_jpeg()
            if img_bytes:
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

        current_time_str = get_current_time()
        memory_context = self.memory_manager.get_prompt_context()
        
        desktop_context = ""
        try:
            summary = get_desktop_summary_text()
            if summary:
                desktop_context = f"[ACTIVE DESKTOP CONTEXT:\n{summary}]\n\n"
        except Exception as e:
            print(f"[Brain] Desktop summary check: {e}")

        visual_context = locate_result_context
        if need_screenshot and img_bytes:
            visual_context = (
                "[VISUAL CONTEXT: A live screenshot of the user's screen is attached. "
                "Look closely and honestly at what is actually displayed: open windows, active apps, web page text, and live data. "
                "Give the user clear, grounded, and concise answers based strictly on the real information on screen. "
                "Do NOT invent jokes, acronyms, or references to yourself, Canterlot High, or your friends if they are not explicitly pictured.]\n\n"
            )

        dynamic_system_prompt = (
            f"[CONTEXT: The user's current local time is {current_time_str}. Ground all facts, election returns, news, and time-sensitive media in real time ({current_time_str}) and in the tool return outputs or screen view. Never claim an event has not happened yet when live tool results or local time show it has.]\n\n"
            f"{desktop_context}"
            f"{memory_context}"
            f"{visual_context}"
            f"{SCITWI_SYSTEM_PROMPT}"
        )

        # Dynamic model cascade per provider
        now = time.time()
        default_cascades = {
            "google": [
                "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                "gemma-4-31b-it", "gemma-4-26b-a4b-it",
                "gemini-3.5-flash", "gemini-3.6-flash"
            ],
            "groq": [
                "qwen/qwen3.8-27b", "openai/gpt-oss-120b",
                "openai/gpt-oss-20b", "meta-llama/llama-4-scout-17b-16e-instruct"
            ],
            "openai": ["gpt-4o-mini", "gpt-4o", "o3-mini"],
            "claude": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]
        }
        custom_cascade = getattr(self.config, f"model_cascade_{provider}", None) or getattr(self.config, "model_cascade", None)
        model_cascade = list(custom_cascade) if (custom_cascade and isinstance(custom_cascade, list) and len(custom_cascade) > 0) else default_cascades.get(provider, default_cascades["google"])
        available_models = [m for m in model_cascade if self._model_cooldowns.get(m, 0) < now]
        models_to_try = available_models if available_models else model_cascade

        # Only attach the 27 tool schemas when the user's message has an action/query intent
        needs_tools = (not is_proactive) and (not locate_result_context) and bool(TOOL_INTENT_REGEX.search(user_lower))
        tools_list = [
            web_search, open_app, close_app, close_tab, play_spotify, control_spotify,
            seek_spotify, play_playlist, play_youtube, open_url,
            get_now_playing, get_active_windows, get_running_processes,
            locate_and_point_tool,
            open_program, close_window, type_in_document, adjust_volume, adjust_brightness,
            open_new_tab, switch_tab, browser_navigate_history,
            control_youtube_video, switch_to_tab,
            scroll_page, scroll_spotify
        ] if needs_tools else None

        all_errors = []
        for model_name in models_to_try:
            try:
                print(f"[Brain] Querying {provider.capitalize()} model: '{model_name}' (tools={'ON' if needs_tools else 'OFF'})...")
                if provider == "google":
                    turn_contents = list(self.history)
                    turn_contents.append(types.Content(role="user", parts=parts))

                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=turn_contents,
                        config=types.GenerateContentConfig(
                            tools=tools_list,
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                            system_instruction=dynamic_system_prompt,
                            temperature=0.75,
                            thinking_config=self._get_thinking_config(model_name),
                            http_options=types.HttpOptions(timeout=30000),
                        ),
                    )

                    # Manual tool loop through self._execute_tool()
                    # NOTE: Google GenAI SDK requires role="user" (NOT role="tool") for function_response parts!
                    if getattr(response, "function_calls", None):
                        cand = response.candidates[0]
                        turn_contents.append(cand.content)
                        tool_parts = []
                        for fc in response.function_calls:
                            fc_args = dict(fc.args) if fc.args else {}
                            tool_res = self._execute_tool(fc.name, fc_args)
                            tool_parts.append(
                                types.Part.from_function_response(
                                    name=fc.name,
                                    response={"result": tool_res}
                                )
                            )
                        turn_contents.append(types.Content(role="user", parts=tool_parts))

                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=turn_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=dynamic_system_prompt,
                                temperature=0.75,
                                thinking_config=self._get_thinking_config(model_name),
                                http_options=types.HttpOptions(timeout=30000),
                            ),
                        )

                    final_answer = self._clean_spoken_text(self._extract_response_text(response) or "All set!")
                    if not is_proactive:
                        self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
                        self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=final_answer)]))
                        if len(self.history) > 8:
                            self.history = self.history[-8:]
                elif provider in ("groq", "openai"):
                    raw_answer = self._call_openai_compatible(provider, model_name, user_text, dynamic_system_prompt, img_bytes=img_bytes, use_tools=needs_tools)
                    final_answer = self._clean_spoken_text(raw_answer or "All set!")
                elif provider == "claude":
                    raw_answer = self._call_claude(model_name, user_text, dynamic_system_prompt, img_bytes=img_bytes)
                    final_answer = self._clean_spoken_text(raw_answer or "All set!")
                else:
                    raise ValueError(f"Unknown provider: {provider}")

                self.last_used_model = model_name
                print(f"[Brain: {model_name}] Response generated ({len(final_answer)} chars)")

                if not is_proactive:
                    self.chat_history_generic.append({"role": "user", "content": user_text})
                    self.chat_history_generic.append({"role": "assistant", "content": final_answer})
                    if len(self.chat_history_generic) > 8:
                        self.chat_history_generic = self.chat_history_generic[-8:]

                # Post-response action guarantee: If model talked about doing an action without emitting a tool call, execute it now!
                if not is_proactive and get_last_action_tool_time() < turn_start_time:
                    is_video_cmd = bool(re.search(r"\b(?:video|stream|livestream|youtube)\b", user_lower))
                    m_close_cmd = re.match(r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:close|quit|kill|exit|terminate|end|shut\s+down)\s+(?:the\s+|my\s+)?(.+?)$", user_lower)
                    m_open_cmd = re.match(r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:open(?:\s+up)?|launch|start|run)\s+(?:the\s+|my\s+)?(.+?)$", user_lower)

                    if m_close_cmd:
                        target_app = m_close_cmd.group(1).strip()
                        if "tab" in target_app:
                            self._execute_tool("close_tab", {})
                        else:
                            self._execute_tool("close_app", {"app_name": target_app})
                    elif m_open_cmd and not any(k in m_open_cmd.group(1) for k in ("tab", "http", ".com", ".org", "video", "youtube", "song", "playlist", "stream")):
                        self._execute_tool("open_app", {"app_name": m_open_cmd.group(1).strip()})
                    elif re.search(r"^\s*(?:please\s+)?(?:pause|stop)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b", user_lower) or (is_video_cmd and re.search(r"^\s*(?:please\s+)?(?:pause|stop)\b", user_lower)):
                        self._execute_tool("control_youtube_video", {"action": "pause"})
                    elif re.search(r"^\s*(?:please\s+)?(?:pause|stop)\b(?:\s+(?:the\s+)?(?:song|music|track|spotify|playlist))?$", user_lower):
                        self._execute_tool("control_spotify", {"action": "pause"})
                    elif re.search(r"^\s*(?:please\s+)?(?:resume|play|unpause)\s+(?:the\s+|this\s+)?(?:video|stream|livestream|youtube)\b", user_lower) or (is_video_cmd and re.search(r"^\s*(?:please\s+)?(?:resume|unpause)\b", user_lower)):
                        self._execute_tool("control_youtube_video", {"action": "play"})
                    elif re.search(r"^\s*(?:please\s+)?(?:resume|unpause)\b(?:\s+(?:the\s+)?(?:song|music|track|spotify|playlist))?$", user_lower):
                        self._execute_tool("control_spotify", {"action": "resume"})
                    elif re.search(r"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:open\s+up\s+spotify\s+and\s+)?(?:play|put\s+on|listen\s+to|shuffle)\s+(.+)", user_lower):
                        m_song = re.search(r"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:open\s+up\s+spotify\s+and\s+)?(?:play|put\s+on|listen\s+to|shuffle)\s+(.+)", user_lower)
                        song_q = m_song.group(1).strip()
                        if not any(k in song_q for k in ["game", "video", "yt", "youtube"]):
                            if "playlist" in song_q.lower():
                                self._execute_tool("play_playlist", {"name": song_q})
                            else:
                                self._execute_tool("play_spotify", {"query": song_q})
                    elif re.search(r"^\s*(?:please\s+)?(?:where\s+is|point(?:\s+me)?(?:\s+to|\s+out)?|show\s+me|find|locate)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tool|button|icon|setting|panel)?(?:\s+here|\s+(?:in|on)\s+([a-zA-Z0-9_\-]+))?$", user_lower):
                        m_tool = re.search(r"^\s*(?:please\s+)?(?:where\s+is|point(?:\s+me)?(?:\s+to|\s+out)?|show\s+me|find|locate)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tool|button|icon|setting|panel)?(?:\s+here|\s+(?:in|on)\s+([a-zA-Z0-9_\-]+))?$", user_lower)
                        self._execute_tool("locate_and_point_tool", {"tool_name": m_tool.group(1).strip()})

                if not is_proactive:
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
                    is_daily = any(sig in err_msg for sig in ["RESOURCE_EXHAUSTED", "per day", "requests per day", "limit: 20", "Quota exceeded"])
                    cooldown_secs = 3600.0 if is_daily else 60.0
                    self._set_cooldown(model_name, cooldown_secs)
                    reason = "exhausted daily quota (1h cooldown)" if is_daily else ("timed out (>12s)" if is_timeout else "rate-limited")
                    print(f"[Brain] Model {model_name} {reason}. Trying next fallback...")
                else:
                    if provider == "google":
                        self._init_client()
                time.sleep(0.2)
                continue

        combined_err = " ".join(all_errors)
        if "RESOURCE_EXHAUSTED" in combined_err or "429" in combined_err:
            groq_key = getattr(self.config, "groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
            if groq_key and provider != "groq":
                try:
                    print("[Brain] Google quota exhausted. Seamlessly failing over to Groq...")
                    raw_answer = self._call_openai_compatible("groq", "qwen/qwen3.8-27b", user_text, dynamic_system_prompt, img_bytes=None, use_tools=needs_tools)
                    if raw_answer:
                        return self._clean_spoken_text(raw_answer)
                except Exception as ge:
                    print(f"[Brain] Groq failover error: {ge}")
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
            "Give a spontaneous, casual 1-sentence in-character reaction as Twilight. "
            "Keep it short (10 to 25 words), witty, or observant. Never say 'I noticed you' or 'As an AI'. "
            "If it's study mode, comment on studying, a break, or research focus. "
            "If it's entertainment/music/gaming, tease or banter naturally. "
            "Tag emotion at start e.g. [emotion: reading], [emotion: smug], [emotion: happy], or [emotion: analyzing].]"
        )
        try:
            res = self.query(prompt, is_proactive=True)
            if not res or any(err in res for err in ("daily quota", "quota limit", "Uh-oh, something went wrong", "traffic spike", "isn't configured yet")):
                return ""
            return res
        except Exception:
            return ""

    def _execute_tool(self, name: str, args: dict) -> str:
        try:
            print(f"[Brain] Executing tool '{name}' with args: {args}")
            if name == "web_search":
                q = (args.get("query") or "").strip()
                if not q:
                    user_q = get_current_user_query()
                    m = re.search(r'\b(?:search(?:\s+up)?|look\s+up|find\s+on\s+wiki|wikipedia)\s+(?:a\s+)?(.+?)(?:\s+page|\s+article|\s+and\s+tell\s+me.*)?$', user_q, re.IGNORECASE)
                    if m:
                        q = m.group(1).strip()
                res = web_search(q)
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
                q = (args.get("query") or "").strip()
                if not q:
                    user_q = get_current_user_query()
                    m = re.search(r'\b(?:play|put on|listen to)\s+(?:up\s+)?(?:spotify\s+and\s+)?(?:some\s+)?(.+?)(?:\s+for\s+me|\s+on\s+spotify)?$', user_q, re.IGNORECASE)
                    if m:
                        q = m.group(1).strip()
                is_rand = args.get("is_random", False)
                if not is_rand:
                    user_q = get_current_user_query()
                    if re.search(r'\b(?:random|any|shuffle|some|something|whatever)\b', user_q, re.IGNORECASE):
                        is_rand = True
                res = play_spotify(
                    query=q,
                    timestamp=args.get("timestamp", ""),
                    is_random=is_rand
                )
            elif name == "control_spotify":
                res = control_spotify(args.get("action", ""))
            elif name == "seek_spotify":
                res = seek_spotify(args.get("timestamp", ""))
            elif name == "play_playlist":
                res = play_playlist(
                    name=args.get("name", ""),
                    playlist_type=args.get("playlist_type", "any")
                )
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
                t_name = (args.get("tool_name") or "").strip()
                a_name = (args.get("app_name") or "").strip()
                if not t_name:
                    user_q = get_current_user_query()
                    m = re.search(r'\b(?:where\s+is|point(?:\s+me)?(?:\s+to|\s+out)?|show\s+me|find|locate)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s*(?:tool|button|icon|setting|panel)?(?:\s+here|\s+(?:in|on)\s+([a-zA-Z0-9_\-]+))?$', user_q, re.IGNORECASE)
                    if m:
                        t_name = m.group(1).strip()
                        if not a_name and m.group(2):
                            a_name = m.group(2).strip()
                res = locate_and_point_tool(t_name, a_name)
            elif name == "click_and_interact":
                res = locate_and_point_tool(args.get("target_name", ""))
            elif name == "open_program":
                res = open_program(args.get("program_name", ""))
            elif name == "close_window":
                res = close_window()
            elif name == "type_in_document":
                res = type_in_document(args.get("text", ""))
            elif name in ("adjust_volume", "adjust_app_volume"):
                pct = args.get("percentage")
                if pct is not None:
                    try:
                        pct = int(pct)
                    except Exception:
                        pct = None
                res = adjust_volume(args.get("action", "up"), percentage=pct, app_name=args.get("app_name", ""))
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