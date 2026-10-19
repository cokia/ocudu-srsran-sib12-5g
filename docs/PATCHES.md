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
