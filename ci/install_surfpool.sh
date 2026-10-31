#!/usr/bin/env bash
# Docker-first Surfpool CI launcher. Never silently switch binary provenance.
set -euo pipefail
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Pull once per runner/job. Subsequent CLI calls reuse the cached image.
IMAGE="${SURFPOOL_DOCKER_IMAGE:-surfpool/surfpool}"
if [[ "$IMAGE" != "surfpool/surfpool" && "$IMAGE" != surfpool/surfpool:* && "$IMAGE" != surfpool/surfpool@sha256:* ]]; then
  echo "Untrusted Surfpool image reference" >&2
  exit 1
fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 &&
   docker pull "$IMAGE" && docker run --rm --network host "$IMAGE" --version; then
  cat > "$HOME/.local/bin/surfpool" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# No --pull=always: use the image pulled once during job initialization.
# Host networking keeps RPC on loopback; each Surfpool server is isolated by job.
exec docker run --rm --network host \
  -e SURFPOOL_PUBLIC_HOST=127.0.0.1 \
  "${SURFPOOL_DOCKER_IMAGE:-surfpool/surfpool}" "$@"
EOF
  chmod 700 "$HOME/.local/bin/surfpool"
  echo "Surfpool runtime: Docker image $IMAGE"
  exit 0
fi

# Escape hatch, not the default. Explicit opt-in prevents an accidental
# switch in runtime behavior and preserves fail-closed CI diagnostics.
if [[ "${SURFPOOL_ALLOW_NATIVE_FALLBACK:-0}" != 1 ]]; then
  echo "Docker Surfpool unavailable; native installer fallback disabled" >&2
  exit 1
fi
echo "Docker unavailable; explicitly authorized native installer fallback" >&2
curl --fail --show-error --silent --location --retry 3 --retry-all-errors --retry-delay 3 \
    https://run.surfpool.run/ -o /tmp/install-surfpool.sh
for attempt in 1 2; do
  if bash /tmp/install-surfpool.sh && command -v surfpool >/dev/null 2>&1; then
    surfpool --version
    exit 0
  fi
  sleep 3
done
echo "Surfpool native fallback installation failed" >&2
exit 1
