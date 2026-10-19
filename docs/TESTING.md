# 테스트 절차와 결과 해석

결과 상태는 `PASS`, `FAIL`, `SKIP`, `BLOCKED`, `NOT VERIFIED`로 구분한다. 실행하지 않은 검사를 성공 처리하지 않는다. mock PASS와 실제 hardware PASS를 구분한다. 기준 환경과 실제 집계는 [구현 보고서](IMPLEMENTATION_REPORT.md)에 있다.

## Unit / integration

```bash
bash scripts/bootstrap-python.sh
.venv/bin/python -m pytest tests/unit tests/non-sdr
bash scripts/test-non-sdr.sh
bash scripts/test-sdr.sh
```

Non-SDR script는 실제 codec이 없으면 실패한다(`LAB_REQUIRE_CODEC=1`). SDR script는 codec와 diagnostic executable이 모두 필요하다(`LAB_REQUIRE_DIAG=1`). 직접 `pytest`를 실행할 때 build 산출물이 없으면 해당 integration fixture는 SKIP으로 표시하며 mock test를 실제 device test로 바꾸지 않는다.

| 범주 | 검사 |
|---|---|
| YAML/schema | missing/unknown field, 잘못된 type, version, RF flag, empty message, metadata, 중복/alias, UTF-8 오류 |
| 문자/길이 | 한국어·영어, 41/42/615자, 616자 거부, UCS-2 non-BMP/surrogate 거부, CR padding |
| ASN.1 | 실제 OCUDU encode/decode, 독립 UPER golden, size 20/128/256 segment, ID/DCS/순서/last 조건 |
| decoder 오류 | truncation, trailing byte, 비정규 bit padding, 중복/역순, bad hex, empty list |
| CLI/report | 두 mode의 공통 report, 잘못된 파일의 exit code, audit의 본문 비기록 |
| gNB isolation | 고정 Dummy profile, RF profile 거부 |
| mock hardware | 모델/FPGA/버전/권한/USB 속도/격리/timeout/분리/corruption/overrun/timestamp/cleanup |

정규 UPER는 `pack(unpack(input)) == input` 조건도 검사한다. 이것만으로 표준 적합성을 주장하지 않고 독립 golden과 field 검사를 함께 사용한다.

## Non-SDR 전체 절차

1. 전용 Ubuntu/Docker 환경에 고정 dependency 설치.
2. `scripts/build-docker.sh controller`, `scripts/build-docker.sh non-sdr` 실행.
3. `scripts/test-non-sdr.sh`로 software suite 실행.
4. `docker compose -f docker/compose.yaml --profile non-sdr up` 실행.
5. gNB 시작 marker, health, 유지 구간, 정상 종료 및 `gnb-smoke.json` 확인.
6. `offline` 서비스의 `result=PASS`, `offline-sib8.json`, `audit.jsonl` 수집.
7. `scripts/stop.sh`로 project resource 정지. 결과 volume 보존.

Native `scripts/test-non-sdr.sh --gnb`는 unprivileged network namespace가 필요하다. Docker의 gNB smoke는 physical SDR, CAP_SYS_ADMIN, operator core 없이 수행한다. full UE attach는 시험하지 않는다.

## SDR 전체 절차

1. `scripts/build-sdr.sh`와 codec build 수행.
2. `scripts/test-sdr.sh`로 hardware-independent suite 실행.
3. 실제 Linux USB host에서 `lsusb -t`, udev group/device 권한 확인.
4. `run-sdr-diag.sh info --hardware`와 `capabilities --hardware`로 모델/driver/FW/FPGA/API 확인.
5. `verify --hardware`로 x40/버전/USB 3.0 profile 확인.
6. `rx --hardware`로 TX disable 상태의 metadata timestamp 및 buffer 검사.
7. `loopback --hardware`로 firmware mode/PA readback과 고정 I/Q 검사. 격리 실패 시 종료.
8. 장치 분리 상태의 info/verify가 BLOCKED/FAIL인지 확인한 뒤 재연결하고 info/verify를 반복한다. 다른 프로그램과 공유하지 않는다.
9. 단일 USB node를 전달한 Docker override에서 info/verify를 반복한다.
10. 별도 `python -m controller validate --mode sdr-bladerf-x40` 실행.
11. 각각의 JSON/TXT/audit와 버전 정보를 보존한다.

실제 하드웨어가 없는 단계 3..9는 BLOCKED 또는 NOT VERIFIED다. 강제 분리/재연결은 hardware 운영자가 bounded test 중 수행하는 별도 수동 절차이며 normal CI에서 자동 실행하지 않는다.

## Docker 검사

추가 hardware-free 검사는 `scripts/test-libbladerf.sh`로 수행한다. 원본 libbladeRF C/C++/version/parser/interleaver 5개 executable과 실제 adapter의 C API boundary 22개 case를 검사한다. 자세한 범위는 [libbladeRF 검사](LIBBLADERF_TESTING.md)를 참조한다.

`docker/compose.zmq.yaml`은 OCUDU ZMQ + srsUE의 실제 MIB/SIB1 수신을 검사한다. `.github/workflows/zmq.yml`은 수동 실행 또는 관련 파일 PR에서 이 경로를 실행하도록 구성했다. [ZMQ 가이드](ZMQ_SRSUE.md)와 [추가 결과](FOLLOWUP_REPORT.md)를 참조한다.

`build-docker.sh`는 source compile, manifest, runtime image assembly를 포함한다. Compose profile은 별도로 실행하여 image 생성과 runtime 결과를 구분한다. `docker compose config --quiet`는 schema 검사이며 실제 실행 증거를 대신하지 않는다.

## Exit code

| code | 의미 |
|---|---|
| 0 | 요청한 검사 PASS |
| 1 | codec/stream/실행 검증 실패 |
| 2 | YAML/schema/input/CLI 또는 보고서 I/O 오류 |
| 3 | executable, permission, USB 또는 격리 환경 부재로 BLOCKED |
| 4 | controller timeout |
| 77 | 안전한 검사 전제 미충족으로 SKIP |
| 124 | shell timeout wrapper의 제한 도달 |

raw C++ diagnostic의 잘못된 명령은 1을 반환하며 Python 설정 검증 오류는 2다. `driver_code`는 libbladeRF 원래 음수 code를 보존한다. 예를 들어 -7은 device 없음, -6은 timeout이다. device open 시 권한/USB 오류가 같은 backend code로 나올 수 있으므로 상세 문자열과 host permission을 함께 확인한다.

## 결과 위치

`artifacts/non-sdr`, `artifacts/sdr`에는 JUnit XML, mode별 validation JSON, ASN.1 hex, audit가 남는다. Docker는 project named volumes를 사용한다. `build/runtime/<mode>/manifest.json`은 binary SHA256, 원본 commit, package 목록, patch hash를 포함한다. `controller.checkpoints`는 각 단계별 log/JSON을 `artifacts/checkpoints`에 저장한다.

report 공통 field: `report_schema_version`, `mode`, `application_version`, `ocudu_commit`, `host`, `sdr_model`, `firmware_version`, `fpga_version`, `test_name`, `result`, `error`, `timestamp`, `artifact_location`, `details`.

## Lint와 GitHub Actions

```bash
.venv/bin/ruff check controller tests scripts
.venv/bin/ruff format --check controller tests scripts
for file in scripts/*.sh; do bash -n "$file"; done
```

C++ diagnostic은 `-Wall -Wextra -Werror`로 빌드한다. `.github/workflows/test.yml`은 lint/unit/실제 ASN.1/mock 검사를, `build.yml`은 두 image의 독립 build/runtime 검사를 수행한다. GitHub-hosted Ubuntu runner만 필요하며 실제 USB hardware test나 privileged runner를 기본 workflow에 넣지 않는다. GitLab CI를 생성하지 않는다.
