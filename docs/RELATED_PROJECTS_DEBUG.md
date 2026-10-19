# 관련 프로젝트 비교와 radio driver 디버깅

조사·검증일: 2026-10-19 KST. 기준 소스는 `ee819147e5b6f0aff57c38e06cd7c8dc7bd73627`다. OCUDU, srsRAN4G, libbladeRF dependency pin은 변경하지 않았다. 비교 소스는 API 계약을 조사하는 데 사용했으며 새 runtime dependency나 복사한 외부 driver 코드는 없다.

## 조사 대상과 적용 판단

| 프로젝트 / 고정 revision 또는 issue | 확인한 구현 | 이번 적용 / 한계 |
|---|---|---|
| [srsRAN4G native bladeRF driver](https://github.com/srsran/srsRAN_4G/blob/6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16/lib/src/phy/rf/rf_blade_imp.c) | `rf_blade_open`의 MGC 설정·gain range 조회, `rf_blade_recv_with_time`의 SC16_Q11 metadata 처리 | MGC/범위 확인을 OCUDU adapter에도 적용. RX 함수는 overrun 시에도 요청 `nsamples`를 변환·반환하므로 그대로 이식하지 않았다. 우리 경로는 짧은 `actual_count`를 거부한다. |
| [SoapyBladeRF Streaming](https://github.com/pothosware/SoapyBladeRF/blob/d0279d584daef1a90daee3703216627de7de1bae/bladeRF_Streaming.cpp), [Settings](https://github.com/pothosware/SoapyBladeRF/blob/d0279d584daef1a90daee3703216627de7de1bae/bladeRF_Settings.cpp) | `readStream`의 actual_count/overflow, `writeStream`의 metadata flag, `setGainMode`의 설정·readback | 오류/event를 최종 판정에도 반영. Soapy abstraction 추가 없이 libbladeRF 직접 adapter 유지. 이 코드만으로 OCUDU timing 호환성이 증명되지는 않는다. |
| [gr-osmosdr bladeRF sink](https://github.com/osmocom/gr-osmosdr/blob/2f230c42d2e7471769041430973776250b8f6d1d/lib/bladerf/bladerf_sink_c.cc), [source](https://github.com/osmocom/gr-osmosdr/blob/2f230c42d2e7471769041430973776250b8f6d1d/lib/bladerf/bladerf_source_c.cc) | GNU Radio tag와 timed burst, sample 변환 | tag 기반 burst와 OCUDU continuous callback은 계약이 다르다. buffer마다 BURST_END를 추가하지 않는다. |
| [srsRAN Project discussion #222](https://github.com/srsran/srsRAN_Project/discussions/222) | SoapyBladeRF/SoapyUHD로 단말 연결했다는 **xA9** 사용자 보고 및 xA4 후속 논의 | x40 검증 근거로 사용하지 않는다. timeout 0 및 destructor reset workaround는 현재의 제한 시간·명시적 장치 상태 정책에 채택하지 않는다. |
| [Nuand issue #855](https://github.com/Nuand/bladeRF/issues/855), [수정 commit 891b404](https://github.com/Nuand/bladeRF/commit/891b404) | 과거 metadata/MIMO timestamp 불연속, 2023-06-27 completed 종료 | x40 SISO 및 현재 FPGA 실물 검증과 구분한다. 옛 FPGA downgrade 제안을 자동 적용하지 않는다. |
| [OCUDU #540](https://gitlab.com/ocudu/ocudu/-/work_items/540), [MR !1074](https://gitlab.com/ocudu/ocudu/-/merge_requests/1074) | DU/F1AP Write-Replace Warning 구현, #540 Done 상태 | 새 scheduler 대신 기존 CMAS test 설정을 계속 사용한다. 이번 ZMQ 검사는 static SI 경로이며 NGAP/F1AP WRW 전체 시험은 아니다. |

Nuand 최신 source도 `35174c30b009cdb335800c411f3c14d45283f12b`의 [sync.c](https://github.com/Nuand/bladeRF/blob/35174c30b009cdb335800c411f3c14d45283f12b/host/libraries/libbladeRF/src/streaming/sync.c)까지 열람했다. 실행용 library는 검증한 2.6.0 (`09c82087786702d2812f3f0fc909beccf3277233`)을 유지한다. 내려받아 비교한 파일의 SHA256은 [reference manifest](evidence/2026-10-19/debug-research/references.json)에 보존했다.

## 재현한 결함과 수정

### 1. gain clamp와 RX AGC 상태 누락

기존 hardware template는 ZMQ의 `tx_gain: 0`을 그대로 가져왔다. [고정 libbladeRF header](https://github.com/Nuand/bladeRF/blob/09c82087786702d2812f3f0fc909beccf3277233/host/libraries/libbladeRF/include/libbladeRF.h)의 `bladerf_set_gain` 계약은 범위 밖 값을 clamp한다. [bladerf1 구현](https://github.com/Nuand/bladeRF/blob/09c82087786702d2812f3f0fc909beccf3277233/host/libraries/libbladeRF/src/board/bladerf1/bladerf1.c)의 system gain 범위는 TX 17..73, RX -1..60 dB다. 따라서 반환값 0만 검사하면 요청과 실제 설정의 불일치를 놓친다. RX AGC도 명시적으로 해제·확인하지 않았다.

`usb.cpp`에서 장치 range 및 정수/step을 검사하고 RX MGC 설정·readback, gain 설정·readback을 요구한다. 실패하면 device를 닫고 module을 활성화하지 않는다. `Settings`와 hardware template만 TX 기본값 17로 변경했다. 실제 RF power 교정값으로 해석하지 않는다.

`tests/radio/usb_test.cpp`는 실제 libbladeRF를 링크하고 장치 C API를 `--wrap`으로 대체한다. 무효 TX gain, gain readback 불일치, AGC 유지, MGC API 실패를 주입했다. 수정 전 새 검사 5개가 실패하고 수정 후 모두 통과했다. range 값은 pinned x40 source에서 가져왔으며 실물 응답을 측정한 값이 아니다.

### 2. sample 처리 후 stream 오류가 발생해도 PASS

기존 `controller/radio_smoke.py`는 gNB exit 0, TX/RX sample > 0, watchdog 오류 부재만 확인했다. stream 중간의 `E_USB`, `E_RX_CONTINUITY`, `E_BUFFER` 및 late/overflow/underflow를 최종 판정에 반영하지 않았다.

`plugin.cpp`가 fatal 오류와 각 event 누적값을 `LAB_RADIO_STOP`에 남긴다. controller는 단일 정상 형식의 summary, 양방향 sample, 모든 오류/event 0, 중간 plugin 오류 부재를 요구한다. 구버전 summary나 중복 summary도 PASS로 해석하지 않는다. 새 Python 회귀 검사 15개 중 수정 전 11개가 실패했으며 수정 후 모두 통과했다. C++ 테스트도 정상 sample 처리 후 잘못된 TX/RX buffer를 전달하여 중단·오류 집계를 검증한다.

### 3. CI 원본 로그 유실

기존 PWS workflow의 `docker run --rm`은 console JSON만 보존하여 컨테이너 내부 gNB/srsUE 로그를 잃었다. named container 생성·실행·exit code 확인 후 `if: always()`에서 raw log를 복사하고 해당 container만 정리하도록 바꿨다. PWS 수신 실패 때도 build가 성공했다면 독립 plugin smoke를 실행한다.

## 실행 결과와 범위

환경: macOS ARM64 host / Colima Linux aarch64, Clang 18.1.3, Python 3.12.3. 기존 고정 toolchain과 OCUDU/srsUE build를 재사용하고 수정한 plugin을 다시 빌드했다. 전체 upstream clean rebuild는 이번 검사 범위가 아니다. 실제 bladeRF, USB, 휴대폰은 연결되지 않았다.

| 검사 | 실제 결과 | 근거 |
|---|---|---|
| 수정 전 gain 회귀 | 예상한 **5 FAIL / 8 PASS** | `usb-before.log` |
| 수정 전 smoke 판정 회귀 | 예상한 **11 FAIL / 4 PASS** | `smoke-before.log` |
| 수정 후 Python 전체 | **151 PASS** | `python-all.xml` |
| RF OFF plugin / USB C API contract | **9 PASS / 13 PASS** | `plugin.xml`, `usb.xml` |
| RF ON 별도 build 및 CTest | **PASS** | `ctest-rf.log`; 8 plugin + 13 USB 검사, 실제 USB API는 대체 |
| 실제 gNB → 수정 plugin mock | **PASS** | `radio.json`, `radio-gnb.log`; 오류/event 모두 0 |
| 기존 ZMQ MIB/SIB1/RRC | **PASS** | `baseline.json` |
| 영어 ID 4380 / 한글 ID 4372 / 615자 15 segments | **PASS** | `english.json`, `korean.json`, `boundary.json`, raw srsUE log |
| ZMQ / radio-plugin Docker image build | **PASS** | `docker-zmq-build.log`, `docker-radio-build.log`, `images.json` |
| source mount 없는 두 packaged runtime / 원본 로그 복사 | **PASS** | `docker-results.json`, `docker-korean.json`, `docker-radio.json`; network none, USB 없음, exit 0 |
| 실제 x40 streaming / 국내 폰 UI | **NOT VERIFIED** | 장비 없음 |

위 근거 파일은 [evidence 디렉터리](evidence/2026-10-19/debug-research/)에 저장하며 `SHA256SUMS`로 확인한다. 수정 전 FAIL은 결함 재현 기록이며 현재 테스트 성공으로 덮어쓰지 않았다. 첫 gNB plugin 실행은 libusb가 없는 ZMQ runtime을 잘못 선택하여 `E_GNB_EXIT`로 실패했다. 이를 `wrong-runtime.json`/`wrong-runtime-gnb.log`로 남기고 libusb가 포함된 radio-plugin runtime에서 다시 검증했다.

기준 commit `ee819147`의 GitHub [software run 39243204520](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39243204520)은 성공했다. 이번 수정의 로컬 결과와 이전 commit의 CI 결과를 구분한다. 새 push의 Actions는 원격에서 별도로 실행하며 진행 중인 build를 PASS로 표기하지 않는다.

## 재실행 명령과 제한

프로젝트를 `/lab`에 mount한 Linux `pws-lab-zmq-toolchain:0.1.0`에서:

```bash
bash scripts/build-radio-plugin.sh
bash scripts/test-radio-plugin.sh
bash scripts/build-radio-plugin.sh --enable-rf
LD_LIBRARY_PATH=/lab/build/deps/lib ctest --test-dir build/radio-plugin-rf --output-on-failure --timeout 20
build/venv/bin/python -m pytest -q
build/venv/bin/ruff check controller tests scripts
build/venv/bin/ruff format --check controller tests scripts
python3 scripts/stage-runtime.py radio-plugin
```

host에서 이미지와 실제 mock gNB 검사:

```bash
docker build --build-context lab_build=build/runtime/radio-plugin \
  -f docker/Dockerfile.radio-plugin -t pws-lab-radio-plugin:0.1.0 .
docker run --rm --network none --cap-drop ALL --memory 2g --cpus 2 \
  pws-lab-radio-plugin:0.1.0
```

ZMQ runtime에 프로젝트를 `/lab`으로 mount하고 `LAB_PYTHON=python bash scripts/test-pws-integration.sh`를 실행한다. source mount 없는 packaged 이미지 시험은 [PWS 가이드](PWS_INTEGRATION.md)를 따른다. plugin build 각 300초, C++ executable 각 25초, gNB smoke 시작 20초/유지 2초/종료 10초, 수신 suite 전체 360초다. Docker는 network none이고 USB를 전달하지 않는다. Python formatting은 Ruff 0.11.13, C++ formatting은 clang-format 18.1.8 및 pinned OCUDU `.clang-format`을 사용했다.

## 남은 검증

현재 counter는 software가 관찰한 event 수다. libbladeRF가 보고하지 않는 TX underrun, module disable 실패, 강제 종료 이후 실제 장치 상태를 검증하는 수단이 아니다. 실물 timestamp domain 정렬, USB throughput, gain readback, RF 출력, 장시간 clock drift 및 국내 휴대폰 표시는 장비 시험이 필요하다. 기본 RF OFF와 명시적 실물 opt-in을 유지하며 mock 성공을 실제 단말 수신 성공으로 기록하지 않는다.
