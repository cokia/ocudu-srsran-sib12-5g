# 설정 참조

모든 YAML key는 JSON Schema로 검사하며 알 수 없는 key, 잘못된 type, 중복 key, YAML alias/anchor, 지원하지 않는 tag를 거부한다. 파일은 UTF-8, 최대 64 KiB이다. 모든 아래 필드는 필수이며 **생략 시 자동 기본값을 삽입하지 않는다**. 표의 예제값은 `configs/*.yaml`의 값이다.

## 공유 PWS 설정

이 설정은 laboratory application 설정이다. OCUDU gNB 설정으로 직접 전달하지 않는다.

| field | type | 필수/기본값 | 허용 값·검증 | 예제 |
|---|---|---|---|---|
| `schema_version` | integer | 필수/없음 | 정확히 1; boolean 거부 | `1` |
| `application` | object | 필수/없음 | 정의된 key만 | 아래 세 항목 |
| `application.name` | string | 필수/없음 | `ocudu-pws-lab` | `ocudu-pws-lab` |
| `application.mode` | string | 필수/없음 | `non-sdr`, `sdr-bladerf-x40` | `non-sdr` |
| `application.log_level` | string | 필수/없음 | stderr JSON event 최소 level: debug/info/warning/error. 최종 결과/audit는 항상 기록 | `info` |
| `pws` | object | 필수/없음 | 정의된 key만 | 아래 항목 |
| `pws.enabled` | boolean | 필수/없음 | `true`만. 검증을 생략한 성공 보고 금지 | `true` |
| `pws.message` | object | 필수/없음 | 정의된 key만 | 아래 항목 |
| `pws.message.id` | string | 필수/없음 | `LAB-` 뒤 영숫자/`-` 1..32개. ASN.1 ID와 별개 | `LAB-0001` |
| `pws.message.profile` | string | 필수/없음 | `TEST`만 | `TEST` |
| `pws.message.language` | string | 필수/없음 | `ko`, `en`; application metadata | `ko` |
| `pws.message.text` | string | 필수/없음 | 1..615 UCS-2 BMP 문자. 공백만, surrogate, non-BMP, 지원하지 않는 제어 문자 거부 | `'[시험] 메시지'` |
| `pws.message.metadata` | object | 필수/없음 | 정의된 key만 | 아래 항목 |
| `...metadata.category` | string | 필수/없음 | `LAB_EXERCISE`만 | `LAB_EXERCISE` |
| `...metadata.description` | string | 필수/없음 | 1..256 문자 | `'오프라인 검증'` |
| `pws.validation` | object | 필수/없음 | 정의된 key만 | 아래 네 항목 |
| `...validation.strict` | boolean | 필수/없음 | `true`만 | `true` |
| `...validation.check_encoding` | boolean | 필수/없음 | `true`만 | `true` |
| `...validation.check_length` | boolean | 필수/없음 | `true`만 | `true` |
| `...validation.round_trip_decode` | boolean | 필수/없음 | `true`만 | `true` |
| `pws.output` | object | 필수/없음 | 정의된 key만 | 아래 항목 |
| `...output.format` | string | 필수/없음 | `json`만 | `json` |
| `...output.directory` | string | 필수/없음 | 길이 1..1024, CWD 기준 상대경로 또는 절대경로. 쓰기 권한 필요 | `output` |
| `...output.audit_log` | boolean | 필수/없음 | `true`만 | `true` |
| `radio` | object | 필수/없음 | 정의된 key만 | 아래 항목 |
| `radio.backend` | string | 필수/없음 | `dummy`만. hardware diagnostic 경로 선택자가 아님 | `dummy` |
| `radio.rf_transmission_enabled` | boolean | 필수/없음 | `false`만. 문자열 `'false'` 거부 | `false` |

`--mode`는 같은 message config의 보고 mode만 바꾸고 RF 경로를 열지 않는다. `--output`은 결과 디렉터리만 override한다. `--codec` 또는 `PWS_CODEC`는 로컬 executable 위치를 선택한다. 신뢰하는 자체 빌드 executable을 사용한다.

## 프로토콜 매핑

`pws-codec`는 고정 test identifier `0x111c`(CMAS Required Monthly Test), serial `0`, DCS `0x48`(비압축 UCS-2, message class 없음)을 사용한다. 이 값은 설정에서 바꿀 수 없다. `LAB-0001`을 16-bit messageIdentifier에 해시하거나 문자열로 집어넣지 않는다. language는 DCS language indicator로 encode하지 않는다. CB Data는 최대 15 page, page당 82 byte와 실제 길이 1 byte다. page padding은 UCS-2 CR이다.

`NR-SIB12-r16`의 message field는 만들지 않는다. `inspect-sib12`는 `SIB12-IEs-r16`의 모든 optional field가 없는 유효한 내부 구조를 pack하여 segment container에 넣고 다시 unpack한다. UE sidelink 동작이나 경고 의미는 검증하지 않는다.

## bladeRF 진단 설정

`configs/bladerf-x40.schema.json`을 사용한다. PWS text, 파일, 주파수 송신 설정을 받는 key는 없다.

| field | type | 필수/기본값 | 허용 값 / 예제 |
|---|---|---|---|
| `schema_version` | integer | 필수/없음 | `1` |
| `device` | object | 필수/없음 | 아래 네 항목 |
| `device.model` | string | 필수/없음 | `bladerf-x40` |
| `device.serial` | string | 필수/없음 | 빈 문자열 또는 32자리 hex; 복수 장치일 때 선택 필요 |
| `device.access` | string | 필수/없음 | `mock` 또는 `hardware`; hardware는 추가 `--hardware` 필수 |
| `device.rf_transmission_enabled` | boolean | 필수/없음 | `false`만 |
| `diagnostics` | object | 필수/없음 | 아래 고정 검증 profile |
| `diagnostics.sample_rate` | integer | 필수/없음 | `1000000` |
| `diagnostics.buffer_samples` | integer | 필수/없음 | `4096` |
| `diagnostics.buffers` | integer | 필수/없음 | `8` |
| `diagnostics.transfers` | integer | 필수/없음 | `4` |
| `diagnostics.transfer_timeout_ms` | integer | 필수/없음 | `1000`; sync call은 별도 2000 ms |
| `diagnostics.loopback_samples` | integer | 필수/없음 | `65536` |
| `diagnostics.loopback_mode` | string | 필수/없음 | `firmware`만 |
| `diagnostics.max_duration_seconds` | integer | 필수/없음 | `20` |
| `output` | object | 필수/없음 | 아래 항목 |
| `output.directory` | string | 필수/없음 | 1..1024 문자, 예: `output/sdr` |

숫자는 실제 C++ profile과 일치하는 값만 허용한다. configurable처럼 보이지만 적용하지 않는 값을 허용하지 않는다. `--mock`은 hardware config도 명시적으로 mock으로 실행한다. `--hardware`는 mock 기본 config에서 실제 device 접근으로 전환한다. 둘을 함께 사용하면 오류다.

## gNB 고정 profile

`gnb.non-sdr.yaml`은 upstream native schema다. shared schema의 `radio` key와 혼합하지 않는다.

| 경로 | type / 값 | 의미 |
|---|---|---|
| `cu_cp.amf.no_core` | boolean / true | 실제 AMF 연결 없음 |
| `cu_cp.amf.addrs`, `bind_addrs` | string / 127.0.0.1 | loopback 주소 |
| `supported_tracking_areas[].tac` | integer / 7 | 논리 TAC |
| `plmn_list[].plmn` | string / '00101' | 시험 PLMN |
| `tai_slice_support_list[].sst` | integer / 1 | slice 설정 |
| `ru_dummy.time_scaling` | number / 10 | Dummy RU slot 시간을 느리게 진행 |
| `cell_cfg.dl_arfcn`, `band` | integer / 632628, 78 | 논리 radio resource 설정 |
| `channel_bandwidth_MHz`, `common_scs` | integer / 20, 30 | bandwidth 및 SCS |
| `plmn`, `tac`, `pci` | string/integer / '00101', 7, 1 | 기본 Dummy RU cell identity. 별도 PWS 생성 설정은 `--plmn` 기본 '45005' |
| `log.filename`, `all_level` | string / stdout, info | harness가 수집하는 gNB log |
| `pcap.mac_enable`, `ngap_enable` | boolean / false | PCAP 비활성화 |
| `buffer_pool.nof_segments`, `segment_size` | integer / 16384, 2048 | 약 32 MiB의 segment storage. 2 GiB 컨테이너 smoke 실행용 |

이 profile의 field들은 제공된 파일에 명시된다. upstream 전체 기본값을 재정의하지 않으며, 확인하지 않은 추가 radio/network/PWS 옵션을 wrapper로 전달하지 않는다.

별도 `gnb.zmq.yaml` / `srsue.zmq.conf`의 고정 n3/FDD profile은 [ZMQ 설정 표](ZMQ_SRSUE.md)를 따른다. 공유 `pws.example.yaml`의 `radio.backend`는 offline 안전 조건으로 유지하며, 이 값을 바꿔 ZMQ나 장치로 payload를 연결하는 기능은 없다.

## 선택적 PWS / radio 연동 설정

기본 공유 YAML의 RF OFF 조건은 그대로 유지한다. 별도 `controller.pws_integration`은 검증한 text를 실제 OCUDU `cell_cfg.sib.cmas.test`에 복사한다. `--profile monthly-test`는 ID 4380, `--profile korean-safety`는 4372이며 serial 0 / DCS 0x48이다. [모든 새 CLI 필드와 예제](PWS_INTEGRATION.md), [plugin device arguments](RADIO_PLUGIN.md)를 참조한다. `prepare --backend bladerf-x40`가 생성하는 YAML은 `rf=off`여서 그대로 실행해도 hardware stream을 열지 못한다.
