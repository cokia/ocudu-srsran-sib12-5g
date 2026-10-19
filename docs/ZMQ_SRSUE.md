# Docker ZMQ와 srsUE NR 수신 시험

OCUDU gNB와 srsRAN 4G의 `srsue`를 하나의 network-isolated container에서 연결한다. IQ sample은 `127.0.0.1` ZMQ socket으로만 이동한다. physical SDR, USB mapping, privileged container, 외부 core, TUN device가 필요하지 않은 **MIB/SIB1 수신 시험**이다.

## 확인한 upstream 조건

- OCUDU는 기존 고정 `release_26_10`, commit `e0db566aac6e6376ddd60e83c84f58698fcc4d70`이다.
- srsRAN 4G는 `release_25_10`, commit `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16`으로 고정했다.
- 두 revision에 각각 worker 수와 FFTW 계획 방식의 최소 [패치](PATCHES.md)를 적용한다. patch와 변경 전후 source hash도 lock에 고정한다.
- [공식 srsUE tutorial](https://docs.srsran.com/projects/project/en/latest/tutorials/source/srsUE/source/index.html)은 NR prototype의 15 kHz SCS, FDD, 5/10/15/20 MHz 제한과 ZMQ 연결을 설명한다.
- OCUDU `configs/gnb_rf_b210_fdd_srsUE.yml`의 cell/PDCCH/PRACH 설정을 조사하고, 이 프로젝트에서는 radio를 ZMQ로 교체했다. UHD/bladeRF/SoapySDR driver는 빌드에서 비활성화한다.
- srsUE `srsue/src/stack/rrc_nr/rrc_nr.cc::write_pdu_bcch_dlsch`는 SIB1 처리만 호출한다. SIB8/PWS 수신 절차는 제공하지 않는다.
- OCUDU `lib/ngap/gateways/n2_connection_client_factory.cpp::ngap_gateway_local_stub`는 NG Setup Response만 생성한다. AMF 인증이나 PDU session은 구현하지 않는다.

따라서 이 시험의 PASS는 **실제 software PHY/ASN.1을 거친 MIB decode와 SIB1 수신**을 뜻한다. NAS registration, IP ping/throughput, PWS reception의 PASS를 뜻하지 않는다. 완전한 IP 연결 시험에는 별도 Open5GS 같은 local 5GC 구성이 필요하다.

## 빌드와 실행

```bash
bash scripts/build-zmq-docker.sh
docker run --rm --network none --cap-drop ALL --memory 3g --cpus 4 \
  pws-lab-zmq:0.1.0
```

결과와 로그를 보존하는 실행:

```bash
docker compose -f docker/compose.zmq.yaml up --abort-on-container-exit --exit-code-from reception
mkdir -p artifacts/zmq-compose
docker compose -f docker/compose.zmq.yaml cp reception:/lab/output/zmq artifacts/zmq-compose/
docker compose -f docker/compose.zmq.yaml down --timeout 25
```

이 Compose project는 기존 Dummy/SDR project와 구분되는 `ocudu-pws-lab-zmq`다. UID 10001, read-only root/config, `network none`, capabilities 없음으로 실행한다. named output volume은 `down` 이후에도 보존한다.

빌드 cache만 정리하려면 모든 build/test 종료 후 `bash scripts/clean.sh zmq`를 실행한다. upstream checkout, 보관된 실행 artifact, output volume은 삭제하지 않는다.

이미 compiler image를 준비한 개발 환경에서는:

```bash
docker run --rm --memory 4g --cpus 2 -v "$PWD:/lab" \
  pws-lab-zmq-toolchain:0.1.0 bash scripts/build-zmq.sh
docker run --rm --network none --cap-drop ALL --memory 3g --cpus 4 \
  -v "$PWD:/lab" -e LAB_PYTHON=build/venv/bin/python \
  pws-lab-zmq-toolchain:0.1.0 bash scripts/run-zmq-rx.sh --output artifacts/zmq/rx
```

`build-zmq.sh gnb`와 `build-zmq.sh ue`로 개별 build도 가능하다. `build/zmq-gnb`, `build/srsue`, `gnb-zmq`, `srsue`를 사용하여 기존 Dummy binary와 구분한다. 같은 build directory에서 build/test를 동시에 실행하지 않는다.

## 고정 설정

| 설정 | 값과 의미 |
|---|---|
| gNB `cu_cp.amf.no_core` | true, 외부 AMF 없음 |
| gNB `ru_sdr.device_driver` | `zmq`; 이름에 SDR이 들어가지만 실제 RF driver가 아님 |
| gNB `device_args` | TX `127.0.0.1:2000`, RX `127.0.0.1:2001`, base rate 23.04 MS/s |
| gNB `tx_gain`, `rx_gain` | 0 dB; 현재 OCUDU ZMQ validator는 양수 gain을 거부함 |
| UE `rf.device_name/device_args` | `zmq`, TX/RX port를 gNB와 반대로 연결 |
| `cell_cfg` | n3, ARFCN 368500, 20 MHz, SCS 15 kHz, PCI 1, PLMN 00101 |
| PDCCH | SS0=0, CORESET0=12, SS2 common, fallback DCI |
| PRACH / MCS | index 1, DL/UL qam64 |
| UE `rat.eutra.nof_carriers` | 0, LTE carrier 비활성화 |
| UE `rat.nr` | carrier 1, PRB 106, DL ARFCN 368500, SSB ARFCN 368410, SCS/SSB SCS 15 |
| UE `phy.nof_phy_threads` | 1 |
| gNB `expert_execution.threads.main_pool.nof_threads` | 2; ZMQ synchronous 작업의 단일 worker 교착 방지 |
| soft USIM | upstream에 공개된 시험용 값; 실제 가입자 정보 아님 |
| logs / PCAP | stdout log, PCAP 비활성화 |

wrapper는 두 config의 SHA256을 확인하고 수정된 endpoint/radio/PWS profile을 거부한다. PWS config와 payload를 읽지 않으며 offline PWS subsystem은 종전대로 별도 process에서 사용한다.

OCUDU `ru_sdr_config_cli11_schema.cpp`는 ZMQ 선택 시 lower PHY를 blocking mode로 자동 설정한다. 과거 tutorial의 USRP용 양수 gain을 그대로 복사하지 않는다. srsUE의 realtime priority/mlock 경고는 제한된 container에서 발생할 수 있으며, 수신 성공 여부는 별도의 MIB/SIB1 증거로 판정한다.

## 판정과 실행 한도

PASS에는 gNB 시작과 **UE log**의 MIB decode, MIB 설정 완료, `SIB1 received, CellID=`, `SIB1 acquired successfully`가 모두 필요하다. MIB의 PCI=1, SCS=15, CORESET0=12, SS0=0도 확인한다. 단순 프로세스 시작이나 gNB의 SIB1 전송 로그만으로 수신 성공을 판단하지 않는다.

고정 srsUE의 `phy_nr_sa.cc::start_cell_search`는 callback의 `ssb_arfcn`을 채우지 않아 log에 `ARFCN=0`을 기록한다. 해당 원인과 실제 decoded MIB를 확인하고 parser에 반영했다. 두 config의 ARFCN은 hash로 고정하며 gNB의 `dl_ssb_arfcn=368410` 로그와 함께 확인한다. `CellID=4095` 같은 prototype의 요약 필드는 정확한 NCI 검증에 사용하지 않는다.

이 profile은 RRC 연결 후 PDU session이 생기지 않아 gNB가 UE를 자동 release한다. RRC 연결·release와 gNB UE 제거까지 관찰한 뒤 **UE 먼저, gNB 나중** 순서로 종료한다. no-core stub에는 NG Reset 응답이 없어 active UE가 있는 상태에서 gNB를 종료하면 강제 종료로 이어질 수 있다. 두 process의 종료 코드 0도 PASS 조건이다. RRC 완료는 NAS registration/IP 연결 완료와 다르다.

전체 Docker build 2,700초, 개별 gNB build 2,700초, UE build 1,800초, 수신 기본 60초/최대 120초, 각 process 종료 10초, 각 log 32 MiB로 제한한다. 실패하면 기존 산출물을 보존하고 원인을 수정한 뒤 해당 단계만 재개한다.

`zmq-rx.json`, `gnb.log`, `srsue.log`, `audit.jsonl`을 보존한다. 실제 실행 결과는 [추가 검증 보고서](FOLLOWUP_REPORT.md), [수신 로그 캡처와 한글 검증](SRSUE_RX_CAPTURE.md)을 참조한다.
