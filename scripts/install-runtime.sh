#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
 apt-get update -o APT::Update::Error-Mode=any
 apt-get install -y --no-install-recommends ca-certificates=20240203
fi
rm -f /etc/apt/sources.list.d/ubuntu.sources
cat > /etc/apt/sources.list <<'APT'
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-updates main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261001T000000Z noble-security main universe
APT
apt-get update -o APT::Update::Error-Mode=any
apt-get install -y --no-install-recommends python3 libstdc++6 libatomic1 libfftw3-single3 libmbedtls14 libmbedcrypto7 libmbedx509-1 libsctp1 libyaml-cpp0.8
rm -rf /var/lib/apt/lists/*
