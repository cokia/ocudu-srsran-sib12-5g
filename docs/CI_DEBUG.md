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

수정 후 전체 CI 결과와 추가 발견 사항은 검증 완료 시 이 문서에 기록한다. 이전 run의 실패는 수정 commit 이후에도 역사로 보존된다.

GitHub build에는 명시적으로 4 jobs / 4 CPUs / 8 GiB를 배정한다. native와 기본 Docker build는 2 jobs / 4 GiB를 유지하며 `LAB_BUILD_JOBS=1..4`, `LAB_BUILD_MEMORY=4g|6g|8g` 범위만 받는다. 기존 x86 실패가 934/1444 compile 단계까지 28분 걸렸으므로, gNB와 srsUE를 연속 빌드하는 PWS 작업이 동일한 2 CPUs/45분 제한에 걸릴 가능성도 줄인다. 총 실행 제한은 늘리지 않는다.

실패한 checkpoint는 마지막 80줄(최대 16 KiB)을 GitHub step stderr에 출력한다. 전체 원본은 artifact에 그대로 남긴다. 컴파일 오류를 다운로드 후에만 볼 수 있었던 문제를 개선한다.
