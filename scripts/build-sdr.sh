#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
jobs=${LAB_BUILD_JOBS:-2}
[[ "$jobs" =~ ^[1-4]$ ]] || exit 2
if [[ "${1:-}" == --mock-only ]]; then
  cmake -S . -B build/sdr-mock -G Ninja -DLAB_WITH_BLADERF=OFF
  cmake --build build/sdr-mock -j "$jobs"
  mkdir -p build/bin
  cp build/sdr-mock/bladerf-x40-diag build/bin/bladerf-x40-diag-mock
  exit 0
fi
python3 scripts/fetch-upstream.py bladerf
if [[ ! -d build/bladerf-source ]]; then
  git clone --local upstream/bladeRF build/bladerf-source
fi
if git -C build/bladerf-source apply --check ../../patches/bladerf-x40-only.patch; then
  git -C build/bladerf-source apply ../../patches/bladerf-x40-only.patch
else
  git -C build/bladerf-source apply --reverse --check ../../patches/bladerf-x40-only.patch
fi
cmake -S build/bladerf-source/host -B build/bladerf -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PWD/build/deps" \
  -DBUILD_AD936X=OFF -DTEST_LIBBLADERF=OFF -DBUILD_DOCUMENTATION=OFF -DBUILD_LIBBLADERF_DOCUMENTATION=OFF \
  -DBUILD_LIBBLADERF_DOC_EXAMPLES=OFF -DTREAT_WARNINGS_AS_ERRORS=OFF
# x40용 shared library만 빌드한다. CLI/firmware/FPGA/AD936x를 설치하지 않는다.
timeout --signal=TERM --kill-after=15s 600s cmake --build build/bladerf --target libbladerf_shared -j "$jobs"
mkdir -p build/deps/lib/pkgconfig build/deps/include build/bin
cp build/bladerf/output/libbladeRF.so* build/deps/lib/
cp upstream/bladeRF/host/libraries/libbladeRF/include/{libbladeRF.h,bladeRF1.h,bladeRF2.h} build/deps/include/
cp build/bladerf/libraries/libbladeRF/libbladeRF.pc build/deps/lib/pkgconfig/
export PKG_CONFIG_PATH="$PWD/build/deps/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
cmake -S . -B build/sdr -G Ninja -DLAB_WITH_BLADERF=ON
cmake --build build/sdr -j "$jobs"
cp build/sdr/bladerf-x40-diag build/bin/
