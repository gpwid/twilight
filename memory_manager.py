import os
import re
import threading
from pathlib import Path

class MemoryManager:
    """Manages Twilight's persistent Research Journal (memories.md).
    Stores durable facts about the user, favorite artists, projects, and habits
    so Twilight remembers them across reboots.
    """
    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = Path(workspace_dir or os.path.dirname(__file__)).resolve()
        self.memory_file = self.workspace_dir / "memories.md"
        self._lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        with self._lock:
            if not self.memory_file.exists():
                initial_content = (
                    "# Twilight Sparkle's Research Journal\n"
                    "Durable notes, observations, and facts about the user and their habits.\n\n"
                    "## Known Facts & Preferences\n"
                    "- User is developing and refining this desktop companion in Python.\n"
                    "- User enjoys music by Clairo, bôa, Radiohead, and CAS.\n"
                    "- User works on coding and physics simulations.\n"
                )
                self.memory_file.write_text(initial_content, encoding="utf-8")

    def get_memories_text(self) -> str:
        """Returns raw text of memories.md."""
        with self._lock:
            if self.memory_file.exists():
                try:
                    return self.memory_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            return ""

    def get_prompt_context(self) -> str:
        """Extracts bullet points from memories.md to ground Twilight's prompt."""
        text = self.get_memories_text()
        bullets = []
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("- ") or line_str.startswith("* "):
                bullets.append(line_str)
        if not bullets:
            return ""
        
        # Limit to top 15 facts to avoid prompt bloat
        clipped = bullets[:15]
        joined = "\n".join(clipped)
        return (
            "[RESEARCH JOURNAL & DURABLE MEMORIES:\n"
            f"{joined}\n"
            "Recall these personal facts naturally in conversation when relevant, just like a close friend would.]\n\n"
        )

    def add_fact(self, fact: str):
        """Append a single verified fact to memories.md."""
        if not fact or not fact.strip():
            return
        fact_str = fact.strip().lstrip("-* ").strip()
        with self._lock:
            try:
                content = self.memory_file.read_text(encoding="utf-8") if self.memory_file.exists() else ""
                # Avoid duplicates
                if fact_str.lower() in content.lower():
                    return
                with open(self.memory_file, "a", encoding="utf-8") as f:
                    f.write(f"- {fact_str}\n")
                print(f"[MemoryManager] Recorded new memory: {fact_str}")
            except Exception as e:
                print(f"[MemoryManager] Error saving fact: {e}")

    def distill_turn_async(self, user_text: str, reply_text: str, client=None, model: str = "gemini-3.1-flash-lite"):
        """Background worker to check if user shared any new personal facts, music tastes, or habits."""
        def worker():
            user_lower = user_text.lower()
            # Fast heuristic check before calling model to save quota
            triggers = ["i like ", "my favorite", "i prefer", "call me ", "i am ", "i work on ", "i'm studying", "i study"]
            has_trigger = any(t in user_lower for t in triggers)
            if not has_trigger:
                return

            if client:
                try:
                    prompt = (
                        "Extract 1 concise bullet point of a durable fact or preference about the user from this dialogue turn.\n"
                        "Only extract enduring facts (names, music taste, hobbies, occupation, pets, study subjects).\n"
                        "If none, reply 'NONE'.\n"
                        f"User: {user_text}\n"
                        f"Assistant: {reply_text}"
                    )
                    r = client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )
                    out = r.text.strip() if r and r.text else ""
                    if out and "NONE" not in out.upper() and len(out) < 120:
                        self.add_fact(out)
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True).start()
