# bladeRF x40 하드웨어와 호환성

대상은 첫 세대 **Nuand bladeRF x40**이다. `bladerf_get_board_name() == "bladerf1"`과 `bladerf_get_fpga_size() == BLADERF_FPGA_40KLE`를 함께 검사한다. USB product 문자열만으로 x40/x115를 구분하지 않는다. bladeRF 2.0 micro, xA4/xA9, x115, USRP는 이 애플리케이션의 대상이 아니다.

## 확인한 구조

[Nuand FPGA 개발 문서](https://github.com/Nuand/bladeRF/wiki/FPGA-Development), [원래 bladeRF brief](https://www.nuand.com/bladeRF-brief.pdf), 고정 libbladeRF source를 확인했다.

| 항목 | 조사 결과 |
|---|---|
| USB | Cypress FX3 USB 3.0, 진단은 `bladerf_device_speed()`의 SuperSpeed 요구 |
| RFIC | LMS6002D, 1 RX / 1 TX |
| FPGA | Altera/Intel Cyclone IV E, x40는 40 KLE |
| clock | 38.4 MHz VCTCXO, Si5338, external clock 경로. 시간 동기화 지원은 단순 USB detection과 별개 |
| sample format | 앱 지원: `BLADERF_FORMAT_SC16_Q11`, `BLADERF_FORMAT_SC16_Q11_META` |
| sample rate | `bladerf1_sample_rate_range`의 80 kS/s..40 MS/s 권장 범위를 조회. 테스트는 1 MS/s 고정 |
| sample 크기 | 16 bit I + 16 bit Q = complex sample당 4 byte. 1 MS/s는 방향당 4 MB/s이며 duplex payload 약 8 MB/s; USB/metadata overhead 별도 |
| timestamp | FPGA ≥0.1.0에서 capability 표시. `bladerf_get_timestamp()`는 coarse counter이고 block timing은 metadata로 확인해야 함 |
| sync interface | `bladerf_sync_config`, `bladerf_sync_rx`, `bladerf_sync_tx`, `bladerf_enable_module` |
| buffer | sync API가 내부 async buffer를 관리. 8 buffers, 4,096 samples/buffer, 4 transfers, timeout 1,000 ms |
| loopback | firmware(FX3), LMS baseband, LMS RF mode가 존재. 이 앱은 firmware만 허용 |

40 MS/s의 양방향 payload 계산은 약 320 MB/s이며 host memory copy·USB controller·케이블·FPGA 동작을 포함한 실제 지속 throughput 보장이 아니다. x40 bandwidth/clock 한계와 OCUDU slot deadline은 별도 측정해야 한다.

## 버전 정책

소스 commit `09c82087786702d2812f3f0fc909beccf3277233`, `libbladeRF_v2.6.0`을 고정한다. 실험실 hardware verification/streaming 허용 조합은 **libbladeRF 2.6.0 + FX3 FW 2.6.0 + hostedx40 FPGA 0.16.0**이다. 이는 모든 기존 bladeRF 버전의 일반 최소 요건이라는 의미가 아니다.

원본 `host/libraries/libbladeRF/src/board/bladerf1/compatibility.c`는 FW/FPGA 양방향 호환 표를 제공한다. FW 2.6.0은 FPGA ≥0.16.0을 요구하고 FPGA 0.16.0 관련 표에는 FW 2.6.0/2.5.0 항목이 있다. `capabilities.c`는 firmware loopback ≥1.7.1, timestamp FPGA ≥0.1.0 등을 검사한다. 이 앱은 오래된 모든 조합을 시험하지 않았으므로 위 단일 조합 외에는 `E_VERSION_POLICY`를 반환한다.

공식 [firmware/FPGA 다운로드](https://www.nuand.com/support/)는 operator가 별도로 수행한다. `hostedx40.rbf`와 x115/xA 계열 bitstream을 혼동하지 않는다. 프로젝트는 다운로드·flash·자동 FPGA 로드를 실행하는 기능을 제공하지 않는다. libbladeRF 자체가 설치 prefix의 파일을 탐색할 수 있으므로 operator는 자동 로드 파일의 출처와 버전을 확인해야 한다. hardware 버전 문자열만으로 bitstream 파일의 SHA256 또는 RF 물리적 무방사를 증명하지 않는다.

## firmware loopback 격리

고정 소스 `bladerf1.c::bladerf1_set_loopback`의 firmware mode는 sample을 FX3에서 되돌려 LMS에 전달하지 않는다. `fpga_common/src/lms.c::lms_set_loopback_mode`와 `lms_select_pa`의 PA 처리를 조사했다.

실행 순서는 모델/버전/USB 확인 → RX/TX 비활성화 → firmware loopback 선택 → mode readback과 LMS register 0x44의 외부 PA enable bit 확인 → buffer 구성 → enable → 격리 재확인 → 고정 I/Q 패턴 전송/수신 → 동일성 검사 → 격리 재확인 → RX/TX disable이다. 조건 실패 시 SKIP/FAIL이며 다른 RF loopback이나 OTA로 대체하지 않는다.

firmware loopback은 FPGA timestamp 경로를 우회하므로 해당 테스트의 timestamp consistency는 **SKIP**이다. 실제 RX timestamp 검사는 `rx` 명령으로 별도 수행하며 TX는 활성화하지 않는다. firmware loopback 후 mode를 normal로 자동 복원하지 않기 때문에 RX 검사 전 전원 재연결이 필요할 수 있다.

## x40 전용 libbladeRF 패치

upstream의 `BUILD_AD936X=OFF`만으로는 ad936x subdirectory 처리 및 공용 소스의 micro symbol 참조가 남는다. `patches/bladerf-x40-only.patch`는 다음을 수행한다.

1. AD936x subdirectory를 해당 옵션으로 guard한다.
2. 사용하지 않는 utilities(update/CLI 등) build를 제외한다.
3. board registry에서 bladerf2를 제외한다.
4. 불필요한 AD936x `common.h` include를 표준 헤더로 대체한다.
5. 공용 code가 참조하는 7개 micro 전용 API는 `BLADERF_ERR_UNSUPPORTED`를 반환한다.

원본 checkout은 변경하지 않고 `build/bladerf-source`에 패치를 적용한다. API/ABI 일반 호환 driver로 배포하지 않으며 이 프로젝트의 x40 diagnostic 전용이다. AD936x/no-OS submodule은 가져오지 않는다.

## OCUDU 호환성 평가

OCUDU `radio_session`은 단순 IQ read/write 이상의 timed streaming, start alignment, discontinuity notification 및 stop contract를 요구한다. CF32 계열 baseband buffer와 SC16_Q11 scaling, USB latency, timestamp conversion, clock drift, underrun recovery는 실측되지 않았다. **OCUDU bladeRF RU plugin은 미구현이며 호환성은 NOT VERIFIED**다. SoapySDR로 이 문제를 해결했다고 가정하지 않는다. 이 단계의 작동 산출물은 standalone 진단 executable과 공통 offline protocol engine이다.
