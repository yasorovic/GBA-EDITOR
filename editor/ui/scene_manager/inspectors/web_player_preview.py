"""Aperçu intégré du lecteur web, sans émulation."""
from __future__ import annotations

import html
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from urllib.parse import unquote, urlsplit

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor

from codegen.web_build import WebTemplateError, web_player_files
from ui.common.labels import label

_ASSET_SUFFIXES = {
    ".css", ".svg", ".png", ".webp", ".jpg", ".jpeg", ".gif", ".avif", ".ico",
    ".ttf", ".otf", ".woff", ".woff2",
}
_PLAYER_POLICY = (
    "sandbox allow-same-origin; default-src 'none'; "
    "style-src 'self' 'unsafe-inline' data:; img-src 'self' data:; font-src 'self' data:; "
    "base-uri 'none'; form-action 'none'"
)

_WINDOW = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<link rel="icon" href="data:,">
<style>
  html, body { margin: 0; overflow: hidden; background: transparent; }
  iframe {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 100%;
    height: 100%;
    transform: translate(-50%, -50%) scale(var(--preview-scale, 1));
    color-scheme: normal;
    border: 0;
    visibility: hidden;
  }
</style>
<iframe sandbox="allow-same-origin" title="__TITLE__"></iframe>
<script>
  const frame = document.querySelector("iframe");
  const mobileSizes = {portrait: [360, 480], landscape: [640, 360]};
  let layout = "portrait";
  let revision;
  let styles = {};
  function applyStyles() {
    const page = frame.contentDocument;
    if (!page || page.URL !== frame.src) return;
    for (const [name, css] of Object.entries(styles)) {
      let style = page.querySelector(`style[data-preview-sheet="${name}"]`);
      if (!style) {
        const href = new URL(name, page.URL).href;
        const link = [...page.querySelectorAll('link[rel="stylesheet"]')]
          .find(node => node.href.split(/[?#]/, 1)[0] === href);
        if (!link) continue;
        style = page.createElement("style");
        style.dataset.previewSheet = name;
        style.media = link.media;
        style.title = link.title;
        link.replaceWith(style);
      }
      if (style.textContent !== css) style.textContent = css;
    }
  }
  function showPlayer(next, nextStyles) {
    styles = nextStyles;
    if (next === revision) {
      applyStyles();
    } else {
      revision = next;
      frame.src = "player/index.html?v=" + next;
    }
  }
  function fitFrame() {
    const margin = 8;
    const availableWidth = Math.max(1, innerWidth - 2 * margin);
    const availableHeight = Math.max(1, innerHeight - 2 * margin);
    const [width, height] = mobileSizes[layout] ?? [availableWidth, availableHeight];
    const scale = Math.min(1, availableWidth / width, availableHeight / height);
    frame.style.width = width + "px";
    frame.style.height = height + "px";
    frame.style.setProperty("--preview-scale", scale);
  }
  function applyView() {
    const page = frame.contentDocument;
    if (!page) return;
    const mobile = layout !== "desktop";
    const landscape = layout === "landscape";
    page.querySelector(".web-prototype")?.classList.toggle("mobile-preview", mobile);
    page.querySelector(".web-prototype")?.classList.toggle("preview-landscape", landscape);
    page.querySelector(".player")?.classList.toggle("side-controls", landscape);
  }
  function setLayout(next) {
    layout = next;
    fitFrame();
    applyView();
  }
  frame.addEventListener("load", () => {
    const page = frame.contentDocument;
    if (!page || page.URL === "about:blank") return;
    const status = page.querySelector("#status");
    if (status) status.textContent = page.title;
    const romPicker = page.querySelector("#rom-file")?.closest("label");
    if (romPicker) romPicker.hidden = true;
    for (const button of page.querySelectorAll("#play, #mute, #fullscreen")) {
      button.disabled = false;
    }
    applyStyles();
    applyView();
    frame.style.visibility = "visible";
  });
  window.addEventListener("resize", fitFrame);
</script>
"""


class WebPlayerPreview:
    """Sert uniquement les fichiers de rendu du lecteur sur une URL locale privée."""

    def __init__(self, parent):
        # Import différé : le gabarit et son aperçu sont réservés aux sources.
        from PyQt6.QtWebEngineCore import QWebEnginePage
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self._revision = 0
        self._snapshot = ({}, {})
        self._ready = False
        self._layout = "portrait"
        window = _WINDOW.replace("__TITLE__", html.escape(label("projset.web_preview_title")))
        prefix = f"/{token_urlsafe(18)}/"
        preview = self

        class Request(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def handle(self):
                try:
                    super().handle()
                except ConnectionError:
                    # Le navigateur peut annuler une requête en actualisant la vue.
                    pass

            def do_GET(self):
                path = unquote(urlsplit(self.path).path)
                port = self.server.server_port
                if self.headers.get("Host") != f"127.0.0.1:{port}" or not path.startswith(prefix):
                    self.send_error(404)
                    return
                name = path[len(prefix):]
                texts, assets = preview._snapshot
                policy = None
                if not name:
                    data, mime = window.encode(), "text/html; charset=utf-8"
                elif name.startswith("player/"):
                    entry = name[len("player/"):]
                    policy = _PLAYER_POLICY
                    if entry in texts:
                        data = texts[entry].encode()
                        mime = "text/html" if entry == "index.html" else "text/css"
                        mime += "; charset=utf-8"
                    elif entry in assets:
                        try:
                            data = assets[entry].read_bytes()
                        except OSError:
                            self.send_error(404)
                            return
                        mime = mimetypes.guess_type(entry)[0] or "application/octet-stream"
                    else:
                        self.send_error(404)
                        return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                safe_mime = mime.replace("\r", "").replace("\n", "")
                if not safe_mime:
                    safe_mime = "application/octet-stream"
                self.send_header("Content-Type", safe_mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.send_header("X-Content-Type-Options", "nosniff")
                if policy:
                    self.send_header("Content-Security-Policy", policy)
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Request)
        url = f"http://127.0.0.1:{self._server.server_port}{prefix}"

        class PreviewPage(QWebEnginePage):
            def acceptNavigationRequest(self, target, _navigation_type, _is_main_frame):
                return target.toString().startswith(url)

        self.view = QWebEngineView(parent)
        self.view.setPage(PreviewPage(self.view))
        self.view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.loadFinished.connect(self._loaded)
        parent.destroyed.connect(self.close)
        Thread(target=self._server.serve_forever, kwargs={"poll_interval": .05}, daemon=True).start()
        self.view.load(QUrl(url))

    def update(self, settings, project_root: Path, title: str):
        try:
            texts, entries = web_player_files(settings, project_root, title, preview=True)
        except (OSError, UnicodeError, WebTemplateError) as exc:
            texts = {"index.html": f'<!doctype html><meta charset="utf-8"><p>{html.escape(str(exc))}</p>'}
            entries = []
        assets = {name: path for name, path in entries if path.suffix.lower() in _ASSET_SUFFIXES}
        old_texts, old_assets = self._snapshot
        if (texts, assets) == self._snapshot:
            return
        if texts["index.html"] != old_texts.get("index.html") or assets != old_assets:
            self._revision += 1
        self._snapshot = (texts, assets)
        self._show_player()

    def _loaded(self, ok):
        self._ready = ok
        self.set_layout(self._layout)
        self._show_player()

    def set_layout(self, layout: str):
        self._layout = layout
        if self._ready:
            self.view.page().runJavaScript(f"setLayout({json.dumps(layout)});")

    def _show_player(self):
        if self._ready and self._snapshot[0]:
            styles = {name: css for name, css in self._snapshot[0].items() if name.endswith(".css")}
            self.view.page().runJavaScript(f"showPlayer({self._revision}, {json.dumps(styles)});")

    def close(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
