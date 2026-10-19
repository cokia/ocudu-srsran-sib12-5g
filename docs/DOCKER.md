# Docker 실행과 재현

세 runtime Dockerfile이 있다: `Dockerfile.non-sdr`(gNB), `Dockerfile.sdr`(x40 diagnostic + offline codec), `Dockerfile.controller`(offline codec). 공통 compiler 환경은 `Dockerfile.build`, 작은 Python/runtime 환경은 multi-stage `Dockerfile.runtime`이다.

## Source부터 빌드

```bash
bash scripts/build-docker.sh controller
bash scripts/build-docker.sh non-sdr
bash scripts/build-docker.sh sdr-bladerf-x40
```

compiler 컨테이너가 host workspace의 `build/`에 Linux 바이너리를 생성한다. native macOS 바이너리를 가져오는 것이 아니다. stage script가 binary SHA256, upstream pin, apt package 목록, bladeRF patch hash를 기록한다. named context가 가리키는 `build/runtime/<mode>`만 runtime 이미지에 복사한다. build cache를 재사용해도 최종 image tag는 동일 application version을 사용한다.

같은 workspace의 build 명령과 host-mounted binary를 사용하는 테스트는 순서대로 실행한다. 빌드가 `build/bin`의 executable을 교체하는 동안 테스트하면 `Text file busy`가 발생할 수 있다. CI의 모드별 job은 독립 workspace를 사용한다.

이미 compile한 결과로 controller 이미지를 다시 조립하는 예:

```bash
docker run --rm -v "$PWD:/lab" pws-lab-toolchain:0.1.0 \
  python3 scripts/stage-runtime.py controller
docker build --build-context lab_build=build/runtime/controller \
  -f docker/Dockerfile.controller -t pws-lab-controller:0.1.0 .
```

runtime Dockerfile에 `lab_build` named context 없이 직접 `docker build`하면 실패한다. compiler/toolchain build와 image assembly를 잇는 공식 진입점은 `build-docker.sh`다. 인터넷은 build dependency 다운로드 단계에만 필요하며 모든 runtime test는 `network none`으로 실행한다.

## 두 Compose profile

```bash
docker compose -f docker/compose.yaml --profile non-sdr up
docker compose -f docker/compose.yaml --profile sdr-bladerf-x40 up
```

Non-SDR의 `gnb`와 `offline`은 같은 output volume을 사용하지만 서로 연결되지 않는다. SDR의 `diagnostics`와 `sdr-offline`도 프로세스와 output subdirectory가 분리된다. gNB는 30초 smoke 실행 후 종료하고 나머지는 one-shot 진단/검증이다. `restart: always`는 설정하지 않는다.

기본 profile은 non-root UID 10001, read-only config/root filesystem, drop ALL capabilities, no-new-privileges, network none을 사용한다. output named volume은 write 가능하다. gNB `/tmp`만 tmpfs이며 USB mapping은 없다.

## 실제 USB 접근

`compose.hardware.yaml`을 명시적으로 추가하고 `BLADERF_USB_DEVICE`, `BLADERF_USB_GID`를 설정해야 한다. 단일 `/dev/bus/usb/BBB/DDD` node를 전달한다. host udev/group 설정은 [SDR 가이드](SDR_BLADERF_X40_GUIDE.md)를 따른다. macOS VM의 USB passthrough는 검증되지 않았으며 Docker Desktop/Colima만 설치했다고 USB 접근이 가능하다고 보고하지 않는다.

## 로그/결과 추출

```bash
docker compose -f docker/compose.yaml --profile non-sdr logs --no-color
mkdir -p artifacts/compose
docker compose -f docker/compose.yaml cp gnb:/lab/output/non-sdr artifacts/compose/
docker compose -f docker/compose.yaml cp offline:/lab/output/validate-non-sdr.json artifacts/compose/
bash scripts/stop.sh
```

`down`은 named volume을 지우지 않는다. 필요할 때 operator가 해당 project volume만 명시적으로 삭제한다. global image/volume prune은 수행하지 않는다.

## 검증 범위

빌드 로그, 실제 image 실행, Compose profile의 exit code를 따로 기록한다. image build 성공만으로 gNB startup이나 hardware streaming 성공을 주장하지 않는다. GitHub Actions는 Linux x86_64에서 두 모드 이미지를 별도 job으로 빌드하고 mock/runtime 검사한다. 실제 실행 환경/결과는 [최종 보고서](IMPLEMENTATION_REPORT.md)를 참조한다.

## ZMQ 수신 확장

OCUDU와 srsUE를 함께 실행하는 별도 이미지는 `scripts/build-zmq-docker.sh`로 생성한다. `docker/compose.zmq.yaml`은 자체 output volume, `network none`, UID 10001, read-only root와 `cap_drop: ALL`을 사용한다. USB, TUN, privileged 설정이 없다. 빌드·실행·로그 수집 명령은 [ZMQ 수신 가이드](ZMQ_SRSUE.md)를 참조한다.
