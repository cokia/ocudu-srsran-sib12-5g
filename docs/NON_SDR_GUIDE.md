# Non-SDR 실행 가이드

이 모드는 Dummy RU와 `no_core`를 사용한다. RF 장치, operator core, 가상 UE attach는 필요하지 않다. gNB 초기화/종료 검증과 PWS protocol 검증은 별도의 process에서 실행한다.

실제 software UE의 MIB/SIB1 수신까지 검사하는 별도 ZMQ 경로는 [ZMQ srsUE 가이드](ZMQ_SRSUE.md)를 따른다. 기존 Dummy 실행과 build/config/runtime이 구분된다.

추가 Colima 회귀 실행에서 Dummy RU의 간헐적 abort와 slot 지연 경고가 관찰됐다. 최초 smoke PASS는 실시간 안정성 보증이 아니다. 실패/재실행 결과와 남은 조사는 [추가 보고서](FOLLOWUP_REPORT.md)의 Dummy RU 항목에 기록했다. 수신 검증에는 실제 통과한 별도 ZMQ profile을 사용한다.

## Ubuntu 준비와 빌드

```bash
sudo bash scripts/install-deps.sh non-sdr
bash scripts/bootstrap-python.sh
bash scripts/build-non-sdr.sh
```

기본 2개 작업으로 45분 제한을 적용한다. 제한에 도달하면 `build/non-sdr`를 보존한 상태로 같은 명령을 다시 실행하여 incremental build를 재개할 수 있다. codec만 필요한 경우:

```bash
bash scripts/build-non-sdr.sh --codec-only
```

설정은 `configs/gnb.non-sdr.yaml`이다. `cu_cp.amf.no_core: true`, loopback bind 주소, `ru_dummy.time_scaling: 10`, n78의 논리적 cell 설정을 사용한다. ARFCN/band 설정은 Dummy RU에서 RF 송신을 만들지 않는다. 알려진 고정 smoke profile 외의 변경은 실행기가 거부한다.

`buffer_pool.nof_segments: 16384`, `segment_size: 2048`로 segment storage를 약 32 MiB로 제한한다. upstream의 기본 1,048,576 segments를 사용하면 초기화에서 약 2 GiB를 할당하여 2 GiB 컨테이너가 OOM 종료될 수 있다. 이 profile은 실제 2 GiB 제한에서 시작과 종료를 검증했다.

## Native 실행

```bash
bash scripts/run-non-sdr.sh --duration 5
```

공유 PWS 검증 후 `unshare --user --map-root-user --net`으로 별도 network namespace를 만든다. 그 안에는 `lo`만 존재해야 한다. Ubuntu 정책으로 unprivileged namespace 생성이 차단되면 우회해서 host network에서 실행하지 않고 Docker 경로를 사용한다.

```bash
.venv/bin/python -m controller validate --config configs/pws.example.yaml
.venv/bin/python -m controller decode --input output/offline-sib8.json
.venv/bin/python -m controller inspect-sib12
```

기대 결과는 JSON의 `result: PASS`, `round_trip: true`, `deterministic: true`이다. NR CMAS type은 `NR-SIB8`이고 NR SIB12 결과는 `cmas: false`다. `output/offline-sib8.json`의 hex는 RF I/Q가 아닌 독립 ASN.1 SIB 객체다.

## Docker 실행

```bash
bash scripts/build-docker.sh controller
bash scripts/build-docker.sh non-sdr
docker run --rm --network none --cap-drop ALL --memory 2g pws-lab-non-sdr:0.1.0
docker run --rm --network none pws-lab-controller:0.1.0
docker compose -f docker/compose.yaml --profile non-sdr up
```

Compose의 gNB는 시작 후 30초 유지하고 정상 종료한다. 기본 Docker `run`은 5초다. 일시적 smoke 환경이므로 무기한 서비스로 유지하지 않는다. `non-sdr-output` volume에 log와 JSON을 보존한다. USB mapping, privileged, host networking을 사용하지 않는다.

## 테스트와 결과 수집

```bash
bash scripts/test-non-sdr.sh
bash scripts/test-non-sdr.sh --gnb
python3 scripts/healthcheck.py output/non-sdr/gnb.health.json
```

`--gnb`는 실행 환경의 network namespace 기능이 필요하다. 공유/ASN.1 검사는 이 옵션 없이 실행할 수 있다. gNB healthcheck는 실행 중 PID와 STARTED 상태를 확인하며 정상 종료 후에는 실패하는 것이 맞다.

- `artifacts/non-sdr/junit.xml`: 실제 실행한 pytest 결과.
- `artifacts/non-sdr/validate-non-sdr.json`: 공통 보고서.
- `output/non-sdr/gnb.log`, `gnb-smoke.json`: 시작 marker, 유지, SIGINT 종료 결과.
- `audit.jsonl`: 설정 digest와 실행 event. 원문 message text를 audit에 저장하지 않음.

## 종료와 정리

Native foreground에서 Ctrl-C 또는 TERM으로 종료한다. harness는 child gNB에 SIGINT를 전달하고 10초 내 종료 여부를 검사한다. Compose는 `scripts/stop.sh`로 정지한다. `scripts/clean.sh non-sdr`는 gNB build만 삭제하며 결과와 upstream checkout은 보존한다.

`E_NETWORK_ISOLATION`은 network none/namespace 부재, `E_CODEC_MISSING`은 codec 미빌드, `E_GNB_START`는 gNB config/runtime 초기화 실패를 뜻한다. 마지막 오류는 반드시 `gnb.log`를 확인한다. UE attach, DL/UL throughput, warning broadcast, 실제 PHY timing은 이 smoke test의 검증 범위가 아니다.
