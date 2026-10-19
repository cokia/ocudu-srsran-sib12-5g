#!/usr/bin/env bash
set -euo pipefail
# Ubuntu compiler container에서 실행. 바이너리 배포 전에 실행하여 대응 source package를 보존한다.
cd "$(dirname "$0")/.."
mkdir -p artifacts/release/dependency-sources
cat > /etc/apt/sources.list.d/pws-source.list <<'APT'
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble main universe
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-updates main universe
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-security main universe
APT
apt-get update -o APT::Update::Error-Mode=any
cd artifacts/release/dependency-sources
for binary in libfftw3-single3 libmbedtls14 libsctp1 libyaml-cpp0.8 libusb-1.0-0 libc6 libstdc++6 python3; do
 source_spec=$(dpkg-query -W -f='${source:Package}=${source:Version}' "$binary")
 apt-get source --download-only "$source_spec"
done
