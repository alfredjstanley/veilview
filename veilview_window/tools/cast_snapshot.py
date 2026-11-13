#!/usr/bin/env python3
"""Grab a frame from mutter's screencast pipeline (the same path browsers use
via xdg-desktop-portal) without the portal permission dialog, so the hiding
can be verified headlessly, e.g. over ssh.

Usage (inside the logged-in user's session environment):
    python3 cast_snapshot.py [--mode shm|dmabuf|auto] [--connector eDP-1] [-o out.png]

Over ssh, first export:
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
    export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
    export WAYLAND_DISPLAY=wayland-0

Deps: sudo dnf install python3-gobject gstreamer1-plugins-good pipewire-gstreamer
      (dmabuf mode also needs gstreamer1-plugins-base GL elements)
"""
import argparse
import json
import os
import subprocess
import sys
import time

from gi.repository import Gio, GLib

BUS_NAME = "org.gnome.Mutter.ScreenCast"
OBJ_PATH = "/org/gnome/Mutter/ScreenCast"
IFACE = "org.gnome.Mutter.ScreenCast"
SESSION_IFACE = "org.gnome.Mutter.ScreenCast.Session"
STREAM_IFACE = "org.gnome.Mutter.ScreenCast.Stream"
CURSOR_MODE_EMBEDDED = 1


def call(bus, path, iface, method, params, reply_type=None):
    return bus.call_sync(BUS_NAME, path, iface, method, params,
                         GLib.VariantType(reply_type) if reply_type else None,
                         Gio.DBusCallFlags.NONE, -1, None)


CAPTURE_NODE = f"cast-snapshot-{os.getpid()}"


def pw_objects():
    out = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=10).stdout
    return json.loads(out or "[]")


def props(obj):
    return (obj.get("info") or {}).get("props") or {}


def is_mutter_stream(objs, node: int) -> bool:
    """The node mutter announced must be gnome-shell's video output stream,
    never a camera or any other source."""
    for o in objs:
        if o.get("id") == node and o.get("type", "").endswith(":Node"):
            p = props(o)
            return (p.get("media.class") == "Stream/Output/Video"
                    and "gnome-shell" in str(p.get("application.name", "")
                                             + p.get("node.name", "")
                                             + p.get("application.process.binary", "")))
    return False


def ports_of(objs, node_id: int, direction: str):
    return [o["id"] for o in objs
            if o.get("type", "").endswith(":Port")
            and str(props(o).get("node.id")) == str(node_id)
            and (o.get("info") or {}).get("direction") == direction]


def node_id_by_name(objs, name: str):
    for o in objs:
        if o.get("type", "").endswith(":Node") and props(o).get("node.name") == name:
            return o["id"]
    return None


def pipeline(mode: str, out: str) -> list:
    # autoconnect=false: the session manager links nothing; we link the
    # capture node to mutter's stream ourselves, so it can never end up on
    # the webcam or another source.
    src = ["pipewiresrc", "autoconnect=false", "keepalive-time=200", "num-buffers=5",
           f"stream-properties=props,node.name={CAPTURE_NODE},node.dont-fallback=true"]
    if mode == "shm":
        src.append("always-copy=true")
    if mode == "dmabuf":
        # GStreamer >= 1.24 negotiates PipeWire DMA-BUFs as format=DMA_DRM.
        mid = ["!", "video/x-raw(memory:DMABuf),format=DMA_DRM", "!", "glupload", "!",
               "glcolorconvert", "!", "gldownload", "!", "videoconvert"]
    elif mode == "shm":
        mid = ["!", "video/x-raw", "!", "videoconvert"]
    else:
        mid = ["!", "videoconvert"]
    # Keep only the last of a few frames (first frame can be incomplete).
    sink = ["!", "pngenc", "!", "multifilesink", f"location={out}", "max-files=1"]
    return ["gst-launch-1.0", "-q"] + src + mid + sink


def link_capture(stream_node: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        objs = pw_objects()
        if not is_mutter_stream(objs, stream_node):
            print(f"error: node {stream_node} is not a mutter screencast stream", file=sys.stderr)
            return False
        cap = node_id_by_name(objs, CAPTURE_NODE)
        outs = ports_of(objs, stream_node, "output")
        ins = ports_of(objs, cap, "input") if cap is not None else []
        if outs and ins:
            rc = subprocess.run(["pw-link", str(outs[0]), str(ins[0])]).returncode
            return rc == 0
        time.sleep(0.2)
    print("error: capture node/ports did not appear", file=sys.stderr)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auto", "shm", "dmabuf"], default="auto")
    ap.add_argument("--connector", default="", help="monitor connector, '' = primary")
    ap.add_argument("-o", "--output", default="cast_snapshot.png")
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    session_path = call(bus, OBJ_PATH, IFACE, "CreateSession",
                        GLib.Variant("(a{sv})", ({},)), "(o)").unpack()[0]
    stream_path = call(bus, session_path, SESSION_IFACE, "RecordMonitor",
                       GLib.Variant("(sa{sv})", (args.connector, {
                           "cursor-mode": GLib.Variant("u", CURSOR_MODE_EMBEDDED),
                       })), "(o)").unpack()[0]

    loop = GLib.MainLoop()
    node_id = {}

    def on_stream_added(_conn, _sender, _path, _iface, _signal, params):
        node_id["id"] = params.unpack()[0]
        loop.quit()

    sub = bus.signal_subscribe(BUS_NAME, STREAM_IFACE, "PipeWireStreamAdded",
                               stream_path, None, Gio.DBusSignalFlags.NONE,
                               on_stream_added)
    GLib.timeout_add_seconds(10, loop.quit)

    call(bus, session_path, SESSION_IFACE, "Start", None)
    loop.run()
    bus.signal_unsubscribe(sub)

    gst = None
    try:
        if "id" not in node_id:
            print("error: no PipeWire stream announced by mutter", file=sys.stderr)
            return 1
        if os.path.exists(args.output):
            os.remove(args.output)
        cmd = pipeline(args.mode, args.output)
        print("node", node_id["id"], "->", " ".join(cmd))
        deadline = time.monotonic() + args.timeout
        gst = subprocess.Popen(cmd)
        if not link_capture(node_id["id"], min(deadline, time.monotonic() + 8)):
            return 1
        try:
            rc = gst.wait(timeout=max(1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            print("error: gst pipeline timed out", file=sys.stderr)
            return 1
        if rc == 0 and os.path.exists(args.output):
            print("wrote", args.output)
            return 0
        return rc or 1
    finally:
        if gst and gst.poll() is None:
            gst.kill()
        try:
            call(bus, session_path, SESSION_IFACE, "Stop", None)
        except GLib.Error:
            pass


if __name__ == "__main__":
    sys.exit(main())
