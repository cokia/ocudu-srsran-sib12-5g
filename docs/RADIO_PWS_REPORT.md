# Radio plugin / PWS 연결 구현·검증 보고서

검증일: 2026-10-19 KST. 환경: macOS ARM64 host의 Colima Docker, Linux aarch64, Clang 18.1.3. 실물 bladeRF/휴대폰은 연결되지 않았다. 이번 추가 요청에 따라 기존 offline 경계를 확장하여 **PWS → 실제 OCUDU SI scheduler**, **OCUDU → bladeRF radio plugin**을 구현했다. 기본 build/Docker는 RF OFF이며 실물 RF 코드는 별도 opt-in build다.

## 구현된 경로

1. `controller/pws_integration.py`: 공유 YAML 검증, 월간시험 ID 4380 / 한국 안전안내 시험 ID 4372 선택, 실제 upstream `cmas.test` 설정 생성, ZMQ 실행·종료, SIB8 재조립, payload와 한글 원문 비교.
2. `hardware/bladerf-x40/radio_plugin/`: dynamic factory/session, ci16↔SC16_Q11, metadata timed TX/RX, buffer/late/continuity 오류, watchdog, mock 및 실제 libbladeRF transport.
3. srsUE patch 5개: opt-in SI monitor, SIB8 ASN.1 로그, other-SI DCI 분류, Type0A time allocation, DMRS 기준점. 별도 FFTW patch는 유지.
4. 기존 generic x86-64 빌드 실패를 해결하는 OCUDU empty CPU feature patch. radio/PWS payload를 수정한 OCUDU patch는 없다.
5. 독립 build/test scripts, RF OFF Docker image/Compose, GitHub Actions, 한국어 가이드와 원본 수신 로그.

파일 목록은 [FILE_INVENTORY](FILE_INVENTORY.md), 세부 interface는 [RADIO_PLUGIN](RADIO_PLUGIN.md), 설정·수신 절차는 [PWS_INTEGRATION](PWS_INTEGRATION.md), upstream 변경은 [PATCHES](PATCHES.md)를 참조한다. 기존 offline codec는 RMT 고정 동작과 CR golden profile을 유지한다. 새 수신 경로만 OCUDU의 zero-padding profile을 명시적으로 사용한다.

## 고정 버전

| 구성요소 | revision |
|---|---|
| OCUDU release_26_10 | `e0db566aac6e6376ddd60e83c84f58698fcc4d70` + lock의 2 patches |
| srsRAN4G release_25_10 | `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16` + FFTW 및 SI 관련 5 patches |
| libbladeRF 2.6.0 | `09c82087786702d2812f3f0fc909beccf3277233` + x40-only patch |
| Ubuntu | 24.04, snapshot `20261001T000000Z`, image digest는 lock 참조 |
| FW/FPGA 정책 | 2.6.0 / hostedx40 0.16.0; 실제 장치 버전은 미확인 |

## 실제 실행 결과

| 검사 | 결과 | 근거 / 범위 |
|---|---|---|
| Python 전체 regression | **136 PASS** | 기존 codec/mock 및 새 profile/segment/padding 검사; [JUnit](evidence/2026-10-19/pws-radio/python-tests.xml) |
| plugin 기본 RF OFF C++ | **7 PASS** | dynamic symbol, config, sample/timestamp, empty/partial, late, watchdog, hardware block |
| timed USB C API contract | **8 PASS** | RF 코드를 실제 libbladeRF에 링크, USB 함수만 wrap; 장치 open 없음 |
| RF ON 별도 build/CTest | **PASS** | 6 plugin + 8 USB contract assertions/tests; 실물 실행은 하지 않음 |
| 실제 gNB → plugin mock | **PASS** | TX/RX samples > 0, exit 0; [raw log](evidence/2026-10-19/pws-radio/radio-gnb.log), [JSON](evidence/2026-10-19/pws-radio/radio.json) |
| 기존 ZMQ MIB/SIB1/RRC | **PASS** | SI monitor 비활성 상태, UE 연결·release, gNB UE removal, 두 rc 0 |
| 영어 SIB8 ID 4380 | **PASS** | 실제 PHY 수신 후 원문 일치, 1 segment |
| 한글 SIB8 ID 4372 | **PASS** | 실제 PHY 수신 후 원문 일치, 1 segment |
| 최대 615자 SIB8 ID 4372 | **PASS** | 15 segments, 원문·CB Data 일치, 두 rc 0 |
| ZMQ image build/runtime | **PASS** | 업데이트된 srsUE patch 및 gNB로 빌드·실행 |
| radio plugin image build/runtime | **PASS** | RF OFF, UID 10001, network none, USB 없음 |
| Compose pws-zmq / radio-mock | **PASS** | read-only root, cap_drop ALL, named volumes, 정상 종료 |
| generic empty CPU list | **PASS (compile probe)** | 원본 compile 오류 재현, 수정 후 성공; GitHub x86 전체 결과와 구분 |
| 실물 x40 timestamp/USB/RF | **NOT VERIFIED** | 장비 없음 |
| 국내 폰 안전안내 표시 | **NOT VERIFIED** | 모델/OS/지역 정책 및 실제 RF 환경 미확인 |
| NGAP WRW / F1AP warning end-to-end | **NOT VERIFIED** | 이번 경로는 upstream static CMAS test 사용 |

RF ON CTest의 숫자는 RF OFF와 별개의 추가 기능 수가 아니라 같은 contract를 다른 build에서 실행한 결과다. mock sample 수는 timing에 따라 달라지며 실제 전파나 UE decode 증거가 아니다. SIB8의 실제 수신 증거는 ZMQ 시험에서 확보했다.

한글 수신 원문:

```text
[시험 데이터] PWS 프로토콜 검증 메시지입니다.
```

srsUE 원본 로그의 수신 metadata:

```text
LAB_SIB8 id=4372 serial=0 segment=0 last=1 dcs=48 payload=01005bc2dcd5d8...
```

위 payload는 가독성을 위해 줄였다. [전체 원본 UE 로그](evidence/2026-10-19/pws-radio/korean-srsue.log), [gNB 로그](evidence/2026-10-19/pws-radio/korean-gnb.log), [원문·전체 payload JSON](evidence/2026-10-19/pws-radio/korean.json)에 생략 없는 값을 보존했다. `SHA256SUMS`로 저장 증거를 확인할 수 있다.

## 성공한 build/test 명령

Linux toolchain container 안에서:

```bash
bash scripts/build-zmq.sh ue
bash scripts/build-zmq.sh gnb
bash scripts/build-radio-plugin.sh
bash scripts/test-radio-plugin.sh
bash scripts/build-radio-plugin.sh --enable-rf
ctest --test-dir build/radio-plugin-rf --output-on-failure --timeout 20
build/venv/bin/python -m pytest -q --junitxml=artifacts/pws-integration/python-tests.xml
```

고정 build 산출물을 `scripts/stage-runtime.py zmq`/`radio-plugin`으로 준비한 뒤 `Dockerfile.zmq`, `Dockerfile.radio-plugin`을 실제 빌드했다. ZMQ runtime에 저장소를 mount한 `network none` 환경에서 `LAB_PYTHON=python bash scripts/test-pws-integration.sh`를 실행했다. Compose 두 profile도 별도로 실행했다. 전체 clean rebuild를 매번 반복한 것은 아니며 이미 검증한 고정 dependencies와 incremental source build를 사용했다.

## 발견·수정한 실패와 남은 한계

- 최초 SIB8 수신은 timeout/CRC 실패였다. DCI의 other-SI 분류, 미구현 Type0A time allocation, SIB1 전용 DMRS 기준점 적용 오류를 수정했다.
- 실제 payload 수신 뒤 padding 비교가 실패했다. 원문 오류가 아니라 upstream zero padding과 offline CR profile 차이였으며 profile을 분리하고 잘못된 padding 거부 검사를 유지했다.
- 실제 gNB의 첫 plugin load는 optimal buffer size 0 때문에 abort했다. libbladeRF buffer에 맞춰 4096으로 고치고 실제 gNB 시작·stream·종료를 재검증했다.
- formatter가 libbladeRF header 순서를 바꿔 compile 실패가 났다. `bladeRF1.h`보다 `libbladeRF.h`를 먼저 include하도록 별도 group으로 고정한 뒤 두 build를 재검증했다.
- 첫 영어 수신 fixture는 요구하는 시험 label이 없어 거부됐다. 전용 `[TEST]` fixture를 생성해 재실행했다. invalid label 거부는 단위 테스트로 유지한다.
- 새 runtime의 중복 apt 설치가 snapshot HTTP 503으로 실패했다. 동일 고정 snapshot에서 이미 생성한 ZMQ runtime과 toolchain의 libusb/copyright를 사용하는 multi-stage packaging으로 수정했다. 다른 snapshot이나 무고정 package로 교체하지 않았다.
- 기존 GitHub software run `39238016199`는 성공, build run `39238015007`의 non-sdr job은 empty CPU feature list로 실패했다. 수정 patch를 추가했다. 새 push의 CI 완료 여부는 해당 run에서 확인하며 이 표의 로컬 PASS로 대신하지 않는다.
- srsUE 로그에 LTE PRACH compatibility 경고가 남는다. 이번 SI monitor는 NR downlink SIB8 수신을 검사하며 NR random access 성공을 요구하지 않는다. 기본 연결 모드 회귀는 별도로 PASS했다.
- 실물 x40의 RX/TX timestamp 정렬, USB throughput, underrun 관측·복구, RF frequency/power, 장시간 clock drift, disconnect 이후 실제 module 상태는 남은 검증 항목이다. 현재 코드는 RF-ready 인증 결과가 아니다.
- generated PLMN은 시험용 00101이다. ID 4372만으로 국내 폰에서 안전안내 UI가 뜬다고 보장하지 않는다. 실제 폰의 NR SA/camping 및 지역/통신사 정책 확인이 필요하다.
- 초기 Dummy RU에서 관찰된 간헐적 abort/late-slot 한계는 이번 radio 작업으로 해결했다고 주장하지 않는다.

기본 비방사 모드는 계속 사용할 수 있다. 다음 실물 단계는 x40 연결 후 version/USB 및 RX timing 검사, 검증된 격리 환경의 bounded RF timing/단말 수신 시험이다. 이번 작업에서는 RF 송신이나 휴대폰 연결을 실행하지 않았다.
