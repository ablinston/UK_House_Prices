"""Local preview server for the static site.

Python's built-in http.server lets the browser cache aggressively, which means
an edited CSS or JS file is often served stale — and with ES modules a stale
file surfaces as a confusing "does not provide an export named ..." error
rather than as obviously old code. This sends no-cache headers so a plain
refresh always picks up the current files.

Production is a normal CDN with normal caching; this is a development aid only.

    python serve.py [--port 8000] [--directory web]
"""

import argparse
import functools
import http.server
import socketserver


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files with caching disabled and sensible content types."""

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.woff2': 'font/woff2',
        '.geojson': 'application/geo+json',
        '.bin': 'application/octet-stream',
        '.mjs': 'text/javascript',
    }

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--directory', default='web')
    args = parser.parse_args()

    handler = functools.partial(NoCacheHandler, directory=args.directory)

    # Allow an immediate restart on the same port after Ctrl+C
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(('', args.port), handler) as httpd:
        print(f'Serving {args.directory}/ at http://localhost:{args.port}')
        print('Press Ctrl+C to stop.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')


if __name__ == '__main__':
    main()
