"""
TechBot Autonomous Agent v2.0 — Casually Professional
═══════════════════════════════════════════════════
A vision-based autonomous desktop agent that can:
 • Plan complex tasks and decompose them into sub-goals
 • Interact with ANY desktop application via mouse/keyboard
 • Run shell commands and read their output
 • Read/write files and clipboard
 • Self-correct by verifying each action's result
 • Maintain conversation memory across steps
 • Save screenshots for debugging
 • Handle errors gracefully with retries
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import sys
import base64
import json
import time
import subprocess
import re
import math
from io import BytesIO
from datetime import datetime

import pyautogui
import keyboard
from PIL import Image, ImageGrab

try:
    from groq import Groq
except ImportError:
    Groq = None

# ═══════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════
BG_MAIN     = "#06060e"
BG_PANEL    = "#0d0d1a"
BG_INPUT    = "#14142a"
BG_HEADER   = "#0a0a18"
BG_LOG      = "#080812"
FG_TEXT     = "#00ffcc"
FG_ACCENT   = "#ff003c"
FG_DIM      = "#3a3a5c"
FG_WHITE    = "#d0d8e8"
CYAN        = "#00d4ff"
YELLOW      = "#ffea00"
GREEN       = "#00ff41"
PURPLE      = "#b040ff"
ORANGE      = "#ff8c00"

FONT_TITLE  = ("Consolas", 16, "bold")
FONT_MAIN   = ("Consolas", 10)
FONT_SM     = ("Consolas", 9)
FONT_XS     = ("Consolas", 8)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15  # Small pause between pyautogui calls for stability

# ═══════════════════════════════════════════════
# AVAILABLE VISION MODELS (in preference order)
# ═══════════════════════════════════════════════
VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
]

PLANNING_MODELS = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "llama-3.1-8b-instant",
]

# Screenshot save directory
CAPTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# APP REGISTRY — maps friendly names to launch commands
# ═══════════════════════════════════════════════
APP_REGISTRY = {
    # Text editors
    "notepad": "notepad.exe",
    "wordpad": "write.exe",
    "notepad++": r"C:\Program Files\Notepad++\notepad++.exe",
    "vscode": "code",
    "code": "code",
    "vim": "vim",
    # Browsers
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge": "msedge",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    # System
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "snipping tool": "snippingtool.exe",
    "screen snip": "snippingtool.exe",
    # Microsoft Office
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    # Media
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "spotify": os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    # Dev
    "python": "python",
    "git bash": r"C:\Program Files\Git\git-bash.exe",
    "github desktop": os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe"),
    # Communication
    "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
    "slack": os.path.expandvars(r"%LOCALAPPDATA%\slack\slack.exe"),
    "teams": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Teams\current\Teams.exe"),
    # Games
    "steam": r"C:\Program Files (x86)\Steam\steam.exe",
}

def find_and_launch_app(app_name, args=None):
    """Try to launch an app by name. Returns (success, message)."""
    app_lower = app_name.lower().strip()
    
    # 1) Check our registry
    if app_lower in APP_REGISTRY:
        target = APP_REGISTRY[app_lower]
        try:
            if target.startswith("ms-"):
                os.startfile(target)
                return True, f"Opened {app_name} via URI"
            cmd_parts = [target]
            if args:
                cmd_parts.extend(args if isinstance(args, list) else [args])
            subprocess.Popen(cmd_parts, shell=True)
            return True, f"Launched {app_name}"
        except Exception as e:
            pass  # Fall through to other methods
    
    # 2) Try os.startfile (works for many exe names and file associations)
    try:
        os.startfile(app_name if not args else f"{app_name} {args}")
        return True, f"Opened {app_name} via startfile"
    except Exception:
        pass
    
    # 3) Try shutil.which to find it on PATH
    import shutil
    exe = shutil.which(app_lower) or shutil.which(app_lower + ".exe")
    if exe:
        try:
            cmd = [exe]
            if args:
                cmd.extend(args if isinstance(args, list) else [args])
            subprocess.Popen(cmd)
            return True, f"Launched {app_name} from PATH"
        except Exception as e:
            return False, f"Found but failed to launch: {e}"
    
    # 4) Try PowerShell Start-Process as last resort
    try:
        extra = f" -ArgumentList '{args}'" if args else ""
        subprocess.Popen(
            f'powershell -command "Start-Process \"{app_name}\"{extra}"',
            shell=True
        )
        return True, f"Launched {app_name} via PowerShell"
    except Exception as e:
        return False, f"All launch methods failed for {app_name}: {e}"


# ═══════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════
def safe_json_parse(text):
    """Try to extract and parse JSON from potentially messy AI output."""
    text = text.strip()
    # Remove markdown fences
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = -1
    return None


def get_clipboard_text():
    """Get text from clipboard cross-platform."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData()
        except TypeError:
            data = ""
        win32clipboard.CloseClipboard()
        return str(data)
    except ImportError:
        pass
    try:
        result = subprocess.run(["powershell", "-command", "Get-Clipboard"],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


def set_clipboard_text(text):
    """Set text to clipboard."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(text))
        win32clipboard.CloseClipboard()
        return True
    except ImportError:
        pass
    try:
        process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-16-le'))
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# MAIN APPLICATION CLASS
# ═══════════════════════════════════════════════
class AutonomousAgentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TechBot Autonomous Agent v2.0")
        self.root.geometry("1050x780")
        self.root.minsize(800, 600)
        self.root.configure(bg=BG_MAIN)
        # NOT topmost — we auto-hide before screenshots instead
        self.root.attributes("-topmost", False)

        # API / Client
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.client = None
        if Groq and self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception:
                pass

        # Agent state
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.auto_hide = True       # Auto-hide window during screenshots
        self.vision_model = VISION_MODELS[0]
        self.planning_model = PLANNING_MODELS[0]
        self.history = []           # Full action history
        self.plan = []              # Current task plan / sub-goals
        self.completed_goals = []   # Sub-goals marked done
        self.step_count = 0
        self.max_steps = 200        # Safety limit
        self.max_retries = 3        # Retries per step on error
        self.action_delay = 1.2     # Seconds between actions
        self.save_screenshots = True
        self.session_id = ""
        self.agent_thread = None

        # Stats
        self.stats = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "screenshots_taken": 0,
            "commands_run": 0,
            "start_time": None,
        }

        self._setup_ui()

        # Global hotkeys
        try:
            keyboard.add_hotkey('ctrl+l', self.request_stop)
            keyboard.add_hotkey('ctrl+shift+p', self.toggle_pause)
        except Exception as e:
            self.log(f"[!] Hotkey binding failed: {e}", "red")
            self.log("    Run as Administrator for global hotkeys, or use UI buttons.", "dim")

    # ═══════════════════════════════════════════
    # UI SETUP
    # ═══════════════════════════════════════════
    def _setup_ui(self):
        # ── HEADER ──
        header = tk.Frame(self.root, bg=BG_HEADER, height=56,
                          highlightbackground="#1a1a3a", highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP, padx=8, pady=(8, 0))
        header.pack_propagate(False)

        tk.Label(header, text="◆ TECHBOT AUTONOMOUS AGENT", fg=FG_ACCENT, bg=BG_HEADER,
                 font=FONT_TITLE).pack(side=tk.LEFT, padx=16)

        hotkey_frame = tk.Frame(header, bg=BG_HEADER)
        hotkey_frame.pack(side=tk.RIGHT, padx=16)
        tk.Label(hotkey_frame, text="STOP", fg="#ff4444", bg=BG_HEADER,
                 font=("Consolas", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(hotkey_frame, text=" Ctrl+L", fg=FG_DIM, bg=BG_HEADER,
                 font=FONT_XS).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(hotkey_frame, text="PAUSE", fg=YELLOW, bg=BG_HEADER,
                 font=("Consolas", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(hotkey_frame, text=" Ctrl+Shift+P", fg=FG_DIM, bg=BG_HEADER,
                 font=FONT_XS).pack(side=tk.LEFT)

        # ── TOP SECTION: Task Input + Config ──
        top_section = tk.Frame(self.root, bg=BG_MAIN)
        top_section.pack(fill=tk.X, padx=8, pady=(6, 0))

        # Task Input
        input_frame = tk.Frame(top_section, bg=BG_PANEL, highlightbackground="#1a1a3a",
                               highlightthickness=1)
        input_frame.pack(fill=tk.X, pady=(0, 4))

        inner = tk.Frame(input_frame, bg=BG_PANEL, padx=12, pady=10)
        inner.pack(fill=tk.X)

        tk.Label(inner, text="MISSION OBJECTIVE:", fg=FG_TEXT, bg=BG_PANEL,
                 font=("Consolas", 10, "bold")).pack(anchor="w")

        self.task_text = tk.Text(inner, bg=BG_INPUT, fg=FG_WHITE, font=("Consolas", 11),
                                 insertbackground=FG_TEXT, relief=tk.FLAT,
                                 selectbackground="#2a2a4a", height=3, wrap=tk.WORD,
                                 padx=8, pady=6)
        self.task_text.pack(fill=tk.X, pady=(4, 8))
        self.task_text.insert("1.0", "Open Notepad and write a Python script that prints the Fibonacci sequence")

        # API Key inline
        api_row = tk.Frame(inner, bg=BG_PANEL)
        api_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(api_row, text="API KEY:", fg=FG_DIM, bg=BG_PANEL,
                 font=FONT_XS).pack(side=tk.LEFT)
        self.api_entry = tk.Entry(api_row, bg=BG_INPUT, fg=FG_WHITE, font=FONT_SM,
                                   insertbackground=FG_TEXT, relief=tk.FLAT,
                                   show="•", width=40)
        self.api_entry.pack(side=tk.LEFT, padx=(6, 12), ipady=2)
        if self.api_key:
            self.api_entry.insert(0, self.api_key)

        tk.Label(api_row, text="MODEL:", fg=FG_DIM, bg=BG_PANEL,
                 font=FONT_XS).pack(side=tk.LEFT)

        self.model_var = tk.StringVar(value=self.vision_model)
        model_menu = ttk.Combobox(api_row, textvariable=self.model_var,
                                   values=VISION_MODELS, state="readonly", width=42)
        model_menu.pack(side=tk.LEFT, padx=6)

        # Buttons row
        btn_frame = tk.Frame(inner, bg=BG_PANEL)
        btn_frame.pack(fill=tk.X)

        self.btn_start = tk.Button(btn_frame, text="▶  START AGENT", font=("Consolas", 11, "bold"),
                                    bg="#00ffcc", fg="#000000", activebackground="#00ccaa",
                                    relief=tk.FLAT, bd=0, command=self.start_agent,
                                    cursor="hand2", padx=20)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3), ipady=5)

        self.btn_pause = tk.Button(btn_frame, text="⏸  PAUSE", font=("Consolas", 11, "bold"),
                                    bg="#ffaa00", fg="#000000", activebackground="#cc8800",
                                    relief=tk.FLAT, bd=0, command=self.toggle_pause,
                                    cursor="hand2", state=tk.DISABLED, padx=20)
        self.btn_pause.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3, ipady=5)

        self.btn_stop = tk.Button(btn_frame, text="⬛  STOP MISSION", font=("Consolas", 11, "bold"),
                                   bg=FG_ACCENT, fg="#ffffff", activebackground="#cc0033",
                                   relief=tk.FLAT, bd=0, command=self.request_stop,
                                   cursor="hand2", state=tk.DISABLED, padx=20)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0), ipady=5)

        # ── CONFIG BAR ──
        config_bar = tk.Frame(top_section, bg=BG_PANEL, highlightbackground="#1a1a3a",
                               highlightthickness=1)
        config_bar.pack(fill=tk.X, pady=(0, 4))

        cfg_inner = tk.Frame(config_bar, bg=BG_PANEL, padx=12, pady=6)
        cfg_inner.pack(fill=tk.X)

        # Max steps
        tk.Label(cfg_inner, text="MAX STEPS:", fg=FG_DIM, bg=BG_PANEL,
                 font=FONT_XS).pack(side=tk.LEFT)
        self.max_steps_var = tk.StringVar(value="200")
        tk.Entry(cfg_inner, textvariable=self.max_steps_var, bg=BG_INPUT, fg=FG_WHITE,
                 font=FONT_SM, width=5, relief=tk.FLAT, insertbackground=FG_TEXT
                 ).pack(side=tk.LEFT, padx=(4, 16))

        # Action delay
        tk.Label(cfg_inner, text="DELAY (s):", fg=FG_DIM, bg=BG_PANEL,
                 font=FONT_XS).pack(side=tk.LEFT)
        self.delay_var = tk.StringVar(value="1.2")
        tk.Entry(cfg_inner, textvariable=self.delay_var, bg=BG_INPUT, fg=FG_WHITE,
                 font=FONT_SM, width=5, relief=tk.FLAT, insertbackground=FG_TEXT
                 ).pack(side=tk.LEFT, padx=(4, 16))

        # Save screenshots toggle
        self.save_ss_var = tk.BooleanVar(value=True)
        tk.Checkbutton(cfg_inner, text="Save Screenshots", variable=self.save_ss_var,
                        bg=BG_PANEL, fg=FG_DIM, selectcolor=BG_INPUT,
                        activebackground=BG_PANEL, activeforeground=FG_TEXT,
                        font=FONT_XS).pack(side=tk.LEFT, padx=(0, 16))

        # Auto-hide during screenshots
        self.hide_var = tk.BooleanVar(value=True)
        tk.Checkbutton(cfg_inner, text="Auto-Hide", variable=self.hide_var,
                        bg=BG_PANEL, fg=FG_DIM, selectcolor=BG_INPUT,
                        activebackground=BG_PANEL, activeforeground=FG_TEXT,
                        font=FONT_XS).pack(side=tk.LEFT, padx=(0, 16))

        # Status indicator
        self.status_label = tk.Label(cfg_inner, text="\u25cf IDLE", fg=FG_DIM, bg=BG_PANEL,
                                      font=("Consolas", 10, "bold"))
        self.status_label.pack(side=tk.RIGHT)

        # ── MAIN AREA: Log + Side Panel ──
        main_area = tk.Frame(self.root, bg=BG_MAIN)
        main_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Log panel (left, larger)
        log_frame = tk.Frame(main_area, bg=BG_PANEL, highlightbackground="#1a1a3a",
                              highlightthickness=1)
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        log_header = tk.Frame(log_frame, bg="#111122", height=26)
        log_header.pack(fill=tk.X)
        log_header.pack_propagate(False)
        tk.Label(log_header, text="  AGENT LOG", fg="#5a5a8a", bg="#111122",
                 font=FONT_XS).pack(side=tk.LEFT, pady=4)

        self.log_area = scrolledtext.ScrolledText(
            log_frame, bg=BG_LOG, fg=FG_TEXT, font=FONT_MAIN,
            bd=0, padx=10, pady=8, highlightthickness=0,
            wrap=tk.WORD, state=tk.DISABLED
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # Log tags
        self.log_area.tag_configure("red", foreground="#ff4455")
        self.log_area.tag_configure("yellow", foreground="#ffea00")
        self.log_area.tag_configure("cyan", foreground="#00d4ff")
        self.log_area.tag_configure("white", foreground="#d0d8e8")
        self.log_area.tag_configure("dim", foreground="#4a4a6a")
        self.log_area.tag_configure("green", foreground="#00ff41")
        self.log_area.tag_configure("accent", foreground=FG_ACCENT)
        self.log_area.tag_configure("purple", foreground="#b040ff")
        self.log_area.tag_configure("orange", foreground="#ff8c00")
        self.log_area.tag_configure("header", foreground=FG_ACCENT,
                                     font=("Consolas", 11, "bold"))
        self.log_area.tag_configure("thought", foreground="#8888cc",
                                     font=("Consolas", 9, "italic"))

        # Side panel (right)
        side_frame = tk.Frame(main_area, bg=BG_PANEL, width=260,
                               highlightbackground="#1a1a3a", highlightthickness=1)
        side_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))
        side_frame.pack_propagate(False)

        # Plan section
        plan_header = tk.Frame(side_frame, bg="#111122", height=26)
        plan_header.pack(fill=tk.X)
        plan_header.pack_propagate(False)
        tk.Label(plan_header, text="  TASK PLAN", fg="#5a5a8a", bg="#111122",
                 font=FONT_XS).pack(side=tk.LEFT, pady=4)

        self.plan_area = scrolledtext.ScrolledText(
            side_frame, bg=BG_LOG, fg=FG_WHITE, font=FONT_XS,
            bd=0, padx=8, pady=6, highlightthickness=0,
            wrap=tk.WORD, height=12, state=tk.DISABLED
        )
        self.plan_area.pack(fill=tk.X)
        self.plan_area.tag_configure("done", foreground=GREEN)
        self.plan_area.tag_configure("active", foreground=YELLOW)
        self.plan_area.tag_configure("pending", foreground=FG_DIM)

        # Stats section
        stats_header = tk.Frame(side_frame, bg="#111122", height=26)
        stats_header.pack(fill=tk.X, pady=(4, 0))
        stats_header.pack_propagate(False)
        tk.Label(stats_header, text="  STATISTICS", fg="#5a5a8a", bg="#111122",
                 font=FONT_XS).pack(side=tk.LEFT, pady=4)

        self.stats_area = scrolledtext.ScrolledText(
            side_frame, bg=BG_LOG, fg=FG_DIM, font=FONT_XS,
            bd=0, padx=8, pady=6, highlightthickness=0,
            wrap=tk.WORD, height=8, state=tk.DISABLED
        )
        self.stats_area.pack(fill=tk.X)

        # History section
        hist_header = tk.Frame(side_frame, bg="#111122", height=26)
        hist_header.pack(fill=tk.X, pady=(4, 0))
        hist_header.pack_propagate(False)
        tk.Label(hist_header, text="  RECENT ACTIONS", fg="#5a5a8a", bg="#111122",
                 font=FONT_XS).pack(side=tk.LEFT, pady=4)

        self.history_area = scrolledtext.ScrolledText(
            side_frame, bg=BG_LOG, fg=FG_DIM, font=FONT_XS,
            bd=0, padx=8, pady=6, highlightthickness=0,
            wrap=tk.WORD, state=tk.DISABLED
        )
        self.history_area.pack(fill=tk.BOTH, expand=True)

    # ═══════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════
    def log(self, text, color="white"):
        """Thread-safe log append."""
        def _do():
            self.log_area.config(state=tk.NORMAL)
            self.log_area.insert(tk.END, text + "\n", color)
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def update_plan_display(self):
        """Refresh the plan panel."""
        def _do():
            self.plan_area.config(state=tk.NORMAL)
            self.plan_area.delete("1.0", tk.END)
            if not self.plan:
                self.plan_area.insert(tk.END, "No plan generated yet.\n", "pending")
            else:
                for i, goal in enumerate(self.plan):
                    if goal in self.completed_goals:
                        self.plan_area.insert(tk.END, f"  ✓ {goal}\n", "done")
                    elif i == len(self.completed_goals):
                        self.plan_area.insert(tk.END, f"  ► {goal}\n", "active")
                    else:
                        self.plan_area.insert(tk.END, f"  ○ {goal}\n", "pending")
            self.plan_area.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def update_stats_display(self):
        """Refresh the stats panel."""
        def _do():
            self.stats_area.config(state=tk.NORMAL)
            self.stats_area.delete("1.0", tk.END)
            s = self.stats
            elapsed = 0
            if s["start_time"]:
                elapsed = time.time() - s["start_time"]
            mins, secs = divmod(int(elapsed), 60)
            self.stats_area.insert(tk.END, f"  Step:        {self.step_count}\n")
            self.stats_area.insert(tk.END, f"  Actions:     {s['total_actions']}\n")
            self.stats_area.insert(tk.END, f"  Success:     {s['successful_actions']}\n")
            self.stats_area.insert(tk.END, f"  Failed:      {s['failed_actions']}\n")
            self.stats_area.insert(tk.END, f"  Screenshots: {s['screenshots_taken']}\n")
            self.stats_area.insert(tk.END, f"  Commands:    {s['commands_run']}\n")
            self.stats_area.insert(tk.END, f"  Elapsed:     {mins:02d}:{secs:02d}\n")
            self.stats_area.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def update_history_display(self):
        """Refresh the recent actions panel."""
        def _do():
            self.history_area.config(state=tk.NORMAL)
            self.history_area.delete("1.0", tk.END)
            for entry in self.history[-15:]:
                step = entry.get("step", "?")
                action = entry.get("action", {})
                act_type = action.get("action", "?")
                thought = action.get("thought", "")[:60]
                self.history_area.insert(tk.END, f"  [{step}] {act_type}\n")
                if thought:
                    self.history_area.insert(tk.END, f"      {thought}\n")
            self.history_area.see(tk.END)
            self.history_area.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def set_status(self, text, color=FG_DIM):
        """Update the status indicator."""
        def _do():
            self.status_label.config(text=f"● {text}", fg=color)
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    # ═══════════════════════════════════════════
    # AGENT CONTROLS
    # ═══════════════════════════════════════════
    def request_stop(self):
        if self.is_running:
            self.stop_requested = True
            self.is_paused = False
            self.log("\n[!] ════ EMERGENCY STOP (Ctrl+L) ════", "red")
            self.set_status("STOPPING...", FG_ACCENT)
            self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.btn_pause.config(state=tk.DISABLED))

    def toggle_pause(self):
        if self.is_running:
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.log("[⏸] Agent PAUSED. Press Ctrl+Shift+P or Pause button to resume.", "yellow")
                self.set_status("PAUSED", YELLOW)
                self.root.after(0, lambda: self.btn_pause.config(text="▶  RESUME", bg="#00cc88"))
            else:
                self.log("[▶] Agent RESUMED.", "green")
                self.set_status("RUNNING", GREEN)
                self.root.after(0, lambda: self.btn_pause.config(text="⏸  PAUSE", bg="#ffaa00"))

    def start_agent(self):
        # Validate API key
        key = self.api_entry.get().strip() or self.api_key
        if not key:
            self.log("[!] Groq API Key required. Enter it in the API KEY field.", "red")
            return

        # Set up client
        self.api_key = key
        try:
            self.client = Groq(api_key=self.api_key)
        except Exception as e:
            self.log(f"[!] Failed to initialize Groq client: {e}", "red")
            return

        task = self.task_text.get("1.0", tk.END).strip()
        if not task:
            self.log("[!] Enter a task directive.", "red")
            return

        # Read config
        try:
            self.max_steps = int(self.max_steps_var.get())
        except ValueError:
            self.max_steps = 200
        try:
            self.action_delay = float(self.delay_var.get())
        except ValueError:
            self.action_delay = 1.2
        self.save_screenshots = self.save_ss_var.get()
        self.auto_hide = self.hide_var.get()
        self.vision_model = self.model_var.get()

        # Reset state
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        self.history = []
        self.plan = []
        self.completed_goals = []
        self.step_count = 0
        self.stats = {
            "total_actions": 0, "successful_actions": 0,
            "failed_actions": 0, "screenshots_taken": 0,
            "commands_run": 0, "start_time": time.time(),
        }
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # UI state
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.NORMAL)
        self.set_status("INITIALIZING", CYAN)

        # Clear log
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state=tk.DISABLED)

        self.log("╔══════════════════════════════════════════════╗", "accent")
        self.log("║   AUTONOMOUS AGENT v2.0  —  SESSION START    ║", "accent")
        self.log("╚══════════════════════════════════════════════╝", "accent")
        self.log(f"  Session:  {self.session_id}", "dim")
        self.log(f"  Model:    {self.vision_model}", "dim")
        self.log(f"  Max steps: {self.max_steps}  |  Delay: {self.action_delay}s", "dim")
        self.log(f"  Mission:  {task[:120]}{'...' if len(task) > 120 else ''}", "white")
        self.log("", "dim")

        self.agent_thread = threading.Thread(target=self.agent_loop, args=(task,), daemon=True)
        self.agent_thread.start()

    # ═══════════════════════════════════════════
    # SCREENSHOT
    # ═══════════════════════════════════════════
    def _hide_window(self):
        """Minimize/hide the agent window so it doesn't appear in screenshots."""
        if self.auto_hide:
            try:
                self.root.after(0, self.root.withdraw)
                time.sleep(0.3)  # Wait for window to fully disappear
            except Exception:
                pass

    def _show_window(self):
        """Restore the agent window after screenshot."""
        if self.auto_hide:
            try:
                self.root.after(0, self.root.deiconify)
                time.sleep(0.15)
            except Exception:
                pass

    def _get_screenshot_base64(self):
        """Capture screen and return as base64 JPEG. Auto-hides agent window first."""
        # Hide our window so the AI sees the actual desktop
        self._hide_window()

        try:
            screen = pyautogui.screenshot()
            screen.thumbnail((1920, 1080))
            self.stats["screenshots_taken"] += 1

            if self.save_screenshots:
                try:
                    path = os.path.join(CAPTURES_DIR,
                                         f"{self.session_id}_step{self.step_count:04d}.jpg")
                    screen.save(path, "JPEG", quality=70)
                except Exception:
                    pass

            buffered = BytesIO()
            screen.save(buffered, format="JPEG", quality=75)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        finally:
            # Always restore window, even if screenshot fails
            self._show_window()

    # ═══════════════════════════════════════════
    # AI CALLS
    # ═══════════════════════════════════════════
    def _call_ai(self, messages, model=None, max_tokens=800, temperature=0.1, retries=3):
        """Call Groq API with automatic retry and model fallback."""
        model = model or self.vision_model
        models_to_try = [model] + [m for m in VISION_MODELS if m != model]

        for attempt in range(retries):
            for m in models_to_try:
                try:
                    response = self.client.chat.completions.create(
                        model=m,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return response.choices[0].message.content.strip(), m
                except Exception as e:
                    err_msg = str(e)
                    err = err_msg.lower()
                    self.log(f"  [API] Model {m}: {err_msg[:120]}", "dim")
                    if "rate" in err or "429" in err:
                        wait = min(2 ** attempt * 2, 30)
                        self.log(f"  [*] Rate limited, waiting {wait}s...", "yellow")
                        time.sleep(wait)
                        break  # retry same model list
                    elif "model" in err or "404" in err or "not found" in err:
                        self.log(f"  [*] Model {m} unavailable, trying next...", "dim")
                        continue  # try next model
                    else:
                        if attempt < retries - 1:
                            time.sleep(2)
                            break
                        raise
        self.log("  [!] All AI models failed.", "red")
        return None, model

    def _call_text_ai(self, prompt, system="", max_tokens=1000):
        """Call a text-only model (for planning, etc.)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for model in PLANNING_MODELS:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()
            except Exception:
                continue
        return None

    # ═══════════════════════════════════════════
    # TASK PLANNING
    # ═══════════════════════════════════════════
    def generate_plan(self, task):
        """Use AI to decompose the task into sub-goals."""
        self.log("[*] Analyzing mission requirements...", "purple")

        prompt = f"""You are a task planner for an autonomous desktop agent on Windows.
The agent has these HIGH-RELIABILITY tools:
- OPEN_APP: opens any app by name (notepad, chrome, vscode, cmd, calculator, etc.)
- OPEN_URL: opens any URL in the browser
- SHELL: runs PowerShell commands and gets output
- WRITE_FILE / READ_FILE: directly read/write files
- WIN_SEARCH: opens Windows search
- WIN_RUN: opens Win+R run dialog
- TYPE / PRESS / HOTKEY: keyboard interaction
- CLICK: mouse click (only when needed for GUI buttons)

Break this task into clear, sequential sub-goals (3-8 steps).
Each step should use the most RELIABLE tool. Never plan "Click Start menu" — use OPEN_APP instead.

Task: {task}

Respond with ONLY a JSON array of strings. Example:
["Use OPEN_APP to open Notepad", "Type the content into Notepad", "Save the file with Ctrl+S"]

No markdown, no backticks, just the JSON array."""

        result = self._call_text_ai(prompt)
        if result:
            try:
                parsed = safe_json_parse(result) if not result.strip().startswith('[') else None
                if parsed is None:
                    # Try direct parse for arrays
                    clean = result.strip()
                    if clean.startswith("```"):
                        clean = re.sub(r'^```\w*\n?', '', clean)
                        clean = re.sub(r'\n?```$', '', clean)
                    plan = json.loads(clean.strip())
                else:
                    plan = parsed
                if isinstance(plan, list) and len(plan) > 0:
                    self.plan = [str(g) for g in plan]
                    self.log(f"[+] Mission plan generated: {len(self.plan)} steps", "green")
                    for i, goal in enumerate(self.plan):
                        self.log(f"    {i+1}. {goal}", "dim")
                    self.update_plan_display()
                    return
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                self.log(f"[!] Plan parse error: {e}", "yellow")

        # Fallback: single-goal plan
        self.plan = [task]
        self.log("[!] Could not decompose task. Using single-goal plan.", "yellow")
        self.update_plan_display()

    # ═══════════════════════════════════════════
    # ACTION EXECUTION
    # ═══════════════════════════════════════════
    def execute_action(self, action_data):
        """Execute a single action and return success/failure."""
        action = action_data.get("action", "").upper()
        self.stats["total_actions"] += 1

        try:
            if action == "CLICK":
                x = int(action_data.get("x", 0))
                y = int(action_data.get("y", 0))
                button = action_data.get("button", "left")
                self.log(f"  → Click ({x}, {y}) [{button}]", "cyan")
                pyautogui.moveTo(x, y, duration=0.3)
                pyautogui.click(button=button)

            elif action == "DOUBLE_CLICK":
                x = int(action_data.get("x", 0))
                y = int(action_data.get("y", 0))
                self.log(f"  → Double-click ({x}, {y})", "cyan")
                pyautogui.moveTo(x, y, duration=0.3)
                pyautogui.doubleClick()

            elif action == "RIGHT_CLICK":
                x = int(action_data.get("x", 0))
                y = int(action_data.get("y", 0))
                self.log(f"  → Right-click ({x}, {y})", "cyan")
                pyautogui.moveTo(x, y, duration=0.3)
                pyautogui.rightClick()

            elif action == "DRAG":
                x1 = int(action_data.get("x", 0))
                y1 = int(action_data.get("y", 0))
                x2 = int(action_data.get("x2", 0))
                y2 = int(action_data.get("y2", 0))
                self.log(f"  → Drag ({x1},{y1}) → ({x2},{y2})", "cyan")
                pyautogui.moveTo(x1, y1, duration=0.3)
                pyautogui.drag(x2 - x1, y2 - y1, duration=0.5)

            elif action == "TYPE":
                text = str(action_data.get("text", ""))
                preview = text[:80] + ('...' if len(text) > 80 else '')
                self.log(f"  → Type: \"{preview}\"", "cyan")
                # Always use clipboard paste — typewrite fails on uppercase, symbols, unicode
                set_clipboard_text(text)
                time.sleep(0.15)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.1)

            elif action == "TYPE_SPECIAL":
                # Type text that may contain special characters, newlines, etc.
                text = str(action_data.get("text", ""))
                preview = text[:80] + ('...' if len(text) > 80 else '')
                self.log(f"  → Type (special): \"{preview}\"", "cyan")
                set_clipboard_text(text)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'v')

            elif action == "PRESS":
                key = action_data.get("key", "")
                self.log(f"  → Press: {key}", "cyan")
                pyautogui.press(key)

            elif action == "HOTKEY":
                keys = action_data.get("keys", [])
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.split('+')]
                self.log(f"  → Hotkey: {'+'.join(keys)}", "cyan")
                pyautogui.hotkey(*keys)

            elif action == "SCROLL":
                amount = int(action_data.get("amount", action_data.get("y", 0)))
                x = action_data.get("x", None)
                y = action_data.get("y_pos", None)
                if x and y:
                    self.log(f"  → Scroll {amount} at ({x},{y})", "cyan")
                    pyautogui.scroll(amount, x=int(x), y=int(y))
                else:
                    self.log(f"  → Scroll {amount}", "cyan")
                    pyautogui.scroll(amount)

            elif action == "MOVE":
                x = int(action_data.get("x", 0))
                y = int(action_data.get("y", 0))
                self.log(f"  → Move to ({x}, {y})", "cyan")
                pyautogui.moveTo(x, y, duration=0.3)

            elif action == "SHELL":
                cmd = action_data.get("command", "")
                self.log(f"  → Shell: {cmd[:100]}", "orange")
                self.stats["commands_run"] += 1
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        timeout=30, cwd=os.path.expanduser("~")
                    )
                    output = result.stdout[:2000] if result.stdout else ""
                    error = result.stderr[:500] if result.stderr else ""
                    action_data["_output"] = output
                    action_data["_error"] = error
                    action_data["_returncode"] = result.returncode
                    if output:
                        self.log(f"  [stdout] {output[:200]}", "dim")
                    if error:
                        self.log(f"  [stderr] {error[:200]}", "yellow")
                except subprocess.TimeoutExpired:
                    self.log("  [!] Command timed out (30s)", "red")
                    action_data["_error"] = "TIMEOUT"
                except Exception as e:
                    self.log(f"  [!] Shell error: {e}", "red")
                    action_data["_error"] = str(e)

            elif action == "READ_FILE":
                filepath = action_data.get("path", "")
                self.log(f"  → Read file: {filepath}", "orange")
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(10000)  # Limit to 10KB
                    action_data["_output"] = content
                    self.log(f"  [file] Read {len(content)} chars", "dim")
                except Exception as e:
                    self.log(f"  [!] Read error: {e}", "red")
                    action_data["_error"] = str(e)

            elif action == "WRITE_FILE":
                filepath = action_data.get("path", "")
                content = action_data.get("content", "")
                self.log(f"  → Write file: {filepath} ({len(content)} chars)", "orange")
                try:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    self.log(f"  [file] Written successfully", "green")
                except Exception as e:
                    self.log(f"  [!] Write error: {e}", "red")
                    action_data["_error"] = str(e)

            elif action == "CLIPBOARD_GET":
                text = get_clipboard_text()
                action_data["_output"] = text
                self.log(f"  → Clipboard: {text[:100]}", "dim")

            elif action == "CLIPBOARD_SET":
                text = action_data.get("text", "")
                set_clipboard_text(text)
                self.log(f"  → Set clipboard: {text[:80]}", "dim")

            elif action == "OPEN_APP":
                app_name = action_data.get("app_name", action_data.get("name", ""))
                app_args = action_data.get("args", None)
                self.log(f"  → Open app: {app_name}", "green")
                success, msg = find_and_launch_app(app_name, app_args)
                action_data["_output"] = msg
                if success:
                    self.log(f"  [✓] {msg}", "green")
                    time.sleep(1.5)  # Give app time to open
                else:
                    self.log(f"  [!] {msg}", "red")
                    self.stats["failed_actions"] += 1
                    self.stats["total_actions"] -= 1  # Don't double-count
                    return False

            elif action == "OPEN_URL":
                url = action_data.get("url", "")
                browser = action_data.get("browser", "default")
                self.log(f"  → Open URL: {url}", "green")
                try:
                    import webbrowser
                    if browser == "default":
                        webbrowser.open(url)
                    elif browser in APP_REGISTRY:
                        subprocess.Popen([APP_REGISTRY[browser], url])
                    else:
                        webbrowser.open(url)
                    action_data["_output"] = f"Opened {url}"
                    time.sleep(2)  # Give browser time to load
                except Exception as e:
                    self.log(f"  [!] Failed to open URL: {e}", "red")

            elif action == "WIN_SEARCH":
                query = action_data.get("query", action_data.get("text", ""))
                self.log(f"  → Windows Search: {query}", "green")
                pyautogui.press('win')
                time.sleep(0.8)
                set_clipboard_text(query)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(1.0)

            elif action == "WIN_RUN":
                command = action_data.get("command", action_data.get("text", ""))
                self.log(f"  → Win+Run: {command}", "green")
                pyautogui.hotkey('win', 'r')
                time.sleep(0.6)
                set_clipboard_text(command)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.3)
                pyautogui.press('enter')
                time.sleep(1.5)

            elif action == "FOCUS_WINDOW":
                title = action_data.get("title", "")
                self.log(f"  → Focus window: {title}", "cyan")
                try:
                    windows = pyautogui.getWindowsWithTitle(title)
                    if windows:
                        win = windows[0]
                        if win.isMinimized:
                            win.restore()
                        win.activate()
                        time.sleep(0.5)
                        action_data["_output"] = f"Focused window: {win.title}"
                    else:
                        self.log(f"  [!] Window '{title}' not found", "yellow")
                        action_data["_error"] = f"Window not found: {title}"
                        # List available windows for AI context
                        all_wins = [w.title for w in pyautogui.getAllWindows() if w.title.strip()]
                        action_data["_output"] = f"Available windows: {', '.join(all_wins[:15])}"
                except Exception as e:
                    self.log(f"  [!] Window focus error: {e}", "red")
                    action_data["_error"] = str(e)

            elif action == "LIST_WINDOWS":
                self.log("  → Listing open windows", "dim")
                try:
                    all_wins = [w.title for w in pyautogui.getAllWindows() if w.title.strip()]
                    action_data["_output"] = json.dumps(all_wins[:30])
                    for w in all_wins[:10]:
                        self.log(f"    • {w}", "dim")
                except Exception as e:
                    action_data["_error"] = str(e)

            elif action == "TECHBOT_CMD":
                cmd = action_data.get("command", action_data.get("text", ""))
                if not cmd.startswith("techbot "):
                    cmd = "techbot " + cmd
                self.log(f"  → TechBot CLI: {cmd}", "purple")
                self.stats["commands_run"] += 1
                try:
                    # Find the TechBot A1 window
                    tb_windows = [w for w in pyautogui.getAllWindows()
                                  if "TECHBOT A1" in w.title.upper() or "TECHR" in w.title.upper()]
                    if tb_windows:
                        win = tb_windows[0]
                        if win.isMinimized:
                            win.restore()
                            time.sleep(0.5)
                        win.activate()
                        time.sleep(0.4)
                        # Click the input field (bottom center of the TechBot window)
                        input_x = win.left + win.width // 2
                        input_y = win.top + win.height - 45
                        pyautogui.click(input_x, input_y)
                        time.sleep(0.2)
                        # Clear any existing text and type the command
                        pyautogui.hotkey('ctrl', 'a')
                        time.sleep(0.1)
                        set_clipboard_text(cmd)
                        time.sleep(0.1)
                        pyautogui.hotkey('ctrl', 'v')
                        time.sleep(0.2)
                        pyautogui.press('enter')
                        time.sleep(1.5)
                        action_data["_output"] = f"Executed '{cmd}' in TechBot CLI"
                        self.log(f"  [+] Command sent to TechBot", "green")
                    else:
                        # TechBot not open — try launching it
                        self.log("  [!] TechBot window not found. Trying to launch...", "yellow")
                        techbot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "techbot_gui.py")
                        if os.path.exists(techbot_path):
                            env = os.environ.copy()
                            if self.api_key:
                                env["GROQ_API_KEY"] = self.api_key
                            subprocess.Popen([sys.executable, techbot_path], env=env)
                            time.sleep(3)
                            action_data["_output"] = "Launched TechBot. Retry the command next step."
                            action_data["_error"] = "TechBot was not open, launched it now. Try TECHBOT_CMD again."
                        else:
                            action_data["_error"] = "TechBot GUI not found"
                except Exception as e:
                    self.log(f"  [!] TechBot cmd error: {e}", "red")
                    action_data["_error"] = str(e)

            elif action == "SCREENSHOT":
                self.log("  → Taking verification screenshot", "dim")

            elif action == "WAIT":
                duration = float(action_data.get("duration", action_data.get("seconds", 2)))
                duration = min(duration, 10)
                self.log(f"  → Waiting {duration}s...", "dim")
                time.sleep(duration)

            elif action == "MARK_GOAL_DONE":
                goal = action_data.get("goal", "")
                if goal and goal not in self.completed_goals:
                    self.completed_goals.append(goal)
                    self.log(f"  ✓ Sub-goal complete: {goal}", "green")
                    self.update_plan_display()

            elif action == "DONE":
                self.log("\n  ╔══════════════════════════════════════╗", "green")
                self.log("  ║   ✓  MISSION COMPLETED SUCCESSFULY   ║", "green")
                self.log("  ╚══════════════════════════════════════╝", "green")
                return "DONE"

            else:
                self.log(f"  [!] Unknown action: {action}", "red")
                self.stats["failed_actions"] += 1
                return False

            self.stats["successful_actions"] += 1
            return True

        except Exception as e:
            self.log(f"  [!] Action failed: {e}", "red")
            self.stats["failed_actions"] += 1
            return False

    # ═══════════════════════════════════════════
    # MAIN AGENT LOOP
    # ═══════════════════════════════════════════
    def agent_loop(self, task):
        screen_width, screen_height = pyautogui.size()
        self.log(f"[*] Display: {screen_width}×{screen_height}", "dim")

        # Step 1: Generate plan
        self.set_status("PLANNING", PURPLE)
        self.generate_plan(task)
        self.log("", "dim")

        # Build system prompt with expanded capabilities
        plan_text = "\n".join(f"  {i+1}. {g}" for i, g in enumerate(self.plan))
        app_list = ", ".join(sorted(APP_REGISTRY.keys()))

        system_prompt = f"""You are an autonomous computer-using AI agent on Windows.
Your mission: {task}

PLAN:
{plan_text}

Display resolution: {screen_width}x{screen_height}
You receive a screenshot at each step. Decide the NEXT SINGLE ACTION.
Do NOT stop until the mission is 100% verified complete.

CRITICAL: ALWAYS prefer OPEN_APP, OPEN_URL, WIN_SEARCH, WIN_RUN, SHELL, TECHBOT_CMD, and WRITE_FILE
over trying to click through menus. These are 100% reliable. Clicking is a last resort.

RESPOND WITH ONLY A RAW JSON OBJECT. No markdown, no backticks, no explanation.

Example response:
{{"thought": "I need to open Notepad to write text", "action": "OPEN_APP", "app_name": "notepad"}}

AVAILABLE ACTIONS:

★★★ PREFERRED ACTIONS (use these first!) ★★★
  OPEN_APP      - Open any app by name. "app_name": "notepad" (or "chrome", "vscode", etc)
                  Known apps: {app_list}
                  Also works with any .exe name or program name.
                  Optional "args": "file.txt" to open with arguments.
  OPEN_URL      - Open a URL in browser. "url": "https://google.com"
  WIN_SEARCH    - Open Windows search and type query. "query": "notepad"
  WIN_RUN       - Open Win+R Run dialog and execute. "command": "notepad"
  SHELL         - Run a PowerShell command. "command": "Get-Process"
                  The output text is returned to you in the next step.
  WRITE_FILE    - Write content directly to a file. "path": "C:\\\\...", "content": "..."
  READ_FILE     - Read a file's contents. "path": "C:\\\\..."

─── TechBot Integration ───
  TECHBOT_CMD   - Run a command in the TechBot A1 CLI. "command": "scan 192.168.1.1 1-1024"
                  The "techbot " prefix is added automatically.
                  Available TechBot commands:
                    scan <ip> [port_range]  - Port scan
                    ping <ip/range>         - Ping sweep
                    wifi scan/crack         - WiFi scanning and cracking
                    recon                   - Network reconnaissance
                    hash <hash>             - Hash cracking
                    brute <url>             - HTTP brute force
                    trace <target>          - Traceroute
                    dns <domain>            - DNS enumeration
                    subdomain <domain>      - Subdomain enumeration
                    whois <domain>          - WHOIS lookup
                    sniff                   - Packet sniffer
                    app <name>              - Launch TechBot sub-apps
                    status                  - System status
                    And many more (type "techbot help" to see all)

─── Mouse (use when you need to interact with GUI elements) ───
  CLICK         - Click at (x, y). Optional "button": "left"/"right"/"middle"
  DOUBLE_CLICK  - Double-click at (x, y)
  RIGHT_CLICK   - Right-click at (x, y)
  DRAG          - Drag from (x, y) to (x2, y2)
  MOVE          - Move mouse to (x, y)
  SCROLL        - "amount": positive=up, negative=down

─── Keyboard ───
  TYPE          - Type text (pasted via clipboard). "text": "hello world"
  TYPE_SPECIAL  - Same as TYPE but for multi-line text with newlines.
  PRESS         - Press key: "key": "enter", "tab", "escape", "backspace", "delete",
                  "up", "down", "left", "right", "f1"-"f12", "win", "space"
  HOTKEY        - Key combo: "keys": ["ctrl", "s"] or "keys": "ctrl+shift+n"

─── Window Management ───
  FOCUS_WINDOW  - Bring a window to front by title. "title": "Untitled - Notepad"
  LIST_WINDOWS  - Get list of all open window titles.

─── Clipboard ───
  CLIPBOARD_GET - Read clipboard text.
  CLIPBOARD_SET - Set clipboard text. "text": "..."

─── Control ───
  WAIT          - Wait for loading. "duration": seconds (max 10)
  SCREENSHOT    - Just observe, take no action.
  MARK_GOAL_DONE - Mark sub-goal done. "goal": "text from plan"
  DONE          - Mission 100% complete and verified.

RULES:
1. To OPEN any application, ALWAYS use OPEN_APP with the app name. Never try to click the Start menu.
2. To open a website, ALWAYS use OPEN_URL. Never try to click browser address bar.
3. To create/edit files, prefer WRITE_FILE over typing in an editor.
4. Use SHELL for system tasks (installing software, listing files, etc).
5. Use TECHBOT_CMD for any hacking/security/network tool available in TechBot.
6. Only use CLICK/TYPE after an app is already open and you need to interact with its UI.
7. Start your "thought" with what you SEE on screen.
8. Be precise with click coordinates — aim for the CENTER of buttons.
9. Only include fields relevant to your action in the JSON.
10. Only use DONE when the ENTIRE mission is verified complete on screen.

OUTPUT ONLY PURE JSON. NOTHING ELSE."""

        self.set_status("RUNNING", GREEN)
        consecutive_errors = 0

        while self.is_running and not self.stop_requested:
            # Pause check
            while self.is_paused and not self.stop_requested:
                time.sleep(0.5)

            if self.stop_requested:
                break

            # Step limit
            self.step_count += 1
            if self.step_count > self.max_steps:
                self.log(f"\n[!] Reached max steps ({self.max_steps}). Stopping.", "red")
                break

            self.log(f"\n{'─' * 44}", "dim")
            self.log(f"  STEP {self.step_count}", "header")
            self.log(f"{'─' * 44}", "dim")

            # Take screenshot
            self.set_status(f"STEP {self.step_count} — OBSERVING", CYAN)
            try:
                b64_img = self._get_screenshot_base64()
            except Exception as e:
                self.log(f"[!] Screenshot failed: {e}", "red")
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    self.log("[!] Too many consecutive errors. Aborting.", "red")
                    break
                time.sleep(2)
                continue

            # Build messages
            messages = [{"role": "system", "content": system_prompt}]

            # Add recent history for context (last 6 steps)
            for h in self.history[-6:]:
                action = h.get("action", {})
                summary = {
                    "step": h["step"],
                    "action": action.get("action"),
                    "thought": action.get("thought", "")[:150],
                    "success": h.get("success", True),
                }
                # Include shell output in context
                if action.get("_output"):
                    summary["output"] = action["_output"][:500]
                if action.get("_error"):
                    summary["error"] = action["_error"][:200]
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(summary)
                })

            # Add completed goals context
            if self.completed_goals:
                goals_text = "Completed sub-goals so far: " + ", ".join(self.completed_goals)
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": goals_text}
                ]})

            # Current screenshot + instruction
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Step {self.step_count}. Analyze the screenshot and output the next action as JSON."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ]
            })

            # Call AI
            self.set_status(f"STEP {self.step_count} — THINKING", YELLOW)
            self.log("  Observing desktop state...", "dim")

            reply_text, used_model = self._call_ai(messages)

            if reply_text is None:
                self.log("[!] AI call failed after all retries.", "red")
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    self.log("[!] Too many consecutive errors. Aborting.", "red")
                    break
                time.sleep(3)
                continue

            # Parse response
            action_data = safe_json_parse(reply_text)
            if action_data is None:
                self.log(f"[!] Failed to parse AI response.", "red")
                self.log(f"  RAW: {reply_text[:200]}", "dim")
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    break
                time.sleep(2)
                continue

            # Reset consecutive error counter on success
            consecutive_errors = 0

            # Log thought
            thought = action_data.get("thought", "No thought provided")
            self.log(f"  💭 {thought}", "thought")

            subgoal = action_data.get("current_subgoal", "")
            if subgoal:
                self.log(f"  📋 Working on: {subgoal}", "dim")

            confidence = action_data.get("confidence", "?")
            action_name = action_data.get("action", "UNKNOWN").upper()
            self.log(f"  ⚡ Action: {action_name}  (confidence: {confidence})", "white")

            # Execute
            self.set_status(f"STEP {self.step_count} — EXECUTING", ORANGE)
            result = self.execute_action(action_data)

            # Record history
            self.history.append({
                "step": self.step_count,
                "action": action_data,
                "success": result not in (False,),
                "model": used_model,
                "timestamp": time.time(),
            })

            # Update displays
            self.update_stats_display()
            self.update_history_display()

            if result == "DONE":
                break

            # Delay between actions
            time.sleep(self.action_delay)

        # ── SESSION END ──
        self.is_running = False
        elapsed = time.time() - (self.stats["start_time"] or time.time())
        mins, secs = divmod(int(elapsed), 60)

        self.log("", "dim")
        self.log("╔══════════════════════════════════════════════╗", "accent")
        self.log("║   MISSION COMPLETE                            ║", "accent")
        self.log("╠══════════════════════════════════════════════╣", "accent")
        self.log(f"║  Steps:      {self.step_count:<32}║", "white")
        self.log(f"║  Actions:    {self.stats['total_actions']:<32}║", "white")
        self.log(f"║  Success:    {self.stats['successful_actions']:<32}║", "green")
        self.log(f"║  Failed:     {self.stats['failed_actions']:<32}║", "red")
        self.log(f"║  Duration:   {mins:02d}:{secs:02d}{' ' * 29}║", "dim")
        self.log("╚══════════════════════════════════════════════╝", "accent")

        self.set_status("IDLE", FG_DIM)
        self.update_stats_display()

        self.root.after(0, lambda: self.btn_start.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))
        self.root.after(0, lambda: self.btn_pause.config(state=tk.DISABLED))


# ═══════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app = AutonomousAgentApp(root)
    root.mainloop()
