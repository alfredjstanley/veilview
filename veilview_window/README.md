# Hidden Viewer

A browser window that is **visible and usable on your own screen, but left out of screen sharing**. When you share your *entire screen* from a browser (Google Meet, Microsoft Teams web, Webex web, Zoom web, …), other participants see whatever is behind the window. You see the window as normal.

| | |
|---|---|
| **Target** | Fedora Linux, GNOME Shell (mutter) **Wayland** session |
| **Verified on** | Fedora 45, GNOME Shell / mutter 51.1, Intel HD Graphics 520 (Dell Vostro 3559) |
| **Extension written for** | GNOME Shell 45–51. Only 51.1 has been tested. |

---

## Contents
1. [Quick start](#1-quick-start)
2. [Using the app](#2-using-the-app)
3. [Managing the extension](#3-managing-the-extension)
4. [Configuration](#4-configuration)
5. [How it works](#5-how-it-works)
6. [Testing and verification](#6-testing-and-verification)
7. [Troubleshooting](#7-troubleshooting)
8. [Limitations and things that can give it away](#8-limitations-and-things-that-can-give-it-away)
9. [Uninstall](#9-uninstall)
10. [Project layout](#10-project-layout)
11. [Development notes](#11-development-notes)

---

## 1. Quick start

### 1.1 Check your session
The extension only works in a **GNOME Shell Wayland** session. Check with:
```bash
echo $XDG_SESSION_TYPE        # must print: wayland
echo $XDG_CURRENT_DESKTOP     # should contain: GNOME
```
If you use Budgie, labwc or X11, log out, click the gear icon on the login screen, and pick **GNOME**. Prefer plain GNOME over **GNOME Classic**; see [§8](#8-limitations-and-things-that-can-give-it-away) for why.

### 1.2 Install dependencies
```bash
sudo dnf install python3-gobject gtk4 webkitgtk6.0
```
These are only needed if you want to run the self-test tool from §6.2:
```bash
sudo dnf install gstreamer1-plugins-good gstreamer1-plugins-base pipewire-gstreamer
```

### 1.3 Install
From the project folder:
```bash
./install.sh
```
The script installs everything for the current user only; it never uses `sudo`.

| What | Where |
|---|---|
| App launcher command | `~/.local/bin/hidden-viewer` (symlink) |
| App code | `~/.local/share/hidden-viewer-app/hidden-viewer.py` |
| Desktop entry (app grid) | `~/.local/share/applications/io.hiddenwindow.Viewer.desktop` |
| GNOME Shell extension | `~/.local/share/gnome-shell/extensions/hide-from-screencast@hiddenwindow/` |

### 1.4 Enable the extension (once)
On Wayland, GNOME Shell only notices a newly installed extension after you **log out and log back in**. Then run:
```bash
gnome-extensions enable hide-from-screencast@hiddenwindow
gnome-extensions info   hide-from-screencast@hiddenwindow   # State: ACTIVE
```
The extension stays enabled across reboots and logins.

When the extension turns on, the screen flickers once (a monitor reconfigure, see [§5.4](#54-the-dma-buf-problem-and-the-fix)). This is expected.

### 1.5 Run
```bash
hidden-viewer https://example.com
```
You can also open **Hidden Viewer** from the app grid (Super key, then type "Hidden").

---

## 2. Using the app

`hidden-viewer` is a small browser built on GTK4 and WebKitGTK (the engine behind GNOME Web).

```
hidden-viewer [URL]
```
- With no URL, it opens `https://www.google.com`.
- If the URL has no scheme, `https://` is added (`example.com` becomes `https://example.com`).
- Text that doesn't look like a URL (it contains spaces or has no dot) is searched on DuckDuckGo.

| Control | Action |
|---|---|
| `←` / `→` buttons | Back / Forward |
| `⟳` button | Reload |
| URL bar + `Enter` | Go to a URL or search |
| `Ctrl+L` | Focus the URL bar |
| Right-click → **Inspect Element** | WebKit developer tools (enabled) |

Behaviour:
- **Popups and `target=_blank` links** open in the same window, so they stay hidden too. A new window would also be hidden, but it would appear somewhere unexpected.
- **Logins persist.** Cookies and site data are stored in `~/.local/share/hidden-viewer/` (cookies in `cookies.sqlite`). The cache is in `~/.cache/hidden-viewer/`.
- **Always on top.** The extension keeps the window above other windows (`KEEP_ABOVE`), because a Wayland app can't request that itself.
- **Several windows:** each run of `hidden-viewer` opens a new window, and all of them are hidden.
- **Camera and microphone:** WebRTC media streams are enabled, so web apps can ask for them.

**Tip:** start the viewer from the app grid or a keyboard shortcut rather than from a terminal. When an app starts without focus, GNOME may show a "*…is ready*" notification, and notifications **do** appear in screen shares ([§8](#8-limitations-and-things-that-can-give-it-away)).

To add a keyboard shortcut, go to *Settings → Keyboard → View and Customise Shortcuts → Custom Shortcuts → +*, and use the command `/home/<you>/.local/bin/hidden-viewer https://your-page`.

---

## 3. Managing the extension

```bash
E=hide-from-screencast@hiddenwindow
gnome-extensions info    $E      # Enabled / State
gnome-extensions disable $E      # stop hiding (window becomes shareable again)
gnome-extensions enable  $E      # start hiding again
```
You can also use the **Extensions** app (`sudo dnf install gnome-extensions-app`) to toggle it.

The **"GNOME Shell integration"** entry on `chrome://extensions` is a different thing. It is Chrome's connector to extensions.gnome.org, and it is not needed here. This extension is managed only with the commands above.

---

## 4. Configuration

All settings are constants at the top of `extension/hide-from-screencast@hiddenwindow/impl.js`. You can edit them in the installed copy at `~/.local/share/gnome-shell/extensions/hide-from-screencast@hiddenwindow/impl.js`, or edit the project copy and rerun `./install.sh`.

To apply a change, run `gnome-extensions disable` and then `enable` on the extension. **You do not need to log out** ([§11](#11-development-notes)).

| Constant | Default | Meaning |
|---|---|---|
| `MATCH_WM_CLASSES` | `['io.hiddenwindow.Viewer']` | Windows to hide, matched by Wayland `app_id` (or X11 `WM_CLASS`). Add other apps here to hide them too. |
| `KEEP_ABOVE` | `true` | Keep hidden windows on top of other windows. |
| `FORCE_STAGE_PAINT` | `true` | Required for Chrome/DMA-BUF shares ([§5.4](#54-the-dma-buf-problem-and-the-fix)). If you set it to `false`, only SHM shares are filtered. |
| `DEBUG` | `false` | Logs paint statistics once per second. |

**Finding another app's `app_id`:** press `Alt+F2`, type `lg`, and press Enter to open Looking Glass. Open the **Windows** tab and read the `wmclass` field. For example, GNOME Text Editor is `org.gnome.TextEditor`.

**Debug logging without editing code:** create an empty file named `DEBUG` in the extension folder, then disable and enable the extension:
```bash
touch ~/.local/share/gnome-shell/extensions/hide-from-screencast@hiddenwindow/DEBUG
journalctl --user -f -o cat | grep hide-from
```
Delete the file to turn logging off again.

---

## 5. How it works

### 5.1 Why an extension is needed
Wayland gives applications no way to opt out of screen capture. Windows has `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` and macOS has `NSWindow.sharingType = .none`, but there is no Wayland protocol, GTK API, Qt API or Electron switch for this. Electron's `setContentProtection()` does nothing on Linux.

When a browser shares the screen on GNOME Wayland, the frames come from here:
```
Browser ──getDisplayMedia()──▶ xdg-desktop-portal-gnome ──▶ mutter ScreenCast (org.gnome.Mutter.ScreenCast)
                                                               │
                                                     PipeWire video stream ──▶ Browser ──▶ Meet/Teams/…
```
mutter, the GNOME compositor, produces every frame. The only place a window can be removed from the stream without touching the browser is **inside mutter**, and that is where GNOME Shell extensions run.

### 5.2 Components
| File | Role |
|---|---|
| `app/hidden-viewer.py` | GTK4 + WebKitGTK 6.0 browser. Its only special property is the fixed `application_id = "io.hiddenwindow.Viewer"`, which becomes the window's Wayland `app_id`. |
| `extension/…/extension.js` | Small loader. It imports `impl.js` with a cache-busting URL (`impl.js?t=<timestamp>`) and starts the `Hider`. |
| `extension/…/impl.js` | All the logic: window tracking, the paint filter, and the linear-blending switch. |
| `extension/…/metadata.json` | Extension metadata (UUID, supported shell versions). |

### 5.3 The paint filter
1. **Window tracking.** `Hider` watches `global.display::window-created` and checks windows that already exist. A window matches if its `wm_class` (the `app_id` on Wayland) is in `MATCH_WM_CLASSES`. It re-checks on `notify::wm-class` and stops tracking on `unmanaged`.
2. **Effect.** Each matching window's `MetaWindowActor` gets a `HideFromCastEffect`, a subclass of `Clutter.Effect`.
3. **Per-paint decision.** In `vfunc_paint(node, paintContext, flags)`, the effect gets the target framebuffer with `paintContext.get_framebuffer()`:
   - **Monitor paint:** the framebuffer is a `Cogl.Onscreen` (for example `MetaOnscreenNative`), or it is the framebuffer/onscreen of one of the actor's `ClutterStageView`s. The effect chains to `super.vfunc_paint()` and the window is drawn normally.
   - **Anything else:** this is a `CoglOffscreen` that mutter uses when it repaints the stage for a screencast or screenshot (`clutter_stage_paint_to_framebuffer` / `paint_to_buffer`). The effect returns **without painting**, so the window, its shadow and its contents are absent and whatever is behind shows through.
4. **Input and picking** are not touched, so clicks and typing work normally.
5. **Why not paint flags?** mutter passes `CLUTTER_PAINT_FLAG_*` for screencast paints, but Clutter 51 has no JS-accessible getter for them (`ClutterPaintContext` has no `get_paint_flags`). The framebuffer identity is the only signal available, and it works.

Because overview and Alt-Tab thumbnails are `Clutter.Clone`s that paint through the same actor and effect, they are hidden from the stream too.

### 5.4 The DMA-BUF problem and the fix
In `src/backends/meta-stream-source-monitor.c` (mutter 51.1), a monitor stream frame is produced in one of two ways:

| Stream buffers | Used by | How mutter makes the frame | Filterable? |
|---|---|---|---|
| **SHM** (memfd) | Firefox, some apps | `record_to_buffer` → repaints the stage into the buffer | ✅ always |
| **DMA-BUF** (GPU) | Chrome/Chromium, most WebRTC | `stage_painted` → `PRE_SWAP_BUFFER` phase → `cogl_framebuffer_blit()` from the **view framebuffer already drawn for the monitor** | ❌ the window is already in the image |

The blit is skipped, and the stage is repainted instead, when:
```c
cogl_driver_has_feature (..., COGL_FEATURE_ID_BLIT_FRAMEBUFFER) &&
clutter_color_state_equals (target_color_state, view_color_state)
```
is false.

The view's color state comes from `clutter_color_state_get_blending(output_color_state, force_linear)`, where `force_linear` is mutter's **debug-control** setting `force-linear-blending` (normally set with `MUTTER_DEBUG_FORCE_LINEAR_BLENDING=1`). The extension sets this property at runtime:
```js
global.context.get_debug_control().force_linear_blending = true;
```
The view then blends in linear light, its color state no longer matches the stream's, mutter abandons the blit, and every DMA-BUF frame goes through a paint the effect can filter.

- **Cost:** one extra full-screen composite per streamed frame, plus one monitor reconfigure (a brief flicker) each time the extension is enabled or disabled. On an HD 520 at 1366×768 this is negligible.
- **Visual change:** blending in linear light can make semi-transparent edges, such as shadows and anti-aliasing, look slightly different. Opaque content is unchanged.
- **Safe restore:** on disable, the extension resets the property only if it was the one that turned it on.

### 5.5 Measured results (mutter 51.1, HD 520)
| Capture | Extension off | Extension on, `FORCE_STAGE_PAINT=false` | Extension on (default) |
|---|---|---|---|
| SHM | visible | **hidden** | **hidden** |
| DMA-BUF | visible | visible (blit) | **hidden** |

---

## 6. Testing and verification

### 6.1 In a browser (what other people will see)
1. Open the viewer (`hidden-viewer https://example.com`) and leave it on screen.
2. In Chrome **and** Firefox, open
   <https://webrtc.github.io/samples/src/content/getusermedia/getdisplaymedia/>
   and click **Start**, then share **Entire Screen**.
3. The page's preview should show the desktop **without** the viewer. You still see the viewer on your real screen.
4. For a definitive check, join a real Meet or Teams call with a second device and look at your shared screen from that device.
5. Control test: `gnome-extensions disable hide-from-screencast@hiddenwindow`. The viewer should now appear in the preview.

### 6.2 Self-test tool (no dialogs; works over SSH)
`tools/cast_snapshot.py` asks mutter's ScreenCast D-Bus API for a stream of the primary monitor and saves one frame as PNG. This is the same capture path the browser portal uses, but without the permission dialog.
```bash
python3 tools/cast_snapshot.py --mode dmabuf -o dmabuf.png   # Chrome-style buffers
python3 tools/cast_snapshot.py --mode shm    -o shm.png      # Firefox-style buffers
```
Options:
- `--connector eDP-1`: pick a specific monitor. The default is the primary monitor.
- `--timeout N`: seconds to wait.

Safety: before capturing, the tool checks with `pw-dump` that the PipeWire node is gnome-shell's `Stream/Output/Video` node. It then links that node to its own capture node with `pw-link`, using `autoconnect=false`. It never auto-connects, so it **cannot** fall back to the webcam or any other source.

Running it over SSH requires the logged-in user's session environment:
```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
export WAYLAND_DISPLAY=wayland-0
```

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Extension "hide-from-screencast@hiddenwindow" doesn't exist` | GNOME hasn't scanned the new extension yet. Log out and back in once (Wayland can't restart the shell). |
| `State: ERROR` or the window is still visible in shares | Check the logs: `journalctl --user -b -o cat \| grep -E "hide-from\|JS ERROR"`. |
| `Enabled: No` after login | Run `gnome-extensions enable …`. Also check that `gsettings get org.gnome.shell disable-user-extensions` prints `false`. |
| Window visible in a **Chrome** share, hidden in a **Firefox** share | `FORCE_STAGE_PAINT` is off, or the log shows `cannot toggle force-linear-blending`. With `DEBUG` on, a share should log `hidden:CoglOffscreen=N`. |
| Nothing hidden at all; log shows no `hiding "…"` line | The window's `app_id` doesn't match. Check it in Looking Glass ([§4](#4-configuration)). |
| Brief screen flicker when enabling or disabling | Expected: the monitor reconfigure caused by `force-linear-blending`. |
| `hidden-viewer: command not found` | `~/.local/bin` isn't on your `PATH`. Run `~/.local/bin/hidden-viewer` or open a new terminal. |
| Viewer fails with `Namespace WebKit not available` | `sudo dnf install webkitgtk6.0` |
| `JS ERROR … dash.js … this.label is null` in the log | GNOME Shell's own dash tooltip code. It is unrelated to this extension. |

---

## 8. Limitations and things that can give it away

These are visible to the people you share with:
- **GNOME Classic's bottom window list** shows the viewer's title ("Example Domain – Hidden Viewer"), and that bar is part of the shared screen. Use the standard **GNOME** session, which has no window list.
- **Notifications:** the "*…is ready*" banner (shown when the viewer starts without focus) and any notification from the page are drawn by the shell, not by the window, so they are shared. Start the viewer from the app grid or a shortcut, or turn on *Do Not Disturb*.
- **Mouse cursor:** the pointer is drawn into the stream, so people can see it moving over an apparently empty area while you interact with the viewer.
- **"Share a window"** picker: if the viewer itself is chosen, it is shared. This tool only filters *entire-screen* (monitor) shares.
- **Direct scanout:** when a fullscreen app is scanned out directly, mutter copies that buffer. The viewer is not on top in that case anyway.

Platform limits:
- Works only in **GNOME Shell on Wayland**. It does nothing under Budgie/labwc, KDE or X11.
- It relies on mutter internals (the stream paint paths and the debug-control property), which can change between GNOME releases. Re-test after major Fedora or GNOME upgrades.
- GNOME's own screenshot tool also repaints the stage offscreen, so the viewer is probably left out of screenshots too. This has not been tested.

---

## 9. Uninstall
```bash
gnome-extensions disable hide-from-screencast@hiddenwindow   # restores linear blending
rm -rf ~/.local/share/gnome-shell/extensions/hide-from-screencast@hiddenwindow
rm -f  ~/.local/bin/hidden-viewer ~/.local/share/applications/io.hiddenwindow.Viewer.desktop
rm -rf ~/.local/share/hidden-viewer-app
rm -rf ~/.local/share/hidden-viewer ~/.cache/hidden-viewer    # browsing data (logins, cache)
```

---

## 10. Project layout
```
hidden_window/
├── app/
│   ├── hidden-viewer.py                 # GTK4/WebKitGTK browser (app_id io.hiddenwindow.Viewer)
│   └── io.hiddenwindow.Viewer.desktop   # launcher template (@BINDIR@ filled in by install.sh)
├── extension/hide-from-screencast@hiddenwindow/
│   ├── metadata.json
│   ├── extension.js                     # loader (cache-busting import of impl.js)
│   └── impl.js                          # paint filter, window tracking, linear-blending switch
├── tools/
│   └── cast_snapshot.py                 # headless capture of mutter's screencast for testing
├── install.sh                           # per-user install
└── README.md
```

---

## 11. Development notes
- **Reload without logging out:** GNOME Shell caches ES modules, and on Wayland the shell can't be restarted without ending the session. `extension.js` therefore imports `impl.js?t=<Date.now()>`, which gives a new module instance on each enable. After editing `impl.js`, run `gnome-extensions disable` and then `enable`. Only changes to `extension.js` or `metadata.json` need a re-login.
- **Unique GType names:** because `impl.js` can be loaded several times in one shell process, the effect class registers a unique `GTypeName` each time.
- **Inspecting mutter:** the exact mutter source can be fetched with `dnf download --source mutter` and unpacked with `rpm2cpio … | cpio -idm`. The relevant file is `src/backends/meta-stream-source-monitor.c`.
- **Introspection:** to check which Clutter/Meta APIs exist for JS, read the typelibs in `/usr/lib64/mutter-<ver>/`, for example with `GIRepository` from Python.
