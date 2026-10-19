# 설치

지원 실행 기준은 Ubuntu 24.04 LTS의 x86_64 또는 ARM64이다. 실제 개발 검증은 macOS ARM64 호스트의 Colima Linux ARM64 환경에서 수행했다. OCUDU native macOS build는 지원 범위에 넣지 않는다.

## 요구 환경

- Git, Docker Engine, BuildKit named context 지원, Docker Compose v2 이상.
- Native 실행은 Ubuntu 24.04, Python 3.12, CMake 3.28, Clang 18, Ninja.
- 빌드에 4 GiB 이상 메모리, 2 CPU 이상, 여유 공간 약 10 GiB 이상 권장. 실제 사용량은 host/compiler/cache에 따라 달라진다.
- Non-SDR 모드에는 bladeRF, libbladeRF, SoapySDR, USRP, 실제 AMF가 필요하지 않다.
- SDR hardware는 별도 Linux USB 3.0 host와 bladeRF x40가 필요하다. macOS VM에 USB 장치가 자동 전달된다고 가정하지 않는다.

## Native 준비

```bash
sudo bash scripts/install-deps.sh non-sdr
bash scripts/bootstrap-python.sh
python3 scripts/fetch-upstream.py ocudu
bash scripts/build-non-sdr.sh
bash scripts/test-non-sdr.sh
```

`install-deps.sh`는 `/etc/apt`의 Ubuntu archive 설정을 고정 snapshot으로 바꾼다. 개발용 전용 Ubuntu 환경에서 사용한다. snapshot은 `20261001T000000Z`이며 bootstrap CA package는 `20240203`이다. 전체 실제 package 버전은 `docs/dependencies.ubuntu-arm64.tsv`에 기록한다. 기존 checkout의 commit이 다르거나 tracked source가 변경되면 fetch script가 덮어쓰지 않고 종료한다.

Python 의존성은 `requirements.txt`, 개발 도구는 `requirements-dev.txt`에 고정되어 있다. Python 3.12 기준의 전체 목록은 `docs/dependencies.python-linux.txt`다. `nlohmann-json3-dev`는 C++ diagnostic/codec용이며 OCUDU 외부 API를 대신 구현하는 용도가 아니다.

## Docker 준비

```bash
bash scripts/build-docker.sh controller
bash scripts/build-docker.sh non-sdr
bash scripts/build-docker.sh sdr-bladerf-x40
```

세 명령은 독립적이다. Non-SDR build가 없어도 SDR image를 만들 수 있으며 SDR build는 gNB target 대신 공유 codec만 빌드한다. Docker toolchain에는 공통 빌드 도구와 libusb 개발 헤더가 있으나 Non-SDR executable은 libbladeRF에 링크하지 않는다.

`build-docker.sh`는 고정 compiler 컨테이너에서 source를 빌드하고, binary hash/패키지 manifest를 생성한 뒤 named context `lab_build`를 runtime Dockerfile에 제공한다. Dockerfile만 직접 호출하려면 이 named context를 먼저 생성해야 한다. 예제는 [Docker 가이드](DOCKER.md)를 참조한다.

## 재현성 범위

OCUDU/bladeRF commit, Python 버전, Ubuntu base digest와 apt snapshot을 고정했다. CPU별 compiler output의 bit-for-bit 동일성을 주장하지 않는다. ARM64와 x86_64 결과는 별도 바이너리이며 CI는 x86_64를 검사한다. 실제 실행한 compiler/container 결과는 [최종 보고서](IMPLEMENTATION_REPORT.md)에 기록한다.

의존성 소스/라이선스를 보존한 GitHub 배포 절차는 [제3자 고지](../THIRD_PARTY_NOTICES.md)를 따른다. `upstream/`, build, output, 개인 설정은 `.gitignore`로 공개 source tree에서 제외한다.

## 추가 개발 도구

실제 library에 링크하는 장비 없는 검사는 [libbladeRF 검증](LIBBLADERF_TESTING.md), Docker ZMQ와 srsUE의 NR MIB/SIB1 검사는 [ZMQ 수신 가이드](ZMQ_SRSUE.md)를 따른다. ZMQ compiler 이미지는 기존 toolchain에 `libzmq3-dev`, `libboost-program-options-dev`를 추가한다. apt snapshot은 기존과 같은 `20261001T000000Z`이며 정확한 설치 버전은 `artifacts/zmq/packages.tsv`와 runtime manifest에 기록한다.
