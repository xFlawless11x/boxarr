#!/bin/sh
set -e

# Fix ownership of the mounted /config volume so the non-root boxarr user
# can write log files and config. This must run as root (before gosu drops
# privileges), because Docker volume mounts are always owned by root on first
# use and ignore the image-level chown.
chown -R boxarr:boxarr /config 2>/dev/null || true

exec gosu boxarr "$@"
