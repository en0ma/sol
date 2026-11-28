#!/usr/bin/env bash
# Build on the same uncredentialed runner that will execute the reader.
# Do not reuse this native-CPU binary on another machine.
set -euo pipefail
if [[ $# != 2 ]]; then
  echo "usage: $0 upstream-checkout evidence-directory" >&2
  exit 2
fi
upstream="$(cd "$1" && pwd -P)"
mkdir -p "$2"
evidence="$(cd "$2" && pwd -P)"
revision=c8265ad3e61a36e8f8f2dee49020f6bb0f01f220
toolchain=1.98.0
# This is the documented upstream requirement for gxhash AES/SSE2.
export RUSTFLAGS="-C target-cpu=native"
# Keep failed compilation output in the artifact, too.
exec > >(tee "$evidence/native-build.log") 2>&1
test "$(git -C "$upstream" rev-parse HEAD)" = "$revision"
printf 'upstream_revision=%s\nrustflags=%s\nrust_toolchain=%s\n' \
  "$revision" "$RUSTFLAGS" "$toolchain" > "$evidence/native-build-inputs.txt"
rustup toolchain install "$toolchain" --profile minimal
rustc +"$toolchain" --version --verbose
rustc +"$toolchain" -C target-cpu=native --print cfg \
  > "$evidence/native-cpu-cfg.txt"
# The GitHub hosted Linux runner is expected to provide both instructions.
# Fail explicitly instead of falling through to a long compiler failure.
grep -Fx 'target_feature="aes"' "$evidence/native-cpu-cfg.txt"
grep -Fx 'target_feature="sse2"' "$evidence/native-cpu-cfg.txt"
cd "$upstream"
cargo +"$toolchain" build --locked -p blockzilla
binary="$upstream/target/debug/blockzilla"
test -x "$binary"
"$binary" --help > "$evidence/native-reader-help.txt"
"$binary" program-dump --help > "$evidence/native-program-dump-help.txt"
for flag in --epoch --archive-url --cache-dir --first-block --max-blocks --key --workers --http-requests --http-range-mib --stats; do
  grep -Fq -- "$flag" "$evidence/native-program-dump-help.txt"
done
sha256sum "$binary" > "$evidence/native-binary-sha256.txt"
printf 'PINNED_NATIVE_READER_BUILT_AND_CLI_CONTRACT_CHECKED\n' > "$evidence/native-build-status.txt"
