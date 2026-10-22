#!/usr/bin/env bash
# CI-only Surfpool installer: fail closed on corrupt release downloads.
set -euo pipefail
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if curl --fail --show-error --silent --location --retry 3 --retry-all-errors --retry-delay 3 \
    https://run.surfpool.run/ -o /tmp/install-surfpool.sh; then
  for attempt in 1 2; do
    if bash /tmp/install-surfpool.sh && command -v surfpool >/dev/null 2>&1; then
      surfpool --version
      exit 0
    fi
    sleep 3
  done
fi
echo 'Surfpool release installer failed; switching to official Docker image' >&2
command -v docker >/dev/null || { echo 'Docker unavailable' >&2; exit 1; }
docker pull surfpool/surfpool
docker run --rm surfpool/surfpool --version
cat > "$HOME/.local/bin/surfpool" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# GitHub Ubuntu runners are Linux; host networking preserves localhost RPC.
exec docker run --rm --network host \
  -e SURFPOOL_PUBLIC_HOST=127.0.0.1 \
  surfpool/surfpool "$@"
EOF
chmod 700 "$HOME/.local/bin/surfpool"
