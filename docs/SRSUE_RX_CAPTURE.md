# srsUE 실제 수신 로그 및 한글 지원 검증

검증 시각: **2026-10-19 19:27–19:28 KST**. Docker/Colima Linux ARM64에서 실제 executable을 다시 실행했다. 아래 로그는 mock 출력이 아니다.

## 결과

| 검사 | 결과 | 증거 |
|---|---|---|
| ZMQ MIB decode 및 SIB1 수신 | PASS | [srsUE 원본 로그](evidence/2026-10-19/srsue.log) |
| RRC 연결·release·gNB UE context 제거 | PASS | [gNB 원본 로그](evidence/2026-10-19/gnb.log) |
| gNB / srsUE 정상 종료 | PASS, 각각 rc=0 | [수신 report](evidence/2026-10-19/zmq-rx.json) |
| Non-SDR 한글 encode/decode | PASS | [validate](evidence/2026-10-19/validate-non-sdr.json), [decode](evidence/2026-10-19/decode-non-sdr.json) |
| SDR 모드 한글 encode/decode, 장비 없음 | PASS | [validate](evidence/2026-10-19/validate-sdr-bladerf-x40.json), [decode](evidence/2026-10-19/decode-sdr-bladerf-x40.json) |
| Python 회귀, 실제 OCUDU codec 포함 | **118 PASS, 0 FAIL, 0 SKIP** | [JUnit](evidence/2026-10-19/python.xml), [실행 로그](evidence/2026-10-19/python.log) |
| Ruff lint / format | PASS | 같은 실행 로그 |
| srsUE에서 한글 PWS 경고문 수신 | UNSUPPORTED | 고정 NR upstream에 SIB8/PWS 수신 처리 없음 |
| NAS registration / IP 통신 / 실물 bladeRF | NOT VERIFIED | 이 실행 범위에 없음 |

## srsUE 수신 발췌

아래 timestamp는 UTC다. 중간 로그는 생략했으며 선택한 줄의 내용은 원본 그대로다.

```text
2026-10-19T10:27:16.605407 [RRC-NR ] [I] Proc "Cell Selection" - Cell search found ARFCN=0 PCI=1 epre=-11.2 snr=+78.8 cfo=-0.0 delay=-0.0  sfn=11 ssb_idx=0 hrf=n scs=15 ssb_offset=6 dmrs_typeA_pos=pos2 coreset0=12 ss0=0 barred=n intra_freq_reselection=y spare=0
2026-10-19T10:27:16.605891 [RRC-NR ] [I] PHY configuration with MIB parameters completed.
2026-10-19T10:27:16.686268 [RRC-NR ] [I] BCCH-DLSCH - Rx systemInformationBlockType1 (80 B)
2026-10-19T10:27:16.686281 [RRC-NR ] [I] SIB1 received, CellID=4095
2026-10-19T10:27:16.686491 [RRC-NR ] [I] Proc "Cell Selection" - SIB1 acquired successfully
RRC Connected
2026-10-19T10:27:16.754231 [RRC-NR ] [I] SRB1 - Tx rrcSetupComplete (27 B)
Received RRC Release
2026-10-19T10:27:20.799886 [RRC-NR ] [I] Received RRC Release
---  exiting  ---
```

`ARFCN=0`은 고정 srsUE callback의 `ssb_arfcn` 미설정에 따른 로그 제한이다. 실제 profile의 SSB ARFCN은 368410이며 gNB 원본 로그에서도 확인했다. `CellID=4095`는 prototype의 요약 출력으로 보존하고 정확한 NCI 일치 판정에는 사용하지 않는다. source 위치와 판정 조건은 [ZMQ 가이드](ZMQ_SRSUE.md)에 있다.

원본에는 `mlockall`/realtime priority 제한, SIB1 이전 PRACH 설정 오류 줄, release 이후 LCID 경고도 있다. 이를 삭제하지 않았다. 판정은 MIB 설정 완료, SIB1 수신·획득, RRC 연결·해제, gNB UE 제거, 두 process 정상 종료를 모두 요구한다. 실시간 성능·무경고 동작을 검증한 것은 아니다.

## 한글 복원

두 runtime image에서 UTF-8 YAML을 읽고 **UCS-2 big-endian CB Data → 실제 OCUDU NR SIB8 UPER → decode**를 실행했다. 두 모드의 복원 문자열은 다음과 같다.

```text
입력: [시험 데이터] PWS 프로토콜 검증 메시지입니다.
복원: [시험 데이터] PWS 프로토콜 검증 메시지입니다.
```

28 UCS-2 문자, UTF-8 62 byte, DCS `0x48`, SIB8 segment 1개이며 원문 일치와 결정적 인코딩 검사가 통과했다. `decode` 결과 JSON에도 한글을 escape 없이 UTF-8로 보존한다. `language: ko`는 application metadata이고 무선상의 별도 언어 필드로 매핑하지 않는다.

추가 회귀 검사는 `한글`의 독립 고정 byte vector(`d55c ae00`), 두 모드 CLI의 별도 decode 및 JSON 원문 일치, 기존 615자 한글 경계와 실제 ASN.1 segment 크기 20/128/256 검사를 포함한다. 지원 범위는 최대 615 UCS-2 BMP 문자이며 emoji 등 non-BMP 문자는 명시적으로 거부한다.

한글 PWS 검증은 offline engine에서 수행했다. srsUE가 수신한 것은 MIB/SIB1이며 경고문을 ZMQ/gNB로 전달하는 경로는 없다. 따라서 이 결과를 UE 경고문 표시 또는 한글 PWS 방송 수신 성공으로 해석하지 않는다.

## 재현 명령과 실행 한도

이미 build한 image를 사용한 실행이다. 전체 clean build 결과와 구분한다.

```bash
docker compose -f docker/compose.zmq.yaml up --abort-on-container-exit --exit-code-from reception
mkdir -p artifacts/publication-20261019
docker compose -f docker/compose.zmq.yaml cp reception:/lab/output/zmq artifacts/publication-20261019/
docker compose -f docker/compose.zmq.yaml down --timeout 25

for mode in non-sdr sdr-bladerf-x40; do
  mkdir -p "artifacts/publication-20261019/korean/$mode"
  docker run --rm --network none --cap-drop ALL --read-only --tmpfs /tmp --memory 512m --cpus 1 \
    -v "$PWD/artifacts/publication-20261019/korean/$mode:/lab/output" \
    --entrypoint python "pws-lab-$mode:0.1.0" \
    -m controller validate --mode "$mode" --output /lab/output
  docker run --rm --network none --cap-drop ALL --read-only --tmpfs /tmp --memory 512m --cpus 1 \
    -v "$PWD/artifacts/publication-20261019/korean/$mode:/lab/output" \
    --entrypoint python "pws-lab-$mode:0.1.0" \
    -m controller decode --mode "$mode" --input /lab/output/offline-sib8.json --output /lab/output
done

docker run --rm --network none --memory 1g --cpus 2 \
  -e LAB_REQUIRE_CODEC=1 -e LAB_REQUIRE_DIAG=1 -v "$PWD:/lab" \
  pws-lab-toolchain:0.1.0 bash -c 'build/venv/bin/ruff check controller tests scripts && build/venv/bin/ruff format --check controller tests scripts && build/venv/bin/python -m pytest --junitxml=artifacts/publication-20261019/python.xml'
```

수신 제한은 60초, process별 정상 종료 제한은 10초, log별 최대 32 MiB, codec 호출은 각 10초다. 수신 container는 `network none`, UID 10001, read-only root, `cap_drop: ALL`, 3 GiB/4 CPU이며 physical USB/TUN mapping이 없다. 원본 로그 SHA256 및 실제 적용 설정은 [manifest](evidence/2026-10-19/manifest.json)에 보존했다.

OCUDU `e0db566aac6e6376ddd60e83c84f58698fcc4d70`, srsRAN 4G `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16`과 [최소 patch](PATCHES.md)를 사용했다. 실물 bladeRF 검증, 기존 Dummy RU의 간헐적 abort 원인 규명, 원격 GitHub Actions의 성공 여부는 이번 로컬 PASS와 별도로 확인해야 한다.
