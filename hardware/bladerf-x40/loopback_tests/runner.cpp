// SPDX-License-Identifier: BSD-3-Clause
#include "driver_adapter/device.h"
#include <exception>
#include <thread>

namespace lab {
void verify(const json& info) {
  if (info.at("board") != "bladerf1" || info.at("fpga_size") != 40) { throw Failure("E_MODEL", "bladeRF x40만 지원합니다."); }
  if (info.at("library") != "2.6.0" || info.at("firmware") != "2.6.0" || info.at("fpga") != "0.16.0") {
    throw Failure("E_VERSION_POLICY", "이 실험실의 허용 조합: libbladeRF 2.6.0 / FW 2.6.0 / FPGA 0.16.0");
  }
  if (info.at("usb") != "super-speed") { throw Failure("E_USB_SPEED", "USB 3.0 SuperSpeed가 필요합니다."); }
  if (info.at("rx_channels") != 1 || info.at("tx_channels") != 1) { throw Failure("E_CHANNELS", "1RX/1TX가 필요합니다."); }
}

class StopGuard {
  Device& device;
  bool active = true;
public:
  explicit StopGuard(Device& d) : device(d) {}
  void stop() {
    std::exception_ptr error;
    try { device.enable(Direction::tx, false); } catch (...) { error = std::current_exception(); }
    try { device.enable(Direction::rx, false); } catch (...) { if (!error) { error = std::current_exception(); } }
    if (error) { std::rethrow_exception(error); }
    active = false;
  }
  ~StopGuard() { if (active) { try { stop(); } catch (...) {} } }
};

json loopback(Device& device) {
  verify(device.inspect());
  StopGuard guard(device);
  device.enable(Direction::tx, false);
  device.enable(Direction::rx, false);
  device.isolate();
  if (!device.isolated()) { throw Failure("E_ISOLATION", "firmware loopback/PA 격리 확인 실패", 0, "SKIP"); }
  // 고정 I/Q 진단 패턴만 사용한다. 입력 파일이나 PWS payload를 받는 API가 없다.
  constexpr unsigned samples = 65536;
  std::vector<int16_t> pattern(samples * 2);
  for (size_t i = 0; i < pattern.size(); ++i) { pattern[i] = i % 2 ? 0x2cc : 0x2ee; }
  device.configure(Direction::rx, false);
  device.configure(Direction::tx, false);
  device.enable(Direction::rx, true);
  device.enable(Direction::tx, true);
  if (!device.isolated()) { throw Failure("E_ISOLATION", "stream 활성화 후 격리 확인 실패", 0, "SKIP"); }
  RxBlock received;
  std::exception_ptr receive_error;
  std::thread rx([&] {
    try { received = device.receive(samples, false); } catch (...) { receive_error = std::current_exception(); }
  });
  try { device.transmit(pattern); }
  catch (...) { rx.join(); throw; }
  rx.join();
  if (receive_error) { std::rethrow_exception(receive_error); }
  if (received.status) { throw Failure("E_BUFFER", "RX overrun/underrun", static_cast<int>(received.status)); }
  if (received.iq != pattern) { throw Failure("E_SAMPLES", "수신 I/Q가 고정 진단 패턴과 다릅니다."); }
  if (!device.isolated()) { throw Failure("E_ISOLATION", "종료 전 격리 확인 실패"); }
  guard.stop();
  return {{"samples_processed", samples}, {"streaming_errors", 0}, {"buffer_errors", 0},
          {"timestamp_consistency", "SKIP"}, {"timestamp_reason", "FX3 loopback은 FPGA timestamp 경로를 우회합니다."},
          {"loopback", "firmware"}, {"external_pa_enabled", false}, {"cleanup", "PASS"}};
}

json rx_diagnostic(Device& device) {
  verify(device.inspect());
  StopGuard guard(device);
  device.enable(Direction::tx, false);
  device.enable(Direction::rx, false);
  device.configure(Direction::rx, true);
  device.enable(Direction::rx, true);
  auto first = device.receive(4096, true);
  auto second = device.receive(4096, true);
  if (first.status || second.status) { throw Failure("E_BUFFER", "RX metadata buffer error", first.status | second.status); }
  if (first.iq.size() != 8192 || second.iq.size() != 8192) { throw Failure("E_SAMPLES", "RX sample 수 오류"); }
  if (second.timestamp != first.timestamp + 4096) { throw Failure("E_TIMESTAMP", "RX timestamp 불연속"); }
  guard.stop();
  return {{"samples_processed", 8192}, {"streaming_errors", 0}, {"buffer_errors", 0},
          {"timestamp_consistency", "PASS"}, {"timestamp_first", first.timestamp}, {"timestamp_second", second.timestamp},
          {"tx_enabled", false}, {"cleanup", "PASS"}};
}
} // namespace lab
