#!/usr/bin/env python3
"""Serve build/site at http://localhost:<port>/ (default 8820)."""
import functools, http.server, sys
from pathlib import Path
SITE = Path(__file__).resolve().parent.parent / "build" / "site"
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8820
http.server.ThreadingHTTPServer(("127.0.0.1", port),
    functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))).serve_forever()
