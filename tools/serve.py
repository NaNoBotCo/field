#!/usr/bin/env python3
"""Serve build/site at http://localhost:<port>/field/ — mounted where the host mounts it,
and answering /field without its slash the way motdang.net does (a 200, not a redirect)."""
import functools, http.server, sys
from pathlib import Path
SITE = Path(__file__).resolve().parent.parent / "build" / "site"
MOUNT = "/field"
class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = path.split("?", 1)[0]
        if p == MOUNT: p = MOUNT + "/"
        if p == "/" : self.path = MOUNT + "/"; p = MOUNT + "/"
        if p.startswith(MOUNT + "/"): p = p[len(MOUNT):]
        return super().translate_path(p)
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8820
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=str(SITE))).serve_forever()
