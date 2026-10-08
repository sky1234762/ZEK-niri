"""Terminal UI primitives: raw key reading, menus, checkbox lists, prompts.

Kept deliberately small. The design charter: order over decoration, no icon
soup, the cursor is always restored (finally / context manager), and disk
writes always get an explicit pre-flight confirmation.
"""

import atexit
import os
import shutil
import sys
import termios
import tty
from contextlib import contextmanager
from typing import List, Optional

from zekniri.constants import Colors
from zekniri.i18n import msg

# --- Display helpers ---------------------------------------------------------

_ANSI_RE = __import__("re").compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def display_width(text: str) -> int:
    """Approximate printable width, ignoring ANSI escapes and wide CJK glyphs."""
    import unicodedata
    clean = _ANSI_RE.sub("", text)
    width = 0
    for ch in clean:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def pad_display(text: str, width: int) -> str:
    """Pad text with spaces so its display width reaches ``width``."""
    gap = width - display_width(text)
    return text + (" " * gap if gap > 0 else "")


def truncate_display(text: str, width: int) -> str:
    """Truncate text to a display width, appending an ellipsis when cut."""
    if display_width(text) <= width:
        return text
    import unicodedata
    out = ""
    used = 0
    for ch in _ANSI_RE.sub("", text):
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def terminal_width(fallback: int = 80) -> int:
    try:
        return shutil.get_terminal_size((fallback, 24)).columns
    except Exception:
        return fallback


def responsive_hint(key: str) -> str:
    """Return an i18n hint string appropriate to the terminal width."""
    return msg(key)


def show_logo() -> None:
    """Print the title from ``logo/title`` verbatim, centered, no added effects.

    Falls back to a plain text title when the terminal is too narrow.
    """
    from zekniri.logo import load_title
    from zekniri.core import get_env
    version = msg("logo_version", get_env().version)
    tagline = msg("logo_tagline")
    note = msg("logo_note")
    width = terminal_width()
    art_text, art_width = load_title()
    if width >= art_width + 4:
        pad = " " * max(0, (width - art_width) // 2)
        version_pad = " " * max(0, (art_width - display_width(version)) // 2)
        note_pad = " " * max(0, (art_width - display_width(note)) // 2)
        sys.stdout.write("\n")
        for line in art_text.splitlines():
            sys.stdout.write(f"{pad}{Colors.BOLD_CYAN}{line}{Colors.RESET}\n")
        sys.stdout.write(f"{pad}{version_pad}{Colors.DIM}{version}{Colors.RESET}\n")
        sys.stdout.write(f"{pad}{Colors.DIM}{tagline}{Colors.RESET}\n")
        sys.stdout.write(f"{pad}{note_pad}{Colors.DIM}{note}{Colors.RESET}\n\n")
    else:
        name = msg("logo_name")
        version_pad = " " * max(0, (display_width(name) - display_width(version)) // 2)
        note_pad = " " * max(0, (display_width(name) - display_width(note)) // 2)
        sys.stdout.write(f"\n  {Colors.BOLD_CYAN}{name}{Colors.RESET}\n")
        sys.stdout.write(f"  {version_pad}{Colors.DIM}{version}{Colors.RESET}\n")
        sys.stdout.write(f"  {Colors.DIM}{tagline}{Colors.RESET}\n")
        sys.stdout.write(f"  {note_pad}{Colors.DIM}{note}{Colors.RESET}\n\n")


# --- Screen control ----------------------------------------------------------

_ALT_SCREEN_ENTER = "\033[?1049h"
_ALT_SCREEN_LEAVE = "\033[?1049l"
_ALT_ACTIVE = False


def enter_alt_screen() -> None:
    """Switch to the terminal's alternate screen buffer (idempotent).

    Every TUI page calls this so the interface is self-contained: on exit the
    terminal is restored to whatever was on screen before. No-op when stdout is
    not a terminal.
    """
    global _ALT_ACTIVE
    if _ALT_ACTIVE or not sys.stdout.isatty():
        return
    sys.stdout.write(_ALT_SCREEN_ENTER + Colors.CURSOR_HIDE)
    sys.stdout.flush()
    _ALT_ACTIVE = True


def leave_alt_screen() -> None:
    """Restore the normal screen buffer (idempotent)."""
    global _ALT_ACTIVE
    if not _ALT_ACTIVE:
        return
    sys.stdout.write(Colors.CURSOR_SHOW + _ALT_SCREEN_LEAVE)
    sys.stdout.flush()
    _ALT_ACTIVE = False


atexit.register(leave_alt_screen)


@contextmanager
def alternate_screen():
    """Scope an interactive session to the alternate screen.

    Enters on the outermost use and leaves on its exit; nested uses are no-ops.
    Even without this scope, TUI pages enter lazily and are left at process exit.
    """
    was_active = _ALT_ACTIVE
    enter_alt_screen()
    try:
        yield
    finally:
        if not was_active:
            leave_alt_screen()


# --- Raw key reading ---------------------------------------------------------

def _drain_pending(fd: int, debounce: bool = False) -> None:
    """Discard buffered input so a held key cannot leak into the next screen."""
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
    except Exception:
        pass
    if debounce:
        import select
        import time
        end = time.monotonic() + 0.12
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.02)
            if r:
                try:
                    os.read(fd, 64)
                except OSError:
                    break


@contextmanager
def raw_input_mode(fd: int):
    """Put the terminal in cbreak mode and always restore it."""
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


def read_key(stream=None) -> str:
    """Read one logical key. Returns names like UP/DOWN/ENTER/ESC or a char.

    ``stream`` may be a raw file object; by default reads from stdin in cbreak
    mode. Raises KeyboardInterrupt on Ctrl-C.
    """
    fd = stream.fileno() if stream is not None else sys.stdin.fileno()
    ch = os.read(fd, 1)
    if not ch:
        return "EOF"
    if ch == b"\x03":
        raise KeyboardInterrupt
    if ch in (b"\r", b"\n"):
        return "ENTER"
    if ch == b"\x1b":
        # Could be ESC alone or an escape sequence. Peek without blocking long.
        import select
        seq = b""
        while True:
            r, _, _ = select.select([fd], [], [], 0.02)
            if not r:
                break
            nxt = os.read(fd, 1)
            if not nxt:
                break
            seq += nxt
            if len(seq) >= 5:
                break
        if not seq:
            return "ESC"
        if seq.startswith(b"[") and seq.endswith(b"~"):
            code = seq[1:-1]
            return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(code.decode(), "ESC")
        if seq[:1] == b"[":
            # ESC [ A/B/C/D  (the final byte may arrive together)
            final = seq[-1:]
            return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(final.decode(errors="replace"), "ESC")
        return "ESC"
    if ch == b"\x7f" or ch == b"\x08":
        return "BACKSPACE"
    if ch == b"\t":
        return "TAB"
    if ch == b" ":
        return "SPACE"
    try:
        return ch.decode("utf-8")
    except UnicodeDecodeError:
        return "?"


# --- Menus -------------------------------------------------------------------

class MenuItem:
    def __init__(self, label: str, style: str = "normal", group_header: str = ""):
        self.label = label
        self.style = style          # normal | warn | subtle
        self.group_header = group_header


def render_menu_item(index: int, label: str, focus: int, style: str = "normal") -> None:
    selected = index == focus
    marker = "❯" if selected else " "
    if style == "warn":
        color = Colors.BOLD_RED
    elif style == "subtle":
        color = Colors.DIM
    elif selected:
        color = Colors.BOLD_CYAN
    else:
        color = Colors.RESET
    line = f"  {marker} {pad_display(label, 52)}"
    sys.stdout.write(f"{color}{line}{Colors.RESET}\n")


class Menu:
    """Vertical menu. Returns the chosen index, or None if cancelled."""

    def __init__(
        self,
        title_key: str,
        items: List[MenuItem],
        hint_key: str = "menu_hint",
        compact: bool = False,
        initial_focus: Optional[int] = None,
    ):
        self.title_key = title_key
        self.items = items
        self.hint_key = hint_key
        self.compact = compact
        self.initial_focus = initial_focus

    def run(self) -> Optional[int]:
        if not sys.stdin.isatty():
            return None
        enter_alt_screen()
        focus = self.initial_focus if self.initial_focus is not None else _first_actionable(self.items)
        if not (0 <= focus < len(self.items)) or not _is_actionable(self.items[focus]):
            focus = _first_actionable(self.items)
        fd = sys.stdin.fileno()
        with raw_input_mode(fd):
            _drain_pending(fd, debounce=True)
            while True:
                sys.stdout.write(Colors.CLEAR_SCREEN)
                show_logo()
                sys.stdout.write(f"  {Colors.BOLD_WHITE}{msg(self.title_key)}{Colors.RESET}\n\n")
                last_header = None
                for i, item in enumerate(self.items):
                    if item.group_header and item.group_header != last_header:
                        last_header = item.group_header
                        sys.stdout.write(f"\n  {Colors.DIM}{item.group_header}{Colors.RESET}\n")
                    render_menu_item(i, item.label, focus, item.style)
                sys.stdout.write(f"\n{responsive_hint(self.hint_key)}\n")
                sys.stdout.flush()

                key = read_key()
                if key in ("UP", "k", "K"):
                    focus = _prev_actionable(self.items, focus)
                elif key in ("DOWN", "j", "J"):
                    focus = _next_actionable(self.items, focus)
                elif key in ("ENTER", "SPACE"):
                    return focus
                elif key in ("q", "Q", "ESC", "0"):
                    return None


def _is_actionable(item: MenuItem) -> bool:
    return item.style != "header"


def _first_actionable(items: List[MenuItem]) -> int:
    for i, it in enumerate(items):
        if _is_actionable(it):
            return i
    return 0


def _next_actionable(items: List[MenuItem], focus: int) -> int:
    for step in range(1, len(items) + 1):
        cand = (focus + step) % len(items)
        if _is_actionable(items[cand]):
            return cand
    return focus


def _prev_actionable(items: List[MenuItem], focus: int) -> int:
    for step in range(1, len(items) + 1):
        cand = (focus - step) % len(items)
        if _is_actionable(items[cand]):
            return cand
    return focus


# --- Checkbox list -----------------------------------------------------------

class CheckboxEntry:
    def __init__(self, key: str, label: str, checked: bool = False, is_separator: bool = False):
        self.key = key
        self.label = label
        self.checked = checked
        self.is_separator = is_separator


class CheckboxList:
    """Multi-select list. Returns the list of checked keys, or None if cancelled."""

    def __init__(self, title_key: str, entries: List[CheckboxEntry], hint_key: str = "selective_hint"):
        self.title_key = title_key
        self.entries = entries
        self.hint_key = hint_key

    def run(self) -> Optional[List[str]]:
        if not sys.stdin.isatty():
            return None
        enter_alt_screen()
        focus = _first_checkable(self.entries)
        fd = sys.stdin.fileno()
        with raw_input_mode(fd):
            _drain_pending(fd, debounce=True)
            while True:
                sys.stdout.write(Colors.CLEAR_SCREEN)
                show_logo()
                sys.stdout.write(f"  {Colors.BOLD_WHITE}{msg(self.title_key)}{Colors.RESET}\n\n")
                for i, e in enumerate(self.entries):
                    if e.is_separator:
                        sys.stdout.write(f"\n  {Colors.DIM}{e.label}{Colors.RESET}\n")
                        continue
                    box = "[✓]" if e.checked else "[ ]"
                    if i == focus:
                        color = Colors.BOLD_CYAN
                    elif e.checked:
                        color = Colors.GREEN
                    else:
                        color = Colors.DIM
                    sys.stdout.write(f"  {color}❯ {box} {e.label}{Colors.RESET}\n" if i == focus
                                     else f"    {color}{box} {e.label}{Colors.RESET}\n")
                sys.stdout.write(f"\n{responsive_hint(self.hint_key)}\n")
                sys.stdout.flush()

                key = read_key()
                if key in ("UP", "k", "K"):
                    focus = _prev_checkable(self.entries, focus)
                elif key in ("DOWN", "j", "J"):
                    focus = _next_checkable(self.entries, focus)
                elif key in ("SPACE",):
                    if not self.entries[focus].is_separator:
                        self.entries[focus].checked = not self.entries[focus].checked
                elif key in ("ENTER",):
                    return [e.key for e in self.entries if e.checked and not e.is_separator]
                elif key in ("a", "A"):
                    for e in self.entries:
                        if not e.is_separator:
                            e.checked = True
                elif key in ("n", "N"):
                    for e in self.entries:
                        if not e.is_separator:
                            e.checked = False
                elif key in ("q", "Q", "ESC"):
                    return None


def _is_checkable(e: CheckboxEntry) -> bool:
    return not e.is_separator


def _first_checkable(entries: List[CheckboxEntry]) -> int:
    for i, e in enumerate(entries):
        if _is_checkable(e):
            return i
    return 0


def _next_checkable(entries: List[CheckboxEntry], focus: int) -> int:
    for step in range(1, len(entries) + 1):
        cand = (focus + step) % len(entries)
        if _is_checkable(entries[cand]):
            return cand
    return focus


def _prev_checkable(entries: List[CheckboxEntry], focus: int) -> int:
    for step in range(1, len(entries) + 1):
        cand = (focus - step) % len(entries)
        if _is_checkable(entries[cand]):
            return cand
    return focus


# --- Prompts -----------------------------------------------------------------

def drain_stdin() -> None:
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass


def prompt_confirm(key: str, default: str = "n", *args) -> bool:
    """Yes/No prompt. Returns True for yes. Non-interactive => default."""
    question = msg(key, *args)
    if not sys.stdin.isatty():
        return default.lower() == "y"
    suffix = "[Y/n]" if default.lower() == "y" else "[y/N]"
    sys.stdout.write(f"{question} {suffix} ")
    sys.stdout.flush()
    drain_stdin()
    answer = sys.stdin.readline().strip().lower()
    if not answer:
        return default.lower() == "y"
    return answer.startswith("y")


def press_any_key() -> None:
    if not sys.stdin.isatty():
        return
    sys.stdout.write(msg("press_any_key"))
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    with raw_input_mode(fd):
        _drain_pending(fd)
        read_key()


def select_language() -> str:
    """Language page, shown before the control panel when appropriate.

    Skipped on later runs when a choice is stored, unless
    ``ask_language_each_start`` is enabled in ``ZEK-niri.conf``. The previously
    chosen language is preselected; Enter confirms. Persists the choice under
    ``~/.config/<PROJECT_NAME>/language``. Returns the selected code.
    """
    from zekniri import i18n
    from zekniri.config import get_config

    if i18n.has_stored_language() and not get_config().ask_language_each_start:
        return i18n.get_language()

    options = [("简体中文", "zh"), ("English", "en")]
    current = i18n.get_language()
    initial = 0 if current == "zh" else 1

    items = [MenuItem(label=label) for label, _ in options]
    choice = Menu(
        "lang_title",
        items,
        hint_key="lang_hint",
        compact=True,
        initial_focus=initial,
    ).run()
    if choice is None:
        choice = initial
    code = options[choice][1]
    i18n.set_language(code)
    return code
