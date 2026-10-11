import json
import os
import re
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional dependency for the GUI app
    def load_dotenv(*_args, **_kwargs):
        return False

APP_NAME = "HADAL"
TINYFISH_RESEARCH_URL = "https://agent.tinyfish.ai/v1/automation/run-research"
RESEARCH_RESPONSE_INSTRUCTIONS = (
    "Response instructions: You are HADAL, the assistant in the HADAL app. "
    "If asked your name or identity, answer HADAL, never Claude. "
    "Start with a direct answer or short summary. Then give only a brief explanation "
    "of at most 2 short sentences. Be concise. Do not include citations or a source list "
    "unless the user asks for sources.\n\n"
    "Question: "
)
SETTINGS_PATH = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "HADAL" / "settings.json"
SIDEBAR_MIN_WIDTH = 190
SIDEBAR_MAX_WIDTH = 390
SIDEBAR_DEFAULT_WIDTH = 255


def build_tinyfish_query(question):
    if not isinstance(question, str):
        raise ValueError("The research question must be text.")
    question = question.strip()
    max_question_length = 2000 - len(RESEARCH_RESPONSE_INSTRUCTIONS)
    if not question or len(question) > max_question_length:
        raise ValueError(
            f"Research questions must contain between 1 and {max_question_length} characters."
        )
    return RESEARCH_RESPONSE_INSTRUCTIONS + question


def run_tinyfish_research(
    query, api_key, language="en", session_id=None, opener=None, on_delta=None
):
    query = build_tinyfish_query(query)
    if not api_key:
        raise ValueError("TINYFISH_API_KEY is not configured.")

    payload = {"query": query, "mode": "instant", "stream": True, "output_language": language}
    if session_id:
        payload["session_id"] = session_id
    request = urllib.request.Request(
        TINYFISH_RESEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        response_context = open_request(request, timeout=2700)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TinyFish returned HTTP {exc.code}: {details or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to TinyFish: {exc.reason}") from exc

    result = None
    citations = []
    new_session_id = session_id
    streamed_text = ""
    with response_context as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError as exc:
                raise RuntimeError("TinyFish returned an invalid event stream.") from exc
            if not isinstance(event, dict):
                raise RuntimeError("TinyFish returned an invalid event.")
            event_type = event.get("event")
            if event_type == "session":
                new_session_id = event.get("session_id", new_session_id)
            elif event_type == "final_result":
                result = event.get("result")
                citations = event.get("citations") or []
            elif event_type == "synthesis_delta":
                delta = event.get("delta", "")
                if not isinstance(delta, str):
                    raise RuntimeError("TinyFish returned an invalid response update.")
                streamed_text += delta
                if on_delta and delta:
                    on_delta(streamed_text)
            elif event_type == "synthesis_discarded":
                streamed_text = ""
                if on_delta:
                    on_delta("")
            elif event_type == "error":
                details = event.get("message") or event.get("error")
                if isinstance(details, dict):
                    details = details.get("message") or json.dumps(details, ensure_ascii=False)
                raise RuntimeError(str(details or "TinyFish research failed."))
            elif event_type == "done":
                break

    if not isinstance(result, str) or not result.strip():
        raise RuntimeError("TinyFish finished without returning a research report.")
    if not isinstance(citations, list):
        raise RuntimeError("TinyFish returned citations in an unexpected format.")
    return {"result": result.strip(), "citations": citations, "session_id": new_session_id}


def format_research_report(report):
    return (report or "").strip()
INTERFACE_PRESETS = {
    "emerald": {
        "accent": "#10a37f",
        "dark": {
            "main": "#151a18", "sidebar": "#0d1310", "card": "#1b2420",
            "border": "#303b35", "user_bubble": "#20382d", "selection": "#294536",
        },
        "light": {
            "main": "#f3f8f5", "sidebar": "#e9f1ec", "card": "#ffffff",
            "border": "#d1ded5", "user_bubble": "#deeee4", "selection": "#cfe2d5",
        },
    },
    "blue": {
        "accent": "#3b82f6",
        "dark": {
            "main": "#101923", "sidebar": "#0b121c", "card": "#162230",
            "border": "#29394a", "user_bubble": "#1c3346", "selection": "#29465d",
        },
        "light": {
            "main": "#f2f7fc", "sidebar": "#e8f0f8", "card": "#ffffff",
            "border": "#ccd9e8", "user_bubble": "#dceeff", "selection": "#cfdeef",
        },
    },
    "violet": {
        "accent": "#8b5cf6",
        "dark": {
            "main": "#171321", "sidebar": "#110d1b", "card": "#211a30",
            "border": "#39304c", "user_bubble": "#302443", "selection": "#403354",
        },
        "light": {
            "main": "#f7f4fc", "sidebar": "#eee9f7", "card": "#ffffff",
            "border": "#ddd5eb", "user_bubble": "#eee7fa", "selection": "#e0d6ef",
        },
    },
    "rose": {
        "accent": "#e65383",
        "dark": {
            "main": "#1f1417", "sidebar": "#170d10", "card": "#2a1a20",
            "border": "#453038", "user_bubble": "#3c242e", "selection": "#513341",
        },
        "light": {
            "main": "#fcf4f6", "sidebar": "#f5e9ed", "card": "#ffffff",
            "border": "#ead3dc", "user_bubble": "#f9e4eb", "selection": "#ead0da",
        },
    },
    "amber": {
        "accent": "#d99a24",
        "dark": {
            "main": "#1c1910", "sidebar": "#141108", "card": "#282316",
            "border": "#423b29", "user_bubble": "#3b311d", "selection": "#51452b",
        },
        "light": {
            "main": "#fbf8ef", "sidebar": "#f4eedc", "card": "#ffffff",
            "border": "#e4d9b9", "user_bubble": "#f7edc7", "selection": "#eadfbf",
        },
    },
    "black": {
        "accent": "#8b8b8b",
        "dark": {
            "main": "#000000", "sidebar": "#050505", "card": "#111111",
            "border": "#303030", "user_bubble": "#252525", "selection": "#383838",
        },
        "light": {
            "main": "#f4f4f4", "sidebar": "#e8e8e8", "card": "#ffffff",
            "border": "#d0d0d0", "user_bubble": "#e5e5e5", "selection": "#d5d5d5",
        },
    },
}
UI_TEXT = {
    "new_chat": {"en": "+   New chat", "hi": "+   नई चैट"},
    "folders": {"en": "SELECTED FOLDERS", "hi": "चुने हुए फ़ोल्डर"},
    "folder_count": {"en": "{count} folders connected", "hi": "{count} फ़ोल्डर जुड़े"},
    "folder_count_one": {"en": "{count} folder connected", "hi": "{count} फ़ोल्डर जुड़ा"},
    "add_folder": {"en": "+  Add folder", "hi": "+  फ़ोल्डर जोड़ें"},
    "remove_folder": {"en": "−  Remove selected", "hi": "−  चुना हुआ हटाएँ"},
    "privacy": {
        "en": "Research questions go to TinyFish.\nSelected folders stay on your device.\nFile contents are never read.\nDrag divider to resize sidebar.",
        "hi": "शोध प्रश्न TinyFish को भेजे जाते हैं।\nचुने हुए फ़ोल्डर आपके डिवाइस पर रहते हैं।\nफ़ाइल सामग्री कभी नहीं पढ़ी जाती।\nसाइडबार का आकार बदलने के लिए रेखा खींचें।",
    },
    "new_conversation": {"en": "New conversation", "hi": "नई बातचीत"},
    "settings": {"en": "⚙  Settings", "hi": "⚙  सेटिंग्स"},
    "theme_dark": {"en": "◐  Dark mode", "hi": "◐  डार्क मोड"},
    "theme_light": {"en": "☀  Light mode", "hi": "☀  लाइट मोड"},
    "settings_title": {"en": "Settings", "hi": "सेटिंग्स"},
    "settings_subtitle": {"en": "Personalize your HADAL experience", "hi": "HADAL को अपनी पसंद के अनुसार बदलें"},
    "appearance": {"en": "Appearance", "hi": "दिखावट"},
    "dark_theme": {"en": "Dark theme", "hi": "डार्क थीम"},
    "accent_color": {"en": "Interface color theme", "hi": "इंटरफ़ेस रंग थीम"},
    "preset_emerald": {"en": "Emerald", "hi": "पन्ना"},
    "preset_blue": {"en": "Ocean blue", "hi": "समुद्री नीला"},
    "preset_violet": {"en": "Violet", "hi": "बैंगनी"},
    "preset_rose": {"en": "Rose", "hi": "गुलाबी"},
    "preset_amber": {"en": "Amber", "hi": "एम्बर"},
    "preset_black": {"en": "Black", "hi": "काला"},
    "resize_sidebar": {"en": "Drag to resize sidebar", "hi": "साइडबार का आकार बदलने के लिए खींचें"},
    "language": {"en": "Language", "hi": "भाषा"},
    "close": {"en": "Done", "hi": "हो गया"},
    "settings_save_error": {"en": "Could not save settings.", "hi": "सेटिंग्स सहेजी नहीं जा सकीं।"},
    "composer_hint": {
        "en": "Message HADAL…  (Ctrl+Enter to send)",
        "hi": "HADAL को संदेश लिखें…  (भेजने के लिए Ctrl+Enter)",
    },
    "footer": {
        "en": "Research by TinyFish · Local file actions stay on your device",
        "hi": "TinyFish द्वारा शोध · फ़ाइल कार्य आपके डिवाइस पर",
    },
    "research_status": {
        "en": "Assistant: Diving into the depths…",
        "hi": "Assistant: गहराइयों में खोज रहा है…",
    },
    "tinyfish_key_error": {
        "en": "HADAL needs a TinyFish API key.\n"
        "Create a .env file beside the app containing:\n"
        "TINYFISH_API_KEY=your_tinyfish_key_here\n"
        "Install .env support with: py -m pip install python-dotenv\n"
        "Get a key from https://agent.tinyfish.ai/api-keys, then restart HADAL.\n"
        "Keep the key private and never commit the .env file. TinyFish Research availability or account limits may apply.",
        "hi": "HADAL को TinyFish API कुंजी चाहिए।\n"
        "ऐप के पास .env फ़ाइल बनाएँ और इसमें जोड़ें:\n"
        "TINYFISH_API_KEY=your_tinyfish_key_here\n"
        ".env समर्थन के लिए चलाएँ: py -m pip install python-dotenv\n"
        "https://agent.tinyfish.ai/api-keys से कुंजी लें, फिर HADAL फिर शुरू करें।\n"
        "कुंजी निजी रखें और .env फ़ाइल कमिट न करें। TinyFish Research की उपलब्धता या खाता सीमाएँ लागू हो सकती हैं।",
    },
    "ready": {
        "en": "HADAL is ready.\nAsk a web research question, or select a folder and use the local file-action buttons.",
        "hi": "HADAL तैयार है।\nवेब शोध प्रश्न पूछें या फ़ोल्डर चुनकर स्थानीय फ़ाइल बटन इस्तेमाल करें।",
    },
    "quick_list": {"en": "List files", "hi": "फ़ाइलें सूचीबद्ध करें"},
    "quick_search": {"en": "Search filenames", "hi": "फ़ाइल नाम खोजें"},
    "quick_organize": {"en": "Preview organization", "hi": "व्यवस्था का पूर्वावलोकन"},
    "quick_apply": {"en": "Apply preview", "hi": "पूर्वावलोकन लागू करें"},
}

# For a PyInstaller one-file build, configuration lives beside the .exe,
# not inside PyInstaller's temporary extraction directory.
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class FileAssistant:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise ValueError("The selected location does not exist.")
        if not self.root.is_dir():
            raise ValueError("The selected location is not a folder.")
        self.organization_plan = None

    def _resolve_folder(self, subfolder):
        if subfolder is None:
            subfolder = ""
        if not isinstance(subfolder, str):
            raise ValueError("Folder path must be text.")
        rel = Path(subfolder)
        if rel.is_absolute() or any(part == ".." for part in rel.parts):
            raise ValueError("That path is outside the selected folder.")
        folder = (self.root / rel).resolve(strict=False)
        try:
            folder.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("That path is outside the selected folder.") from exc
        if not folder.exists() or not folder.is_dir():
            raise ValueError("That path is not a folder.")
        return folder

    def list_files(self, subfolder=""):
        folder = self._resolve_folder(subfolder)
        entries = []
        for item in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if item.is_symlink():
                    continue
                resolved = item.resolve(strict=True)
                if not is_inside(resolved, self.root):
                    continue
                if item.is_dir():
                    entries.append(item.name + "/")
                else:
                    entries.append(item.name)
            except (OSError, RuntimeError):
                continue
        return {"entries": entries}

    def search_files(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search text cannot be empty.")
        needle = query.casefold()
        matches = []
        for path in self.root.rglob("*"):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve(strict=True)
                if not is_inside(resolved, self.root):
                    continue
                if needle in path.name.casefold():
                    rel = str(path.relative_to(self.root)).replace("/", os.sep)
                    matches.append(rel)
            except (OSError, RuntimeError):
                continue
        matches.sort(key=lambda value: value.casefold())
        return {"matches": matches}

    def preview_organization(self):
        plan = []
        skipped = []
        for source in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if source.is_symlink() or not source.is_file():
                    continue
                if not is_inside(source.resolve(strict=True), self.root):
                    continue
                ext = source.suffix[1:].upper() if source.suffix else "No extension"
                folder_name = ext if ext else "No extension"
                destination = self.root / folder_name / source.name
                if destination.exists() or destination.is_symlink():
                    skipped.append({"source": source.name, "reason": "Destination already exists."})
                    continue
                plan.append({
                    "source_name": source.name,
                    "extension_folder": folder_name,
                    "destination_name": source.name,
                })
            except (OSError, RuntimeError):
                skipped.append({"source": source.name, "reason": "Could not safely inspect this file."})
        self.organization_plan = {"root": self.root, "moves": plan}
        return {
            "count": len(plan),
            "moves": [
                {"source": item["source_name"], "destination": f'{item["extension_folder"]}/{item["destination_name"]}'}
                for item in plan
            ],
            "skipped": skipped,
        }

    def apply_organization(self):
        if not self.organization_plan:
            return {"status": "No current preview. Preview an organization plan first."}
        root = self.organization_plan["root"]
        moves = self.organization_plan["moves"]
        if not moves:
            self.organization_plan = None
            return {"status": "Nothing needs to be moved."}

        response = input(
            "Move " + str(len(moves)) + " file(s)? [yes/no]: "
        ).strip().lower()
        if response not in {"y", "yes"}:
            self.organization_plan = None
            return {"status": "Cancelled by user. No files were moved."}

        moved = []
        skipped = []
        for item in moves:
            source_name = item["source_name"]
            folder_name = item["extension_folder"]
            source = root / source_name
            try:
                if source.is_symlink() or not source.is_file() or not is_inside(source.resolve(strict=True), root):
                    skipped.append({"source": source_name, "reason": "Source is missing or unsafe."})
                    continue
                destination_dir = root / folder_name
                if destination_dir.exists() and (destination_dir.is_symlink() or not destination_dir.is_dir()):
                    skipped.append({"source": source_name, "reason": "Destination folder is not a safe directory."})
                    continue
                destination_dir.mkdir(exist_ok=True)
                destination = destination_dir / source_name
                if destination.exists() or destination.is_symlink():
                    skipped.append({"source": source_name, "reason": "Destination already exists."})
                    continue
                source.rename(destination)
                moved.append({"source": source_name, "destination": f"{folder_name}/{source_name}"})
            except (OSError, RuntimeError, ValueError) as exc:
                skipped.append({"source": source_name, "reason": str(exc)})
        self.organization_plan = None
        return {"status": "Organization finished.", "moved": moved, "skipped": skipped}


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_root(path_text: str) -> Path:
    """Resolve and validate a user-selected root directory."""
    if not isinstance(path_text, (str, os.PathLike)):
        raise ValueError("The selected location must be a folder path.")
    root = Path(path_text).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The selected location is not a folder.")
    return root


def safe_child(root: Path, relative: str, must_exist: bool = True) -> Path:
    """Resolve a relative path and ensure it stays within its selected root."""
    if not isinstance(relative, str):
        raise ValueError("Path must be text.")
    rel = Path(relative)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ValueError("Absolute paths and '..' are not allowed.")
    candidate = root / rel
    candidate = candidate.resolve(strict=must_exist)
    if not is_inside(candidate, root):
        raise ValueError("That path is outside the selected folder.")
    return candidate


class LocalFileAIApp:
    def __init__(self, root):
        self.root = root
        self.chat_font = tkfont.Font(root=root, family="Segoe UI", size=11)
        self.quick_action_font = tkfont.Font(root=root, family="Segoe UI", size=9)
        self.root.title(APP_NAME)
        self.root.geometry("1000x720")
        self.root.minsize(760, 560)

        self.folders = []
        self.organization_plan = None
        self.busy = False
        self.tinyfish_api_key = os.getenv("TINYFISH_API_KEY", "").strip()
        self.research_session_id = None
        self.dark_mode = True
        self.chat_items = []
        self.connection_status = "checking"
        self.language = "en"
        self.accent_preset = "emerald"
        self.sidebar_width = SIDEBAR_DEFAULT_WIDTH
        self.settings_error = None
        self._load_settings()

        self._build_ui()
        if self.settings_error:
            self._append(f"Could not load saved settings: {self.settings_error}", role="system")
        self._load_api_key()

    def _load_settings(self):
        try:
            if not SETTINGS_PATH.exists():
                return
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            language = settings.get("language", "en")
            accent_preset = settings.get("accent_preset")
            legacy_accent = settings.get("accent_color")
            sidebar_width = settings.get("sidebar_width", SIDEBAR_DEFAULT_WIDTH)
            dark_mode = settings.get("dark_mode", True)
            if language in {"en", "hi"}:
                self.language = language
            if accent_preset in INTERFACE_PRESETS:
                self.accent_preset = accent_preset
            elif legacy_accent in {
                preset["accent"] for preset in INTERFACE_PRESETS.values()
            }:
                self.accent_preset = next(
                    key for key, preset in INTERFACE_PRESETS.items()
                    if preset["accent"] == legacy_accent
                )
            if isinstance(sidebar_width, int) and not isinstance(sidebar_width, bool):
                self.sidebar_width = max(SIDEBAR_MIN_WIDTH, min(SIDEBAR_MAX_WIDTH, sidebar_width))
            if isinstance(dark_mode, bool):
                self.dark_mode = dark_mode
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.settings_error = str(exc)

    def _save_settings(self):
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps({
                    "language": self.language,
                    "accent_preset": self.accent_preset,
                    "dark_mode": self.dark_mode,
                    "sidebar_width": self.sidebar_width,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror(
                self._t("settings_title"),
                f"{self._t('settings_save_error')}\n{exc}",
                parent=self.root,
            )

    def _t(self, key):
        return UI_TEXT.get(key, {}).get(self.language, UI_TEXT.get(key, {}).get("en", key))

    @property
    def accent_color(self):
        return INTERFACE_PRESETS[self.accent_preset]["accent"]

    def _start_sidebar_resize(self, _event=None):
        self.sidebar_separator.configure(bg=self._theme_colors()["accent"])

    def _resize_sidebar(self, event):
        self.root.update_idletasks()
        requested = event.x_root - self.shell.winfo_rootx()
        available_max = max(
            SIDEBAR_MIN_WIDTH,
            min(SIDEBAR_MAX_WIDTH, self.shell.winfo_width() - 430),
        )
        self.sidebar_width = max(SIDEBAR_MIN_WIDTH, min(available_max, requested))
        self.sidebar.configure(width=self.sidebar_width)

    def _finish_sidebar_resize(self, _event=None):
        self.sidebar.configure(width=self.sidebar_width)
        self._save_settings()

    def _sidebar_divider_hover(self, _event=None):
        self.sidebar_separator.configure(bg=self._theme_colors()["accent"])

    def _sidebar_divider_unhover(self, _event=None):
        self.sidebar_separator.configure(bg=self._theme_colors()["sidebar_divider"])

    def _build_ui(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.style = style
        style.configure(".", font=("Segoe UI", 10))
        self.root.configure(bg="#f7f7f8")

        self.shell = tk.Frame(self.root, bg="#f7f7f8")
        self.shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(self.shell, width=self.sidebar_width, bg="#f0f1f3", padx=14, pady=16)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.brand_label = tk.Label(
            self.sidebar, text=APP_NAME, bg="#f0f1f3", fg="#17201f",
            font=("Segoe UI", 15, "bold"), anchor="w"
        )
        self.brand_label.pack(fill="x", pady=(0, 16))
        self.brand_label.configure(text="◈  HADAL")
        self.new_chat_button = self._create_rounded_button(
            self.sidebar, "+   New chat", self.new_chat,
            variant="sidebar", anchor="w", height=42, padding=14, bold=True,
        )
        self.new_chat_button.pack(fill="x", pady=(0, 22))

        self.folders_heading = tk.Label(
            self.sidebar, text="SELECTED FOLDERS", bg="#f0f1f3", fg="#6b7280",
            font=("Segoe UI", 8, "bold"), anchor="w"
        )
        self.folders_heading.pack(fill="x", pady=(0, 7))
        self.folder_count_label = tk.Label(
            self.sidebar, text="0 folders connected", bg="#f0f1f3", fg="#6b7280",
            font=("Segoe UI", 8), anchor="w"
        )
        self.folder_count_label.pack(fill="x", pady=(0, 7))
        self.folder_list = tk.Listbox(
            self.sidebar, height=9, exportselection=False, bd=0,
            relief="flat", highlightthickness=0, activestyle="none",
            font=("Segoe UI", 10), selectborderwidth=0
        )
        self.folder_list.pack(fill="x", pady=(0, 8))
        self.add_folder_button = self._create_rounded_button(
            self.sidebar, "+  Add folder", self.add_folder,
            variant="sidebar", anchor="w", height=38, padding=12,
        )
        self.add_folder_button.pack(fill="x")
        self.remove_folder_button = self._create_rounded_button(
            self.sidebar, "−  Remove selected", self.remove_folder,
            variant="sidebar", anchor="w", height=38, padding=12,
        )
        self.remove_folder_button.pack(fill="x")

        self.privacy_label = tk.Label(
            self.sidebar,
            text=self._t("privacy"),
            bg="#f0f1f3", fg="#6b7280", justify="left",
            font=("Segoe UI", 9), anchor="w", wraplength=self.sidebar_width - 32,
        )
        self.privacy_label.pack(side="bottom", fill="x", pady=(12, 0))

        self.sidebar_separator = tk.Frame(
            self.shell, width=6, bg="#555555", cursor="sb_h_double_arrow"
        )
        self.sidebar_separator.pack(side="left", fill="y")
        self.sidebar_separator.bind("<Button-1>", self._start_sidebar_resize)
        self.sidebar_separator.bind("<B1-Motion>", self._resize_sidebar)
        self.sidebar_separator.bind("<ButtonRelease-1>", self._finish_sidebar_resize)
        self.sidebar_separator.bind("<Enter>", self._sidebar_divider_hover)
        self.sidebar_separator.bind("<Leave>", self._sidebar_divider_unhover)

        self.main_panel = tk.Frame(self.shell, bg="#f7f7f8")
        self.main_panel.pack(side="left", fill="both", expand=True)

        self.header = tk.Frame(self.main_panel, bg="#f7f7f8", padx=24, pady=16)
        self.header.pack(fill="x")
        self.title_label = tk.Label(
            self.header, text="New conversation", bg="#f7f7f8", fg="#17201f",
            font=("Segoe UI", 14, "bold"), anchor="w"
        )
        self.title_label.pack(side="left")
        self.settings_button = self._create_rounded_button(
            self.header, "⚙  Settings", self.open_settings,
            variant="main", height=36, padding=13,
        )
        self.settings_button.pack(side="right", padx=(8, 0))
        self.theme_button = self._create_rounded_button(
            self.header, "◐  Dark mode", self.toggle_theme,
            variant="main", height=36, padding=13,
        )
        self.theme_button.pack(side="right", padx=(8, 0))

        chat_area = tk.Frame(self.main_panel, bg="#f7f7f8")
        chat_area.pack(fill="both", expand=True, padx=24)
        self.chat = tk.Canvas(chat_area, bg="#f7f7f8", highlightthickness=0, bd=0)
        self.chat_scrollbar = ttk.Scrollbar(chat_area, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=self.chat_scrollbar.set)
        self.chat_scrollbar.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat_inner = tk.Frame(self.chat, bg="#f7f7f8")
        self.chat_window = self.chat.create_window((0, 0), window=self.chat_inner, anchor="nw")
        self.chat_inner.bind("<Configure>", self._update_chat_scrollregion)
        self.chat.bind("<Configure>", self._resize_chat_inner)
        self.chat_render_width = 0
        self.chat.bind_all("<MouseWheel>", self._on_chat_mousewheel)

        self.prompt_area = tk.Frame(self.main_panel, bg="#f7f7f8", padx=24, pady=14)
        self.prompt_area.pack(fill="x")
        self.prompt_shell = tk.Canvas(
            self.prompt_area, height=96, bg="#f7f7f8",
            highlightthickness=0, bd=0
        )
        self.prompt_shell.pack(fill="x")
        self.prompt_shell.bind("<Configure>", self._redraw_prompt_shell)
        self.prompt = tk.Text(
            self.prompt_shell, height=2, wrap="word", bg="#ffffff", fg="#17201f",
            insertbackground="#17201f", relief="flat", bd=0, padx=5, pady=5,
            font=("Segoe UI", 11)
        )
        self.prompt_window = self.prompt_shell.create_window(
            (28, 18), window=self.prompt, anchor="nw"
        )
        self.prompt.bind("<Control-Return>", self._send_on_shortcut)
        self.prompt.bind("<Return>", self._send_on_return)
        self.prompt.bind("<FocusIn>", self._clear_prompt_placeholder)
        self.prompt.bind("<FocusOut>", self._restore_prompt_placeholder)
        self.prompt_placeholder_active = False
        self.send_button = tk.Canvas(
            self.prompt_shell, width=42, height=42, bg="#ffffff",
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self.send_window = self.prompt_shell.create_window(
            (0, 0), window=self.send_button, anchor="nw"
        )
        self.send_button.create_oval(2, 2, 40, 40, fill="#10a37f", outline="", tags="send-circle")
        self.send_button.create_text(21, 20, text="↑", fill="#ffffff", font=("Segoe UI", 16, "bold"), tags="send-arrow")
        self.send_button.bind("<Button-1>", lambda _event: self.send_message())
        self.send_button.bind("<Enter>", self._send_button_hover)
        self.send_button.bind("<Leave>", self._send_button_unhover)
        self.quick_actions = tk.Frame(self.prompt_area, bg="#f7f7f8")
        self.quick_actions.pack(fill="x", pady=(0, 6), before=self.prompt_shell)
        self.quick_action_buttons = []
        for text_key, prompt in (
            ("quick_list", "List files in folder 1"),
            ("quick_search", "Search filenames for "),
            ("quick_organize", "Preview organization for folder 1"),
            ("quick_apply", "Apply the previewed organization"),
        ):
            button = tk.Canvas(
                self.quick_actions, height=34, bg="#f7f7f8",
                highlightthickness=0, bd=0, cursor="hand2"
            )
            button.text_key = text_key
            button.command = lambda value=prompt: self._fill_prompt(value)
            button.bind("<Button-1>", lambda _event, target=button: target.command())
            button.bind("<Enter>", lambda _event, target=button: self._style_quick_action(target, hovering=True))
            button.bind("<Leave>", lambda _event, target=button: self._style_quick_action(target))
            button.pack(side="left", padx=(0, 7))
            self.quick_action_buttons.append((button, text_key))
            self._style_quick_action(button)

        self._apply_theme()
        self._refresh_language()
        self._restore_prompt_placeholder()
        self._append(self._t("ready"), role="system")

    def _create_rounded_button(
        self, parent, text, command, variant="main", anchor="center",
        height=36, padding=14, bold=False,
    ):
        font = tkfont.Font(
            root=self.root, family="Segoe UI", size=9, weight="bold" if bold else "normal"
        )
        width = font.measure(text) + padding * 2
        button = tk.Canvas(
            parent, width=width, height=height, highlightthickness=0,
            bd=0, cursor="hand2",
        )
        button.button_text = text
        button.button_command = command
        button.button_variant = variant
        button.button_anchor = anchor
        button.button_font = font
        button.button_padding = padding
        button.button_bold = bold
        button.button_hovering = False
        button.bind("<Button-1>", lambda _event: button.button_command())
        button.bind("<Enter>", lambda _event: self._set_button_hover(button, True))
        button.bind("<Leave>", lambda _event: self._set_button_hover(button, False))
        button.bind("<Configure>", lambda _event: self._style_rounded_button(button))
        self._style_rounded_button(button)
        return button

    def _style_rounded_button(self, button):
        colors = self._theme_colors()
        if button.button_variant == "accent":
            base = colors["accent"]
            fill = base
            text_color = "#ffffff"
        else:
            base = colors["sidebar"] if button.button_variant == "sidebar" else colors["main"]
            fill = colors["hover"] if button.button_hovering else base
            text_color = colors["text"] if button.button_bold or button.button_hovering else colors["muted"]
        width = max(button.winfo_width(), button.winfo_reqwidth())
        height = max(button.winfo_height(), button.winfo_reqheight())
        button.configure(bg=base)
        button.delete("all")
        self._draw_rounded_rectangle(
            button, 1, 1, width - 1, height - 1,
            radius=height // 2, fill=fill,
        )
        x = button.button_padding if button.button_anchor == "w" else width / 2
        button.create_text(
            x, height / 2,
            text=button.button_text, anchor="w" if button.button_anchor == "w" else "center",
            fill=text_color, font=button.button_font,
        )

    def _set_rounded_button_text(self, button, text):
        button.button_text = text
        button.configure(width=button.button_font.measure(text) + button.button_padding * 2)
        self._style_rounded_button(button)

    def _style_quick_action(self, button, hovering=False):
        colors = self._theme_colors()
        text = self._t(button.text_key)
        font = self.quick_action_font
        width = font.measure(text) + 28
        button.configure(
            width=width, bg=colors["main"],
            cursor="hand2",
        )
        button.delete("all")
        self._draw_rounded_rectangle(
            button, 1, 1, width - 1, 33, radius=16,
            fill=colors["hover"] if hovering else colors["card"],
            outline=colors["border"] if not hovering else colors["hover"],
            width=1,
        )
        button.create_text(
            width / 2, 17, text=text,
            fill=colors["text"] if hovering else colors["muted"],
            font=font,
        )

    def _set_button_hover(self, button, hovering):
        button.button_hovering = hovering
        self._style_rounded_button(button)

    def _redraw_prompt_shell(self, event=None):
        width = event.width if event else self.prompt_shell.winfo_width()
        height = event.height if event else self.prompt_shell.winfo_height()
        if width < 30 or height < 30:
            return
        colors = self._theme_colors()
        self.prompt_shell.delete("composer-background")
        self._draw_rounded_rectangle(
            self.prompt_shell, 3, 4, width - 2, height - 1,
            radius=42, fill=colors["border"], tags=("composer-background",)
        )
        self._draw_rounded_rectangle(
            self.prompt_shell, 2, 1, width - 3, height - 6,
            radius=40, fill=colors["card"], outline=colors["border"],
            width=1, tags=("composer-background",)
        )
        self.prompt_shell.tag_lower("composer-background")
        self.prompt_shell.coords(self.prompt_window, 27, 14)
        self.prompt_shell.itemconfigure(
            self.prompt_window,
            width=max(100, width - 108), height=height - 25
        )
        self.prompt_shell.coords(
            self.send_window, max(30, width - 66), max(12, (height - 42) / 2 - 2)
        )

    def _send_button_hover(self, _event=None):
        if str(self.send_button.cget("state")) != "disabled":
            self.send_button.itemconfigure("send-circle", fill=self._theme_colors()["hover"])

    def _send_button_unhover(self, _event=None):
        self.send_button.itemconfigure("send-circle", fill=self._theme_colors()["accent"])

    def _clear_prompt_placeholder(self, _event=None):
        if self.prompt_placeholder_active:
            self.prompt.delete("1.0", "end")
            self.prompt.configure(fg=self._theme_colors()["text"])
            self.prompt_placeholder_active = False

    def _restore_prompt_placeholder(self, _event=None):
        if not self.prompt.get("1.0", "end-1c").strip():
            self.prompt.delete("1.0", "end")
            self.prompt.insert("1.0", self._t("composer_hint"))
            self.prompt.configure(fg=self._theme_colors()["muted"])
            self.prompt_placeholder_active = True

    def _theme_colors(self):
        palette = INTERFACE_PRESETS[self.accent_preset]["dark" if self.dark_mode else "light"]
        if self.dark_mode:
            colors = {
                **palette,
                "text": "#ececec", "muted": "#a1a1a1",
                "assistant_bubble": palette["card"],
                "system_bubble": palette["main"],
                "hover": palette["border"],
                "success": "#55c89a", "warning": "#e5b567",
                "sidebar_divider": palette["border"],
            }
        else:
            colors = {
                **palette,
                "text": "#17201f", "muted": "#6b7280",
                "assistant_bubble": palette["card"],
                "system_bubble": palette["main"],
                "hover": palette["border"],
                "success": "#16845b", "warning": "#a66a12",
                "sidebar_divider": palette["border"],
            }
        colors["accent"] = self.accent_color
        return colors

    def _apply_theme(self):
        colors = self._theme_colors()
        self.root.configure(bg=colors["main"])
        for widget in (self.shell, self.main_panel, self.header, self.chat, self.chat_inner, self.prompt_area, self.prompt_shell, self.quick_actions):
            widget.configure(bg=colors["main"])
        self.sidebar_separator.configure(bg=colors["sidebar_divider"])
        for widget in (self.sidebar, self.brand_label, self.folders_heading, self.folder_count_label, self.privacy_label):
            widget.configure(bg=colors["sidebar"])
        for widget in (self.brand_label, self.title_label):
            widget.configure(fg=colors["text"])
        for widget in (self.folders_heading, self.folder_count_label, self.privacy_label):
            widget.configure(fg=colors["muted"])
        self.folder_list.configure(
            bg=colors["sidebar"], fg=colors["text"],
            selectbackground=colors["selection"], selectforeground=colors["text"]
        )
        for button in (self.new_chat_button, self.add_folder_button, self.remove_folder_button, self.theme_button, self.settings_button):
            self._style_rounded_button(button)
        self.sidebar_separator.configure(cursor="sb_h_double_arrow")
        for button, _key in self.quick_action_buttons:
            self._style_quick_action(button)
        self.prompt.configure(bg=colors["card"], fg=colors["text"], insertbackground=colors["text"])
        if self.prompt_placeholder_active:
            self.prompt.configure(fg=colors["muted"])
        self.send_button.configure(bg=colors["card"])
        self.send_button.itemconfigure("send-circle", fill=colors["accent"], outline="")
        self.style.configure(
            "Vertical.TScrollbar",
            background=colors["sidebar"],
            troughcolor=colors["main"],
            bordercolor=colors["main"],
            arrowcolor=colors["muted"],
        )
        self.title_label.configure(bg=colors["main"])
        self._redraw_prompt_shell()
        self._refresh_language()
        self._set_button_hover(self.new_chat_button, False)
        self._set_button_hover(self.add_folder_button, False)
        self._set_button_hover(self.remove_folder_button, False)
        self._set_button_hover(self.theme_button, False)
        self._set_button_hover(self.settings_button, False)
        self._render_chat_items()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()
        self._save_settings()

    def new_chat(self):
        if self.busy:
            return
        self.research_session_id = None
        self.organization_plan = None
        self.chat_items.clear()
        self.title_label.configure(text=self._t("new_conversation"))
        self._render_chat_items()
        self._append(self._t("ready"), role="system")

    def open_settings(self):
        if getattr(self, "settings_window", None) and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        colors = self._theme_colors()
        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title(self._t("settings_title"))
        window.geometry("390x360")
        window.resizable(False, False)
        window.configure(bg=colors["main"])
        window.transient(self.root)

        body = tk.Frame(window, bg=colors["main"], padx=24, pady=22)
        body.pack(fill="both", expand=True)
        title = tk.Label(
            body, text=self._t("settings_title"), bg=colors["main"],
            fg=colors["text"], font=("Segoe UI", 17, "bold"), anchor="w"
        )
        title.pack(fill="x")
        subtitle = tk.Label(
            body, text=self._t("settings_subtitle"), bg=colors["main"],
            fg=colors["muted"], font=("Segoe UI", 9), anchor="w"
        )
        subtitle.pack(fill="x", pady=(3, 20))

        appearance_label = tk.Label(
            body, text=self._t("appearance"), bg=colors["main"],
            fg=colors["text"], font=("Segoe UI", 10, "bold"), anchor="w"
        )
        appearance_label.pack(fill="x", pady=(0, 9))
        self.settings_dark_var = tk.BooleanVar(value=self.dark_mode)
        dark_toggle = tk.Checkbutton(
            body, text=self._t("dark_theme"), variable=self.settings_dark_var,
            command=self._settings_theme_changed, bg=colors["main"],
            fg=colors["text"], activebackground=colors["main"],
            activeforeground=colors["text"], selectcolor=colors["card"],
            font=("Segoe UI", 9), anchor="w", relief="flat",
        )
        dark_toggle.pack(fill="x", pady=(0, 13))

        accent_row = tk.Frame(body, bg=colors["main"])
        accent_row.pack(fill="x", pady=(0, 18))
        accent_label = tk.Label(
            accent_row, text=self._t("accent_color"), bg=colors["main"],
            fg=colors["text"], font=("Segoe UI", 9), anchor="w"
        )
        accent_label.pack(side="left")
        self.accent_preview = tk.Canvas(
            accent_row, width=76, height=24, bg=colors["main"],
            highlightthickness=0, bd=0
        )
        self.accent_preview.pack(side="right", padx=(8, 0), pady=2)
        self.accent_preset_var = tk.StringVar(
            value=self._t(f"preset_{self.accent_preset}")
        )
        self.accent_preset_box = ttk.Combobox(
            accent_row,
            textvariable=self.accent_preset_var,
            values=[self._t(f"preset_{key}") for key in INTERFACE_PRESETS],
            state="readonly",
            width=14,
        )
        self.accent_preset_box.pack(side="right")
        self.accent_preset_box.bind("<<ComboboxSelected>>", self._settings_accent_changed)

        language_row = tk.Frame(body, bg=colors["main"])
        language_row.pack(fill="x", pady=(0, 22))
        language_label = tk.Label(
            language_row, text=self._t("language"), bg=colors["main"],
            fg=colors["text"], font=("Segoe UI", 9), anchor="w"
        )
        language_label.pack(side="left")
        self.language_var = tk.StringVar(value="हिन्दी" if self.language == "hi" else "English")
        self.language_box = ttk.Combobox(
            language_row, textvariable=self.language_var,
            values=("English", "हिन्दी"), state="readonly", width=16
        )
        self.language_box.pack(side="right")
        self.language_box.bind("<<ComboboxSelected>>", self._settings_language_changed)

        done_button = self._create_rounded_button(
            body, self._t("close"), window.destroy,
            variant="accent", height=38, padding=20, bold=True,
        )
        done_button.pack(anchor="e")
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        self.settings_labels = {
            "title": title, "subtitle": subtitle, "appearance": appearance_label,
            "dark": dark_toggle, "accent": accent_label,
            "language": language_label, "done": done_button,
        }
        self._style_settings_window()

    def _style_settings_window(self):
        if not getattr(self, "settings_window", None) or not self.settings_window.winfo_exists():
            return
        colors = self._theme_colors()
        self.settings_window.configure(bg=colors["main"])
        for child in self.settings_window.winfo_children():
            child.configure(bg=colors["main"])
        for key in ("title", "appearance"):
            self.settings_labels[key].configure(fg=colors["text"])
        for key in ("subtitle", "accent", "language"):
            self.settings_labels[key].configure(fg=colors["muted"] if key == "subtitle" else colors["text"])
        self.settings_labels["dark"].configure(
            bg=colors["main"], fg=colors["text"], activebackground=colors["main"],
            activeforeground=colors["text"], selectcolor=colors["card"]
        )
        self._style_rounded_button(self.settings_labels["done"])
        self.accent_preview.configure(bg=colors["main"])
        self.accent_preview.delete("all")
        self.accent_preview.create_rectangle(1, 2, 24, 22, fill=colors["main"], outline=colors["border"])
        self.accent_preview.create_rectangle(26, 2, 49, 22, fill=colors["sidebar"], outline=colors["border"])
        self.accent_preview.create_rectangle(51, 2, 75, 22, fill=colors["accent"], outline="")
        self.style.configure(
            "Settings.TCombobox",
            fieldbackground=colors["card"], background=colors["card"],
            foreground=colors["text"], arrowcolor=colors["text"],
        )
        self.accent_preset_box.configure(style="Settings.TCombobox")
        self.language_box.configure(style="Settings.TCombobox")

    def _settings_theme_changed(self):
        self.dark_mode = self.settings_dark_var.get()
        self._apply_theme()
        self._style_settings_window()
        self._save_settings()

    def _settings_language_changed(self, _event=None):
        self.language = "hi" if self.language_var.get() == "हिन्दी" else "en"
        self._refresh_language()
        self._save_settings()

    def _settings_accent_changed(self, _event=None):
        selected = self.accent_preset_var.get()
        self.accent_preset = next(
            key for key in INTERFACE_PRESETS
            if self._t(f"preset_{key}") == selected
        )
        self._apply_theme()
        self._style_settings_window()
        self._save_settings()

    def _refresh_language(self):
        self._set_rounded_button_text(self.new_chat_button, self._t("new_chat"))
        self.folders_heading.configure(text=self._t("folders"))
        count = len(self.folders)
        count_key = "folder_count_one" if count == 1 else "folder_count"
        self.folder_count_label.configure(text=self._t(count_key).format(count=count))
        self._set_rounded_button_text(self.add_folder_button, self._t("add_folder"))
        self._set_rounded_button_text(self.remove_folder_button, self._t("remove_folder"))
        self._set_rounded_button_text(self.theme_button, self._t("theme_light" if self.dark_mode else "theme_dark"))
        self._set_rounded_button_text(self.settings_button, self._t("settings"))
        self.privacy_label.configure(
            text=self._t("privacy"),
            wraplength=max(150, self.sidebar_width - 32),
        )
        for button, key in self.quick_action_buttons:
            self._style_quick_action(button)
        if self.prompt_placeholder_active:
            self.prompt.delete("1.0", "end")
            self.prompt.insert("1.0", self._t("composer_hint"))
        if self.title_label.cget("text") in {"New conversation", "नई बातचीत"}:
            self.title_label.configure(text=self._t("new_conversation"))
        if getattr(self, "settings_labels", None) and self.settings_window.winfo_exists():
            labels = self.settings_labels
            self.settings_window.title(self._t("settings_title"))
            labels["title"].configure(text=self._t("settings_title"))
            labels["subtitle"].configure(text=self._t("settings_subtitle"))
            labels["appearance"].configure(text=self._t("appearance"))
            labels["dark"].configure(text=self._t("dark_theme"))
            labels["accent"].configure(text=self._t("accent_color"))
            labels["language"].configure(text=self._t("language"))
            self._set_rounded_button_text(labels["done"], self._t("close"))
            self.language_var.set("हिन्दी" if self.language == "hi" else "English")
            self.accent_preset_var.set(self._t(f"preset_{self.accent_preset}"))
            self.accent_preset_box.configure(
                values=[self._t(f"preset_{key}") for key in INTERFACE_PRESETS]
            )

    def _update_chat_scrollregion(self, _event=None):
        self.chat.configure(scrollregion=self.chat.bbox("all"))

    def _resize_chat_inner(self, event):
        self.chat.itemconfigure(self.chat_window, width=event.width)
        if self.chat_render_width != event.width and self.chat_items:
            self.chat_render_width = event.width
            self.chat.after_idle(self._render_chat_items)

    def _send_on_shortcut(self, _event):
        self.send_message()
        return "break"

    def _send_on_return(self, event):
        if event.state & 0x0001:
            return None
        self.send_message()
        return "break"

    def _fill_prompt(self, value):
        self._clear_prompt_placeholder()
        self.prompt.delete("1.0", "end")
        self.prompt.insert("1.0", value)
        self.prompt.focus_set()
        self.prompt.mark_set("insert", "end-1c")

    def _on_chat_mousewheel(self, event):
        if self.chat.winfo_exists():
            self.chat.yview_scroll(int(-event.delta / 120), "units")

    def _render_chat_items(self):
        for child in self.chat_inner.winfo_children():
            child.destroy()
        colors = self._theme_colors()
        for item in self.chat_items:
            self._create_chat_bubble(item, colors)
        self.chat.after_idle(lambda: self.chat.yview_moveto(1.0))

    def _create_chat_bubble(self, item, colors=None):
        colors = colors or self._theme_colors()
        role = item["role"]
        text = item["text"]
        if role == "user" and text.startswith("You: "):
            text = text[5:]
        elif role == "assistant" and text.startswith("Assistant: "):
            text = text[11:]
        background = {
            "user": colors["user_bubble"],
            "assistant": colors["assistant_bubble"],
            "thinking": colors["system_bubble"],
            "system": colors["system_bubble"],
        }.get(role, colors["assistant_bubble"])
        foreground = colors["muted"] if role in {"system", "thinking"} else colors["text"]

        row = tk.Frame(self.chat_inner, bg=colors["main"])
        row.pack(fill="x", pady=(5, 10))
        bubble_font = self.chat_font
        max_text_width = max(220, min(680, self.chat.winfo_width() - 150))
        lines = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            line = ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if line and bubble_font.measure(candidate) > max_text_width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        display_text = "\n".join(lines)
        text_width = max((bubble_font.measure(line) for line in lines), default=40)
        bubble_width = min(max_text_width + 40, max(120, text_width + 40))
        label_text = {"user": "", "assistant": "HADAL", "thinking": "HADAL", "system": "INFO"}.get(role, "")
        bubble_height = max(48, len(lines) * 21 + (34 if role == "user" else 48))
        bubble = tk.Canvas(
            row, width=bubble_width, height=bubble_height, bg=colors["main"],
            highlightthickness=0, bd=0
        )
        if role == "user":
            bubble.pack(side="right", padx=(72, 8))
        elif role == "system":
            bubble.pack(anchor="center")
        else:
            bubble.pack(side="left", padx=(8, 72))
        self._draw_rounded_rectangle(
            bubble, 2, 2, bubble_width - 2, bubble_height - 2,
            radius=min(28, bubble_height // 2) if role == "user" else 24,
            fill=background
        )
        if label_text:
            bubble.create_text(
                20, 11, anchor="nw", text=label_text, fill=colors["muted"],
                font=("Segoe UI", 9, "bold")
            )
        bubble.create_text(
            20, 17 if role == "user" else 31, anchor="nw", text=display_text, fill=foreground,
            font=bubble_font, width=bubble_width - 40, justify="left"
        )
        item["widget"] = row

    @staticmethod
    def _draw_rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        canvas.create_polygon(points, smooth=True, splinesteps=20, **kwargs)

    def _load_api_key(self):
        if self.tinyfish_api_key:
            self._set_connection_status("TinyFish key found", "success")
            self._append(
                "TinyFish API key found. Research mode is ready; selected folders are only used for local file actions.\n",
                role="system",
            )
        else:
            self._set_connection_status("TinyFish key needed", "missing")
            self._append(self._t("tinyfish_key_error"), role="system")

    def _append(self, text, role="system"):
        message = text.rstrip("\n")
        item = {"role": role, "text": message, "widget": None}
        self.chat_items.append(item)
        if role == "user" and self.title_label.cget("text") in {"New conversation", "नई बातचीत"}:
            title = (message[5:] if message.startswith("You: ") else message).replace("\n", " ").strip()
            self.title_label.configure(text=title[:36] + ("…" if len(title) > 36 else ""))
        self._create_chat_bubble(item)
        self.chat.after_idle(lambda: self.chat.yview_moveto(1.0))

    def _set_connection_status(self, text, color):
        if color == "success":
            self.connection_status = "connected"
        elif color == "unavailable":
            self.connection_status = "unavailable"
        else:
            self.connection_status = "missing"

    def add_folder(self):
        chosen = filedialog.askdirectory(title="Choose a folder the assistant may access", mustexist=True)
        if not chosen:
            return
        try:
            path = safe_root(chosen)
        except Exception as exc:
            messagebox.showerror("Folder not available", str(exc))
            return

        # Avoid duplicates and redundant nested roots; users can still add any separate folder.
        if path in self.folders:
            messagebox.showinfo("Already added", "That folder is already selected.")
            return
        self.folders.append(path)
        self._refresh_folders()
        self._append(f"Added folder {len(self.folders)}: {path}\n", role="system")

    def remove_folder(self):
        selection = self.folder_list.curselection()
        if not selection:
            messagebox.showinfo("Select a folder", "Choose a folder in the list first.")
            return
        idx = selection[0]
        removed = self.folders.pop(idx)
        self.organization_plan = None
        self._refresh_folders()
        self._append(f"Removed selected folder: {removed}\nThe previous organization plan was cleared.\n", role="system")

    def _refresh_folders(self):
        self.folder_list.delete(0, "end")
        for index, folder in enumerate(self.folders, start=1):
            self.folder_list.insert("end", f"{index}. {folder}")
        count = len(self.folders)
        self.folder_count_label.configure(
            text=f"{count} folder{'s' if count != 1 else ''} connected"
        )

    def _root_by_index(self, index):
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("Folder index must be an integer.")
        if index < 1 or index > len(self.folders):
            raise ValueError("That folder index is not in the current selected-folder list.")
        root = safe_root(str(self.folders[index - 1]))
        return root

    def _tool_list_files(self, root_index, subfolder):
        root = self._root_by_index(root_index)
        folder = safe_child(root, subfolder, must_exist=True)
        if not folder.is_dir():
            raise ValueError("That path is not a folder.")
        entries = []
        for item in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if item.is_symlink():
                    continue
                if not is_inside(item.resolve(strict=True), root):
                    continue
                suffix = "/" if item.is_dir() else ""
                entries.append(item.name + suffix)
            except (OSError, RuntimeError):
                continue
            if len(entries) >= 500:
                break
        rel = "." if folder == root else str(folder.relative_to(root))
        return {"root_index": root_index, "folder": rel, "entries": entries, "truncated": len(entries) >= 500}

    def _tool_search(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search text cannot be empty.")
        matches = []
        q = query.casefold()
        for index, stored_root in enumerate(self.folders, start=1):
            try:
                root = safe_root(str(stored_root))
            except (OSError, ValueError):
                continue
            for current, dirs, files in os.walk(root, followlinks=False, onerror=lambda _e: None):
                current_path = Path(current)
                dirs[:] = [
                    name for name in dirs
                    if not (current_path / name).is_symlink()
                    and self._is_safe_resolved(current_path / name, root)
                ]
                for name in files:
                    p = current_path / name
                    if p.is_symlink() or q not in name.casefold():
                        continue
                    try:
                        resolved = p.resolve(strict=True)
                        if not is_inside(resolved, root):
                            continue
                        rel = str(p.relative_to(root))
                        matches.append({"root_index": index, "path": rel})
                    except (OSError, RuntimeError):
                        continue
                    if len(matches) >= 500:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    @staticmethod
    def _is_safe_resolved(path, root):
        try:
            return is_inside(path.resolve(strict=True), root)
        except (OSError, RuntimeError):
            return False

    def _tool_preview(self, root_index):
        root = self._root_by_index(root_index)
        plan = []
        skipped = []
        for source in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if source.is_symlink() or not source.is_file():
                    continue
                if not is_inside(source.resolve(strict=True), root):
                    continue
                ext = source.suffix[1:].upper() if source.suffix else "_NO_EXTENSION"
                # Prevent special directory names from being interpreted as paths.
                if ext in {"", ".", ".."} or "/" in ext or "\\" in ext:
                    ext = "_NO_EXTENSION"
                dest_dir = root / ext
                dest = dest_dir / source.name
                if dest.exists() or dest.is_symlink():
                    skipped.append({"source": source.name, "reason": "Destination already exists."})
                    continue
                plan.append({
                    "root_index": root_index,
                    "source_name": source.name,
                    "extension_folder": ext,
                    "destination_name": source.name
                })
            except (OSError, RuntimeError):
                skipped.append({"source": source.name, "reason": "Could not safely inspect this file."})

        self.organization_plan = {"root_index": root_index, "root": root, "moves": plan}
        return {
            "root_index": root_index,
            "folder_name": root.name or str(root),
            "moves": [{"source": x["source_name"], "destination": f'{x["extension_folder"]}/{x["destination_name"]}'} for x in plan],
            "count": len(plan),
            "skipped": skipped,
            "note": "Preview only; no files have been changed. Only files directly inside this selected folder are considered."
        }

    def _tool_apply(self):
        saved = self.organization_plan
        if not saved:
            return {"status": "No current preview. Preview an organization plan first."}
        root = safe_root(str(saved["root"]))
        if root != saved["root"]:
            self.organization_plan = None
            return {"status": "Selected folder changed; preview again."}
        moves = saved["moves"]
        if not moves:
            self.organization_plan = None
            return {"status": "Nothing needs to be moved."}

        lines = []
        for item in moves[:100]:
            lines.append(f'{item["source_name"]}  ->  {item["extension_folder"]}/{item["destination_name"]}')
        if len(moves) > 100:
            lines.append(f"... and {len(moves) - 100} more move(s)")
        message = (
            f"Move {len(moves)} file(s) in this folder?\n\n{root}\n\n"
            + "\n".join(lines)
            + "\n\nNo files will be overwritten. Continue?"
        )
        approved = messagebox.askyesno("Confirm file moves", message, icon="warning")
        if not approved:
            self.organization_plan = None
            return {"status": "Cancelled by user. No files were moved."}

        moved, skipped = [], []
        for item in moves:
            try:
                # Only simple filenames and extension folder names are accepted.
                source_name = item["source_name"]
                ext = item["extension_folder"]
                if Path(source_name).name != source_name or source_name in {".", ".."}:
                    raise ValueError("Unsafe source filename.")
                if Path(ext).name != ext or ext in {"", ".", ".."} or "/" in ext or "\\" in ext:
                    raise ValueError("Unsafe destination folder.")
                source = root / source_name
                if source.is_symlink() or not source.is_file() or not is_inside(source.resolve(strict=True), root):
                    skipped.append({"source": source_name, "reason": "Source is missing or unsafe."})
                    continue

                target_folder = root / ext
                if target_folder.exists() and (target_folder.is_symlink() or not target_folder.is_dir()):
                    skipped.append({"source": source_name, "reason": "Destination folder is not a safe directory."})
                    continue
                target_folder.mkdir(exist_ok=True)
                target_folder = target_folder.resolve(strict=True)
                if not is_inside(target_folder, root):
                    skipped.append({"source": source_name, "reason": "Destination escaped selected folder."})
                    continue

                target = target_folder / source_name
                if target.exists() or target.is_symlink():
                    skipped.append({"source": source_name, "reason": "Destination already exists."})
                    continue
                # Source is a direct child of root; target is inside a child folder of root.
                source.rename(target)
                moved.append({"source": source_name, "destination": f"{ext}/{source_name}"})
            except Exception as exc:
                skipped.append({"source": item.get("source_name", "?"), "reason": str(exc)})

        self.organization_plan = None
        return {"status": "Organization finished.", "moved": moved, "skipped": skipped}

    def _run_tool(self, name, args):
        if name == "list_files":
            return self._tool_list_files(args.get("root_index"), args.get("subfolder", ""))
        if name == "search_filenames":
            return self._tool_search(args.get("query", ""))
        if name == "preview_organization":
            return self._tool_preview(args.get("root_index"))
        if name == "apply_organization":
            return self._tool_apply()
        raise ValueError("Unsupported tool requested.")

    def send_message(self):
        if self.busy:
            return
        if self.prompt_placeholder_active:
            return
        text = self.prompt.get("1.0", "end").strip()
        if not text:
            return
        self.prompt.delete("1.0", "end")
        self._append(f"You: {text}\n", role="user")

        if not self.tinyfish_api_key and not self._is_local_command(text):
            messagebox.showerror(
                "TinyFish API key missing",
                "Create a .env file beside the app with TINYFISH_API_KEY=your_tinyfish_key_here, then restart HADAL."
            )
            return

        self.busy = True
        self.send_button.configure(state="disabled")
        self._append(self._t("research_status") + "\n", role="thinking")

        threading.Thread(target=self._request_worker, args=(text,), daemon=True).start()

    def _request_worker(self, user_text):
        try:
            local_result = self._run_local_command(user_text)
            if local_result is not None:
                answer = "Local file action:\n" + json.dumps(local_result, ensure_ascii=False, indent=2)
            else:
                report = run_tinyfish_research(
                    user_text,
                    self.tinyfish_api_key,
                    language=self.language,
                    session_id=self.research_session_id,
                    on_delta=lambda text: self.root.after(
                        0, self._show_research_progress, text
                    ),
                )
                self.research_session_id = report["session_id"]
                answer = format_research_report(report["result"])
            self.root.after(0, self._finish_request, answer, None)
        except Exception as exc:
            self.root.after(0, self._finish_request, None, str(exc))

    def _show_research_progress(self, text):
        for item in reversed(self.chat_items):
            if item["role"] == "thinking":
                item["text"] = f"Assistant: {text}" if text else self._t("research_status")
                self._render_chat_items()
                return

    def _run_local_command(self, user_text):
        match = re.fullmatch(r"\s*list files in folder\s+(\d+)\s*", user_text, re.IGNORECASE)
        if match:
            return self._tool_list_files(int(match.group(1)), "")

        match = re.fullmatch(r"\s*search filenames for(?:\s+(.*))?\s*", user_text, re.IGNORECASE)
        if match:
            return self._tool_search(match.group(1))

        match = re.fullmatch(r"\s*preview organization for folder\s+(\d+)\s*", user_text, re.IGNORECASE)
        if match:
            return self._tool_preview(int(match.group(1)))

        if re.fullmatch(
            r"\s*apply (?:the )?(?:previewed )?organization\s*", user_text, re.IGNORECASE
        ):
            return self._run_tool_threadsafe("apply_organization", {})
        return None

    @staticmethod
    def _is_local_command(user_text):
        return any((
            re.fullmatch(r"\s*list files in folder\s+\d+\s*", user_text, re.IGNORECASE),
            re.fullmatch(r"\s*search filenames for(?:\s+.*)?\s*", user_text, re.IGNORECASE),
            re.fullmatch(r"\s*preview organization for folder\s+\d+\s*", user_text, re.IGNORECASE),
            re.fullmatch(
                r"\s*apply (?:the )?(?:previewed )?organization\s*", user_text, re.IGNORECASE
            ),
        ))

    def _run_tool_threadsafe(self, name, args):
        if name != "apply_organization":
            # Folder state is read by the worker; GUI mutations are disabled only for Send,
            # so protect list state with the app's normal simple single-user interaction model.
            return self._run_tool(name, args)

        event = threading.Event()
        result_box = {}

        def ask_on_gui_thread():
            try:
                result_box["result"] = self._tool_apply()
            except Exception as exc:
                result_box["result"] = {"error": str(exc)}
            finally:
                event.set()

        self.root.after(0, ask_on_gui_thread)
        if not event.wait(timeout=600):
            return {"status": "Confirmation timed out; no move was performed."}
        return result_box.get("result", {"error": "No confirmation result."})

    def _finish_request(self, answer, error):
        # Remove the temporary "Thinking…" line without clearing earlier conversation.
        self._remove_thinking_line()
        if error:
            self._append(f"Error: {error}\n", role="system")
        else:
            self._append(f"Assistant: {answer}\n", role="assistant")
        self.busy = False
        self.send_button.configure(state="normal")

    def _remove_thinking_line(self):
        for index in range(len(self.chat_items) - 1, -1, -1):
            if self.chat_items[index]["role"] == "thinking":
                self.chat_items.pop(index)
                self._render_chat_items()
                break


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    LocalFileAIApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
