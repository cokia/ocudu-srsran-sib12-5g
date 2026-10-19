# 최종 구현 및 검증 보고서

검증일: **2026-10-19 KST**. application version: **0.1.0**.

이 문서는 최초 구현 검증 기록이다. 이후 추가한 실제 libbladeRF software 검사와 ZMQ/srsUE 결과는 [추가 검증 보고서](FOLLOWUP_REPORT.md)를 참조한다.

공유 offline protocol engine, Dummy RU gNB 실행 환경, bladeRF x40 standalone diagnostic, 세 Docker runtime 이미지, 두 Compose profile, 테스트와 한국어 문서를 구현했다. 실제 software build와 runtime 검증을 수행했다. 실제 x40는 연결되어 있지 않아 hardware 검증은 **BLOCKED**이며 OCUDU bladeRF RU 통합은 **NOT VERIFIED / 미구현**이다.

NR CMAS의 올바른 ASN.1 type은 **SIB8**이다. NR SIB12-r16은 sidelink 구조이므로 별도의 구조 round-trip만 제공한다. PWS에서 gNB broadcast scheduler 또는 hardware stream으로 이어지는 연결은 구현하지 않았다.

## 고정 revision과 실행 환경

| 항목 | 실제 사용 값 |
|---|---|
| OCUDU | `release_26_10`, `e0db566aac6e6376ddd60e83c84f58698fcc4d70` |
| bladeRF | `libbladeRF_v2.6.0`, `09c82087786702d2812f3f0fc909beccf3277233` |
| 실제 linked library describe | `2.6.0-git-09c8208-dirty`; 문서화된 x40 전용 patch에 따른 suffix |
| 요구 hardware 조합 | libbladeRF 2.6.0 / FW 2.6.0 / FPGA 0.16.0; 실제 FW/FPGA 값은 미확인 |
| host | macOS ARM64, Darwin 24.6.0 |
| build/runtime | Colima의 Linux aarch64 6.8.0-117-generic, Ubuntu 24.04 container |
| Docker / Compose | 29.5.2 / 5.4.0 |
| compiler / CMake / Ninja | Clang 18.1.3 / 3.28.3 / 1.11.1 |
| Python / pytest | 3.12.3 / 8.3.5 |
| libusb / nlohmann-json | 1.0.27 / diagnostic 3.11.3; OCUDU codec는 vendored 3.12.0 |
| container build 제한 | OCUDU 2 CPU/4 GiB, SDR 1 CPU/1 GiB, image build 2,700초 |

전체 package 버전은 [Ubuntu manifest](dependencies.ubuntu-arm64.tsv), [Python manifest](dependencies.python-linux.txt), [dependency lock](../dependencies.lock.json), `build/runtime/<mode>/manifest.json`에 있다. 마지막 파일에는 실제 executable SHA256과 bladeRF patch SHA256도 포함된다. 최초 OCUDU 전체 build는 약 21분이 소요됐다. 뒤의 Docker assembly는 같은 source build cache를 사용한 incremental 실행이다.

## 구현한 기능과 파일

| 경로 | 구현 내용 |
|---|---|
| `controller/` | UTF-8 YAML, 중복/alias/크기 제한, JSON Schema, 불변 model, UCS-2 CB Data, offline encode/decode, JSON/audit, subprocess 제한 |
| `controller/offline_codec/` | 실제 OCUDU `encode_sib8` 및 `rrc_nr_asn1`을 링크한 C++ codec, strict segment/canonical UPER 검사, SIB12 구조 검사 |
| `controller/gnb.py` | 고정 Dummy/no-core profile, network namespace 검사, startup/health/종료 및 오류 보고 |
| `hardware/bladerf-x40/` | C++ Device abstraction, 실제 libbladeRF adapter, mock, info/capabilities/verify/rx/loopback, udev rule |
| `configs/` | PWS YAML/schema, x40 전용 YAML/schema, upstream native gNB 설정 |
| `patches/` | AD936x 및 micro 의존성을 제외하는 재현 가능한 x40 libbladeRF patch |
| `scripts/` | dependency 설치, exact revision checkout, 독립 build/run/test, runtime staging, health/cleanup, source packaging |
| `docker/` | toolchain/runtime multi-stage, Non-SDR/SDR/controller 이미지, 두 profile와 선택적 단일 USB node override |
| `tests/` | 한국어/영어/경계/오류/golden/round-trip/isolation/mock 실패 주입과 CLI 검사 |
| `.github/workflows/` | lint, unit, actual ASN.1, mock, 두 mode Docker build/runtime; hardware 없는 hosted runner 구성 |
| `docs/`, `README.md` | 한국어 설치·운영·설정·테스트·조사·제한·문제 해결 문서 |
| `licenses/`, `THIRD_PARTY_NOTICES.md`, `LICENSE` | 원본 upstream 고지, 자체 BSD-3-Clause, 동적 링크/대응 소스 배포 조건 |

작업 시작 시 Git 저장소에 기존 tracked source가 없었다. 생성 파일 전체는 [파일 목록](FILE_INVENTORY.md)에 기록했다. OCUDU와 bladeRF의 원본 checkout은 tracked 변경이 없음을 확인했다. OCUDU build plugin은 symlink로 연결하며, bladeRF 패치는 `build/bladerf-source` 사본에만 적용한다. GitHub push나 release/registry 발행은 수행하지 않았다.

## 성공한 빌드 및 실행 명령

아래 명령을 실제 실행했다. host는 Docker를 사용했으며 Linux executable을 macOS에서 직접 실행하지 않았다.

```bash
docker run --rm --memory 4g --cpus 2 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash scripts/build-non-sdr.sh
docker run --rm --memory 1g --cpus 1 -e LAB_BUILD_JOBS=1 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash scripts/build-sdr.sh
bash scripts/build-docker.sh non-sdr
bash scripts/build-docker.sh sdr-bladerf-x40
bash scripts/build-docker.sh controller
docker run --rm --network none --cap-drop ALL --memory 2g \
  pws-lab-non-sdr:0.1.0
docker run --rm --network none -v "$PWD:/lab" \
  -e LAB_PYTHON=build/venv/bin/python pws-lab-toolchain:0.1.0 \
  bash -c 'scripts/test-non-sdr.sh && scripts/test-sdr.sh'
docker compose -f docker/compose.yaml --profile non-sdr up -d
docker compose -f docker/compose.yaml --profile sdr-bladerf-x40 up -d
```

## 실제 테스트 결과

| 검사 | 결과 | 증거 |
|---|---|---|
| OCUDU gNB + C++ codec compile/link | PASS | `artifacts/non-sdr-build.log`, `build/bin/gnb`, `pws-codec` |
| libbladeRF + 실제 adapter compile/link | PASS | `artifacts/sdr-build.log`, 최종 SDR image build log |
| 최종 Non-SDR suite | **74 PASS, 0 FAIL, 0 SKIP** | `artifacts/non-sdr/junit.xml` |
| 최종 SDR hardware-independent suite | **98 PASS, 0 FAIL, 0 SKIP** | `artifacts/sdr/junit.xml` |
| 별도 libbladeRF 없는 mock build 및 suite | **78 PASS, 0 FAIL, 0 SKIP** | `artifacts/mock-independent.log`, `.xml` |
| 두 mode suite의 고유 test case | **100개** | JUnit classname/name의 합집합; 중복 검사를 더하여 172개라고 세지 않음 |
| Ruff lint/format, shell syntax | PASS | `artifacts/lint.log`; Python 24 files |
| 두 mode offline validation | PASS | `artifacts/{non-sdr,sdr}/validate-*.json` |
| SIB12 inner/container round-trip | PASS | `artifacts/non-sdr/inspect-sib12-non-sdr.json`; `cmas=false` |
| 최종 image gNB 5초 실행 | PASS | `artifacts/docker/gnb.json` |
| Compose gNB 30초 실행/health/정상 종료 | PASS | `artifacts/compose/non-sdr/gnb-smoke.json`, `health.json` |
| 실제 hardware discovery | **BLOCKED** | `artifacts/docker/hardware-unavailable.json`: `E_DISCOVERY`, driver -7 |
| 실제 FW/FPGA/USB speed/RX/loopback | **NOT VERIFIED** | 실제 장치 없음 |
| firmware loopback의 timestamp | **SKIP** | FX3 bypass는 FPGA timestamp 경로를 지나지 않음 |

모드별 suite는 공통 테스트를 포함한다. mock의 firmware/FPGA와 sample 수는 가상 값이며 `mock=true`, `hardware_verified=false`로 기록한다. 실제 library 자체는 로드됐고 version 2.6.0을 읽었다. 물리 device를 읽은 것으로 보고하지 않는다.

검증 결과의 기계 판독용 사본은 [verification JSON](verification-2026-10-19.json)에 있다. 상세 log/encoded artifact는 로컬 `artifacts/`에 보존하며 Git에는 포함하지 않는다.

## Docker 검증

| 최종 이미지 | build | 실제 실행 | 로컬 크기 |
|---|---|---|---|
| `pws-lab-controller:0.1.0` | PASS | Compose offline validation PASS | 약 247 MB |
| `pws-lab-non-sdr:0.1.0` | PASS | gNB startup/healthy/graceful shutdown PASS | 약 321 MB |
| `pws-lab-sdr-bladerf-x40:0.1.0` | PASS | mock info/RX/65,536-sample loopback 및 offline PWS PASS | 약 251 MB |

`artifacts/checkpoints/docker-*.json/.log`에 build 제한과 결과가 있다. Compose의 `gnb`, `offline`, `diagnostics`, `sdr-offline` 네 서비스 모두 exit code **0**으로 종료했다. 실제 적용한 조건은 UID 10001, read-only root/config, `network none`, `cap_drop: ALL`이다. USB 장치는 전달하지 않았다. `ldd`로 gNB/codec/diagnostic의 미해결 shared library가 없음을 확인했다.

로그와 JSON을 복사한 후 `scripts/stop.sh`로 이 프로젝트 컨테이너만 제거했고 named output volume은 보존했다. 기존 다른 프로젝트의 이미지/컨테이너/volume은 prune하지 않았다.

## 발견한 실패와 수정

1. **gNB OOM**: 최초 실행은 upstream 기본 pool의 약 2 GiB 할당으로 cgroup OOM kill, rc=-9가 발생했다. source에서 확인한 `buffer_pool.nof_segments: 16384`, `segment_size: 2048`을 적용하여 segment storage를 약 32 MiB로 줄였다. 이후 2 GiB 컨테이너에서 3초/5초/30초 실행을 통과했다. 실패 자료는 `artifacts/gnb-investigate/`, `gnb-oom-evidence.txt`에 보존했다.
2. **최소 runtime shared dependency**: 초기 `ldd` 검사에서 gNB의 `libatomic.so.1` 누락을 확인하여 runtime package에 추가했다. SDR은 libusb를 package로 설치하여 libudev/libcap와 copyright도 보존하도록 수정했다.
3. **build/test 동시 실행**: codec executable을 복사하는 순간 병렬로 테스트하여 `Text file busy` 1건이 발생했다. 해당 실행은 FAIL로 보존했다(`artifacts/mode-tests-concurrent-failure.*`). 모든 build 완료 후 순차 실행한 최종 두 suite는 통과했다. 같은 workspace의 build와 mounted executable 테스트는 동시에 실행하지 않도록 문서화했다.
4. **upstream x40-only build**: `BUILD_AD936X=OFF`만으로 build가 성립하지 않는 부분을 작은 patch로 분리했다. micro/AD936x/no-OS 의존성을 받아서 x40 지원으로 오인하지 않는다.
5. **배포 고지 경로**: upstream LICENSES의 상대 symlink를 별도 디렉터리에 복사하면 target이 끊기는 것을 확인했다. 해당 고지는 upstream LICENSE 원문 파일로 보존하고 세 image를 다시 조립했다. 프로젝트 파일 107개의 로컬 문서 링크와 일반적인 private-key/token 패턴 정적 검사에서 누락/일치가 없었다. 이 검사는 모든 secret 형식의 부재를 보증하는 검사는 아니다.

## 알려진 제한과 남은 검증

- 실제 x40의 board/FW/FPGA, USB 권한/속도, timestamp, stream, disconnect/reconnect, PA readback 및 내부 loopback은 장비가 있는 Linux host에서 별도로 수행해야 한다. 계측기 기반 RF emission 측정도 수행하지 않았다.
- OCUDU bladeRF RU driver는 제공하지 않는다. libbladeRF timestamp와 OCUDU timing/buffer 계약을 연결하려면 별도의 실측과 개발이 필요하다. 현재 산출물은 요청에 허용된 standalone diagnostic 방식이다.
- UE attach, operator core, upstream 전체 unit suite, NGAP/F1AP warning procedure의 end-to-end 실행은 미검증이다. 이 플랫폼에는 live warning 수신 또는 방송 기능이 없다.
- UCS-2 BMP 한국어/영어만 지원하며 emoji/non-BMP, GSM 7-bit compression, 실제 operational CMAS field 선택은 지원하지 않는다. NR SIB12 검사는 유효한 최소 sidelink IEs 구조만 다룬다.
- firmware loopback은 normal mode로 자동 복원하지 않는다. 다음 RX 시험 전 전원 재연결이 필요할 수 있다. USB 분리/강제 종료에서는 hardware cleanup 완료를 보장하지 않는다.
- ARM64 Linux에서 실제 실행했다. x86_64 GitHub workflow는 구성했지만 GitHub에 push하지 않아 원격 Actions 실행 결과는 **NOT VERIFIED**다. native macOS gNB는 지원 범위가 아니다.
- 같은 workspace에서 build/test 병렬 실행을 지원하지 않는다. binary-level bit-for-bit 재현성은 보장하지 않으며 입력 revision/dependency를 고정한다.
- 공개 binary/container release 시 LGPL/GPL 대응 dependency source를 수집해 함께 제공해야 한다. source packaging script를 제공했으나 이번 로컬 검증에서는 전체 dependency source archive 생성이나 공개 배포를 실행하지 않았다.

현재 최종 software suite에서 남은 실패는 없다. 실제 hardware 기능을 완료됐다고 주장하지 않는다. 단계별 조건과 재개 기준은 [실행 제한과 체크포인트](EXECUTION_LIMITS.md)의 C0..C8을 따른다. C0..C6 및 로컬 C8은 완료했고 C7은 장치 부재로 BLOCKED다.
