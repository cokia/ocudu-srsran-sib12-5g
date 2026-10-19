# Upstream 분석

분석 기준일: 2026-10-19 KST. OCUDU 최신 정식 태그 `release_26_10`, commit **`e0db566aac6e6376ddd60e83c84f58698fcc4d70`** (2026-09-30)을 선택했다. `release_26_04`, 26.10 RC와 branch HEAD를 구분하여 정식 release를 사용한다. 기본 branch의 이후 변경을 추적하지 않는다.

- [고정 OCUDU 소스](https://gitlab.com/ocudu/ocudu/-/tree/e0db566aac6e6376ddd60e83c84f58698fcc4d70)
- [공식 설치 문서](https://docs.ocudu.org/user_manual/installation/)
- [공식 release 페이지](https://docs.ocudu.org/releases/)
- [bladeRF 2.6.0 소스](https://github.com/Nuand/bladeRF/tree/09c82087786702d2812f3f0fc909beccf3277233)

공식 문서의 요약보다 고정 소스의 CMake/CLI schema를 우선 확인했다. 예를 들어 문서의 ZMQ 기본값 설명과 현재 CMake의 기본값이 다를 수 있으므로 모든 물리 radio 관련 옵션을 명시적으로 OFF로 지정한다.

## NR SIB 번호의 정정

**NR CMAS는 SIB8**이다. NR SIB6/7은 ETWS이며, **NR SIB12-r16은 sidelink 구성의 segment container**이다. LTE CMAS의 SIB12 번호를 NR에 적용하면 다른 ASN.1 구조를 생성하게 된다. 이 프로젝트는 요청한 SIB12 조사를 제공하되 PWS 메시지를 NR SIB12에 잘못 매핑하지 않는다.

- `include/ocudu/asn1/rrc_nr/sys_info.h`: `sib6_s`, `sib7_s`, `sib8_s`, `sib12_r16_s`, `sys_info_ies_s`의 SIB choice.
- `lib/asn1/rrc_nr/sys_info.cpp`: 위 구조의 `pack`, `unpack`, `to_json`.
- `include/ocudu/asn1/rrc_nr/rrc_nr.h`: `sib12_ies_r16_s`, `sl_cfg_common_nr_r16_s`.
- `lib/asn1/rrc_nr/rrc_nr.cpp`: SIB12 내부 IEs encoding/decoding.
- [TS 38.331 Release 16](https://www.etsi.org/deliver/etsi_ts/138300_138399/138331/16.20.00_60/ts_138331v162000p.pdf): §6.3.1의 SIB8/SIB12 정의.

SIB8은 messageIdentifier 16 bit, serialNumber 16 bit, segment type, segment number 0..63, warningMessageSegment, 첫 segment의 dataCodingScheme를 사용한다. application의 `id`, `category`, `description`, `language`는 ASN.1 field를 임의 확장하지 않고 보고서 metadata로 유지한다.

## 구현 경로와 검증 범위

아래 경로는 모두 위 OCUDU commit의 상대 경로다. 최종 실제 실행 결과는 [구현 보고서](IMPLEMENTATION_REPORT.md)를 참조한다.

| 기능 | 정확한 source/interface | 분류 및 근거 |
|---|---|---|
| NR RRC ASN.1 | `include/ocudu/asn1/rrc_nr/`, `lib/asn1/rrc_nr/`, `rrc_nr_asn1` target | 구현됨. 이 프로젝트가 SIB8/SIB12 pack/unpack을 실제 호출하여 검증 |
| PWS encoder | `lib/cu_cp/routines/pws_sib_encoder.{h,cpp}`: `ocudu::ocucp::encode_sib6/7/8` | 구현됨. SIB8을 원본 source 그대로 별도 executable에 링크하여 검증 |
| NGAP warning 수신 | `lib/ngap/ngap_impl.cpp`: Write-Replace Warning handling | 구현되어 있으나 이 플랫폼은 N2 warning 입력을 열지 않아 미검증 |
| CU-CP PWS | `lib/cu_cp/routines/write_replace_warning_routine.{h,cpp}`: `cu_cp_write_replace_warning_routine` | 구현됨, 방송 절차는 이 플랫폼에서 실행하지 않음 |
| CU F1AP | `lib/f1ap/cu_cp/procedures/write_replace_warning_procedure.{h,cpp}`: `write_replace_warning_procedure` | 구현됨, 전체 procedure는 미검증 |
| DU F1AP | `lib/f1ap/du/f1ap_du_impl.cpp`, `procedures/f1ap_du_write_replace_warning_procedure.{h,cpp}` | 구현됨, 실제 경고 전달은 실행하지 않음 |
| DU PWS | `lib/du/du_high/du_manager/procedures/du_pws_broadcast_procedure.{h,cpp}` | 구현됨, 의도적으로 연결하지 않음 |
| SI scheduling | `lib/scheduler/common_scheduling/si_scheduler.cpp`, `lib/mac/mac_dl/segmented_sib_list.h` | 반복/segment 지원 존재. PWS 방송 시험은 미검증 |
| Dummy RU | `lib/ru/dummy/ru_dummy_impl.cpp`, `ru_dummy_factory.cpp`, `include/ocudu/ru/dummy/ru_dummy_configuration.h` | 구현됨. gNB smoke 대상으로 사용 |
| Dummy CLI | `apps/units/flexible_o_du/split_dynamic/dynamic_o_du_unit_cli11_schema.cpp` | `ru_dummy.time_scaling` 존재를 확인; 앱 자체 `radio` 설정과 별개 |
| no-core | `apps/units/o_cu_cp/cu_cp/cu_cp_unit_config_cli11_schema.cpp` 및 `cu_cp_config_translators.cpp` | `cu_cp.amf.no_core` 지원. 실제 operator core 불필요 |
| buffer pool | `apps/services/buffer_pool/buffer_pool_appconfig_cli11_schema.cpp` | `buffer_pool.nof_segments`, `segment_size` 지원. 16384 × 2048 profile로 2 GiB 컨테이너에서 시작/종료 검증 |
| radio abstraction | `include/ocudu/radio/radio_factory.h`, `radio_session.h`, `radio_management_plane.h` | 구현됨. session start/init_time, stop, timestamp, management/data plane 필요 |
| sample I/O | `include/ocudu/gateways/baseband/baseband_gateway_{buffer,transmitter,receiver}*.h` | complex sample buffer 및 timestamp 계약. libbladeRF buffer를 그대로 연결할 수 없음 |
| 지원 driver | `lib/radio/radio_factory.cpp` | UHD, Sidekiq, ZMQ, realtime_loopback 및 plugin loader. bladeRF/SoapySDR 내장 지원 없음 |
| ZeroMQ | `lib/radio/zmq/radio_session_zmq_impl.cpp` | 실제 ZMQ/srsUE MIB·SIB1 수신 및 RRC 연결/release 검증. [추가 결과](FOLLOWUP_REPORT.md) |
| 동적 radio plugin | `lib/radio/plugin_radio_factory.cpp` | 확장 지점 존재. bladeRF adapter로 full timing 계약을 충족하는지는 미검증 |
| build plugin | 루트 `CMakeLists.txt`의 `plugins/*` 검색 | `plugins/pws_lab` symlink를 사용. plugin에 필요한 source 수정 없음; 별도 worker 수정은 [patch 문서](PATCHES.md) 참조 |
| logging/config | `lib/ocudulog`, `apps/helpers`, `apps/units/**/**cli11_schema.cpp` | 기존 YAML/CLI11/ocudulog 재사용. laboratory JSON audit는 별도 Python 구현 |
| containers | upstream `docker/Dockerfile`, `docker/scripts/` | 기존 구조 조사. 이 플랫폼은 별도 GitHub용 Docker workflow 사용 |
| UE simulation | upstream `configs/testmode.yml` | PHY/MAC 부하용 test UE 기능 존재. 완전한 UE NAS/RRC end-to-end 시뮬레이터로 주장하지 않음 |

## 기존 테스트

`tests/unittests/cu_cp/cu_cp_write_replace_warning_test.cpp`, `tests/unittests/ngap/ngap_write_replace_warning_test.cpp`, `tests/unittests/f1ap/cu_cp/f1ap_cu_write_replace_warning_test.cpp`, `tests/unittests/f1ap/du/f1ap_du_write_replace_warning_test.cpp`, `tests/unittests/du_manager/procedures/du_pws_broadcast_procedure_test.cpp`가 존재한다. 이들 upstream 전체 suite를 실행한 것으로 보고하지 않는다. 본 프로젝트는 직접 사용하는 SIB8 encoder를 실제 링크하고 독립 golden vector, 잘못된 segment, 한국어와 경계 길이로 검사한다.

## Work item #540

[#540](https://gitlab.com/ocudu/ocudu/-/work_items/540)은 DU/F1AP Write-Replace Warning 지원 작업으로, GitLab API 확인 결과 2026-07-20 종료되었다. 관련 [MR !1074](https://gitlab.com/ocudu/ocudu/-/merge_requests/1074)는 같은 날 merge되었으며 source HEAD는 `42d29b50b62d83d9c9e1ed2d2d94bb2234a4dfe7`이다. 관련 #537은 상위 PWS 기능 작업이다. #540의 상태만으로 end-to-end 상용 PWS 검증을 주장하지 않으며, 선택 release의 실제 procedure source도 확인했다.

## 빌드와 의존성

Linux, C++17, CMake/Ninja, Clang 18, FFTW, mbedTLS, SCTP, yaml-cpp를 사용한다. `BUILD_TESTING=OFF`로 gNB를 만들고, 프로젝트 tests는 별도로 실행한다. nlohmann-json은 codec/diagnostic의 JSON 경계에 사용한다. Python은 YAML/schema/report/process orchestration에만 사용한다. 정확한 버전은 `dependencies.lock.json`, `requirements*.txt`, `docs/dependencies.ubuntu-arm64.tsv`, runtime manifest에 기록한다.

OCUDU의 `external/` include 경로가 우선하므로 codec는 vendored nlohmann-json **3.12.0**을 사용한다. standalone diagnostic은 Ubuntu의 **3.11.3**을 사용한다. vendored fmt는 **11.1.3**, CLI11은 **2.4.2**다. 각 macro와 실제 `build.ninja` include 순서를 확인했다. 버전 번호가 없는 vendored header들은 위 OCUDU commit에 함께 고정되며 출처/저작권은 `licenses/OCUDU-COPYRIGHTS.txt`에 있다.

최초 구현 이후 ZMQ 검증에서 OCUDU의 명시적 worker 수 처리와 srsUE FFTW 계획 방식의 최소 patch를 추가했다. 각 upstream에서 source file 하나만 수정하며 [patch 문서](PATCHES.md)에 근거와 hash 검증을 설명한다. bladeRF에는 AD936x를 빌드하지 않는 x40 전용 패치가 있다. upstream의 라이선스/고지를 `licenses/`에 보존한다. 공개 소스 및 바이너리 배포 조건은 [제3자 고지](../THIRD_PARTY_NOTICES.md)를 따른다.

## 2026-10-19 추가 구현 상태

Upstream 자체에는 bladeRF factory가 없다. 로컬 `hardware/bladerf-x40/radio_plugin`이 기존 dynamic loader를 사용하므로 OCUDU radio source patch는 필요하지 않았다. 실제 gNB 로딩/mock streaming은 검증했고 실물 timing은 미검증이다. pinned gateway buffer는 `ci16_t`; ZMQ의 wire CF32와 구분한다.

PWS 연결은 upstream `apps/units/flexible_o_du/o_du_high/du_high/du_high_config_cli11_schema.cpp`의 `cmas.test`, `du_high_config_translators.cpp`의 `create_sib8_info`/`fill_pws_si_messages`, `lib/du/du_high/du_manager/converters/asn1_sys_info_packer.cpp`의 segmentation, `cbs/cbs_encoder_impl.cpp::fill_cb_data_ucs2`를 재사용했다. static SI의 실제 ZMQ→srsUE 수신을 검증했다. 별도 NGAP WRW/F1AP 동적 warning 전달 시험을 수행한 것은 아니다. [수신 patch](PATCHES.md), [결과](RADIO_PWS_REPORT.md)를 참조한다.
