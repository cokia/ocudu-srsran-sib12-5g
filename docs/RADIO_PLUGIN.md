# OCUDU bladeRF x40 radio plugin

2026-10-19 추가 구현. `radio_factory`/`radio_session`을 실제로 구현한 동적 library이며, standalone 진단 앱과 별도 target이다. 고정 OCUDU commit은 `e0db566aac6e6376ddd60e83c84f58698fcc4d70`다. **gNB 로딩·mock streaming과 libbladeRF API contract는 검증했으나 실물 RF timing/휴대폰 수신은 NOT VERIFIED**다.

## 인터페이스와 구현

| 파일 | 역할 |
|---|---|
| `hardware/bladerf-x40/radio_plugin/plugin.cpp` | factory, config validator, session, management plane, baseband TX/RX, event, watchdog |
| `stream.h`, `stream.cpp` | typed transport, mock, ci16 ↔ SC16_Q11 변환 |
| `usb.cpp` | 실제 libbladeRF synchronous metadata TX/RX, init/stop/cleanup |
| `tests/radio/plugin_test.cpp` | OCUDU 인터페이스와 dynamic symbol 검사 |
| `tests/radio/usb_test.cpp` | RF 코드 활성화 상태에서 실제 library 링크 + USB C API test double |
| `controller/radio_smoke.py` | 실제 gNB에서 plugin 로드, sample 처리, 정상 종료 확인 |

loader는 `libocudu_radio_bladerf_x40.so`와 `ocudu::create_dynamic_radio_factory()`를 찾는다. OCUDU radio source는 수정하지 않았다. `ru_sdr.device_driver: bladerf_x40`는 upstream 내장 이름이 아니라 이 프로젝트가 구현한 외부 plugin 이름이다. standalone `Device` 진단 구현의 firmware loopback 제약은 변경하지 않았다.

**고정 OCUDU gateway sample은 `ci16_t`다.** 기존 조사 문서의 CF32 gateway 설명을 정정했다. `ocuduvec/conversion.h`의 full scale 32767을 기준으로 Q11 [-2048, 2047]에 반올림·포화 변환하고 RX는 역변환한다. ZMQ wire의 CF32와 gateway 내부 형식을 혼동하지 않는다.

## 제한된 지원 범위

- x40(`bladerf1`, 40KLE), USB SuperSpeed, libbladeRF/FW 2.6.0 및 FPGA 0.16.0 단일 조합.
- 1 TX + 1 RX, integer sample rate 80 kS/s..40 MS/s, internal/default clock, SC16/default OTW, continuous stream. 실제 gNB smoke profile은 n3 FDD, 20 MHz, 23.04 MS/s다.
- `SC16_Q11_META`, 16 buffers, 4096 samples/buffer, 8 transfers, USB timeout 250 ms. gNB optimal buffer는 4096 samples, 한 callback 최대 65,536 samples.
- TX는 최초 `TX_BURST_START`, 이후 `TX_UPDATE_TIMESTAMP`; 매 callback의 `TX_BURST_END`로 생기는 flush gap을 피한다. RX는 `RX_NOW` 없이 요청 timestamp를 사용한다.
- RX actual_count/역행 timestamp 오류는 stream 중단, 전진 gap은 OVERFLOW event. TX late는 LATE, 기타 library 오류는 OTHER. flags의 overflow/underrun은 event로 전달한다.
- `BLADERF_META_STATUS_UNDERRUN`은 고정 libbladeRF header에 현재 보고되지 않는 상태로 설명되어 있다. 따라서 코드의 flag mapping 검사는 실제 TX underrun 검출 보장이 아니다.
- USB 오류와 watchdog 만료 시 RX/TX disable을 시도한다. disconnect/강제 kill 이후 장치 상태를 보장하지 않는다. stop 호출 자체의 반환 오류를 상위 OCUDU stop interface로 전달하지 못하는 한계가 있다.
- runtime gain/frequency 변경, LO offset, external clock/PPS, TDD, 다중 channel/stream, 자동 reconnect/firmware flash는 지원하지 않는다. 설정상의 sample rate 범위는 USB 지속 처리 성능 보장이 아니다.

23.04 MS/s의 양방향 I/Q payload만 약 184.32 MB/s다. host copy, metadata, USB jitter는 추가된다. 실제 RX/TX timestamp domain 정렬, 시작 lead time, oscillator 오차, 장시간 underflow, 수신 감도, RF 출력은 장비로 측정해야 한다. mock은 CPU 시간을 기준으로 RX를 pace하며 RF 채널/UE를 모사하지 않는다.

## 독립 빌드와 테스트

Ubuntu toolchain, 고정 OCUDU source, `build/deps`의 libbladeRF가 필요하다. 기존 setup 이후:

```bash
bash scripts/build-sdr.sh
bash scripts/build-radio-plugin.sh
bash scripts/test-radio-plugin.sh
# network none 컨테이너 안에서 실제 gNB 로딩까지 검사
LAB_PYTHON=build/venv/bin/python bash scripts/test-radio-plugin.sh --gnb
```

기본 산출물 `build/radio-plugin/`은 `LAB_ENABLE_BLADERF_RF=OFF`다. `mode=hardware,rf=on`을 전달해도 USB open 전에 `E_RF_BUILD_DISABLED`로 실패한다. CI의 USB API 테스트는 RF 코드를 컴파일하되 장치 C API를 linker `--wrap`으로 대체한다. 실제 장치를 열지 않는다.

실물용 **컴파일만** 수행하는 별도 명령:

```bash
bash scripts/build-radio-plugin.sh --enable-rf
```

산출물은 `build/radio-plugin-rf/libocudu_radio_bladerf_x40.so`다. 이 명령은 장치를 열거나 gNB를 시작하지 않는다. 기본 library를 덮어쓰지 않는다. 실물 사용 시 해당 디렉터리를 `LD_LIBRARY_PATH`에 지정해야 한다.

## device arguments

| 항목 | 값 / 기본값 | 검증 |
|---|---|---|
| `mode` | `mock` / `hardware`, 기본 `mock` | 다른 값 거부 |
| `rf` | `off` / `on`, 기본 `off` | mock은 off, hardware는 명시적 on 필요 |
| `serial` | hardware에서 필수, 32 hex | 임의 첫 장치 선택 없음 |
| `max_seconds` | 1..60, 기본 20 | 시작 후 watchdog의 wall time 한도 |

알 수 없는 key와 중복 key를 거부한다. 주파수/gain은 upstream `ru_sdr`와 `cell_cfg`에서 받아 libbladeRF에 전달한다. 주파수는 x40 범위, gain은 유한 정수 여부를 먼저 검사하며 실제 장치 설정 실패는 library error로 중단한다. 모든 허용 gain이 실제 장치에서 유효함을 보장하지 않는다.

`controller.pws_integration prepare --backend bladerf-x40 --serial <32-hex>`는 검토용 `rf=off` YAML을 만든다. 실제 송신 연결 코드는 RF 활성 build와 명시적 `mode=hardware,rf=on` 설정에서 사용된다. 이 조합은 normal RF mode에서 TX를 활성화하며 firmware loopback이 아니다. 실물 시험은 주파수 조건, 차폐/전도 연결, 외부 누설 확인 및 단말 정보를 확인한 환경에서만 별도 실행·판정한다. 이번 작업에서는 실물 실행을 하지 않았다.

## Docker

```bash
bash scripts/build-pws-integration-docker.sh
docker compose -f docker/compose.pws.yaml --profile radio-mock run --rm radio-mock
```

이미지는 RF OFF library만 package하며 `stage-runtime.py`가 CMake cache를 검사한다. USB mount와 privileged 권한이 없다. 실물 USB 접근은 기존 [SDR 가이드](SDR_BLADERF_X40_GUIDE.md)의 Linux host 조건을 따르되, 기본 diagnostic 이미지와 이 plugin의 동작을 혼동하지 않는다. macOS VM의 USB passthrough는 검증하지 않았다.
