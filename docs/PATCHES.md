# 재현 가능한 upstream 패치

기준 commit을 바꾸지 않고 필요한 수정만 `patches/`에 보관한다. 원본 저작권·license header를 유지한다. OCUDU/srsUE patch는 `dependencies.lock.json`에 patch 파일, 원본 source, 적용 후 source의 SHA256을 모두 고정한다. `fetch-upstream.py`는 clean 원본 또는 정확히 일치하는 patched 상태만 허용한다. 다른 사용자 변경은 `E_UPSTREAM_DIRTY`로 중단하며 덮어쓰지 않는다. 적용은 idempotent이며 임시 Git repository에서 이 조건들을 테스트한다.

## OCUDU main pool

- 파일: `patches/ocudu-main-pool.patch`
- 기준: `e0db566aac6e6376ddd60e83c84f58698fcc4d70`
- 수정: `apps/services/worker_manager/worker_manager.cpp::get_default_nof_workers`
- 문제: 4 CPU host에서 자동 계산은 CPU 3개를 예약해 main pool을 1 worker로 줄인다. 명시한 `nof_threads`도 같은 제한에 걸린다. ZMQ의 synchronous cell executor가 같은 pool에 task를 넣고 기다리면 실행할 다른 worker가 없어 DU 시작이 정지한다.
- 수정 내용: 명시적 worker 수는 가용 CPU 수 안에서 허용한다. 명시하지 않은 자동 계산은 기존과 같다. ZMQ config에서 upstream에 존재하는 `expert_execution.threads.main_pool.nof_threads: 2`를 설정한다.
- 관찰 근거: `artifacts/zmq/threads-before-fix.json`의 main worker futex 대기와 `rx/gnb.log`의 마지막 scheduler activation. 수정 후 `rx-pool-fix/gnb.log`에서 2 workers, DU-High 시작, gNB 시작 및 정상 종료를 확인했다.

이 패치는 물리 driver, PWS, ASN.1, scheduler payload를 수정하지 않는다. 1 CPU만 가용한 환경은 해당 synchronous 경로에 충분하지 않으므로 최소 2 CPU가 필요하다. 검증 환경은 4 CPU VM이다.

## srsUE FFTW 계획 생성

- 파일: `patches/srsue-fftw-estimate.patch`
- 기준: `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16`
- 수정: `lib/src/phy/dft/dft_fftw.c`의 `FFTW_TYPE` 한 줄
- 문제: cold start의 `FFTW_MEASURE`가 이 ARM64 VM에서 PHY 초기화 시간을 크게 늘렸다. instrumentation에서 첫 1,536-point plan 생성만 약 **26.6초**를 사용했다. 120초 전체 수신 한도에서도 UE 초기화가 끝나지 않았다.
- 수정 내용: 실험용 srsUE의 계획 방식을 `FFTW_ESTIMATE`로 고정한다. FFTW 공식 API에서 지원하는 heuristic 계획이며 초기 benchmark를 생략한다. FFT 연산, RF format, ASN.1 구조를 대체하거나 수신 marker를 만들지 않는다.
- 관찰 근거: `artifacts/zmq/fftw-trace.log`, `rx-pool-fix/zmq-rx.json`. instrumentation은 로컬 artifact에만 있고 최종 runtime에는 포함하지 않는다.

`ESTIMATE`는 실행 시 최적 plan을 보장하지 않으므로 throughput 비교용 설정으로 해석하지 않는다. 계획 방식의 의미는 [FFTW 공식 Planner Flags](https://www.fftw.org/fftw3_doc/Planner-Flags.html)를 따른다. 최종 정확성 판정은 실제 UE MIB/SIB1 decode로 수행한다.

## bladeRF x40 전용 빌드

기존 `patches/bladerf-x40-only.patch`는 별도 `build/bladerf-source` 사본에 적용한다. AD936x와 bladeRF 2.0 micro 의존성을 제외하는 범위이며 API 전체를 구현했다고 주장하지 않는다. 세부 내용은 [x40 조사](BLADERF_X40.md)를 따른다.

## 배포와 관리

base commit만으로 patched binary를 완전히 설명할 수 없으므로 patch 목록과 hash도 함께 배포한다. `build/runtime/<mode>/manifest.json`에는 전체 dependency lock과 executable hash를 보관한다. `scripts/package-source.sh`는 base와 patch가 적용된 대응 source 및 프로젝트 patch 파일을 포함한다. upstream merge나 외부 issue 작성은 수행하지 않았다.

## srsUE SIB8 SI monitor

모든 patch의 기준은 `6bcbd9e5bf8686aa7085202cd847c5ddd64a9c16`이며 원본/적용 결과/patch hash를 lock에 고정했다.

| patch | source | 변경 |
|---|---|---|
| `srsue-sib8-monitor.patch` | `srsue/src/stack/rrc_nr/rrc_nr.cc` | SIB8 ASN.1 metadata/payload 로그, SIB1의 other-SI search space |
| `srsue-si-monitor.patch` | `srsue/src/stack/rrc_nr/rrc_nr_procedures.cc` | 환경변수 opt-in 시 SIB1 이후 SI-RNTI 감시 유지 |
| `srsue-si-dci.patch` | `srsue/src/phy/nr/cc_worker.cc` | 겹치는 common search에서 SI indicator 1을 Type0A로 분류 |
| `srsue-type0a-time.patch` | `lib/src/phy/phch/ra_dl_nr.c` | 미구현 Row 2를 common time allocation list/Default A로 구현; list 범위 검사 |
| `srsue-other-si-dmrs.patch` | `lib/src/phy/phch/ra_nr.c` | SIB1만 CORESET0 DMRS 기준점을 사용; other SI는 CRB0 |

Type0A는 [TS 38.214 V16.5.0 Table 5.1.2.1.1-1](https://www.etsi.org/deliver/etsi_ts/138200_138299/138214/16.05.00_60/ts_138214v160500p.pdf), DMRS는 [TS 38.211 V15.2.0 §7.4.1.1.2](https://etsi.org/deliver/etsi_ts/138200_138299/138211/15.02.00_60/ts_138211v150200p.pdf)를 근거로 한다. 패치 전 실제 DCI는 잡혔으나 other SI의 PDSCH CRC가 실패했다. patch 후 실제 SIB8 수신·한글 복원·15 segments 재조립이 PASS다. marker만 삽입하거나 PHY 결과를 대체하지 않았다.

SI monitor는 opt-in이며 기존 연결 모드 회귀도 PASS다. time-allocation/DMRS 수정은 해당 PHY 의미에 맞게 공통 구현에 적용했다. 검증 profile은 n3 FDD, normal CP, SCS 15 kHz, CORESET multiplexing pattern 1에 한정한다. upstream의 다른 미구현 Row, 모든 carrier offset/CORESET 조합까지 해결한 것은 아니다.

## generic CPU의 빈 feature 목록

기존 GitHub `build` run `39238015007`에서 `-march=x86-64`의 `cpu_features.h`가 `to_array<cpu_feature>({})`의 길이를 추론하지 못해 컴파일에 실패했다. `patches/ocudu-empty-cpu-features.patch`는 고정 feature 목록을 빈 경우도 허용하는 `constexpr std::initializer_list`로 바꾼다. CPU 필수 instruction을 추가하거나 runtime feature 검사를 제거하지 않는다. hash와 source `include/ocudu/support/cpu_features.h`는 lock에 고정했다.

ARM64의 feature macro를 비활성화한 별도 compile probe에서 원본의 동일 오류와 수정 후 empty-list compile 성공을 확인했다. 실제 ARM64 gNB도 재빌드했다. GitHub x86-64 전체 빌드 결과는 해당 새 CI run에서 별도 확인해야 한다.

## LTE SIB12 monitor와 종료 수정

기준 srsRAN 4G commit은 위와 같으며 patch와 원본·적용 결과 hash를 `dependencies.lock.json`에 고정한다.

| patch | source | 변경 |
|---|---|---|
| `srsenb-sib12-segments.patch` | `srsenb/src/enb_cfg_parser.cc` | vector 재할당 전에 ID/serial 복사, dangling reference 제거 |
| `srsue-lte-sib12.patch` | `srsue/src/stack/rrc/rrc.cc` | 실제 ASN.1에서 SIB1 PLMN/SIB12 payload 로그, monitor에서 SIB2 재설정 생략 |
| `srsue-lte-si-rnti.patch` | `srsue/src/stack/mac/mac.cc` | monitor에서 모든 TTI의 SI-RNTI 수신 유지 |
| `srsue-lte-si-monitor.patch` | `srsue/src/stack/rrc/rrc_procedures.cc` | SIB1 선행 수신 및 SI acquire 완료 두 경로 모두 attach 진입 억제 |
| `srsue-lte-stop-deadlock.patch` | `srsue/src/phy/sync.cc` | `intra_freq_cfg_mutex`를 SYNC thread join 전에 해제 |

LTE monitor는 `PWS_LAB_LTE_SI_MONITOR=1`로 명시적으로 켠다. 정상 종료 수정은 LTE PHY 공통 코드에 적용한다. GDB에서 main thread의 `sync::stop()`/join과 SYNC thread의 `radio_recv_fnc()`/mutex 대기가 서로 막히는 것을 확인했다. 기존 5초 signal watchdog을 늘려 숨기지 않고 lock 범위를 수정한다. eNB의 UE disconnect 이후 대기는 upstream의 `fail_on_disconnect=true,trx_timeout_ms=1000` 설정으로 제한한다. 상세 결과는 [LTE 검증](LTE_SIB12_VERIFICATION.md)을 참조한다.

x86 CI의 SSE4.1 요구 조건과 build target 수정은 [CI 진단](CI_DEBUG.md)에 설명한다.
