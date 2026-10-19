# 실행 제한과 체크포인트

무제한 실행이나 실패의 자동 성공 처리는 하지 않는다. 실패한 단계의 원인을 수정한 뒤 해당 단계만 다시 실행하며, 독립적인 단계는 계속 진행한다. 사용자 확인을 단계마다 요구하지 않는다.

| 작업 | 기본/최대 제한 | 제한 도달 시 |
|---|---|---|
| upstream clone | 저장소당 300초, 고정 tag/commit | 비정상 종료, 기존 checkout 보존 |
| OCUDU build | 작업 2개, 허용 1..4개, compiler 2 CPU/4 GiB, 호출당 2,700초 | TERM 후 15초 뒤 종료, incremental build 보존 |
| libbladeRF build | 기본 작업 2개, Docker 1 CPU/1 GiB, 600초 | 실패로 종료 |
| YAML/codec JSON | 64 KiB | 입력 거부 |
| 메시지 | UCS-2 BMP 615자, CB Data 15 page/1,246 byte | 길이/encoding 오류 |
| ASN.1 segment | 최대 64개, 이 앱의 크기 20..256 byte, 기본 128 | 범위 오류 |
| codec subprocess | 호출당 10초 | FAIL, exit 4 |
| gNB smoke | 시작 20초 + 유지 1..30초(기본 5초) + 종료 10초, 전체 watchdog 60초 권장 | marker 미검출/조기 종료/강제 종료를 FAIL 처리 |
| 하드웨어 진단 | 전체 20초, USB transfer 1,000 ms, sync call 2,000 ms | FAIL, 장치 상태 재확인 |
| firmware loopback | 1 MS/s, 65,536 complex samples, 8 buffers × 4,096 samples, 4 transfers | RF fallback 없이 종료 |
| RX timestamp | 4,096 samples 두 block | 불연속 또는 overrun/underrun은 FAIL |
| Docker runtime | gNB 2 GiB/2 CPU, controller/SDR 512 MiB, network none | 런타임 오류를 결과에 반영 |
| CI | test 30분, build 60분/job | GitHub Actions 실패; hardware 실행 없음 |
| 실제 libbladeRF API 검사 | upstream build 300초, adapter build 180초, 각 검사 20초 | FAIL, log 보존; 실제 장치 접근 없음 |
| ZMQ / srsUE 수신 | 기본 60초, 최대 120초 + process별 종료 10초; log별 32 MiB | UE MIB/SIB1 증거가 없으면 FAIL |
| ZMQ build | Docker 전체 2700초, 개별 gNB 2700초 / srsUE 1800초 | 각 build directory 보존 후 재개 |

제한은 `scripts/build-*.sh`, `controller/protocol.py`, `controller/gnb.py`, `controller/hardware.py`, `driver_adapter/real_device.cpp`에 구현되어 있다. Docker image 빌드는 `controller.checkpoints`의 2,700초 제한으로 감싸서 수행한다. 큰 빌드에서 제한에 도달하면 원인을 확인한 뒤 incremental build를 재개한다. 임의 반복 횟수를 늘려 성공으로 간주하지 않는다.

## 체크포인트

| ID | 통과 조건 | 증거 |
|---|---|---|
| C0 | upstream commit/라이선스/NR SIB8·SIB12 의미 확인 | `dependencies.lock.json`, `UPSTREAM_ANALYSIS.md` |
| C1 | Python 검증기 unit test와 schema 검사 | `artifacts/non-sdr/junit.xml` |
| C2 | OCUDU gNB와 codec 실제 링크 성공 | build log, `build/bin/`, runtime manifest |
| C3 | 실제 ASN.1 round-trip 및 독립 UPER golden 비교 | protocol tests, `offline-sib8.json` |
| C4 | libbladeRF 링크 및 mock 성공/실패 경로 검사 | `artifacts/sdr/`, mock JUnit |
| C5 | network none gNB 초기화와 정상 종료 | `gnb.log`, `gnb-smoke.json` |
| C6 | 세 runtime 이미지 및 두 Compose profile 실행 | Docker build/Compose logs |
| C7 | 실제 x40 모델/FW/FPGA/USB/격리 검사 | hardware JSON. 미연결 시 BLOCKED |
| C8 | 최종 lint/테스트/라이선스/비밀정보 검사 | `IMPLEMENTATION_REPORT.md` |
| C9 | 실제 libbladeRF 원본 테스트 + C API contract | `artifacts/libbladerf/`, `LIBBLADERF_TESTING.md` |
| C10 | OCUDU/srsUE ZMQ build 및 실제 MIB/SIB1 수신 | `artifacts/zmq/`, `FOLLOWUP_REPORT.md` |

예:

```bash
.venv/bin/python -m controller.checkpoints --name C3 --timeout 300 -- \
  scripts/test-non-sdr.sh
.venv/bin/python -m controller.checkpoints --name C6 --timeout 2700 -- \
  scripts/build-docker.sh non-sdr
```

각 호출은 log, JSON, append-only audit event를 남긴다. PASS는 실행이 성공했을 때만 사용한다. SKIP은 조건 미충족으로 검사하지 않음, BLOCKED는 환경/장치/도구 부재, NOT VERIFIED는 기능은 있으나 해당 동작 검증을 하지 않음을 뜻한다. mock PASS는 실제 hardware PASS가 아니다.

빌드 cache와 기존 사용자의 Docker 이미지/volume은 자동 prune하지 않는다. `clean.sh`는 지정한 프로젝트 build 경로만 지우고 결과와 upstream을 보존한다. hardware 진단 timeout/USB 분리 후에는 firmware loopback 상태와 모듈 비활성화를 확인하고 필요하면 USB 전원을 다시 연결한다.
