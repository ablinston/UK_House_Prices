#!/usr/bin/env bash
# =============================================================================
# Preview the static site locally, exactly as it will be served in production.
#
# The Linux/macOS twin of run_website_locally.bat, and what to use inside the
# dev container, where a .bat cannot run.
#
# This is a plain static file server - there is no build step and no app
# process. serve.py imports nothing but the Python standard library, so this
# needs no virtual environment and nothing from requirements.txt, which is
# there for the data pipeline rather than for the site.
# =============================================================================

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
    py=python3
elif command -v python >/dev/null 2>&1; then
    py=python
else
    echo "ERROR: no Python found on PATH. Install Python 3 and try again." >&2
    exit 1
fi

if [ ! -f "$here/web/data/meta.json" ]; then
    cat >&2 <<EOF

ERROR: web/data/meta.json is missing, so the site has no data to show.
Generate it with:
    $py src/06_export_web_data.py

That step is the data pipeline, which does need the dependencies in
requirements.txt - unlike this preview server.
EOF
    exit 1
fi

echo
echo "  UK House Prices - local preview"
echo "  Open http://localhost:8000"
echo "  Press Ctrl+C to stop."
echo

exec "$py" "$here/serve.py" --port 8000 --directory "$here/web"
