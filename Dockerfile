# UK House Prices — dev container image.
#
# Slim Python base for the data pipeline (src/, functions/, global.py).
# Also provisions git and the Claude Code CLI so both are usable inside the
# container. Host credentials for git and Claude Code are bind-mounted at
# runtime by .devcontainer/devcontainer.json — this image itself ships no
# secrets, so it's safe to rebuild/share.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        ca-certificates \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Container-local git config that *includes* the host's ~/.gitconfig (bind-
# mounted read-only to /root/.gitconfig-host) instead of writing into it, and
# adds a safe.directory exception for the bind-mounted /workspace repo.
RUN printf '[include]\n\tpath = /root/.gitconfig-host\n[safe]\n\tdirectory = /workspace\n' > /root/.gitconfig

WORKDIR /workspace

# Copied separately so this layer only rebuilds when dependencies change.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Claude Code CLI — native installer, no Node.js required.
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"

CMD ["bash"]
