// Hide From Screencast - loader.
//
// The real logic lives in impl.js. It is imported with a cache-busting query
// string so that editing impl.js and running
//   gnome-extensions disable hide-from-screencast@hiddenwindow
//   gnome-extensions enable  hide-from-screencast@hiddenwindow
// picks up the new code without logging out (Wayland can't restart the shell).

import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class HideFromScreencastExtension extends Extension {
    enable() {
        this._generation = (this._generation ?? 0) + 1;
        const generation = this._generation;
        const url = `${import.meta.url.replace(/[^/]*$/, 'impl.js')}?t=${Date.now()}`;

        import(url).then(impl => {
            if (generation !== this._generation || this._hider)
                return; // disabled (or re-enabled) while loading
            const debug = debugFlag(this.path);
            this._hider = new impl.Hider(debug === null ? {} : {debug});
            this._hider.enable();
        }).catch(e => logError(e, '[hide-from-screencast] failed to load impl.js'));
    }

    disable() {
        this._generation = (this._generation ?? 0) + 1;
        this._hider?.disable();
        this._hider = null;
    }
}

// Touch a file named DEBUG in the extension directory to turn on paint stats
// without editing code.
function debugFlag(path) {
    return GLib.file_test(`${path}/DEBUG`, GLib.FileTest.EXISTS) ? true : null;
}
