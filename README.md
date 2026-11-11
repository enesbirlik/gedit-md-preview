# gedit-md-preview

A small gedit plugin that shows Markdown files side by side with a live preview.

Open a `.md` file and its tab splits into editor | preview. Press **F9** (or **Ctrl+Alt+M**) to cycle:

1. side by side
2. preview only
3. text only

The preview updates as you type, keeps its scroll position, resolves relative images, supports tables and code blocks, follows the light/dark theme, and opens clicked links in your browser. Drag the divider to resize.

## Requirements

gedit 46 (GTK 3), WebKit2GTK 4.1 introspection and `markdown-it-py`. On Ubuntu 24.04:

```sh
sudo apt install gir1.2-webkit2-4.1 python3-markdown-it
```

## Install

```sh
mkdir -p ~/.local/share/gedit/plugins
cp mdpreview.py mdpreview.plugin ~/.local/share/gedit/plugins/
```

Restart gedit, then enable **Markdown Preview** under Preferences → Plugins.

## Notes

While enabled, F9 is taken from gedit's side panel toggle (restored when the plugin is disabled).

The plugin moves the tab's editor frame into a `Gtk.Paned`. That relies on gedit internals, so a future gedit release may break it.

## License

MIT, see [LICENSE](LICENSE).
