#!/usr/bin/env python3
"""Hidden Viewer - a minimal GTK4/WebKitGTK browser window.

Its Wayland app_id is fixed to APP_ID so the companion GNOME Shell extension
(hide-from-screencast@hiddenwindow) can find it and keep it out of screencasts.

Usage:  hidden-viewer [URL]
Fedora deps:  sudo dnf install python3-gobject gtk4 webkitgtk6.0
"""
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gio, GLib, Gtk, WebKit  # noqa: E402

APP_ID = "io.hiddenwindow.Viewer"
DEFAULT_URL = "https://www.google.com"

DATA_DIR = os.path.join(GLib.get_user_data_dir(), "hidden-viewer")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "hidden-viewer")


def normalize_url(text: str) -> str:
    text = text.strip()
    if not text:
        return DEFAULT_URL
    if "://" in text or text.startswith(("about:", "file:", "data:")):
        return text
    if " " in text or "." not in text:
        return "https://duckduckgo.com/?q=" + GLib.uri_escape_string(text, None, False)
    return "https://" + text


class ViewerWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, session: WebKit.NetworkSession, url: str):
        super().__init__(application=app, title="Hidden Viewer")
        self.set_default_size(900, 600)

        self.webview = WebKit.WebView(network_session=session)
        settings = self.webview.get_settings()
        settings.set_enable_developer_extras(True)
        settings.set_enable_media_stream(True)
        self.webview.connect("notify::uri", self._on_uri_changed)
        self.webview.connect("notify::title", self._on_title_changed)
        self.webview.connect("create", self._on_create)

        header = Gtk.HeaderBar()

        back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        back.set_tooltip_text("Back")
        back.connect("clicked", lambda *_: self.webview.go_back())
        header.pack_start(back)

        forward = Gtk.Button.new_from_icon_name("go-next-symbolic")
        forward.set_tooltip_text("Forward")
        forward.connect("clicked", lambda *_: self.webview.go_forward())
        header.pack_start(forward)

        reload_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        reload_btn.set_tooltip_text("Reload")
        reload_btn.connect("clicked", lambda *_: self.webview.reload())
        header.pack_start(reload_btn)

        self.entry = Gtk.Entry(hexpand=True, placeholder_text="Enter URL")
        self.entry.connect("activate", self._on_entry_activate)
        header.set_title_widget(self.entry)

        self.set_titlebar(header)
        self.set_child(self.webview)

        # Ctrl+L focuses the URL bar.
        ctrl = Gtk.ShortcutController()
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>l"),
            Gtk.CallbackAction.new(lambda *_: self.entry.grab_focus() or True),
        ))
        self.add_controller(ctrl)

        self.webview.load_uri(url)

    def _on_entry_activate(self, entry: Gtk.Entry) -> None:
        self.webview.load_uri(normalize_url(entry.get_text()))
        self.webview.grab_focus()

    def _on_uri_changed(self, webview, _pspec) -> None:
        uri = webview.get_uri()
        if uri and not self.entry.has_focus():
            self.entry.set_text(uri)

    def _on_title_changed(self, webview, _pspec) -> None:
        title = webview.get_title()
        self.set_title(f"{title} - Hidden Viewer" if title else "Hidden Viewer")

    def _on_create(self, _webview, action):
        # Open popups / target=_blank links in this same window so they stay hidden too.
        uri = action.get_request().get_uri()
        if uri:
            self.webview.load_uri(uri)
        return None


class ViewerApp(Gtk.Application):
    def __init__(self, url: str):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.url = url
        self.session = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.session = WebKit.NetworkSession.new(DATA_DIR, CACHE_DIR)
        self.session.get_cookie_manager().set_persistent_storage(
            os.path.join(DATA_DIR, "cookies.sqlite"),
            WebKit.CookiePersistentStorage.SQLITE,
        )

    def do_activate(self) -> None:
        ViewerWindow(self, self.session, self.url).present()


def main() -> int:
    url = normalize_url(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_URL
    return ViewerApp(url).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
