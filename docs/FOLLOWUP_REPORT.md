# libbladeRF 및 ZMQ/srsUE 추가 구현 보고서

검증일: **2026-10-19 KST**. 최초 결과는 [기존 구현 보고서](IMPLEMENTATION_REPORT.md)에 보존한다. 이 문서는 추가 구현 당시 기록이며, 이후 커밋 준비 중 실행한 **118개 PASS**, 최신 수신 로그와 한글 검증은 [수신 캡처](SRSUE_RX_CAPTURE.md)에 보존한다.

장비 없이 실행하는 실제 libbladeRF 검사와 별도 Docker ZMQ/srsUE 수신 환경을 추가했다. PWS 입력은 계속 offline engine에서만 처리하며 gNB, ZMQ IQ, hardware stream과 연결하지 않는다.

## 고정 버전과 변경 범위

| 항목 | revision |
|---|---|
| OCUDU | `release_26_10`, `e0db566aac6e6376ddd60e83c84f58698fcc4d70` |
| libbladeRF | `libbladeRF_v2.6.0`, `09c82087786702d2812f3f0fc909beccf3277233`, 기존 x40 patch |
| srsRAN 4G / srsUE | `release_25_10`, `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16` |
| Ubuntu / apt snapshot | 24.04 / `20261001T000000Z` |
| 실제 실행 환경 | macOS ARM64 host, Colima Linux aarch64, Clang 18.1.3 |

전체 pin과 OCUDU/srsUE patch hash는 [dependency lock](../dependencies.lock.json)에 있다. ZMQ build package 목록은 [ARM64 package manifest](dependencies.zmq-arm64.tsv), binary SHA256은 `build/runtime/zmq/manifest.json`에 기록한다. srsRAN 4G AGPL-3.0과 COPYRIGHT 원문을 `licenses/`에 추가했다. 최초 구현 후 실제 ZMQ 시험에서 발견한 문제를 각각 하나의 source file에 적용한 [최소 patch](PATCHES.md)로 관리한다.

| 파일 | 추가·수정 내용 |
|---|---|
| `tests/libbladerf/`, `controller/libbladerf_tests.py`, `scripts/test-libbladerf.sh`, `CMakeLists.txt` | 실제 libbladeRF 원본 test 5개와 실제 adapter의 C API contract 검사 |
| `hardware/bladerf-x40/driver_adapter/real_device.cpp` | 대문자 hex serial 정규화, 잘못된 serial의 조기 거부 |
| `controller/zmq_rx.py`, `tests/non-sdr/test_zmq_reception.py` | 실제 수신 증거·격리·제한·종료·오류 판정 |
| `configs/gnb.zmq.yaml`, `configs/srsue.zmq.conf` | 고정 20 MHz FDD n3, 15 kHz SCS, loopback socket profile |
| `scripts/*zmq*.sh`, `docker/*zmq*` | 독립 build, runtime image, Compose, 제한된 실행 |
| `scripts/fetch-upstream.py`, `scripts/stage-runtime.py`, `scripts/package-source.sh` | srsRAN pin, runtime manifest, 대응 source 포함 |
| `.github/workflows/test.yml`, `.github/workflows/zmq.yml` | 실제 library 검사 및 hosted runner ZMQ 수신 job |
| `README.md`, `docs/`, `THIRD_PARTY_NOTICES.md`, `licenses/` | 한국어 절차·범위·결과·라이선스 고지 |

## 실제 libbladeRF 검사 결과

| 검사 | 결과 | 증거 |
|---|---|---|
| 실제 libbladeRF 및 production diagnostic build | PASS | `artifacts/libbladerf-final-build-test.log` |
| upstream C/C++/version/parser/interleaver | **5개 executable PASS** | `artifacts/libbladerf/upstream-*.json` |
| 실제 adapter C API contract | **22개 PASS** | `artifacts/libbladerf/adapter.xml` |
| Python 전체 회귀 검사 | **117개 PASS** | `artifacts/followup-python.xml` |
| SDR Docker image 재빌드 | PASS | `artifacts/sdr-followup-docker.log`, checkpoint log |
| 새 SDR image mock loopback | PASS, 65,536 samples | `artifacts/libbladerf/sdr-docker-mock.log` |
| 실제 library 로드 및 version 조회 | PASS, 2.6.0 | `artifacts/libbladerf/no-device/info.json` |
| 실제 hardware discovery | BLOCKED, driver -7 | 같은 JSON: `mock=false`, `hardware_verified=false` |
| 실제 FW/FPGA/USB stream/내부 loopback | NOT VERIFIED | 실제 장비 미연결 |

upstream executable 5개, GTest case 22개, Python case 117개는 서로 다른 계층이므로 한 종류의 test count로 합산하지 않는다. adapter contract는 실제 `RealDevice`를 검사하지만 장치 API 경계는 test double로 대체한다. 하드웨어 기능 검증으로 표기하지 않는다.

대문자 serial regression은 수정 전 실패를 실제로 재현했다(`artifacts/libbladerf/uppercase-before-fix.log`). libbladeRF device-string parser와 동일하게 소문자로 정규화한 뒤 선택하도록 수정해 최종 검사를 통과했다.

실행한 명령:

```bash
docker run --rm --memory 1g --cpus 1 -e LAB_BUILD_JOBS=1 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash scripts/build-sdr.sh
docker run --rm --network none --memory 1g --cpus 1 \
  -e LAB_PYTHON=python3 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash scripts/test-libbladerf.sh
bash scripts/build-docker.sh sdr-bladerf-x40
docker run --rm --network none --cap-drop ALL \
  pws-lab-sdr-bladerf-x40:0.1.0 loopback --mock
```

## ZMQ 수신 검증

| 검사 | 결과 | 증거 |
|---|---|---|
| OCUDU ZMQ 전체 build 및 worker patch build | PASS | `artifacts/zmq/gnb-build.log`, `gnb-pool-fix-build.log` |
| srsUE 전체 build 및 FFTW patch build | PASS | `artifacts/zmq/ue-build.log`, `ue-fftw-fix-build.log` |
| 개발 container 실제 MIB/SIB1 수신 | **PASS** | `artifacts/zmq/rx-complete/zmq-rx.json` |
| RRC 연결 / 자동 release / UE context 제거 | **PASS** | 같은 JSON 및 UE/gNB log |
| 개발 container 두 process 정상 종료 | **PASS**, `[0, 0]` | 같은 JSON |
| 별도 ZMQ runtime image build | **PASS** | `artifacts/checkpoints/docker-zmq.json/.log` |
| read-only Compose 실제 수신 및 정상 종료 | **PASS**, `[0, 0]` | `artifacts/zmq/compose/zmq/zmq-rx.json` |
| NAS registration / IP ping / throughput | **NOT VERIFIED** | 실제 5GC를 구성하지 않음 |
| srsUE NR SIB8/PWS 수신 | **UNSUPPORTED** | 고정 upstream NR 처리 경로에 없음 |

최종 Compose는 UID 10001, read-only root/config, `network none`, `cap_drop: ALL`, 메모리 3 GiB, CPU 4 조건이었다. USB나 TUN device를 전달하지 않았다. `artifacts/zmq/compose-container.json`에 적용 조건과 container exit code 0을 보존했다. 로그 수집 후 이 Compose project의 container만 제거했으며 named output volume은 보존했다.

실행한 최종 명령:

```bash
bash scripts/build-zmq-docker.sh
docker compose -f docker/compose.zmq.yaml up --abort-on-container-exit --exit-code-from reception
mkdir -p artifacts/zmq/compose
docker compose -f docker/compose.zmq.yaml cp reception:/lab/output/zmq artifacts/zmq/compose/
docker compose -f docker/compose.zmq.yaml down --timeout 25
```

최초 source build와 Docker assembly는 구분한다. 최종 image assembly는 이미 검증한 compiler cache를 재사용했고 초기 checkpoint는 약 9.8초였다. 이것을 clean 전체 source build 시간으로 보고하지 않는다.

### 발견한 실패와 수정

1. **단일 worker 교착**: 처음 60초 실행과 thread 조사에서 DU 시작이 멈췄다. source의 synchronous executor와 worker 수 자동 제한을 확인하여 작은 patch와 `nof_threads: 2`로 해결했다. `rx/`, `rx-investigate/`에 실패 기록을 보존했다.
2. **srsUE FFTW 계획 지연**: gNB 수정 후에도 120초 안에 UE 초기화가 끝나지 않았다. 실제 API instrumentation에서 첫 1,536-point plan이 약 26.6초 걸렸다. `FFTW_ESTIMATE` patch 후 초기화와 실제 수신이 진행됐다. trace 도구는 최종 이미지에 포함하지 않는다.
3. **수신 판정의 ARFCN 가정**: 최초 수신 로그에는 실제 MIB/SIB1과 RRC 연결이 있었지만 UE callback이 `ssb_arfcn`을 채우지 않아 `ARFCN=0`을 기록했다. source를 확인하고 PCI/SCS/CORESET0/SS0와 MIB 적용 완료를 함께 검사하도록 판정을 수정했다. `rx-final/`의 기존 FAIL 결과는 바꾸지 않았다.
4. **no-core 종료 순서**: active UE가 있는 상태에서 gNB를 종료하면 stub가 NG Reset 응답을 제공하지 않아 강제 종료됐다. UE부터 먼저 종료해도 active context가 남으면 gNB가 실패했다(`rx-verified/`). 정상 자동 RRC release와 UE context 제거를 관찰한 뒤 UE, gNB 순으로 종료하여 두 process의 rc=0을 확인했다.

단독 srsUE config preflight는 peer 없이 timeout으로 종료했으며 수신 PASS로 세지 않는다. 위 실패를 최종 성공 결과로 덮어쓰지 않았다.

### 기존 Dummy RU의 추가 회귀 관찰

공통 worker patch 적용 후 기존 Non-SDR image를 다시 빌드했다(`artifacts/zmq/dummy-regression-build.log`). 추가 5초 smoke는 처음 **FAIL, rc=-6**, 다음 실행은 **PASS**였다. 첫 실행의 report는 `dummy-regression-runtime.log`에 있으나 `--rm` 실행으로 내부 gNB 상세 log가 보존되지 않아 abort 원인은 확정하지 못했다. 다음 실행의 상세 log와 JSON은 `artifacts/zmq/dummy-regression/non-sdr/`에 보존했다.

두 번째 실행에는 FAPI late-slot 및 task queue 경고가 있었다. 따라서 이 Colima 환경의 기존 Dummy RU를 안정성/실시간성까지 검증했다고 주장하지 않는다. 원인 규명은 남은 작업이며, 재현할 때는 named container 또는 bind output으로 crash log를 먼저 보존해야 한다. 이 관찰은 ZMQ 경로의 MIB/SIB1 및 정상 종료 PASS와 별도로 보고한다.

전체 파일 목록은 [파일 목록](FILE_INVENTORY.md), 기계 판독 결과는 [추가 verification JSON](verification-followup-2026-10-19.json)에 있다.

## 실행 한도와 미검증 범위

실제 library 검사는 upstream build 300초, adapter build 180초, executable별 20초다. ZMQ는 Docker build 2,700초, gNB build 2,700초, UE build 1,800초, 수신 기본 60초/최대 120초, process별 종료 10초로 제한한다. C9/C10 체크포인트는 [실행 제한](EXECUTION_LIMITS.md)을 따른다.

- x40 firmware/FPGA/USB/timestamp/실제 loopback은 장비 연결 후 검증해야 한다.
- ZMQ 수신은 MIB/SIB1 범위다. srsUE NR의 SIB8/PWS 수신은 지원하지 않으며 해당 기능을 추가하지 않았다.
- `no_core` stub는 AMF 인증이나 PDU session을 제공하지 않는다. NAS registration과 IP connectivity는 NOT VERIFIED다.
- 이 보고서를 기록한 시점에는 x86_64 원격 GitHub Actions, GitHub push 및 공개 registry publish를 수행하지 않았다. 로컬 PASS를 원격 CI PASS로 표시하지 않는다.
- 본 검증에서는 실물 SDR, 실제 가입자, 외부 operator core, warning-to-RF 경로를 사용하지 않는다.

재현 절차: [libbladeRF 검사](LIBBLADERF_TESTING.md), [ZMQ 수신](ZMQ_SRSUE.md).
