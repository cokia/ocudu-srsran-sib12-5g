# LTE SIB12 구현·검증 보고서

2026-10-20 KST, macOS ARM64 host의 Colima Linux aarch64/Docker에서 실행했다. srsRAN 4G `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16`에 다섯 개 LTE patch를 적용했다. OCUDU pin은 `e0db566aac6e6376ddd60e83c84f58698fcc4d70`이며 LTE 실행에는 사용하지 않는다. libbladeRF도 LTE build에 필요하지 않다.

## 구현 내용

- 공유 YAML/schema에서 LTE srsENB와 srsUE 설정 생성. ID 4372/4380, DCS 0x48, 국내 2-digit MNC를 유지한다.
- upstream CMAS CB Data encoder, LTE SIB12 ASN.1 pack, SI scheduler 및 srsUE 실제 PHY/MAC/ASN.1 unpack을 재사용한다.
- 수신 segment metadata 검사, 중복·순서 바뀜 처리, 손상 거부, CB Data/UCS-2 한글 복원과 입력 비교를 구현했다.
- `PWS_LAB_LTE_SI_MONITOR=1`에서 SI 수신을 유지하고 NAS attach 진입을 억제한다. Random Access가 시작되면 수신 시험을 FAIL 처리한다.
- 전용 build/run/test scripts, Docker image/Compose, GitHub Actions, Korean guide를 추가했다.

주요 파일은 `controller/lte_sib12.py`, `controller/pws_profiles.py`, `configs/lte/`, `patches/srsue-lte-*.patch`, `patches/srsenb-sib12-segments.patch`, `scripts/*lte*.sh`, `docker/*lte*`, `tests/unit/test_lte_sib12.py`, `.github/workflows/lte-sib12.yml`이다. 기존 NR controller는 profile 상수를 공유 모듈로 옮겼다. 전체 목록은 [FILE_INVENTORY](FILE_INVENTORY.md)에 있다.

## 실제 결과

| 검사 | 결과 | 확인 내용 |
|---|---|---|
| srsENB / srsUE C++ build | PASS | Clang 18.1.3, 물리 RF backend OFF |
| Python 전체 검사 | PASS | 214 tests, LTE test 32개 포함 |
| LTE 한글 / PLMN 45005 | PASS | SIB1 PLMN, ID 4372, DCS 0x48, 원문 일치 |
| LTE 한글 / PLMN 45008 | PASS | 두 자리 MNC 08 유지 |
| LTE 한글 / PLMN 45006 | PASS | 두 자리 MNC 06 유지 |
| LTE 영어 / PLMN 00101 | PASS | monthly-test ID 4380, 원문 일치 |
| LTE 한글 최대 615자 | PASS | CB Data 1,246 bytes, 13 segments 전체 수신 |
| 전용 Docker image / Compose | PASS | non-root / read-only / cap-drop ALL / network none, 두 process exit 0 |
| 위 5개 수신의 종료 | PASS | srsENB와 srsUE 모두 exit 0 |
| 의도적 UE 조기 종료 | 예상 FAIL 확인 | `/bin/false`로 `E_EARLY_EXIT`, harness exit 1 |
| 기존 NR 연결 회귀 | PASS | 새 srsUE binary로 MIB/SIB1, RRC 연결·해제 |
| 기존 NR 한글 SIB8 회귀 | PASS | 새 srsUE binary로 ID 4372, PLMN 45005, 원문 일치 |
| 실제 bladeRF / 국내 폰 | NOT VERIFIED | 장비 없음; LTE image에는 RF driver 없음 |

실행 명령:

```bash
docker run --rm --memory 4g --cpus 2 -v "$PWD:/lab" \
  pws-lab-lte-toolchain:0.1.0 bash scripts/build-lte.sh

docker run --rm --network none --cap-drop ALL --memory 3g --cpus 4 \
  -v "$PWD:/lab" -e LAB_PYTHON=build/venv/bin/python \
  pws-lab-lte-toolchain:0.1.0 bash scripts/test-lte-sib12.sh

# build 산출물 staging 후 전용 runtime image 조립
# 전체 준비는 scripts/build-lte-docker.sh에 같은 순서로 들어 있다.
docker run --rm -v "$PWD:/lab" pws-lab-lte-toolchain:0.1.0 \
  python3 scripts/stage-runtime.py lte
docker build --build-context lab_build=build/runtime/lte \
  -f docker/Dockerfile.lte -t pws-lab-lte:0.1.0 .
```

Docker 최종 결과는 [보고서](evidence/2026-10-20/lte-sib12/docker-lte-sib12.json)와 [Compose log](evidence/2026-10-20/lte-sib12/compose.log)에 있다.

원본 [수신 로그](evidence/2026-10-20/lte-sib12/korean-45005-srsue.log)의 일부:

```text
LAB_LTE_SIB1 plmn=45005
LAB_LTE_SIB12 id=4372 serial=0 segment=0 last=1 dcs=48 payload=01005bc2dcd5d8...
```

위 payload는 가독성을 위해 이 문서에서만 축약했다. 원본 로그와 [수신 JSON](evidence/2026-10-20/lte-sib12/korean-45005-lte-sib12.json)에는 전체 hex가 있다. 복원 결과는 `[시험 데이터] PWS 프로토콜 검증 메시지입니다.`다. 최대 길이는 [boundary 결과](evidence/2026-10-20/lte-sib12/boundary-lte-sib12.json), Python 결과는 [JUnit](evidence/2026-10-20/lte-sib12/python.xml), executable/dependency hash는 [manifest](evidence/2026-10-20/lte-sib12/manifest.json)에 보존한다.

## 디버깅에서 수정한 결함

1. `parse_sib12()`는 vector의 첫 element 참조를 다음 `emplace_back()` 이후 읽었다. ID/serial을 재할당 전에 값으로 복사한다. 실제 13-segment 시험에서 모든 ID/serial을 검사한다.
2. LTE `sync::stop()`이 `intra_freq_cfg_mutex`를 잡고 SYNC thread를 join했다. SYNC의 `radio_recv_fnc()`도 같은 mutex를 기다려 최초 시험은 exit -9였다. [수정 전 GDB stack](evidence/2026-10-20/lte-sib12/shutdown-before-fix-backtrace.txt)에서 확인하고 lock scope를 줄였다.
3. SIB1이 SI acquisition procedure보다 먼저 도착하는 경로에서도 monitor를 유지해야 한다. 두 완료 경로를 모두 처리한다. procedure 문자열 하나에 의존하던 증거 검사는 실제 PHY 셀 획득과 수신 SIB1 PLMN으로 바꿨다.
4. ZMQ 상대 종료 후 eNB RX 대기는 `fail_on_disconnect=true,trx_timeout_ms=1000`으로 제한한다. watchdog을 늘려 강제 종료를 성공처럼 취급하지 않는다.

원본 SIB12의 ASN.1 표준 정의를 변경하거나 실제 수신 값을 예상 text로 대체하지 않았다. 이 구현은 SI 수신 시험이며 paging 기반 warning 발견, 상용 단말 UI/알림, S1AP live warning procedure를 완성한 것이 아니다.

## GitHub CI

별도 `.github/workflows/lte-sib12.yml`은 Ubuntu x86-64 runner에서 image build와 한글 수신을 수행한다. 코드 commit `5db83a8be254c6ac23b4442b1f60d41a7ca97896`의 [GitHub run 39294395555](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39294395555)는 PASS다. 실제 srsUE가 PLMN `45005`, ID `4372`, DCS `0x48`, 한글 원문을 수신했고 srsENB/srsUE 종료 코드는 모두 0이었다. [GitHub 수신 JSON](evidence/2026-10-20/github-ci/lte-lte-sib12.json)과 [srsUE 원본 로그](evidence/2026-10-20/github-ci/lte-srsue.log)를 보존한다.

위 GitHub 검사는 기본 한글 메시지 한 건이다. PLMN 45008/45006, 영어, 13-segment 경계값 검사는 앞서 기록한 local ARM64 결과다. 기존 CI의 SIMD compile 오류, Docker 출력 폴더 권한 및 오류 log 출력 개선은 [CI_DEBUG](CI_DEBUG.md)에 기록한다.
