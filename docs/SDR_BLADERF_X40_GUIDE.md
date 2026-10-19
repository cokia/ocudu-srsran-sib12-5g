# SDR bladeRF x40 실행 가이드

이 모드는 standalone device diagnostics다. OCUDU gNB의 RF driver로 x40를 연결하지 않는다. PWS 검증은 같은 offline codec로 별도 실행한다.

## 준비

Linux Ubuntu 24.04, USB 3.0 SuperSpeed port, 적절한 케이블과 bladeRF x40가 필요하다. 가상 머신은 장치 passthrough를 별도로 설정해야 하며 Colima/macOS가 이를 지원한다고 가정하지 않는다. 하드웨어를 다른 SDR 프로그램과 동시에 열지 않는다.

```bash
sudo bash scripts/install-deps.sh sdr-bladerf-x40
bash scripts/bootstrap-python.sh
bash scripts/build-sdr.sh
bash scripts/build-non-sdr.sh --codec-only
```

원본 libbladeRF는 고정 commit을 별도 checkout하고 x40 전용 패치를 적용한다. `build/deps/lib/libbladeRF.so.2`에 동적 링크한다. native executable의 build RPATH가 이 디렉터리를 참조하므로 파일을 따로 이동하면 `LD_LIBRARY_PATH` 또는 install layout을 조정해야 한다.

## firmware/FPGA

[Nuand 공식 배포](https://www.nuand.com/support/)에서 x40용 hosted FPGA와 FX3 firmware를 별도로 준비한다. 이 실험실의 허용 조합은 libbladeRF 2.6.0 / firmware 2.6.0 / FPGA 0.16.0이다. version policy를 통과하지 못하면 info를 확인하고 operator가 공식 도구로 필요한 조치를 수행한다. 프로젝트에는 자동 flash 명령이나 firmware blob이 없다.

실제 장비 없이 다음 사항은 확인할 수 없다: FPGA가 현재 로드되어 있는지, bitstream이 정확한 x40 이미지인지, USB SuperSpeed 협상, timestamp 진행, sustained stream, PA readback, loopback pattern 동일성. mock 결과는 이 항목의 증거가 아니다.

## Linux udev 권한

원본 `host/misc/udev/88-nuand-bladerf1.rules.in`의 VID/PID를 확인했다. 이 프로젝트의 first-generation VID/PID 및 legacy VID/PID rule을 설치한다.

```bash
sudo groupadd -f bladerf
sudo usermod -aG bladerf "$USER"
sudo install -m 0644 hardware/bladerf-x40/88-pws-bladerf-x40.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

다시 로그인하고 USB를 분리/연결한 뒤 group 적용을 확인한다. bootloader의 Cypress VID/PID에 광범위한 권한을 부여하지 않는다. USB bus/device 번호는 재연결할 때 달라질 수 있다.

```bash
lsusb -t
ls -l /dev/bus/usb/BBB/DDD
bash scripts/run-sdr-diag.sh info --hardware
bash scripts/run-sdr-diag.sh capabilities --hardware
bash scripts/check-bladerf-x40.sh --hardware
```

`lsusb`가 없다면 host에 `usbutils`를 설치한다. 최종 속도 판단은 진단의 `device.usb == super-speed` 결과를 사용한다. `bladerf1` board와 FPGA size 40을 함께 확인한다. 여러 device가 있으면 `configs/bladerf-x40.yaml`의 `device.serial`을 지정한다.

## RX와 비방사 loopback

```bash
bash scripts/run-sdr-diag.sh rx --hardware
bash scripts/run-sdr-diag.sh loopback --hardware
```

RX는 TX를 disable한 상태에서 SC16_Q11_META 두 block의 timestamp 연속성과 buffer error를 검사한다. loopback은 firmware bypass, LMS PA disable readback, 허용 버전/USB를 모두 확인한 뒤 고정 I/Q만 사용한다. 지원/격리 확인 실패 시 SKIP 또는 FAIL이며 OTA로 바꾸지 않는다. 결과는 `output/sdr/<command>.json`, `<command>.txt`, `audit.jsonl`에 남는다.

loopback은 원래 normal mode로 자동 복원하지 않는다. 이어서 RX timestamp 검사를 하려면 전원 재연결 후 info/verify부터 반복한다. timeout 또는 disconnect가 발생하면 cleanup 확인 전 다른 stream을 시작하지 않는다. 이 절차의 소프트웨어 격리 확인은 계측기를 사용한 RF emission 측정과 동일하지 않다.

## Mock 및 offline PWS

```bash
bash scripts/run-sdr-diag.sh loopback --mock
bash scripts/run-sdr-diag.sh loopback --mock --fault timeout
bash scripts/test-sdr.sh
.venv/bin/python -m controller validate --mode sdr-bladerf-x40 --output output/sdr-pws
```

libbladeRF 없이 diagnostic interface만 빌드하려면 `scripts/build-sdr.sh --mock-only`를 사용하고 `BLADERF_DIAG=build/bin/bladerf-x40-diag-mock`를 지정한다. no-device, permission, wrong-model, x115, firmware, fpga, usb2, unsafe, disconnect, timeout, corrupt, overrun, timestamp, cleanup fault를 제공한다. normal GitHub runner는 이 mock 경로만 실행한다.

## Docker

```bash
bash scripts/build-docker.sh sdr-bladerf-x40
docker compose -f docker/compose.yaml --profile sdr-bladerf-x40 up
```

기본 profile은 USB를 전달하지 않고 mock으로 실행한다. 실제 Linux host에서 특정 device node만 전달하려면:

```bash
export BLADERF_USB_DEVICE=/dev/bus/usb/001/005
export BLADERF_USB_GID=$(getent group bladerf | cut -d: -f3)
docker compose -f docker/compose.yaml -f docker/compose.hardware.yaml \
  --profile sdr-bladerf-x40 run --rm diagnostics info --hardware
```

예시 USB 경로는 실제 장치 경로로 바꾼다. `privileged`, 전체 `/dev`, host networking은 필요하지 않다. 컨테이너 group에 host udev group GID를 추가한다. 재연결 후에는 새 device node로 컨테이너를 다시 생성한다. `sdr-offline` 서비스에는 USB mapping을 추가하지 않는다.

## 미지원

OCUDU bladeRF RU plugin, 외부 RF TX, live PWS/CMAS, 주파수/gain 조정 CLI, firmware flash, bladeRF 2.0/x115, GPS/PTP/PPS timing 보장, full-duplex PHY 성능 보장은 제공하지 않는다. 실제 하드웨어 미연결 시 `BLOCKED`는 예상 결과이며 PASS로 바꾸지 않는다.
