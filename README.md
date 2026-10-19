# OCUDU PWS Laboratory

OCUDU 5G NR의 **오프라인 PWS/CMAS 검증**, **NR SIB8 및 LTE SIB12 ZMQ 수신**, **bladeRF x40 radio plugin 및 standalone 진단**을 제공하는 실험실 플랫폼이다. 공유 메시지 → OCUDU SI scheduler → srsUE 한글 수신을 검증했다. x40 timed USB 송신 코드는 별도 RF 활성 build에 있으며, 기본 build와 Docker는 RF OFF다. **실물 x40/휴대폰 수신은 NOT VERIFIED**다.

**5G NR CMAS는 SIB8이다.** NR SIB12-r16은 sidelink 설정 구조이므로 별도의 ASN.1 구조 검사만 제공한다. LTE SIB12를 NR 경고 메시지로 잘못 매핑하지 않는다.

## 기능과 지원 범위

| 기능 | `non-sdr` | `sdr-bladerf-x40` |
|---|---|---|
| UTF-8 YAML / JSON Schema / metadata 검사 | 지원 | 동일 공유 모듈 |
| 한국어·영어 UCS-2 CB Data / NR SIB8 UPER | 지원 | RF와 분리하여 지원 |
| 실제 OCUDU ASN.1 encode/decode / golden test | 지원 | 동일 codec |
| LTE SIB12 한글 수신·최대 13 segments | 별도 ZMQ image | 필요 없음 |
| NR SIB12 구조 round-trip | 지원 | 동일 codec |
| gNB / Dummy RU / no-core / network isolation | 지원 | 필요 없음 |
| Docker ZMQ / srsUE MIB·SIB1 / RRC 수신 | 별도 이미지와 Compose | 필요 없음 |
| x40 board/FW/FPGA/USB/library probe | 필요 없음 | 구현; 실제 장치 연결 필요 |
| RX metadata / firmware loopback | 필요 없음 | 격리/버전 조건 충족 시 실행 |
| 오류 주입 mock | SDR 없이 별도 build 가능 | 지원 |
| OCUDU bladeRF RU driver | 실제 gNB + mock stream PASS | timed USB 구현·build/API 검사 PASS; 실물 timing 미검증 |
| PWS → SI scheduler → SIB8 수신 | ZMQ 한글/영어/615자 PASS | RF 연결 코드 구현, 실제 RF 수신 미검증 |
| live warning distribution API | 제공하지 않음 | 제공하지 않음 |

기준 OCUDU: `release_26_10` / `e0db566aac6e6376ddd60e83c84f58698fcc4d70` + worker 수와 빈 CPU feature 목록을 보완하는 [최소 patch](docs/PATCHES.md).
bladeRF: `libbladeRF_v2.6.0` / `09c82087786702d2812f3f0fc909beccf3277233` + 문서화된 x40 전용 patch.
대상 SDR은 첫 세대 **bladeRF x40**뿐이다. 실제 장치 검증 결과는 mock과 구분하여 [최종 구현 보고서](docs/IMPLEMENTATION_REPORT.md)에 기록한다.

## PWS 수신과 radio plugin

```bash
bash scripts/build-pws-integration-docker.sh
docker compose -f docker/compose.pws.yaml --profile pws-zmq run --rm reception
docker compose -f docker/compose.pws.yaml --profile radio-mock run --rm radio-mock
```

[PWS 연동 가이드](docs/PWS_INTEGRATION.md), [radio plugin](docs/RADIO_PLUGIN.md), [실제 수신 로그·검증 보고서](docs/RADIO_PWS_REPORT.md)를 참조한다. 기본 `monthly-test`는 ID 4380, `korean-safety`는 4372다. 국내 폰의 화면 분류는 지역/통신사/단말 설정에 따라 달라진다.

PWS 연동 기본 PLMN은 **`45005`(MCC 450, SKT MNC 05)**다. CLI `--plmn 45008`은 KT, `--plmn 45006`은 LG U+를 선택한다. Compose에서는 `PWS_LAB_PLMN=45008`처럼 지정한다. 실제 ZMQ 수신 SIB1의 MCC/MNC와 한글 SIB8을 함께 검사한다. [국내 PLMN 검증과 로그](docs/KOREAN_PLMN.md)를 참조한다.

## LTE SIB12 수신

LTE는 별도 srsENB/srsUE 경로를 사용한다. 공유 한글 YAML을 LTE SIB12로 인코딩하고 ZMQ IQ 수신 결과를 재조립한다. 기본 PLMN은 `45005`, DCS는 `0x48`, messageIdentifier는 `4372`다.

```bash
bash scripts/build-lte-docker.sh
docker compose -f docker/compose.lte.yaml --profile lte-zmq up \
  --abort-on-container-exit --exit-code-from lte-sib12
```

[LTE 설치·실행·제한](docs/LTE_SIB12.md), [실제 수신과 검증 결과](docs/LTE_SIB12_VERIFICATION.md)를 참조한다. LTE image에는 물리 RF backend를 빌드하지 않으며 장치와 EPC 없이 실행한다.

## 빠른 시작: Non-SDR

Docker Engine/Compose와 Git이 필요하다. Linux Ubuntu 24.04가 실행 기준이며 macOS에서는 Linux VM의 Docker를 사용한다.

```bash
bash scripts/build-docker.sh controller
bash scripts/build-docker.sh non-sdr
docker run --rm --network none pws-lab-controller:0.1.0
docker run --rm --network none --cap-drop ALL --memory 2g pws-lab-non-sdr:0.1.0
```

결과를 보존하는 Compose 실행:

```bash
docker compose -f docker/compose.yaml --profile non-sdr up
```

gNB는 최대 30초 유지 후 정상 종료하는 smoke 환경이다. UE attach나 실제 PHY throughput을 시뮬레이션했다고 주장하지 않는다.

Native Ubuntu:

```bash
sudo bash scripts/install-deps.sh non-sdr
bash scripts/bootstrap-python.sh
bash scripts/build-non-sdr.sh
bash scripts/test-non-sdr.sh
bash scripts/run-non-sdr.sh
```

설치 script는 전용 개발 환경의 apt archive를 고정 snapshot으로 설정한다. 상세 조건은 [설치](docs/INSTALLATION.md), [Non-SDR 가이드](docs/NON_SDR_GUIDE.md)를 참조한다.

## 빠른 시작: SDR

장치 없이도 SDR image와 mock을 실행할 수 있다.

```bash
bash scripts/build-docker.sh sdr-bladerf-x40
docker run --rm --network none pws-lab-sdr-bladerf-x40:0.1.0 loopback --mock
docker compose -f docker/compose.yaml --profile sdr-bladerf-x40 up
```

실제 Linux USB host에서 별도 설치/udev/firmware 확인 후:

```bash
bash scripts/run-sdr-diag.sh info --hardware
bash scripts/check-bladerf-x40.sh --hardware
bash scripts/run-sdr-diag.sh rx --hardware
bash scripts/run-sdr-diag.sh loopback --hardware
```

libbladeRF/FW/FPGA의 실험실 조합은 2.6.0 / 2.6.0 / 0.16.0이다. firmware와 FPGA blob은 별도 설치하며 프로젝트는 자동 flash하지 않는다. [SDR 실행 가이드](docs/SDR_BLADERF_X40_GUIDE.md)에 단일 USB node를 전달하는 Docker override와 실제 장비에서만 확인 가능한 항목을 설명한다.

## 설정과 오프라인 실행

`configs/pws.example.yaml`의 예:

```yaml
schema_version: 1
application:
  name: ocudu-pws-lab
  mode: non-sdr
  log_level: info
```

전체 필수 field는 예제 파일을 사용한다. `pws.message.profile: TEST`, `metadata.category: LAB_EXERCISE`, `radio.backend: dummy`, `radio.rf_transmission_enabled: false`만 허용한다. text는 최대 615 UCS-2 BMP 문자다. device 설정은 `configs/bladerf-x40.yaml`로 분리한다.

```bash
.venv/bin/python -m controller validate
.venv/bin/python -m controller decode --input output/offline-sib8.json
.venv/bin/python -m controller inspect-sib12
```

구조: YAML → 검증 → CB Data → 별도 C++ codec → OCUDU SIB8 → offline decode/비교 → JSON/audit. gNB와 hardware diagnostic은 이 흐름에서 독립된 process다. [아키텍처](docs/ARCHITECTURE.md)에 diagram과 인터페이스를 정리했다.

## 테스트·제한·정리

장비 없이 실제 libbladeRF API를 검사하려면 `scripts/test-libbladerf.sh`를 사용한다. [libbladeRF 검증](docs/LIBBLADERF_TESTING.md)은 upstream 원본 테스트와 실제 adapter의 C API 경계 검사를 구분한다.

Dummy RU 외에 Docker ZMQ와 srsUE로 실제 NR MIB/SIB1 수신을 시험할 수 있다. `scripts/build-zmq-docker.sh`로 별도 이미지를 만들고 [ZMQ srsUE 가이드](docs/ZMQ_SRSUE.md)의 절차를 따른다. 이 기존 명령의 PASS는 MIB/SIB1/RRC에 한정한다. SIB8은 새 `controller.pws_integration receive`에서 검사하며 NAS/IP 연결 완료는 검증하지 않는다. [추가 검증 결과](docs/FOLLOWUP_REPORT.md), [실제 수신 로그와 한글 왕복 검증](docs/SRSUE_RX_CAPTURE.md)을 참조한다.

```bash
bash scripts/test-non-sdr.sh
bash scripts/test-sdr.sh
.venv/bin/ruff check controller tests scripts
.venv/bin/ruff format --check controller tests scripts
bash scripts/stop.sh
```

빌드 기본 2 jobs/45분, codec 호출 10초, 장치 진단 20초, loopback 65,536 samples로 제한한다. [실행 제한과 체크포인트](docs/EXECUTION_LIMITS.md)를 참조한다. 보고서는 PASS/FAIL/SKIP/BLOCKED/NOT VERIFIED를 구분하며 실행하지 않은 항목을 PASS로 표시하지 않는다.

## 문서와 배포

- [Upstream 분석과 #540](docs/UPSTREAM_ANALYSIS.md)
- [설정 전체 참조](docs/CONFIGURATION.md), [PWS 테스트](docs/PWS_TESTING.md)
- [bladeRF 기술 조사](docs/BLADERF_X40.md), [Docker](docs/DOCKER.md)
- [관련 프로젝트 비교와 radio driver 디버깅 결과](docs/RELATED_PROJECTS_DEBUG.md)
- [테스트 절차](docs/TESTING.md), [문제 해결](docs/TROUBLESHOOTING.md)
- [국내 휴대폰 안전안내문자 시험의 호환성 평가](docs/DOMESTIC_PHONE_TESTING.md)
- [최종 구현·검증 보고서](docs/IMPLEMENTATION_REPORT.md)
- [라이선스/제3자 배포 조건](THIRD_PARTY_NOTICES.md)

GitHub Actions는 software build, lint, ASN.1, mock, Docker runtime을 검사한다. normal PR에 self-hosted runner나 실제 SDR이 필요하지 않다. GitLab CI 파일은 만들지 않는다. 원본 source는 고정 commit으로 가져오고, 필요한 최소 변경은 hash를 검증하는 [패치](docs/PATCHES.md)로 관리한다. source 공개와 binary/container release는 구분하며, 재배포 조건은 제3자 고지를 따른다.

2026-10-20 코드 commit `5db83a8`의 GitHub workflow 4개가 모두 통과했다. x86 SIMD 설정과 Docker 출력 권한의 수정 내용, 실제 LTE/NR 한글 수신 로그는 [CI 검증 보고서](docs/CI_DEBUG.md)에 있다.
