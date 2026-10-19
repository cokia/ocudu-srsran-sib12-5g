#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Linux ]] || { echo 'OCUDU는 Linux가 필요합니다. scripts/build-docker.sh non-sdr 사용.' >&2; exit 3; }
python3 scripts/fetch-upstream.py ocudu
jobs=${LAB_BUILD_JOBS:-2}
[[ "$jobs" =~ ^[1-4]$ ]] || { echo E_JOBS >&2; exit 2; }
arch=armv8-a
[[ $(uname -m) == x86_64 ]] && arch=x86-64-v2
cmake -S upstream/ocudu -B build/non-sdr -G Ninja \
 -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
 -DCMAKE_CXX_FLAGS_RELEASE='-O1 -DNDEBUG' -DMARCH="$arch" -DMCPU=generic \
 -DENABLE_UHD=OFF -DENABLE_SIDEKIQ=OFF -DENABLE_ZEROMQ=OFF -DENABLE_DIFI=OFF \
 -DENABLE_DPDK=OFF -DENABLE_BACKWARD=OFF -DENABLE_MKL=OFF -DENABLE_FFTZ=OFF -DENABLE_ARMPL=OFF \
 -DBUILD_TESTING=OFF -DENABLE_WERROR=OFF -DASSERT_LEVEL=NORMAL
if [[ "${1:-}" != --codec-only ]]; then
 timeout --signal=TERM --kill-after=15s 120s cmake --build build/non-sdr --target ocudu_channel_equalizer -j "$jobs"
fi
if [[ "${1:-}" == --codec-only ]]; then
 timeout --signal=TERM --kill-after=15s 2700s cmake --build build/non-sdr --target pws-codec -j "$jobs"
else
 timeout --signal=TERM --kill-after=15s 2700s cmake --build build/non-sdr --target gnb pws-codec -j "$jobs"
fi
mkdir -p build/bin
cp build/non-sdr/plugins/pws_lab/pws-codec build/bin/
if [[ -f build/non-sdr/apps/gnb/gnb ]]; then cp build/non-sdr/apps/gnb/gnb build/bin/; fi
