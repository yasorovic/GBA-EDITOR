"""Sert _build/html en local, sans cache navigateur : une page reconstruite s'affiche aussitôt."""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


directory = sys.argv[1]
ThreadingHTTPServer(("127.0.0.1", 8000), partial(NoCacheHandler, directory=directory)).serve_forever()
