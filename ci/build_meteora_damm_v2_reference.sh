#!/usr/bin/env bash
set -euo pipefail
out="$1"
mkdir -p "$out"
manifest="tools/meteora_damm_v2_reference/Cargo.toml"
binary="tools/meteora_damm_v2_reference/target/release/sol-meteora-damm-v2-official-reference"
rustup toolchain install 1.94.0 --profile minimal
rustup run 1.94.0 rustc --version | tee "$out/rust-version.txt"
# The first uncredentialed build resolves dependencies and retains its lock.
# The independent build can take that exact lock as input, never a binary.
# Do not silently regenerate a supplied lock or accept a missing artifact.
if [[ $# -ge 2 ]]; then
    test -s "$2"
    cp "$2" tools/meteora_damm_v2_reference/Cargo.lock
    printf '%s\n' "REUSED_SIZING_DEPENDENCY_LOCK" > "$out/lock.log"
else
    cargo +1.94.0 generate-lockfile --manifest-path "$manifest" 2>&1 | tee "$out/lock.log"
fi
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
