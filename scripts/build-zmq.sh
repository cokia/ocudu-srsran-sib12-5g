#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${LAB_BUILD_JOBS:-2}
[[ "$jobs" =~ ^[1-4]$ ]] || exit 2
component=${1:-all}
[[ "$component" == all || "$component" == gnb || "$component" == ue ]] || exit 2
mkdir -p build/bin artifacts/zmq
if [[ "$component" != ue ]]; then
 python3 scripts/fetch-upstream.py ocudu
 arch=armv8-a
 [[ $(uname -m) == x86_64 ]] && arch=x86-64
 cmake -S upstream/ocudu -B build/zmq-gnb -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_CXX_FLAGS_RELEASE='-O1 -DNDEBUG' -DMARCH="$arch" -DMCPU=generic \
  -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF -DENABLE_SIDEKIQ=OFF -DENABLE_DIFI=OFF \
  -DENABLE_DPDK=OFF -DENABLE_BACKWARD=OFF -DENABLE_MKL=OFF -DENABLE_FFTZ=OFF -DENABLE_ARMPL=OFF \
  -DBUILD_TESTING=OFF -DENABLE_WERROR=OFF -DASSERT_LEVEL=NORMAL
 timeout --signal=TERM --kill-after=15s 2700s cmake --build build/zmq-gnb --target gnb -j "$jobs"
 cp build/zmq-gnb/apps/gnb/gnb build/bin/gnb-zmq
fi
if [[ "$component" != gnb ]]; then
 python3 scripts/fetch-upstream.py srsran4g
 cmake -S upstream/srsran4g -B build/srsue -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_C_FLAGS_RELEASE='-O2 -DNDEBUG' -DCMAKE_CXX_FLAGS_RELEASE='-O1 -DNDEBUG' \
  -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF -DENABLE_BLADERF=OFF -DENABLE_SOAPYSDR=OFF \
  -DENABLE_SRSENB=OFF -DENABLE_SRSEPC=OFF -DENABLE_ALL_TEST=OFF \
  -DENABLE_RF_PLUGINS=OFF -DENABLE_GUI=OFF -DENABLE_HARDSIM=OFF -DENABLE_WERROR=OFF
 timeout --signal=TERM --kill-after=15s 1800s cmake --build build/srsue --target srsue -j "$jobs"
 cp build/srsue/srsue/src/srsue build/bin/srsue
fi
dpkg-query -W > artifacts/zmq/packages.tsv
