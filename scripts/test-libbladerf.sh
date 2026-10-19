#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/libbladerf
# 실제 device를 사용하는 upstream test는 빌드/실행하지 않는다.
[[ -f build/deps/lib/pkgconfig/libbladeRF.pc ]] || bash scripts/build-sdr.sh
python3 scripts/fetch-upstream.py bladerf
cmake -S tests/libbladerf/upstream -B build/libbladerf-upstream -G Ninja
targets=(libbladeRF_test_c libbladeRF_test_cpp libbladeRF_test_version libbladeRF_test_parse libbladeRF_test_interleaver)
timeout --kill-after=10s 300s cmake --build build/libbladerf-upstream --target "${targets[@]}" -j 1
export PKG_CONFIG_PATH="$PWD/build/deps/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
cmake -S . -B build/libbladerf-tests -G Ninja -DLAB_WITH_BLADERF=ON -DLAB_ADAPTER_TESTS=ON
timeout --kill-after=10s 180s cmake --build build/libbladerf-tests --target bladerf-adapter-tests -j 1
python=${LAB_PYTHON:-.venv/bin/python}
"$python" -m controller.libbladerf_tests
