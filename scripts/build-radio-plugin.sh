#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
option=${1:---mock-only}
[[ "$option" == --mock-only || "$option" == --enable-rf ]] || exit 2
rf=OFF
build_dir=build/radio-plugin
if [[ "$option" == --enable-rf ]]; then
  rf=ON
  build_dir=build/radio-plugin-rf
fi
python3 scripts/fetch-upstream.py ocudu
export PKG_CONFIG_PATH="$PWD/build/deps/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
cmake -S hardware/bladerf-x40/radio_plugin -B "$build_dir" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++-18 \
  -DLAB_ENABLE_BLADERF_RF="$rf"
timeout --signal=TERM --kill-after=10s 300s cmake --build "$build_dir" -j 2
mkdir -p "$build_dir/lib"
cp "$build_dir/libocudu_radio_bladerf_x40.so" "$build_dir/lib/"
