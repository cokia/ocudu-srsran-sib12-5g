# 국내 휴대폰 안전안내문자 시험의 호환성 평가

조사일: 2026-10-19. radio plugin과 PWS scheduler 연결을 추가 구현했다. 실제 국내 휴대폰 기본 재난문자 화면과 x40 timing은 아직 검증되지 않았다. ZMQ에서 ID 4372의 실제 한글 SIB8 수신은 PASS다. [추가 구현 결과](RADIO_PWS_REPORT.md)를 기준으로 소프트웨어 구현과 실물 검증을 구분한다.

2026-10-20 추가: PWS 연동의 기본 PLMN은 `45005`(SKT), 선택값은 `45008`(KT), `45006`(LG U+)다. SIB1의 MCC/MNC와 SIB8 한글 수신을 함께 검사한다. [설정 방법](PWS_INTEGRATION.md)과 [실행 결과](KOREAN_PLMN.md)를 참조한다. PLMN 변경만으로 실제 가입자 인증이나 국내 단말 알림 표시가 검증되는 것은 아니다.

## 국내 분류와 현재 test identifier

[ETRI 연구진의 국내외 재난문자 서비스 활용 동향, 2024-09-04, 표 1](https://ksp.etri.re.kr/ksp/article/file/69860.pdf#page=6)은 국내 안전안내문자의 한글 identifier를 4372 (`0x1114`), 외국어 identifier를 4385 (`0x1121`)로 설명한다. 현재 codec의 4380 (`0x111C`)은 CMAS Required Monthly Test이며 국내 안전안내 분류와 다르다.

같은 identifier라도 국가별 정책이 다르다. [3GPP TS 23.041 V18.0.0](https://www.etsi.org/deliver/etsi_ts/123000_123099/123041/18.00.00_60/ts_123041v180000p.pdf#page=74)의 4372는 CMAS 관점에서는 Extreme/Immediate/Likely 조합이다. 미국 CMAS 분류를 국내 화면 명칭으로 그대로 해석하지 않는다.

[AOSP 한국 MCC 450 설정](https://android.googlesource.com/platform/packages/apps/CellBroadcastReceiver/+/17f1a4acf0db7133581f006498a511266e58ee57/res/values-mcc450/config.xml)을 source에서 확인했다. 이 revision은 4372를 `public_safety_messages_channels_range_strings`의 `type=info`로 분류하며 `required_monthly_test_range_strings`는 빈 배열이다. 따라서 현재 RMT 값을 일반 국내 폰에 전달하면 기본 재난문자 화면이 반드시 뜬다고 판단할 수 없다. 이는 해당 AOSP source의 결과이며 Samsung 또는 Apple 제품의 실측 결과가 아니다.

메시지에 `[시험]`을 넣거나 YAML의 `profile: TEST`를 변경하는 것만으로 휴대폰의 경보 등급을 제어할 수 없다. `LAB_EXERCISE`와 `language: ko`도 현재 application metadata다. [Android CellBroadcast 문서](https://source.android.com/docs/core/ota/modular-system/cellbroadcast)는 단말 표시가 carrier/지역 정책 및 resource overlay의 영향을 받는다고 설명한다.

## 현재 증거와 부족한 부분

| 단계 | 상태 | 의미 |
|---|---|---|
| 한글 UTF-8 → UCS-2 → NR SIB8 → 복원 | PASS | 두 Docker 모드에서 원문 일치; [실행 증거](SRSUE_RX_CAPTURE.md) |
| ZMQ gNB → srsUE MIB/SIB1 및 RRC | PASS | 소프트웨어 PHY 경로; 휴대폰이나 PWS 수신 시험은 아님 |
| libbladeRF 연결 및 오류 처리 | 구현, 장비 없는 검사 PASS | 실물 x40는 NOT VERIFIED |
| x40 내부 firmware loopback | 구현, mock PASS | LMS RF 경로를 우회하므로 휴대폰 수신 시험에 사용할 수 없음 |
| OCUDU ↔ bladeRF x40 radio driver | 구현, mock/API 검사 PASS | timed streaming 코드 포함; 실제 timestamp/USB/RF는 NOT VERIFIED |
| lab PWS → gNB SI scheduling → ZMQ 수신 | PASS | 한글 ID 4372 및 615자/15 segments 실제 수신 |
| SI waveform → x40 RF | 코드 구현, 실물 NOT VERIFIED | RF 활성 build 및 명시적 설정 필요; 기본 OFF |
| 국내 실제 단말의 안전안내 수신·표시 | NOT VERIFIED | 모델/OS/지역·통신사 설정/NR SA 지원 및 실제 시험 환경 필요 |

단독 SIB8 UPER 파일은 RF waveform이 아니다. bladeRF 내부 loopback 성공도 휴대폰의 cell acquisition, SIB8 수신 또는 알림 표시 성공을 의미하지 않는다. 휴대폰에 5G 표시가 있는 것만으로 해당 모델의 NR SA PWS 시험 호환성을 판단하지 않는다.

소스에서 확인한 경계는 다음과 같다.

- `controller/offline_codec/main.cpp`는 encode와 decode 모두 고정 RMT identifier를 검사한다. 설정의 identifier만 바꿔서 국내 운영 채널을 생성하는 기능은 없다.
- 고정 OCUDU의 `lib/radio/radio_factory.cpp`에는 `sidekiq`, `uhd`, `zmq`, `realtime_loopback` 및 외부 plugin 진입점이 있지만 bladeRF 내장 factory는 없다. 현재 외부 `bladerf_x40` plugin을 별도 구현했다. upstream 내장 driver는 아니다.
- `hardware/bladerf-x40/driver_adapter/real_device.cpp`는 TX 구성·활성화·전송 전에 firmware loopback 격리를 요구한다. 이 내부 stream을 handset 시험용 RF 출력으로 간주하지 않는다.

단말 기본 재난문자 수신을 목표로 삼을 경우 필요한 단계는 단말의 시험 셀 수신 가능성 확인 → x40 radio timing/stream 호환성 검증 → 격리된 환경의 PWS 수신·표시 검증이다. 각 단계는 현재 offline PASS와 별도로 판정해야 하며, 식별자 변경만으로 완료되지 않는다.

## 시험 범위 결정에 필요한 정보

1. 원하는 결과가 별도 앱의 한글 화면 검증인지, 단말 기본 재난문자 앱의 실제 셀룰러 수신인지 구분한다.
2. 단말 모델 번호, OS/build, 국내판 여부와 통신사 설정을 확인한다. 인증키나 실제 가입자 식별정보는 수집하지 않는다.
3. 실제 RF 경로를 평가하려면 RF 차폐함/전도 연결 가능 여부, 외부 누설 검증 수단, 해당 시험의 주파수 사용 조건을 확인한다. 차폐함 보유만으로 무누설 또는 법적 요건 충족을 단정하지 않는다.
4. 추가 요청으로 구현한 RF plugin은 standalone 내부 loopback 진단과 별도 target이다. 실물 시험은 새 RF 활성 build와 명시적 설정으로 분리하며 기존 진단의 격리 검사를 해제하지 않는다.

모델과 환경 확인 전에도 한글 offline protocol 검사 및 bladeRF 독립 진단 개발은 계속할 수 있다. Android system UI 검사는 [공식 CellBroadcast module tests](https://source.android.com/docs/core/ota/modular-system/cellbroadcast#testing)를 검토할 수 있지만, 일반 상용 폰에서 권한 없이 실행할 수 있다고 가정하지 않는다. UI 모의시험, modem 수신, RF 수신은 각각 별도 결과로 기록한다.

현재 ZMQ 수신은 소프트웨어 실행 증거가 있으며 단말 UI 평가는 source와 문서에 대한 검사다. 휴대폰 연결, RF 송신, bladeRF 실물 시험은 실행하지 않았다.
