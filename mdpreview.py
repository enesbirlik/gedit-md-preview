# Markdown preview for gedit: splits a .md tab into editor | live preview.
# F9 or Ctrl+Alt+M cycles: side by side -> preview only -> text only.
import json
import gi
gi.require_version('Gedit', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GObject, GLib, Gio, Gtk, Gedit, WebKit2
from markdown_it import MarkdownIt

MD = MarkdownIt('commonmark').enable(['table', 'strikethrough'])
SHORTCUTS = ['F9', '<Primary><Alt>m']
SPLIT, PREVIEW, TEXT = 0, 1, 2
RENDER_DELAY_MS = 300

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
:root { color-scheme: light dark; }
body { font: 15px/1.55 sans-serif; margin: 12px 20px; max-width: 900px; }
pre, code { font-family: monospace; background: rgba(127,127,127,.15); border-radius: 4px; }
code { padding: 1px 4px; } pre { padding: 8px 10px; overflow-x: auto; } pre code { padding: 0; background: none; }
table { border-collapse: collapse; } th, td { border: 1px solid rgba(127,127,127,.5); padding: 4px 8px; }
blockquote { margin: 0; padding-left: 12px; border-left: 3px solid rgba(127,127,127,.5); opacity: .85; }
h1, h2 { border-bottom: 1px solid rgba(127,127,127,.3); padding-bottom: 3px; }
img { max-width: 100%; } a { color: #3584e4; }
</style></head><body><div id="c"></div></body></html>"""


def is_markdown(doc):
    lang = doc.get_language()
    if lang and lang.get_id() == 'markdown':
        return True
    loc = doc.get_file().get_location()
    return bool(loc and loc.get_basename().lower().endswith(('.md', '.markdown')))


class Split:
    """Moves a tab's editor frame into a Gtk.Paned and puts a WebView next to it."""

    def __init__(self, tab, window):
        self.tab, self.window = tab, window
        self.doc = tab.get_document()
        view = tab.get_view()
        # The tab child holding the editor (GeditViewFrame) is the one containing the view.
        self.frame = next(c for c in tab.get_children() if view.is_ancestor(c))
        self.position = tab.child_get_property(self.frame, 'position')

        self.web = WebKit2.WebView()
        self.web.connect('decide-policy', self.on_decide_policy)
        self.web.connect('load-changed', self.on_load_changed)
        self.loaded, self.base_uri, self.pending, self.timer = False, None, '', 0

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        tab.remove(self.frame)
        self.paned.pack1(self.frame, True, False)
        self.paned.pack2(self.web, True, False)
        tab.pack_start(self.paned, True, True, 0)
        tab.reorder_child(self.paned, self.position)
        self.paned.show_all()

        self.changed_id = self.doc.connect('changed', self.on_changed)
        self.mode = None
        self.set_mode(SPLIT)
        self.render()

    def remove(self):
        self.doc.disconnect(self.changed_id)
        if self.timer:
            GLib.source_remove(self.timer)
        self.frame.show()
        self.paned.remove(self.frame)
        self.tab.remove(self.paned)
        self.tab.pack_start(self.frame, True, True, 0)
        self.tab.reorder_child(self.frame, self.position)
        self.paned.destroy()

    def set_mode(self, mode):
        self.mode = mode
        self.frame.set_visible(mode != PREVIEW)
        self.web.set_visible(mode != TEXT)
        if mode == SPLIT:
            GLib.idle_add(self.center_divider)
        (self.web if mode == PREVIEW else self.tab.get_view()).grab_focus()

    def center_divider(self):
        width = self.paned.get_allocated_width()
        if width > 1:
            self.paned.set_position(width // 2)
        return False

    def on_changed(self, *args):
        # Render once typing pauses, not on every keystroke.
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(RENDER_DELAY_MS, self.render)

    def render(self):
        self.timer = 0
        doc = self.doc
        html = MD.render(doc.get_text(doc.get_start_iter(), doc.get_end_iter(), False))
        loc = doc.get_file().get_location()
        base_uri = loc.get_parent().get_uri() + '/' if loc else 'file:///'
        if not self.loaded or base_uri != self.base_uri:
            # Load with the file's folder as base so relative images/links resolve.
            self.base_uri, self.loaded, self.pending = base_uri, False, html
            self.web.load_html(PAGE, base_uri)
        else:
            self.inject(html)
        return False

    def inject(self, html):
        # Swapping innerHTML keeps the scroll position, unlike reloading the page.
        self.web.run_javascript(
            'document.getElementById("c").innerHTML = %s;' % json.dumps(html), None, None, None)

    def on_load_changed(self, web, event):
        if event == WebKit2.LoadEvent.FINISHED:
            self.loaded = True
            self.inject(self.pending)

    def on_decide_policy(self, web, decision, kind):
        # Clicked links open in the default app instead of replacing the preview.
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            action = decision.get_navigation_action()
            if action.get_navigation_type() == WebKit2.NavigationType.LINK_CLICKED:
                Gtk.show_uri_on_window(self.window, action.get_request().get_uri(),
                                       Gtk.get_current_event_time())
                decision.ignore()
                return True
        return False


class MdPreview(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = 'MdPreview'
    window = GObject.Property(type=Gedit.Window)

    def do_activate(self):
        self.splits = {}       # tab -> Split
        self.doc_handlers = {} # tab -> [document signal ids]
        action = Gio.SimpleAction.new('md-preview-mode', None)
        action.connect('activate', self.cycle_mode)
        self.window.add_action(action)
        app = Gtk.Application.get_default()
        # gedit binds F9 to the side panel; take our keys over while enabled, restore on disable.
        self.taken = {}
        for key in SHORTCUTS:
            for name in app.get_actions_for_accel(key):
                self.taken.setdefault(name, app.get_accels_for_action(name))
                app.set_accels_for_action(name, [a for a in app.get_accels_for_action(name) if a != key])
        app.set_accels_for_action('win.md-preview-mode', SHORTCUTS)
        self.window_handlers = [
            self.window.connect('tab-added', lambda w, t: self.add_tab(t)),
            self.window.connect('tab-removed', lambda w, t: self.remove_tab(t)),
        ]
        for doc in self.window.get_documents():
            self.add_tab(Gedit.Tab.get_from_document(doc))

    def do_deactivate(self):
        for h in self.window_handlers:
            self.window.disconnect(h)
        for tab in list(self.doc_handlers):
            self.remove_tab(tab)
        self.window.remove_action('md-preview-mode')
        app = Gtk.Application.get_default()
        app.set_accels_for_action('win.md-preview-mode', [])
        for name, accels in self.taken.items():
            app.set_accels_for_action(name, accels)

    def do_update_state(self):
        pass

    def add_tab(self, tab):
        doc = tab.get_document()
        # Re-check after load / save-as, when the file name becomes known or changes.
        self.doc_handlers[tab] = [doc.connect('loaded', lambda d: self.refresh(tab)),
                                  doc.connect('saved', lambda d: self.refresh(tab))]
        self.refresh(tab)

    def remove_tab(self, tab):
        doc = tab.get_document()
        for h in self.doc_handlers.pop(tab, []):
            doc.disconnect(h)
        split = self.splits.pop(tab, None)
        if split:
            split.remove()

    def refresh(self, tab):
        md = is_markdown(tab.get_document())
        if md and tab not in self.splits:
            self.splits[tab] = Split(tab, self.window)
        elif not md and tab in self.splits:
            self.splits.pop(tab).remove()

    def cycle_mode(self, *args):
        split = self.splits.get(self.window.get_active_tab())
        if split:
            split.set_mode((split.mode + 1) % 3)
