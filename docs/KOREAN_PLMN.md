# 국내 MCC/MNC 적용 및 수신 검증

검증일: 2026-10-20 KST. PWS 연동 설정 생성의 기본 PLMN을 `00101`에서 `45005`로 변경했다. `controller.pws_integration prepare`와 `receive`, 기본 Compose 수신, radio plugin mock 설정에 적용된다. 실제 RF 실행은 하지 않았다.

## 선택값

| 통신사 / 용도 | MCC | MNC | `--plmn` |
|---|---|---|---|
| SKT, 기본값 | `450` | `05` | `45005` |
| KT | `450` | `08` | `45008` |
| LG U+ | `450` | `06` | `45006` |
| 기존 시험 PLMN 재현 | `001` | `01` | `00101` |

국내 값은 [ITU E.212, OB 1280 부록 p.36](https://www.itu.int/dms_pub/itu-t/opb/sp/T-SP-E.212B-2023-PDF-E.pdf) 및 [OB 1314 register](https://www.ituob.org/registers/e212-mnc/at/1314/)와 대조했다. MNC 앞의 `0`을 유지한다. `450005`는 `45005`와 다른 식별자이므로 이 profile에서 거부한다.

PLMN은 SIB1의 망 식별자다. CMAS SIB8의 message identifier는 별도로 `--profile korean-safety`에서 4372를 사용한다. 국내 PLMN 선택만으로 message identifier, 주파수, 대역, RF enable 또는 실제 가입자 인증 정보를 바꾸지 않는다.

## 구현

- `controller/pws_integration.py`: `--plmn` 검증, `cell_cfg.plmn`과 `cu_cp.amf.supported_tracking_areas[].plmn_list[].plmn` 동시 설정. ZMQ용 `srsue.pws.conf`를 생성하여 공개 시험용 soft USIM IMSI prefix도 일치시킨다.
- 수신 srsUE의 RRC debug log에서 실제 decode한 SIB1 PLMN을 추출하고 요청값과 비교한다. `pws-integration.json`에 `plmn`, `mcc`, `mnc`, `received_plmn`을 기록한다.
- `docker/compose.pws.yaml`: 기본 `PWS_LAB_PLMN=45005`, 환경변수로 선택 가능.
- `tests/unit/test_pws_integration.py`: 두 backend의 설정 일치, leading zero, 무효 PLMN, 잘못된 수신 PLMN, 실제 srsUE log fixture 검사.
- `scripts/test-pws-integration.sh`: 기존 RRC/영어/한글/615자 회귀에 KT·LG U+ 수신 추가. 전체 제한은 기존 360초다.

고정 `configs/gnb.zmq.yaml`/`srsue.zmq.conf`와 Dummy RU의 일반 RRC 회귀는 `00101`을 유지한다. PWS 명령이 별도 생성하는 `gnb.pws.yaml`/`srsue.pws.conf`에 국내 값을 적용하므로 고정 profile hash와 기존 base 실행 경로를 바꿀 필요가 없다. hardware용 `prepare`도 같은 PLMN을 적용하며 생성 YAML의 `rf=off`를 유지한다.

## 사용

```bash
# Docker: 기본 SKT
docker compose -f docker/compose.pws.yaml --profile pws-zmq run --rm reception
# Docker: KT
PWS_LAB_PLMN=45008 docker compose -f docker/compose.pws.yaml --profile pws-zmq run --rm reception
# 격리된 ZMQ runtime 안의 CLI: LG U+
python -m controller.pws_integration receive --profile korean-safety --plmn 45006
# bladeRF x40 설정 생성만 수행
python -m controller.pws_integration prepare --profile korean-safety \
  --backend bladerf-x40 --plmn 45005 --serial 0123456789abcdef0123456789abcdef
```

마지막 명령의 serial은 예시다. 결과는 `output/pws-integration/gnb.pws.yaml`에 생성되며 장치를 열지 않는다. source 변경 전 이미지가 있으면 `scripts/build-pws-integration-docker.sh`로 갱신해야 새 기본값과 옵션이 포함된다.

## 실제 결과

macOS ARM64 host / Colima Linux aarch64의 기존 고정 OCUDU·srsUE binary를 사용했다. source mount 환경에서 PLMN별로 gNB/UE를 새로 시작하고 `--network none`으로 실행했다. 각 수신 한도는 60초이며 종료는 process별 10초다. upstream dependency revision과 patch는 변경하지 않았다.

| 검사 | 결과 |
|---|---|
| Python 전체 | **180 PASS** |
| SKT `45005`, KT `45008`, LG U+ `45006` | **각 PASS**, 수신 SIB1 PLMN 일치, 한글 SIB8 ID 4372 복원, 두 process exit 0 |
| 기존 `00101` 명시적 선택 | **PASS**, 수신 PLMN 및 한글 원문 일치 |
| Ruff 및 shell syntax / Compose 기본·KT 렌더링 | **PASS** |
| ZMQ / radio-plugin image 갱신 | **PASS**, 기존 binary 재사용·새 controller package |
| source mount 없는 새 이미지 실행 | **PASS**, 기본 `45005` 한글 수신 및 gNB radio mock 정상 종료 |
| 6개 수신 회귀 suite | **PASS**, RRC/영어/국내 세 PLMN 한글/615자, 30.395초 |
| 실물 x40 RF / 국내 단말 표시 | **NOT VERIFIED**, 장비 없음 |

[실행 증거](evidence/2026-10-20/korean-plmn/)에는 PLMN별 JSON과 원본 srsUE log, Python JUnit, `SHA256SUMS`를 보존한다. 예를 들어 SKT 수신 log의 identity는 `mcc: [4,5,0]`, `mnc: [0,5]`이며 복원한 문구는 `[시험 데이터] PWS 프로토콜 검증 메시지입니다.`다.

첫 수신 시도는 전체 debug JSON을 파싱하려다 `E_RX_TIMEOUT`으로 실패했다. srsUE `pdcch-ConfigCommon` logger가 필드명 없이 중괄호를 출력하고, identity 목록의 JSON 이름도 OCUDU logger와 다르기 때문이다. 고정 srsUE의 실제 출력 구조에 맞춰 정상 `cellAccessRelatedInfo` 객체만 읽도록 수정했다. 처음 실패한 JSON도 보존하며, 실제 raw log를 `tests/fixtures/srsue-sib1-45005.txt` 회귀 fixture로 사용한다. 수신 SIB1 구조가 아닌 임의 텍스트나 `SIB1 acquired` 문구만으로 통과시키지 않는다.

이전 commit `0150351`의 GitHub software 검사는 성공했지만 [non-sdr build](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39245105995)와 [PWS build](https://github.com/cokia/ocudu-srsran-sib12-5g/actions/runs/39245105976)는 generic x86-64 equalizer의 `simd_f_t`/`simd_cf_t` compile 오류로 실패한 상태임을 추가 확인했다. 이번 PLMN 변경의 Linux ARM64 실행 성공과 구분한다. 해당 upstream SIMD 빌드 문제는 이번 설정 변경에서 수정하지 않았다.
