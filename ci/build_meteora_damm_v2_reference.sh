#!/usr/bin/env bash
set -euo pipefail
out="$1"
mkdir -p "$out"
manifest="tools/meteora_damm_v2_reference/Cargo.toml"
binary="tools/meteora_damm_v2_reference/target/release/sol-meteora-damm-v2-official-reference"
rustup toolchain install 1.94.0 --profile minimal
rustup run 1.94.0 rustc --version | tee "$out/rust-version.txt"
# The upstream Git dependencies are revision-pinned. The wrapper has no
# committed Cargo.lock yet; retain the resolved lock for reproducibility.
cargo +1.94.0 generate-lockfile --manifest-path "$manifest" 2>&1 | tee "$out/lock.log"
cp tools/meteora_damm_v2_reference/Cargo.lock "$out/Cargo.lock"
cargo +1.94.0 build --locked --release --manifest-path "$manifest" 2>&1 | tee "$out/build.log"
test -x "$binary"
sha256sum "$binary" > "$out/binary.sha256"
# Invalid input must fail closed, never return a plausible quote.
if printf '{}' | "$binary" > "$out/invalid-response.json" 2> "$out/invalid-response.log"; then
    echo "SDK unexpectedly accepted missing source bytes" >&2
    exit 1
fi
echo "OFFICIAL_SDK_BUILT" > "$out/status.txt"
