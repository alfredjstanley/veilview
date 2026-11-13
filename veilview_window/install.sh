#!/usr/bin/env bash
# Installs Hidden Viewer + the Hide From Screencast GNOME Shell extension
# for the current user. Run inside the target user's account on Fedora.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
UUID="hide-from-screencast@hiddenwindow"
BINDIR="$HOME/.local/bin"
APPDIR="$HOME/.local/share/hidden-viewer-app"
EXTDIR="$HOME/.local/share/gnome-shell/extensions/$UUID"
DESKDIR="$HOME/.local/share/applications"

missing=()
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("WebKit","6.0"); from gi.repository import Gtk, WebKit' 2>/dev/null \
    || missing+=(python3-gobject gtk4 webkitgtk6.0)
if ((${#missing[@]})); then
    echo "Missing dependencies. Install with:"
    echo "  sudo dnf install ${missing[*]}"
    exit 1
fi

mkdir -p "$BINDIR" "$APPDIR" "$EXTDIR" "$DESKDIR"

install -m 0755 "$HERE/app/hidden-viewer.py" "$APPDIR/hidden-viewer.py"
ln -sf "$APPDIR/hidden-viewer.py" "$BINDIR/hidden-viewer"

sed "s|@BINDIR@|$BINDIR|g" "$HERE/app/io.hiddenwindow.Viewer.desktop" \
    > "$DESKDIR/io.hiddenwindow.Viewer.desktop"

install -m 0644 "$HERE/extension/$UUID/metadata.json" "$EXTDIR/metadata.json"
install -m 0644 "$HERE/extension/$UUID/extension.js"  "$EXTDIR/extension.js"
install -m 0644 "$HERE/extension/$UUID/impl.js"       "$EXTDIR/impl.js"

echo "Installed:"
echo "  app        -> $BINDIR/hidden-viewer"
echo "  extension  -> $EXTDIR"
echo
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]] || [[ -z "${XDG_SESSION_TYPE:-}" ]]; then
    echo "Next steps (Wayland): log out and back in so GNOME Shell sees the new extension, then:"
else
    echo "Next steps:"
fi
echo "  gnome-extensions enable $UUID"
echo "  hidden-viewer https://example.com"
