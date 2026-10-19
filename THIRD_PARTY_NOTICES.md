# 제3자 구성요소와 배포 조건

자체 코드에는 루트 `LICENSE`의 BSD-3-Clause를 적용한다. 외부 코드를 이 라이선스로 재라이선스하지 않는다. 원본 upstream은 `dependencies.lock.json`의 commit으로 가져온다. upstream checkout과 firmware/FPGA 바이너리는 GitHub 저장소에 포함하지 않는다.

| 구성요소 | 라이선스/출처 | 이 프로젝트에서의 처리 |
|---|---|---|
| OCUDU 26.10 | 소스 SPDX `BSD-3-Clause-Open-MPI`, 원문 `licenses/OCUDU-LICENSE` | ASN.1/PWS encoder 재사용, worker 수와 빈 CPU feature 목록을 보완하는 최소 patches. `COPYRIGHTS.txt`와 포함 third-party 고지 보존 |
| libbladeRF 2.6.0 | LGPL-2.1-or-later | 동적 링크. x40 전용 패치는 `patches/bladerf-x40-only.patch`; 교체 가능한 shared library로 제공 |
| bladeRF의 FPGA HDL/FX3 source | upstream COPYING의 MIT 등 | 분석용 checkout에만 존재. FPGA IP별 예외가 있으므로 firmware/bitstream 배포 없음 |
| bladeRF-cli | GPL-2.0 | 이 플랫폼에서는 빌드/배포하지 않음 |
| Analog Devices no-OS | 별도 라이선스 | x40 전용 패치로 의존성을 제거하여 다운로드/빌드/배포하지 않음 |
| FFTW 3.3.10 | GPL-2.0-or-later | gNB runtime이 링크함. gNB/Non-SDR 이미지의 바이너리 배포에는 GPL 조건과 대응 소스 제공이 필요함 |
| yaml-cpp, fmt, nlohmann-json | MIT | 배포 패키지와 OCUDU 포함 고지 유지 |
| mbedTLS | Apache-2.0 | Ubuntu 패키지 copyright 보존 |
| lksctp-tools / libsctp | LGPL-2.1-or-later 등 패키지별 고지 | runtime 라이브러리 동적 링크; 정확한 고지는 `/usr/share/doc/libsctp1/copyright` |
| libusb | LGPL-2.1-or-later | SDR 이미지에만 shared library 포함, 고지와 source package 기록 |
| srsRAN 4G / srsUE / srsENB 25.10 | AGPL-3.0-or-later 및 원본 COPYRIGHT의 구성요소별 고지 | 선택적 ZMQ 수신 이미지에 포함. LICENSE/COPYRIGHT 보존, 고정 commit의 대응 source를 함께 제공해야 함 |
| ZeroMQ / Boost.Program_options | MPL-2.0 / BSL-1.0 | ZMQ 이미지의 Ubuntu 고정 snapshot package, `/usr/share/doc/*/copyright` 보존 |
| PyYAML, attrs, jsonschema, referencing, rpds-py | MIT | 고정 버전, 배포 wheel의 dist-info 고지 유지 |
| Python, GNU runtime, glibc, Ubuntu 패키지 | 각 패키지의 라이선스 | 컨테이너 `/usr/share/doc/*/copyright` 및 패키지 manifest로 추적 |

공개 GitHub **소스** 배포를 허용하는 구성요소로 구성하였다. 표의 조건은 독점 firmware blob 재배포 권한을 의미하지 않는다. 3GPP 문서 자체는 복제하지 않고 원본을 링크한다. OCUDU의 원래 특허 관련 고지를 보존한다.

컨테이너/바이너리를 공개 배포할 때는 `scripts/package-source.sh`로 자체 및 upstream 대응 소스를 생성하고, `scripts/collect-dependency-sources.sh`로 Ubuntu source package를 수집하여 **동일 release에 함께 제공**한다. LGPL 라이브러리 교체를 금지하지 않는다. 패키지 빌드 manifest와 scripts를 함께 제공해야 한다. 소스 archive 생성만으로 모든 제3자 바이너리의 대응 소스가 자동 포함되는 것은 아니다.

실험실에서 생성한 Docker 이미지는 로컬 검증용이다. 소스는 사용자 요청으로 GitHub에 push한다. 이미지 registry 업로드와 binary release 발행은 수행하지 않는다.

OCUDU/srsUE source의 diff 조각은 해당 upstream license를 유지하며 자체 BSD license로 바뀌지 않는다. patch 범위와 적용 hash는 [patch 문서](docs/PATCHES.md) 및 `dependencies.lock.json`에 기록한다.

추가 radio plugin 자체 코드는 BSD-3-Clause이며 기존 OCUDU/libbladeRF 고지를 유지한다. srsUE SI monitor 및 PHY 수정 patch는 원본 AGPL-3.0-or-later 조건을 유지한다. C++ 정렬에 사용한 개발 도구는 clang-format 18.1.8이며 runtime에 포함하지 않는다.

LTE image의 `libconfig++9v5`와 build의 `libconfig++-dev`는 Ubuntu snapshot `1.5-0.4build2`를 사용한다. libconfig library는 LGPL-2.1-or-later이며 패키지별 고지는 `/usr/share/doc/libconfig++9v5/copyright`에 보존한다. `configs/lte/*.conf`는 srsENB 원본 example의 파생 파일로 AGPL-3.0-or-later 고지를 유지한다. LTE binary를 배포할 때에도 srsRAN 고정 source와 적용 patch, libconfig source package를 함께 제공해야 한다.
