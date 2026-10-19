#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${LAB_BUILD_JOBS:-2}
[[ "$jobs" =~ ^[1-4]$ ]] || exit 2
mkdir -p build/bin artifacts/lte-sib12
python3 scripts/fetch-upstream.py srsran4g
cmake -S upstream/srsran4g -B build/lte -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_C_FLAGS_RELEASE='-O2 -DNDEBUG' -DCMAKE_CXX_FLAGS_RELEASE='-O1 -DNDEBUG' \
  -DENABLE_ZEROMQ=ON -DENABLE_UHD=OFF -DENABLE_BLADERF=OFF -DENABLE_SOAPYSDR=OFF \
  -DENABLE_SRSUE=ON -DENABLE_SRSENB=ON -DENABLE_SRSEPC=OFF -DENABLE_ALL_TEST=OFF \
  -DENABLE_RF_PLUGINS=OFF -DENABLE_GUI=OFF -DENABLE_HARDSIM=OFF -DENABLE_WERROR=OFF
# LTE build에는 물리 RF backend가 포함되지 않는다.
timeout --signal=TERM --kill-after=15s 1800s cmake --build build/lte --target srsenb srsue -j "$jobs"
cp build/lte/srsenb/src/srsenb build/bin/srsenb-lte
cp build/lte/srsue/src/srsue build/bin/srsue-lte
dpkg-query -W > artifacts/lte-sib12/packages.tsv
