#!/usr/bin/env bash
set -euo pipefail
# Ubuntu 24.04 전용. 컨테이너에서는 root, native에서는 sudo로 실행한다.
[[ "$(. /etc/os-release; echo "$ID:$VERSION_ID")" == ubuntu:24.04 ]] || { echo 'Ubuntu 24.04가 필요합니다.' >&2; exit 2; }
mode=${1:-non-sdr}
[[ "$mode" == non-sdr || "$mode" == sdr-bladerf-x40 ]] || exit 2
export DEBIAN_FRONTEND=noninteractive
if [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
  apt-get update -o APT::Update::Error-Mode=any
  apt-get install -y --no-install-recommends ca-certificates=20240203
fi
# 날짜가 고정된 archive를 직접 사용하여 snapshot 옵션 무시를 방지한다.
rm -f /etc/apt/sources.list.d/ubuntu.sources
cat > /etc/apt/sources.list <<'APT'
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-updates main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-security main universe
APT
apt-get update -o APT::Update::Error-Mode=any
apt-get install -y --no-install-recommends \
  ca-certificates git cmake ninja-build clang-18 lld-18 pkg-config \
  libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev \
  python3 python3-venv python3-pip nlohmann-json3-dev coreutils iproute2
if [[ "$mode" == sdr-bladerf-x40 ]]; then
  apt-get install -y --no-install-recommends libusb-1.0-0-dev
fi
