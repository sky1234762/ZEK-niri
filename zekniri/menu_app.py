"""Transparent GTK layer-shell menu for Wayland/Niri."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

os.environ.setdefault("GDK_BACKEND", "wayland")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell  # type: ignore

from zekniri.menu_instance import release_listener, start_or_toggle
from zekniri.menu_fullscreen import focused_window_is_fullscreen
from zekniri.menu_config import menu_config_path, read_menu_entries

CARD_WIDTH = 320
CARD_HEIGHT = 58
CARD_GAP = 9
POINTER_GAP = 24
ANIMATION_STEP_MS = 16
ANIMATION_DURATION_MS = 320
ENTRY_STAGGER_MS = 46
SLIDE_DISTANCE = 54


def _which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _detached(argv: list[str]) -> None:
    try:
        subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class MenuApp:
    def __init__(self, listener) -> None:
        Gtk.init(None)
        self.listener = listener
        self.display = Gdk.Display.get_default()
        self.closed = False
        self.opened_at = GLib.get_monotonic_time() // 1000
        self.surfaces: list[MenuSurface] = []
        if self.display is not None:
            for index in range(self.display.get_n_monitors()):
                self.surfaces.append(MenuSurface(self, self.display.get_monitor(index)))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for surface in self.surfaces:
            surface.window.destroy()
        Gtk.main_quit()

    def launch_appimage(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass
        _detached([str(path)])

    def launch_memo(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        if _which("kitty"):
            _detached(["kitty", "nano", str(path)])
        elif _which("alacritty"):
            _detached(["alacritty", "-e", "nano", str(path)])

    def run(self) -> int:
        for surface in self.surfaces:
            surface.build()
            surface.window.connect("key-press-event", surface.on_key)
            surface.window.show_all()
        if not self.surfaces:
            return 1
        GLib.timeout_add(70, self.poll_toggle)
        Gtk.main()
        return 0

    def poll_toggle(self) -> bool:
        try:
            connection, _ = self.listener.accept()
        except BlockingIOError:
            return True
        with connection:
            if connection.recv(32) == b"toggle":
                self.close()
                return False
        return True


class MenuSurface:
    def __init__(self, app: MenuApp, monitor) -> None:
        self.app = app
        geometry = monitor.get_geometry()
        self.width, self.height = geometry.width, geometry.height
        self.positioned = False
        self.cards: list[Gtk.Widget] = []
        self.started_at = 0
        self.card_x = self.card_y = 0
        self.origin = (0.0, 0.0)

        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_app_paintable(True)
        self.window.set_can_focus(True)
        self.window.set_default_size(self.width, self.height)
        self.window.set_opacity(1.0)
        visual = self.window.get_screen().get_rgba_visual()
        if visual is not None:
            self.window.set_visual(visual)
        self.window.add_events(
            Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.window.connect("enter-notify-event", self.on_pointer)
        self.window.connect("motion-notify-event", self.on_pointer)
        self.window.connect("button-release-event", self.on_outside_click)

        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_monitor(self.window, monitor)
        GtkLayerShell.set_namespace(self.window, "zekniri-menu")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.ON_DEMAND)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.RIGHT, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT):
            GtkLayerShell.set_anchor(self.window, edge, True)
        GtkLayerShell.set_exclusive_zone(self.window, -1)

        self.fixed = Gtk.Fixed()
        self.fixed.set_has_window(False)
        self.window.add(self.fixed)
        self._install_style()

    def _install_style(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        window { background-color: rgba(0, 0, 0, 0); }
        .card { background: linear-gradient(110deg, rgba(24, 48, 66, 0.68), rgba(8, 19, 31, 0.52)); border: 1px solid rgba(80, 215, 241, 0.82); border-left: 3px solid #55e8f5; border-radius: 5px; box-shadow: 0 8px 28px rgba(0, 0, 0, 0.34), inset 0 1px rgba(190, 247, 255, 0.16); }
        .card:hover { background: linear-gradient(110deg, rgba(35, 91, 111, 0.82), rgba(10, 35, 50, 0.72)); border-color: #a1f8ff; box-shadow: 0 10px 32px rgba(0, 0, 0, 0.42), inset 0 1px rgba(220, 252, 255, 0.28); }
        .card-label { color: #edfcff; font: 600 14px Cantarell; }
        .card-index { color: #63e5f1; font: 700 11px Monospace; }
        .hint { color: rgba(210, 239, 244, 0.76); font: 10px Monospace; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            self.window.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _make_card(self, index: int, title: str, callback) -> Gtk.Widget:
        card = Gtk.EventBox()
        card.get_style_context().add_class("card")
        card.set_size_request(CARD_WIDTH, CARD_HEIGHT)
        card.set_opacity(0)
        card.connect("button-release-event", self.on_card_release, callback)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_valign(Gtk.Align.CENTER)
        number = Gtk.Label(label=f"{index:02d}")
        number.get_style_context().add_class("card-index")
        label = Gtk.Label(label=title, xalign=0)
        label.get_style_context().add_class("card-label")
        row.pack_start(number, False, False, 0)
        row.pack_start(label, True, True, 0)
        card.add(row)
        return card

    def on_card_release(self, _widget, event, callback) -> bool:
        if event.button == 1:
            callback()
            self.app.close()
        elif event.button in (2, 3):
            self.app.close()
        return True

    def build(self) -> None:
        apps, memo = read_menu_entries(menu_config_path(), Path.home())
        actions = [(title, lambda path=path: self.app.launch_appimage(path)) for _, title, path in apps]
        if memo is not None:
            actions.append(("打开备忘录", lambda path=memo: self.app.launch_memo(path)))
        if not actions:
            actions.append(("请配置 ZEKniri-menu.conf", lambda: None))

        for index, (title, callback) in enumerate(actions, 1):
            card = self._make_card(index, title, callback)
            self.cards.append(card)
            self.fixed.put(card, 0, 0)
        hint = Gtk.Label(label="中键打开 · Esc 关闭")
        hint.get_style_context().add_class("hint")
        hint.set_opacity(0)
        self.cards.append(hint)
        self.fixed.put(hint, 0, 0)

    def on_pointer(self, _widget, event) -> bool:
        if not self.positioned:
            self.positioned = True
            self.origin = (event.x, event.y)
            GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
            self.window.grab_focus()
            self.start_animation()
        return True

    def on_outside_click(self, _widget, event) -> bool:
        if GLib.get_monotonic_time() // 1000 - self.app.opened_at < 220:
            return True
        if event.button in (1, 2, 3) and not self.inside_cards(event.x, event.y):
            self.app.close()
        return True

    def inside_cards(self, x: float, y: float) -> bool:
        height = len(self.cards) * (CARD_HEIGHT + CARD_GAP) - CARD_GAP
        return self.card_x <= x <= self.card_x + CARD_WIDTH and self.card_y <= y <= self.card_y + height

    def on_key(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape or (
            event.keyval == Gdk.KEY_Shift_R
            and GLib.get_monotonic_time() // 1000 - self.app.opened_at >= 220
        ):
            self.app.close()
            return True
        return False

    def start_animation(self) -> None:
        pointer_x, pointer_y = self.origin
        x = min(int(pointer_x + POINTER_GAP), max(10, self.width - CARD_WIDTH - 10))
        y = int(pointer_y - CARD_HEIGHT / 2)
        total_height = len(self.cards) * (CARD_HEIGHT + CARD_GAP) - CARD_GAP
        y = max(10, min(y, self.height - total_height - 10))
        self.card_x, self.card_y = x, y
        self.started_at = GLib.get_monotonic_time() // 1000
        GLib.timeout_add(ANIMATION_STEP_MS, self._animate)

    def _animate(self) -> bool:
        elapsed = GLib.get_monotonic_time() // 1000 - self.started_at
        active = False
        for index, card in enumerate(self.cards):
            progress = max(0.0, min(1.0, (elapsed - index * ENTRY_STAGGER_MS) / ANIMATION_DURATION_MS))
            eased = 1 - (1 - progress) ** 3
            card.set_opacity(eased)
            offset = int(SLIDE_DISTANCE * (1 - eased))
            self.fixed.move(card, self.card_x + offset, self.card_y + index * (CARD_HEIGHT + CARD_GAP))
            active = active or progress < 1
        return active


def main() -> int:
    listener = start_or_toggle(allow_start=not focused_window_is_fullscreen())
    if listener is None:
        return 0
    try:
        return MenuApp(listener).run()
    finally:
        release_listener(listener)


if __name__ == "__main__":
    raise SystemExit(main())
