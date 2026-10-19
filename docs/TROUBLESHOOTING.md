# 문제 해결

| 증상/오류 | 확인과 조치 |
|---|---|
| `E_REVISION` / `E_UPSTREAM_DIRTY` | 고정 commit과 기존 checkout이 다름. 개인 변경을 별도 보존한 뒤 checkout을 준비한다. script가 reset/overwrite하지 않음 |
| CMake가 dependency를 찾지 못함 | Ubuntu 24.04 toolchain/snapshot 설치 확인. macOS native gNB build 대신 Docker 사용 |
| build exit 124 | 45분 제한 도달. log의 마지막 대상/메모리/CPU를 확인하고 같은 명령으로 incremental build 재개 |
| `Killed` / OOM | compiler jobs를 1로 줄이고 전용 VM 메모리 여유 확인. 전체 Docker prune으로 다른 프로젝트 자료를 지우지 않음 |
| gNB 시작 전 rc=-9 / OOM | 제공된 buffer pool 16384 × 2048 설정인지 확인. upstream 기본 pool은 2 GiB 제한을 넘을 수 있음. 실제 실패 로그와 수정 후 PASS는 최종 보고서 참조 |
| `.venv` / `build/venv` executable 오류 | macOS와 Linux venv는 호환되지 않음. 사용 환경의 Python 3.12로 생성. Docker compiler venv는 Linux 안에서만 실행 |
| `E_CODEC_MISSING` | `build-non-sdr.sh --codec-only` 실행, 또는 `PWS_CODEC` 경로 확인 |
| `E_SCHEMA` | 출력 detail의 field를 확인. boolean과 문자열, `TEST`, `LAB_EXERCISE`, schema 1을 구분 |
| `E_ENCODING` | emoji/surrogate 대신 UCS-2 BMP 문자열 사용. UTF-8 YAML과 UCS-2 wire encoding은 구분 |
| `E_CODEC_OUTPUT` / `E_NONCANONICAL` | 외부 encoder/다른 SIB type/잘린 파일/UPER padding 문제. 원본 `offline-sib8.json`으로 재시험 |
| `E_NETWORK_ISOLATION` | network none 또는 namespace에서 실행. host network에서 retry하지 않음 |
| `E_GNB_START` | `gnb.log`의 첫 오류 확인. 실제 upstream schema와 CPU affinity/loopback bind 확인 |
| Docker named context 오류 | `build-docker.sh`로 runtime stage 생성. `lab_build=build/runtime/<mode>` 전달 |
| output permission 오류 | named volume UID 10001 소유권 확인. bind mount는 host에서 쓰기 권한 준비 |
| `E_DISCOVERY`, `E_NO_DEVICE`, driver -7 | USB 연결/VM passthrough/device node 확인. mock PASS와 혼동하지 않음 |
| `E_OPEN`, driver -5 | udev group, 실제 device 권한, 다른 프로그램의 점유 확인. 일반 USB I/O 실패도 가능 |
| `E_MODEL` | board `bladerf1`과 FPGA 40 KLE 필요. x115/micro는 지원하지 않음 |
| `E_VERSION_POLICY` | info의 FW/FPGA/library가 실험실 허용 조합인지 확인. 자동 flash하지 않음 |
| `E_USB_SPEED` | USB 3.0 포트·케이블·허브 및 `lsusb -t` 확인 |
| `E_ISOLATION` | mode/PA readback 검증 실패. loopback을 건너뛰고 RF test로 대체하지 않음 |
| `E_RX_MODE` | 앞선 firmware loopback 상태일 수 있음. USB 전원을 다시 연결한 후 info/verify/rx 실행 |
| `E_STREAM`/driver -6, `E_BUFFER` | transfer timeout, overrun/underrun. USB controller/host 부하 확인; 반복 결과와 timestamp 보존 |
| `E_TIMESTAMP` | RX block 간 sample counter 불연속. USB/FPGA/clock 및 buffer 오류 확인 |
| `E_DIAG_TIMEOUT` | 20초 watchdog. cleanup 완료를 가정하지 말고 장치 상태 확인 후 전원 재연결 |

문제 보고 시 application version, OCUDU commit, libbladeRF describe, FW/FPGA, OS/architecture, 실제 command, JSON과 관련 log를 포함한다. serial 등 장치 식별정보는 공개 issue에 첨부하기 전에 확인한다. message 원문은 audit에 기록하지 않지만 offline ASN.1 artifact에는 내용이 포함된다.

패치가 적용된 x40 전용 libbladeRF를 시스템의 일반 bladeRF driver로 교체하지 않는다. 프로젝트 build/deps 또는 SDR image 안에서만 사용한다. native 시스템 library와 혼용 시 `ldd build/bin/bladerf-x40-diag`로 실제 로드 경로를 확인한다.

## ZMQ 수신 오류

- `E_ZMQ_PROFILE`: 고정 config hash가 변경됐다. endpoint/radio를 임의 변경한 파일은 실행하지 않는다. 저장소의 검증된 config로 복원한다.
- `E_NETWORK_ISOLATION`: `docker run --network none` 또는 제공된 Compose를 사용한다.
- `E_ZMQ_EARLY_EXIT`: 같은 실행의 `gnb.log`, `srsue.log`를 확인한다. runtime shared library, config 오류 또는 메모리 제한 초과를 구분한다.
- `E_RX_TIMEOUT`: UE의 MIB decode와 SIB1 수신 marker가 모두 필요한데 제한 시간 안에 확인되지 않았다. CPU 사용량과 UE의 cell search 오류를 확인하며 PHY 시작 로그만으로 PASS 처리하지 않는다.
- `E_SHUTDOWN`: SIGINT 후 종료가 지연되거나 nonzero exit가 발생했다. 수신 marker가 있어도 전체 결과는 FAIL이다.

실제 AMF를 제공하지 않는 profile에서는 NAS registration timeout이 예상된다. 이 오류만으로 MIB/SIB1 수신이 실패했다는 뜻은 아니며 IP ping 성공은 이 시험의 검사 항목이 아니다.
