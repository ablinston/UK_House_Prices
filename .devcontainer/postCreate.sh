#!/usr/bin/env bash
#
# Runs once, after the container is created.
#
# devcontainer.json stages the host's ~/.ssh at /tmp/host-ssh rather than
# mounting it straight onto /root/.ssh, and this is the half that finishes the
# job. Two reasons it has to be a copy:
#
#   ssh refuses a private key that anyone other than its owner can read, and a
#   bind mount carries the host's mode and ownership across unchanged - which
#   coming off Windows is routinely wide open. The mount is read-only, so the
#   mode cannot be fixed in place.
#
#   known_hosts has to be written to on first connection. On a read-only mount
#   that write fails, and the failure reads as 'Host key verification failed',
#   which sounds like a credentials problem and is not.
#
# Without this, the key sits at /tmp/host-ssh, ssh never looks there, and every
# push fails with 'Permission denied (publickey)' on a container that appears
# to have been given a key.

set -euo pipefail

SSH_DIR=/root/.ssh
STAGED=/tmp/host-ssh

echo 'Setting up git over SSH'

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

if [ -d "$STAGED" ]; then
    # -L so a symlinked key on the host arrives as the key itself rather than
    # as a link pointing at a path that does not exist in here
    cp -rL "$STAGED"/. "$SSH_DIR"/ 2>/dev/null || true
    chmod 600 "$SSH_DIR"/* 2>/dev/null || true
    chmod 644 "$SSH_DIR"/*.pub "$SSH_DIR/known_hosts" 2>/dev/null || true
else
    echo "  nothing mounted at $STAGED - pushing will not work until there is"
fi

# Checked against the key GitHub publishes rather than trusted on sight, so a
# hijacked DNS answer is refused instead of being written into known_hosts and
# believed from then on.
GITHUB_ED25519='SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU'

scanned=$(ssh-keyscan -t ed25519 github.com 2>/dev/null || true)
if [ -n "$scanned" ]; then
    fingerprint=$(printf '%s\n' "$scanned" | ssh-keygen -lf - | awk '{print $2}')
    if [ "$fingerprint" = "$GITHUB_ED25519" ]; then
        printf '%s\n' "$scanned" >> "$SSH_DIR/known_hosts"
        sort -u -o "$SSH_DIR/known_hosts" "$SSH_DIR/known_hosts"
        chmod 644 "$SSH_DIR/known_hosts"
        echo '  github.com host key verified and trusted'
    else
        echo "  REFUSED github.com host key: got $fingerprint"
        echo '  that is not the key GitHub publishes - do not push from this container'
    fi
else
    echo '  could not reach github.com to fetch its host key'
fi

# Said here rather than left to be discovered on the first push. GitHub exits 1
# on this command even when it works, so the greeting is what gets read.
if ls "$SSH_DIR"/id_* >/dev/null 2>&1; then
    greeting=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com 2>&1 || true)
    case "$greeting" in
        *successfully\ authenticated*) echo "  ${greeting%%.*} - push will work" ;;
        *)                             echo '  SSH key present but GitHub did not accept it:'
                                       echo "    $greeting" ;;
    esac
else
    echo '  no SSH private key found - add one to the host ~/.ssh and rebuild'
fi

echo "  committing as $(git config --get user.name) <$(git config --get user.email)>"
