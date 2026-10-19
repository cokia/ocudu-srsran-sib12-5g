# GitHub Actions 실패 진단

2026-10-20 확인한 run `39286994794`의 Non-SDR build 실패는 `-march=x86-64` 설정이 OCUDU의 새 MxN SIMD equalizer 요구 조건을 만족하지 않아서 발생했다. ARM64 NEON 환경에서는 드러나지 않았고 GitHub-hosted x86-64 runner에서 `simd_cf_t`, `simd_f_t` 미정의 오류가 발생했다. 같은 run의 SDR image build와 별도 software workflow는 성공했다.

고정 OCUDU `e0db566aac6e6376ddd60e83c84f58698fcc4d70`의 `include/ocudu/ocuduvec/simd.h`는 x86에서 `__SSE4_1__`이 있을 때 SIMD 형식을 제공한다. `lib/phy/upper/equalization/channel_equalizer_generic_impl.cpp`의 MxN 구현은 SIMD를 전제로 한다. SSE4.1이 없는 scalar target을 지원한다고 가정한 build script가 원인이었다.

`scripts/build-non-sdr.sh`, `scripts/build-zmq.sh`의 x86 target을 `x86-64-v2`로 고정한다. 이 binary는 x86-64-v2 이상 CPU가 필요하다. `native`를 사용하지 않으므로 빌드 runner의 AVX-512 기능에 따라 요구 CPU가 달라지지 않는다. ARM64는 기존 `armv8-a`/NEON을 유지한다. equalizer target을 전체 gNB보다 먼저 컴파일하고 이 검사에 120초 제한을 둔다. SIMD 설정 오류가 전체 compile 28분 뒤에야 드러나는 문제를 줄인다.

오류 로그는 GitHub step stdout 대신 upload artifact의 `artifacts/checkpoints/docker-non-sdr.log`에 저장되어 있었다. 확인 명령:

```bash
gh run view 39286994794 --log-failed
gh run download 39286994794 -n build-non-sdr -D artifacts/ci-debug/build-53ecdd7
rg 'FAILED:|error:' artifacts/ci-debug/build-53ecdd7
```

수정 후 전체 CI 결과는 아래에 기록한다. 이전 run의 실패는 수정 commit 이후에도 역사로 보존된다.

GitHub build에는 명시적으로 4 jobs / 4 CPUs / 8 GiB를 배정한다. native와 기본 Docker build는 2 jobs / 4 GiB를 유지하며 `LAB_BUILD_JOBS=1..4`, `LAB_BUILD_MEMORY=4g|6g|8g` 범위만 받는다. 기존 x86 실패가 934/1444 compile 단계까지 28분 걸렸으므로, gNB와 srsUE를 연속 빌드하는 PWS 작업이 동일한 2 CPUs/45분 제한에 걸릴 가능성도 줄인다. 총 실행 제한은 늘리지 않는다.

실패한 checkpoint는 마지막 80줄(최대 16 KiB)을 GitHub step stderr에 출력한다. 전체 원본은 artifact에 그대로 남긴다. 컴파일 오류를 다운로드 후에만 볼 수 있었던 문제를 개선한다.

## 출력 폴더 소유권

`6cf85fb`의 LTE run `39292864371`은 x86-64 C++ 및 Docker build를 완료했으나 runtime 직전 `mkdir artifacts/lte-sib12/docker: Permission denied`로 실패했다. build container가 root 소유로 만든 bind-mount 출력 폴더가 원인이다. host build wrapper에서 결과 폴더를 먼저 만들어 runner의 소유권을 유지한다. 같은 구조의 NR PWS/radio-plugin, ZMQ, 독립 mode wrapper에도 적용한다. `chmod 777`, privileged runtime 또는 sudo로 수신 시험을 실행하는 방법을 사용하지 않는다.

## 최종 GitHub 검증

2026-10-20 KST, 코드 commit **`5db83a8be254c6ac23b4442b1f60d41a7ca97896`**의 push workflow 네 개가 모두 완료되어 **PASS**임을 확인했다. 이후 이 결과를 기록하는 문서 전용 commit은 실행 코드 변경을 포함하지 않는다. runner는 GitHub-hosted Ubuntu 24.04 x86-64이며 실제 SDR은 연결하지 않았다.

| Workflow | 결과 | 실행 증거 |
|---|---|---|
| 소프트웨어 검사 | PASS | [run 39294395549](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39294395549): lint, protocol/mock, 실제 libbladeRF library 및 adapter 검사 |
| 독립 모드 빌드 및 Docker | PASS | [run 39294395503](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39294395503): Non-SDR gNB와 SDR diagnostic 이미지 각각 build/runtime |
| LTE SIB12 ZMQ 수신 | PASS | [run 39294395555](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39294395555): srsENB/srsUE build, 한글 수신, 정상 종료 |
| PWS ZMQ 수신과 radio plugin | PASS | [run 39294395537](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39294395537): OCUDU/srsUE 한글 SIB8 수신, OCUDU plugin mock stream |

GitHub API의 commit·job·step 결과와 실행 시각은 [results.json](evidence/2026-10-20/github-ci/results.json)에 보존했다. 선택한 원본 artifact의 [SHA256SUMS](evidence/2026-10-20/github-ci/SHA256SUMS)로 무결성을 확인할 수 있다.

실제 runtime 결과:

- [Dummy RU gNB](evidence/2026-10-20/github-ci/non-sdr-gnb.json): 초기화 및 graceful shutdown PASS. 별도 [offline PWS](evidence/2026-10-20/github-ci/non-sdr-pws.json) 왕복·결정성 검사 PASS.
- [LTE SIB12](evidence/2026-10-20/github-ci/lte-lte-sib12.json)와 [NR SIB8](evidence/2026-10-20/github-ci/nr-pws-integration.json): 실제 수신 PLMN `45005`, ID `4372`, 복원 text `[시험 데이터] PWS 프로토콜 검증 메시지입니다.`, 양쪽 process exit `0`. 원본 [LTE srsUE](evidence/2026-10-20/github-ci/lte-srsue.log)·[NR srsUE](evidence/2026-10-20/github-ci/nr-srsue.log) 로그를 함께 보존한다.
- [radio plugin mock](evidence/2026-10-20/github-ci/radio-mock-radio-smoke.json): RX 51,859,456 / TX 51,862,740 samples, error/late/overflow/underflow 모두 0. 물리 장비 및 이 mock 경로의 receiver decode는 NOT VERIFIED다.
- Python suite는 [Non-SDR 188개](evidence/2026-10-20/github-ci/software-non-sdr.xml), [SDR 199개](evidence/2026-10-20/github-ci/software-sdr.xml)가 각각 통과했다. 두 suite는 공유 검사를 포함하므로 합산한 고유 test 수가 아니다. local 전체 214개 검사는 [LTE 검증 보고서](LTE_SIB12_VERIFICATION.md)에 별도 기록했다.
- 실제 libbladeRF upstream library 검사 5개, [adapter contract 22개](evidence/2026-10-20/github-ci/libbladerf-adapter.xml), [plugin 9개](evidence/2026-10-20/github-ci/radio-plugin.xml), [USB API contract 13개](evidence/2026-10-20/github-ci/radio-usb.xml)가 통과했다. 실제 장치에 대한 송수신 검증을 의미하지 않는다.

가장 긴 [PWS 통합 build checkpoint](evidence/2026-10-20/github-ci/pws-build-checkpoint.json)는 2,293.663초로 2,700초 제한 안에서 완료됐다. 제한 초과 시 계속 재시도하거나 PASS로 바꾸지 않는다. 실패하면 저장된 checkpoint의 마지막 오류와 전체 log를 확인한다.
