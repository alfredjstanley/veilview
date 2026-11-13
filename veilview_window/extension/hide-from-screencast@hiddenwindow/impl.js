// Implementation of Hide From Screencast. Loaded by extension.js with a
// cache-busting query (impl.js?t=...) so changes take effect on
// disable/enable without logging out of a Wayland session.
//
// How it works
// ------------
// A Clutter.Effect is attached to each matching MetaWindowActor. For every
// paint of that actor the effect looks at the framebuffer being painted into:
//   * a stage-view framebuffer (the real monitor, its onscreen or shadow fb)
//     -> paint normally
//   * any other framebuffer (mutter re-painting the stage for a screencast or
//     screenshot stream: clutter_stage_paint_to_framebuffer/_buffer)
//     -> paint nothing
// Picking/input is untouched, so the window stays interactive.
//
// Clutter 51 exposes no getter for ClutterPaintFlag on a PaintContext, so the
// framebuffer is the only signal available to JS.
//
// Limitation: if mutter makes stream frames by blitting the monitor
// framebuffer instead of re-painting, there is no separate paint to skip.
// DEBUG stats show which framebuffers are painted while a cast runs.

import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';

// WM_CLASS (X11) / app_id (Wayland) values of windows to hide.
export const MATCH_WM_CLASSES = ['io.hiddenwindow.Viewer'];
// Keep matched windows above others (Wayland clients can't request this).
const KEEP_ABOVE = true;
// DMA-BUF screencasts (used by Chrome and most browsers) are normally made by
// blitting the monitor framebuffer, which already contains the window. Mutter
// skips that blit and re-paints the stage when the view's color state differs
// from the stream's; forcing linear blending (a mutter debug-control switch)
// makes them differ, so every stream frame goes through a paint we can filter.
// Costs one extra full-screen pass per frame and triggers one monitor
// reconfigure (brief flicker) when toggled.
const FORCE_STAGE_PAINT = true;
// Log per-second paint statistics (journalctl --user -f -o cat | grep hide-from).
const DEBUG = false;

const EFFECT_NAME = 'hide-from-screencast';
const TAG = '[hide-from-screencast]';

function typeName(obj) {
    try {
        return GObject.type_name(obj.constructor.$gtype);
    } catch (e) {
        return String(obj);
    }
}

// Unique GType name per load, since impl.js may be imported several times
// in one gnome-shell process.
const HideFromCastEffect = GObject.registerClass({
    GTypeName: `HideFromCastEffect_${GLib.get_monotonic_time()}`,
}, class HideFromCastEffect extends Clutter.Effect {
    _init(debug) {
        super._init();
        this._debug = debug;
        this._stats = new Map();
        this._lastLog = 0;
    }

    _isMonitorFramebuffer(fb) {
        if (!fb || fb instanceof Cogl.Onscreen)
            return true; // the monitor itself (e.g. MetaOnscreenNative); never hide there
        const actor = this.get_actor();
        if (!actor)
            return true; // be conservative: never hide from the real screen by mistake
        // Shadow-fb / transformed views paint into an offscreen owned by the view.
        const views = actor.peek_stage_views();
        for (const view of views.length ? views : global.stage.peek_stage_views()) {
            if (fb === view.get_framebuffer() || fb === view.get_onscreen())
                return true;
        }
        return false;
    }

    _record(kind) {
        this._stats.set(kind, (this._stats.get(kind) ?? 0) + 1);
        const now = GLib.get_monotonic_time();
        if (now - this._lastLog >= 1000000) {
            const s = [...this._stats].map(([k, v]) => `${k}=${v}`).join(' ');
            console.log(`${TAG} paints/s: ${s}`);
            this._stats.clear();
            this._lastLog = now;
        }
    }

    vfunc_paint(node, paintContext, flags) {
        let fb = null;
        try {
            fb = paintContext.get_framebuffer();
        } catch (e) {
            // fall through and paint normally
        }
        const onMonitor = this._isMonitorFramebuffer(fb);

        if (this._debug)
            this._record(onMonitor ? 'monitor' : `hidden:${fb ? typeName(fb) : 'null'}`);

        if (!onMonitor)
            return; // screencast / screenshot paint: draw nothing

        super.vfunc_paint(node, paintContext, flags);
    }
});

export class Hider {
    constructor({debug = DEBUG, wmClasses = MATCH_WM_CLASSES} = {}) {
        this._debug = debug;
        this._wmClasses = wmClasses;
        this._tracked = new Map(); // MetaWindow -> entry
        this._pendingIdles = new Set();
        this._windowCreatedId = 0;
    }

    enable() {
        if (FORCE_STAGE_PAINT)
            this._forceLinearBlending(true);
        this._windowCreatedId = global.display.connect('window-created',
            (_display, win) => this._watchWindow(win));
        for (const actor of global.get_window_actors())
            this._watchWindow(actor.get_meta_window());
        if (this._debug)
            console.log(`${TAG} enabled, matching ${this._wmClasses.join(', ')}`);
    }

    disable() {
        if (this._windowCreatedId) {
            global.display.disconnect(this._windowCreatedId);
            this._windowCreatedId = 0;
        }
        for (const id of this._pendingIdles)
            GLib.source_remove(id);
        this._pendingIdles.clear();
        for (const win of [...this._tracked.keys()])
            this._untrack(win);
        this._forceLinearBlending(false);
    }

    // Only ever turns off what we turned on ourselves.
    _forceLinearBlending(on) {
        try {
            const dc = global.context.get_debug_control();
            if (on) {
                if (!dc.force_linear_blending) {
                    dc.force_linear_blending = true;
                    this._setLinearBlending = true;
                }
            } else if (this._setLinearBlending) {
                dc.force_linear_blending = false;
                this._setLinearBlending = false;
            }
            if (this._debug)
                console.log(`${TAG} force-linear-blending=${dc.force_linear_blending}`);
        } catch (e) {
            console.warn(`${TAG} cannot toggle force-linear-blending: ${e.message}`);
        }
    }

    _matches(win) {
        const wmClass = win.get_wm_class();
        return wmClass !== null && this._wmClasses.includes(wmClass);
    }

    _watchWindow(win) {
        if (!win || this._tracked.has(win))
            return;
        const entry = {
            actor: null, effect: null, actorDestroyId: 0, madeAbove: false,
            wmClassId: win.connect('notify::wm-class', () => this._apply(win)),
            unmanagedId: win.connect('unmanaged', () => this._untrack(win)),
        };
        this._tracked.set(win, entry);
        this._apply(win);
    }

    _apply(win) {
        const entry = this._tracked.get(win);
        if (!entry)
            return;
        if (!this._matches(win)) {
            this._removeEffect(win, entry);
            return;
        }
        if (entry.effect)
            return;

        const actor = win.get_compositor_private();
        if (!actor) {
            const id = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this._pendingIdles.delete(id);
                this._apply(win);
                return GLib.SOURCE_REMOVE;
            });
            this._pendingIdles.add(id);
            return;
        }

        entry.actor = actor;
        entry.effect = new HideFromCastEffect(this._debug);
        actor.add_effect_with_name(EFFECT_NAME, entry.effect);
        entry.actorDestroyId = actor.connect('destroy', () => {
            entry.actor = null;
            entry.effect = null;
            entry.actorDestroyId = 0;
        });

        if (KEEP_ABOVE && !win.is_above()) {
            win.make_above();
            entry.madeAbove = true;
        }
        if (this._debug)
            console.log(`${TAG} hiding "${win.get_title()}" (${win.get_wm_class()})`);
    }

    _removeEffect(win, entry) {
        if (entry.actor) {
            if (entry.actorDestroyId)
                entry.actor.disconnect(entry.actorDestroyId);
            if (entry.effect)
                entry.actor.remove_effect(entry.effect);
        }
        if (entry.madeAbove) {
            try {
                win.unmake_above();
            } catch (e) {}
            entry.madeAbove = false;
        }
        entry.actor = null;
        entry.effect = null;
        entry.actorDestroyId = 0;
    }

    _untrack(win) {
        const entry = this._tracked.get(win);
        if (!entry)
            return;
        try {
            this._removeEffect(win, entry);
        } catch (e) {}
        try {
            win.disconnect(entry.wmClassId);
            win.disconnect(entry.unmanagedId);
        } catch (e) {}
        this._tracked.delete(win);
    }
}
