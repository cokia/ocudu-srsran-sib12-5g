# 오프라인 PWS / ASN.1 검사

검사 순서는 YAML load → schema → typed message → UCS-2/길이 검사 → CB Data → OCUDU SIB8 UPER → OCUDU unpack → segment 재조립 → CB Data decode → 원문 비교 → 재인코딩 비교 → report이다.

## 실제 사용한 표준과 source

- [TS 23.041 §9.3.51, §9.4.2.2.5](https://www.etsi.org/deliver/etsi_ts/123000_123099/123041/18.00.00_60/ts_123041v180000p.pdf): NG-RAN Warning Message Content 및 CB Data 구조.
- [TS 23.038 §5, §6.2.3](https://www.etsi.org/deliver/etsi_ts/123000_123099/123038/18.00.00_60/ts_123038v180000p.pdf): DCS 0x48, UCS-2, CR padding.
- [TS 23.041 identifier 표](https://www.etsi.org/deliver/etsi_TS/123000_123099/123041/10.01.00_60/ts_123041v100100p.pdf): test identifier 4380/0x111c.
- OCUDU `pws_sib_encoder.cpp::encode_sib8`, `sys_info.cpp::sib8_s::{pack,unpack}`.

텍스트는 UTF-8 YAML로 입력하고 UCS-2 big-endian으로 encode한다. emoji 등 non-BMP 문자는 UCS-2로 표현하지 못하므로 명확히 거부한다. UTF-8 바이트를 UCS-2 DCS로 잘못 표시하지 않는다. metadata의 language는 application level로만 유지한다.

## 실행

```bash
.venv/bin/python -m controller validate
.venv/bin/python -m controller decode --input output/offline-sib8.json
.venv/bin/python -m controller inspect-sib12
bash scripts/test-non-sdr.sh
```

SDR 모드에서도 같은 codec를 사용한다.

```bash
.venv/bin/python -m controller validate --mode sdr-bladerf-x40 --output output/sdr-pws
```

## 시험 내용

`tests/unit/test_cb_data.py`는 독립적으로 정한 `A` 및 `한글`(U+D55C U+AE00)의 CB Data byte vector, 41/42/615자 경계, 한글, CR/LF, invalid UCS-2, 잘못된 page 수/길이/padding을 검사한다. `tests/integration/test_protocol.py`는 실제 OCUDU executable로 segment size 20/128/256을 검사한다. `tests/integration/test_cli.py`는 두 모드에서 한글 예제를 별도 decode 명령으로 복원하고 stdout 및 UTF-8 JSON 파일의 원문 일치를 검사한다. Docker runtime에서 직접 수행한 결과는 [한글 검증 기록](SRSUE_RX_CAPTURE.md)에 있다.

독립 UPER golden은 SIB8의 4 presence bit + 16-bit ID + 16-bit serial + 1-bit type + 6-bit segment index + length determinant + payload + DCS를 표준의 순서로 직접 구성한다. encoder와 decoder가 같은 오류를 공유할 가능성을 단순 round-trip보다 줄인다. 이 fixture는 외부 상용 UE certification을 대체하지 않는다.

decoder는 segment 순서/중복, last indicator, ID/serial/DCS, 첫 segment의 DCS 조건, trailing byte, 비정규 padding, truncation을 거부한다. extension field는 이 laboratory profile에서 지원하지 않는다. 출력은 독립 SIB8 ASN.1 객체의 UPER이며 BCCH-DL-SCH frame, MAC transport block, RF waveform이 아니다.

## SIB12

`inspect-sib12`는 **NR sidelink SIB12-r16**과 내부 `sib12_ies_r16_s`를 encode/decode한다. PWS text를 segment container에 넣지 않는다. 결과의 `inner_asn1_round_trip=true`는 내부 ASN.1 구조 일치이고 `payload_semantics_verified=false`는 실제 sidelink 동작 미시험을 뜻한다.

## 제한

GSM 7-bit alphabet, compression, language prefix, warning area coordinates, active operational identifier 선택, ETWS message 생성, NGAP/F1AP warning 요청 전송, SI scheduler 연결은 제공하지 않는다. 실제 CMAS 단말 표시나 operator policy 준수 여부는 NOT VERIFIED다.
