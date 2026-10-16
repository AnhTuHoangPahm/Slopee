#!/usr/bin/env bash
# Cài thư viện cho contracts/ ở ĐÚNG phiên bản đã khóa (SRS 10.2). Không dùng `forge install` thẳng vì một số bản
# Foundry bỏ qua tag khi cài và kéo bản mới nhất (OpenZeppelin ≥ 5.1 đòi solc ≥ 0.8.24, vỡ cấu hình 0.8.20).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/contracts/lib"
FORGE_STD_TAG="v1.9.4"
OZ_TAG="v5.0.2"
mkdir -p "$LIB"

clone() { # <url> <tag> <dir>
  local url="$1" tag="$2" dir="$LIB/$3"
  if [ -d "$dir" ]; then echo "đã có $3"; return; fi
  git clone --quiet --depth 1 --branch "$tag" "$url" "$dir"
  rm -rf "$dir/.git"
  echo "đã cài $3 @ $tag"
}
clone https://github.com/foundry-rs/forge-std.git "$FORGE_STD_TAG" forge-std
clone https://github.com/OpenZeppelin/openzeppelin-contracts.git "$OZ_TAG" openzeppelin-contracts

grep -q '"version": "5.0.2"' "$LIB/openzeppelin-contracts/package.json" || { echo "OpenZeppelin không phải 5.0.2" >&2; exit 1; }
