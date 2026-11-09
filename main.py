import os
import sys
import threading
import time
import random
import pygame
import win32gui
import brain
from config import Config
from audio_manager import AudioManager
from brain import SciTwiBrain
from overlay import SciTwiOverlay
import overlay
from voice_input import VoiceInputManager
from wake_word import WakeWordDetector

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("=" * 50)
    print("Starting Twilight Desktop Companion...")
    print("=" * 50)

    # 1. Load configuration
    config = Config.load()
    print(f"Loaded config: Model={config.model}, Voice={config.tts_voice}")
    if config.api_key:
        print("Gemini API Key detected.")
    else:
        print("Note: No Gemini API Key in config.json or environment yet.")

    # 2. Preload RVC neural voice model in background if enabled
    # Kept non-blocking so Twilight overlay launches immediately (<0.3s)
    if config.use_rvc:
        print("[Startup] Background preload for RVC voice model queued.")

    # 3. Initialize Audio Manager
    audio = AudioManager(
        voice=config.tts_voice,
        rate=config.tts_rate,
        pitch=config.tts_pitch,
        use_rvc=config.use_rvc,
        rvc_pitch=config.rvc_pitch,
        rvc_index_rate=config.rvc_index_rate,
        rvc_f0_method=config.rvc_f0_method,
        tts_engine=config.tts_engine,
        fish_audio_api_key=config.fish_audio_api_key,
        fish_audio_model_id=config.fish_audio_model_id,
        fish_audio_backend=getattr(config, "fish_audio_backend", "s2.1-pro-free")
    )

    # 4. Initialize Brain
    brain = SciTwiBrain(config)

    # Callback when user submits text via the floating input card
    overlay_ref = [None]  # Mutable ref to access overlay inside callback
    proactive_lock = threading.Lock()
    state_tracker = {
        "last_proactive_time": time.time() - 180.0,
        "last_speech_time": time.time(),
        "last_commented_title": "",
        "next_interval": random.uniform(300.0, 600.0)
    }

    last_query_tracker = {"text": "", "time": 0.0}

    def on_user_submit(user_prompt: str):
        if not user_prompt or not user_prompt.strip():
            return
        user_prompt = user_prompt.strip()

        # Deduplicate identical consecutive voice/text commands arriving within 2.8s
        now = time.time()
        if user_prompt.lower() == last_query_tracker["text"].lower() and (now - last_query_tracker["time"] < 2.8):
            print(f"[Main] Dropping rapid duplicate submission: '{user_prompt}'")
            return
        last_query_tracker["text"] = user_prompt
        last_query_tracker["time"] = now

        state_tracker["last_speech_time"] = now
        print(f"User query received: {user_prompt}")
        ov = overlay_ref[0]
        if ov:
            ov.response_query = user_prompt
            ov.show_response = False
            ov.is_processing = True
            ov.set_state("thinking", "Formulating a reply...", query=user_prompt)
        
        # Intercept "settings" command to launch the settings popup window
        clean_prompt = user_prompt.strip().lower()
        if clean_prompt in ("settings", "setting", "config", "open settings", "open setting"):
            try:
                import subprocess
                subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), "settings_ui.py")])
                resp = "[emotion: happy] Pulling up the research mainframe now! All core telemetry and engine controls ready."
                overlay = overlay_ref[0]
                if overlay:
                    overlay.show_response_card(resp, user_query=user_prompt)
                audio.speak(resp)
                return
            except Exception as e:
                print(f"[Main] Error opening settings: {e}")

        def worker():
            overlay = overlay_ref[0]
            if overlay:
                overlay.is_processing = True
                overlay.response_query = user_prompt
                overlay.show_response = False
                overlay.set_state("thinking", "Formulating a reply...", query=user_prompt)

            try:
                def on_status_trailer(trailer_text: str):
                    if overlay:
                        overlay.show_response_card(trailer_text, user_query=user_prompt, is_trailer=True)
                    audio.speak(trailer_text)

                response_text = brain.query(user_prompt, status_callback=on_status_trailer)
                active_m = getattr(brain, "last_used_model", getattr(brain.config, "model", "default"))
                print(f"[Twilight ({active_m})]: {response_text}")

                # Stop any lingering status trailer speech so the main response callbacks never get stuck
                audio.stop()

                card_shown = [False]

                def show_card_sync():
                    if not card_shown[0] and overlay:
                        card_shown[0] = True
                        overlay.is_processing = False
                        overlay.is_trailer = False
                        overlay.show_response_card(response_text, user_query=user_prompt)
                        overlay.set_state("speaking")

                def on_done():
                    if overlay:
                        overlay.is_processing = False
                        overlay.is_trailer = False
                        # Allow a clean 3.5s reading window after speech completes
                        overlay.response_start_time = time.time()
                        overlay._current_read_duration = 3.5
                        overlay.restore_ambient_state()

                # Fallback timer: ensure card displays within 6.5s if cloud TTS has a network delay
                fallback_timer = threading.Timer(6.5, show_card_sync)
                fallback_timer.daemon = True
                fallback_timer.start()

                def on_start():
                    fallback_timer.cancel()
                    show_card_sync()

                audio.speak(response_text, on_start=on_start, on_done=on_done)

            except Exception as e:
                print(f"[Main] Error formulating response: {e}")
                if overlay:
                    overlay.is_processing = False
                    overlay.is_trailer = False
                    overlay.show_response_card(f"Whoops, analysis mainframe hiccup: {e}", user_query=user_prompt)

        threading.Thread(target=worker, daemon=True).start()

    # 5. Initialize Overlay
    overlay = SciTwiOverlay(config, on_submit_callback=on_user_submit)
    overlay.is_tts_speaking_fn = audio.is_speaking
    overlay_ref[0] = overlay
    print(f"[Brain] Active Provider: {config.provider.capitalize()} | Primary Model: {config.model}")

    # 6. Initialize Voice Command & Speech-to-Text Manager
    def on_voice_state_change(new_state, details):
        ov = overlay_ref[0]
        if ov:
            ov.voice_state = new_state
            ov.voice_details = details
            if new_state in ("listening", "recording"):
                ov.set_state("idle", details)
            elif new_state == "processing":
                ov.set_state("thinking", "Processing voice command...")
            elif new_state == "idle":
                if not ov.is_processing and not ov.show_response:
                    ov.restore_ambient_state()

    def on_voice_audio_level(level):
        ov = overlay_ref[0]
        if ov:
            ov.voice_audio_level = level

    def on_voice_transcription(recognized_text):
        if not recognized_text:
            return
        ov = overlay_ref[0]
        if ov:
            ov.voice_state = "idle"
            ov.show_input = False
            ov.response_query = recognized_text
            ov.show_response = False
        on_user_submit(recognized_text)

    def on_voice_error(err_msg):
        ov = overlay_ref[0]
        if ov:
            ov.voice_state = "idle"
            ov.status_message = "Ready"

    voice_mgr = VoiceInputManager(
        config=config,
        is_speaking_fn=audio.is_speaking,
        on_state_change=on_voice_state_change,
        on_audio_level=on_voice_audio_level,
        on_transcription_complete=on_voice_transcription,
        on_error=on_voice_error,
    )
    overlay.set_voice_input_manager(voice_mgr)
    print(f"[VoiceInput] Engine: {getattr(config, 'stt_engine', 'groq_whisper')} | Hotkey: {getattr(config, 'voice_input_hotkey', 'ctrl+shift+v')}")

    # 7. Initialize Local Wake-Word Detector
    def on_wake_detected(phrase: str):
        print(f"[Twilight] Wake phrase recognized: '{phrase}'!")
        ov = overlay_ref[0]
        if ov:
            ov.show_input = False
            ov.show_response = False
        voice_mgr.start_listening()

    wake_detector = WakeWordDetector(
        config=config,
        on_wake=on_wake_detected,
        is_speaking_fn=audio.is_speaking,
        is_voice_active_fn=voice_mgr.is_active,
        is_processing_fn=lambda: (overlay_ref[0].is_processing if overlay_ref[0] else False),
    )

    # 7. Register Global Hotkeys (Ctrl+Shift+Space summon, Ctrl+Shift+V voice, Ctrl+Shift+P perch, Ctrl+Shift+Q study)
    def setup_global_hotkeys(summon_callback, voice_callback, perch_callback, study_callback):
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        VK_SPACE = 0x20
        VK_V = 0x56
        VK_P = 0x50
        VK_Q = 0x51
        HOTKEY_SUMMON = 8888
        HOTKEY_PERCH = 8889
        HOTKEY_STUDY = 8890
        HOTKEY_VOICE = 8891

        def hotkey_loop():
            registered = []
            if user32.RegisterHotKey(None, HOTKEY_SUMMON, MOD_CONTROL | MOD_SHIFT, VK_SPACE):
                registered.append(HOTKEY_SUMMON)
                print("[Hotkey] Global summon shortcut (Ctrl+Shift+Space) active.")
            if user32.RegisterHotKey(None, HOTKEY_VOICE, MOD_CONTROL | MOD_SHIFT, VK_V):
                registered.append(HOTKEY_VOICE)
                print("[Hotkey] Global voice command shortcut (Ctrl+Shift+V) active.")
            if user32.RegisterHotKey(None, HOTKEY_PERCH, MOD_CONTROL | MOD_SHIFT, VK_P):
                registered.append(HOTKEY_PERCH)
                print("[Hotkey] Window perching toggle (Ctrl+Shift+P) active.")
            if user32.RegisterHotKey(None, HOTKEY_STUDY, MOD_CONTROL | MOD_SHIFT, VK_Q):
                registered.append(HOTKEY_STUDY)
                print("[Hotkey] Quiet study mode toggle (Ctrl+Shift+Q) active.")

            msg = ctypes.wintypes.MSG()
            try:
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312:  # WM_HOTKEY
                        if msg.wParam == HOTKEY_SUMMON:
                            summon_callback()
                        elif msg.wParam == HOTKEY_VOICE:
                            voice_callback()
                        elif msg.wParam == HOTKEY_PERCH:
                            perch_callback()
                        elif msg.wParam == HOTKEY_STUDY:
                            study_callback()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            finally:
                for hid in registered:
                    user32.UnregisterHotKey(None, hid)

        t = threading.Thread(target=hotkey_loop, daemon=True)
        t.start()

    setup_global_hotkeys(
        summon_callback=lambda: overlay.summon(),
        voice_callback=lambda: voice_mgr.toggle_listening(),
        perch_callback=lambda: overlay.toggle_perch(),
        study_callback=lambda: overlay.toggle_study_mode()
    )

    # 8. Dynamic Autonomous Proactive Desktop Observer
    def check_proactive_commentary():
        now = time.time()
        # Minimum 240s (4 mins) cooldown from any speech
        if now - state_tracker["last_speech_time"] < 240.0:
            return
        if now - state_tracker["last_proactive_time"] < state_tracker["next_interval"]:
            return

        if not overlay or overlay.show_input or overlay.show_response or overlay.is_dragging:
            return
        if overlay.state not in ("idle", "music") and overlay.current_emotion not in ("idle", "reading"):
            return
        if audio.is_speaking():
            return

        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd or not win32gui.IsWindow(fg_hwnd):
                return
            title = win32gui.GetWindowText(fg_hwnd).strip()
            if not title or title == state_tracker["last_commented_title"] or len(title) < 3:
                return
            class_name = win32gui.GetClassName(fg_hwnd)
            if class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
                return
        except Exception:
            return

        if not proactive_lock.acquire(blocking=False):
            return

        state_tracker["last_proactive_time"] = now
        state_tracker["next_interval"] = random.uniform(300.0, 600.0)
        state_tracker["last_commented_title"] = title

        def proactive_worker():
            try:
                is_study = getattr(overlay, "study_mode", False)
                session_start = getattr(overlay, "study_session_start", 0.0)
                session_mins = int((time.time() - session_start) / 60) if is_study and session_start > 0 else 0

                # Silently query Gemini in background - DO NOT set overlay state to "thinking"!
                comment = brain.query_proactive(title, is_study=is_study, session_mins=session_mins)
                if not comment or not comment.strip():
                    return

                print(f"[Proactive Desktop Reaction] Twilight on '{title[:45]}': {comment}")
                state_tracker["last_speech_time"] = time.time()

                # Synchronized proactive speech & card presentation
                p_shown = [False]

                def show_p_card():
                    if not p_shown[0] and overlay:
                        p_shown[0] = True
                        overlay.show_response_card(comment)
                        overlay.set_state("speaking")

                def on_done():
                    if overlay:
                        overlay.is_processing = False
                    if not overlay.show_response:
                        overlay.restore_ambient_state()

                fb_timer = threading.Timer(3.5, show_p_card)
                fb_timer.daemon = True
                fb_timer.start()

                def on_start():
                    fb_timer.cancel()
                    show_p_card()

                audio.speak(comment, on_start=on_start, on_done=on_done)
            except Exception as e:
                print(f"[Proactive Error]: {e}")
            finally:
                proactive_lock.release()

        threading.Thread(target=proactive_worker, daemon=True).start()

    # 8. Main 60 FPS loop
    clock = pygame.time.Clock()
    running = True
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    last_config_mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0.0
    last_config_check = time.time()

    try:
        while running:
            dt = clock.tick(60) / 1000.0

            # Hot-reload settings ONLY when AI provider/model or audio settings actually changed
            now_t = time.time()
            if now_t - last_config_check > 1.5:
                last_config_check = now_t
                if os.path.exists(config_path):
                    mtime = os.path.getmtime(config_path)
                    if mtime > last_config_mtime:
                        last_config_mtime = mtime
                        try:
                            new_cfg = Config.load()
                            b_cfg = getattr(brain, "config", None)
                            brain_changed = (
                                not b_cfg or
                                getattr(new_cfg, "provider", "google") != getattr(b_cfg, "provider", "google") or
                                getattr(new_cfg, "model", "") != getattr(b_cfg, "model", "") or
                                getattr(new_cfg, "api_key", "") != getattr(b_cfg, "api_key", "") or
                                getattr(new_cfg, "groq_api_key", "") != getattr(b_cfg, "groq_api_key", "") or
                                getattr(new_cfg, "openai_api_key", "") != getattr(b_cfg, "openai_api_key", "") or
                                getattr(new_cfg, "claude_api_key", "") != getattr(b_cfg, "claude_api_key", "") or
                                getattr(new_cfg, "model_cascade", []) != getattr(b_cfg, "model_cascade", [])
                            )
                            audio_changed = (
                                getattr(new_cfg, "tts_engine", "") != getattr(audio, "tts_engine", "") or
                                getattr(new_cfg, "fish_audio_api_key", "") != getattr(audio, "fish_audio_api_key", "") or
                                getattr(new_cfg, "fish_audio_model_id", "") != getattr(audio, "fish_audio_model_id", "") or
                                getattr(new_cfg, "elevenlabs_api_key", "") != getattr(audio, "elevenlabs_api_key", "") or
                                getattr(new_cfg, "elevenlabs_voice_id", "") != getattr(audio, "elevenlabs_voice_id", "") or
                                getattr(new_cfg, "use_rvc", True) != getattr(audio, "use_rvc", True) or
                                getattr(new_cfg, "rvc_pitch", 0) != getattr(audio, "rvc_pitch", 0) or
                                getattr(new_cfg, "rvc_index_rate", 0.65) != getattr(audio, "rvc_index_rate", 0.65)
                            )
                            if brain_changed:
                                brain.reload_config(new_cfg)
                                print(f"[Brain] Settings updated from disk: provider={new_cfg.provider}, model={new_cfg.model}")
                            if audio_changed:
                                audio.reload_config(new_cfg)
                                print(f"[AudioManager] Settings updated from disk: engine={new_cfg.tts_engine}")
                            voice_mgr.config = new_cfg
                            voice_mgr.silence_timeout = getattr(new_cfg, "mic_silence_timeout", 1.2)
                            voice_mgr.energy_threshold = getattr(new_cfg, "mic_energy_threshold", 400)
                            voice_mgr.stt_engine = getattr(new_cfg, "stt_engine", "groq_whisper")
                            wake_detector.reload_config(new_cfg)
                        except Exception as e:
                            print(f"[Main] Error reloading config: {e}")

            check_proactive_commentary()
            running = overlay.update_and_render(dt)
    except KeyboardInterrupt:
        print("\nShutdown signal received.")
    finally:
        wake_detector.stop()
        audio.stop()
        pygame.quit()
        print("SciTwi companion shut down cleanly.")

if __name__ == "__main__":
    main()
