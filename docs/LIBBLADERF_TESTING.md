# 장비 없는 libbladeRF 검증

장비 부재는 software 개발이나 libbladeRF API 시험을 막지 않는다. 기존 `Device` mock과 별도로 **실제 libbladeRF 2.6.0 shared library**에 링크한 upstream 테스트 및 **실제 `RealDevice` 구현**의 C API 경계 검사를 제공한다.

## 실행

Ubuntu 개발 환경:

```bash
bash scripts/build-sdr.sh
bash scripts/test-libbladerf.sh
```

이미 준비한 Docker toolchain과 Linux build가 있는 경우:

```bash
docker run --rm --network none --memory 1g --cpus 1 \
  -e LAB_PYTHON=python3 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash scripts/test-libbladerf.sh
```

최초 library build에는 upstream 다운로드를 위한 네트워크가 필요하다. 위 `--network none` 명령은 library/source 준비 후 실행한다. 어떤 테스트에도 USB device mapping이 필요하지 않다.

## 검사 계층과 실제 결과

2026-10-19 Linux ARM64 실행에서 upstream executable **5개 PASS**, adapter contract **22개 PASS**를 확인했다.

| 계층 | 실제 사용하는 코드 | 검사 범위 |
|---|---|---|
| upstream `test_c`, `test_cpp` | 원본 C/C++ source + 실제 shared library | 언어별 API compile/link 및 runtime version 호출 |
| upstream `test_version` | 원본 source + 실제 shared library | 설치 header API version과 linked library version 일치 |
| upstream `test_parse` | 원본 `parse.c`, `conversions.c` | 입력 parser의 정상/경계 처리 |
| upstream `test_interleaver` | 원본 `helpers/interleave.c` | SC16_Q11/SC16_Q11_META buffer 배열과 round-trip |
| adapter contract | 실제 `real_device.cpp`, `runner.cpp` + 실제 header/library | C API argument, 오류 전달, TX 격리 순서, timeout, 짧은 수신, cleanup |

upstream interleaver에는 2-channel 메모리 배열 검사도 있다. 이것은 x40가 2RX/2TX를 지원한다는 뜻이 아니다. x40 profile은 계속 1RX/1TX만 허용한다.

adapter contract는 Linux linker의 `--wrap=bladerf_*`로 **device를 여는 API 경계만 test double로 대체**한다. version, error string, device-string parser는 실제 library 함수를 호출한다. 기존 `MockDevice`만 테스트하는 경로와 다르지만, USB firmware/FPGA 실제 동작을 검증한 것은 아니다. 결과의 `device_api_double=true`, `hardware_verified=false`를 확인한다.

## 오류·격리 검사

장치 없음, 복수 장치 선택 누락, invalid/missing serial, open permission 오류, probe 시 stream 미활성화, TX configure/enable/transmit 각각의 격리 확인, firmware loopback 미지원, LMS PA bit 0x04/0x08/0x10, 고정 stream profile, RX metadata, short read, USB timeout/disconnect, overrun, 실제 sample rate 불일치, enable 직후 격리 해제, firmware loopback에서 timestamp 시험 거부를 검사한다.

## 제한과 artifact

- upstream test build 300초, adapter build 180초, 각 executable 실행 20초.
- `artifacts/libbladerf/adapter.xml`: 22개 GTest case 결과.
- `artifacts/libbladerf/*.json`, `*.log`, `audit.jsonl`: 공통 보고서와 실제 출력.
- `tests/libbladerf/upstream/CMakeLists.txt`는 허용한 5개 upstream test만 추가한다. 전체 upstream test 목록은 RF stream/firmware 변경 시험도 포함하므로 일괄 실행하지 않는다.
- `.github/workflows/test.yml`의 `libbladerf-api` job이 동일한 장비 없는 경로를 수행한다. 원격 CI 실행 결과는 실제 push 후 확인해야 한다.

이 범위는 **PASS**로 완료할 수 있다. 물리 x40의 FPGA, USB transport, RF isolation readback은 별도 hardware acceptance 항목이다.

이 검사로 대문자 hex serial 선택 실패를 재현하고 수정했다. 실제 adapter는 libbladeRF parser와 같은 소문자 정규화를 적용하며, 잘못된 serial은 USB discovery보다 먼저 거부한다. 수정 전 실패 증거는 `artifacts/libbladerf/uppercase-before-fix.log`에 있다.
