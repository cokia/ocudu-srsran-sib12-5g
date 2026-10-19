// SPDX-License-Identifier: BSD-3-Clause
#include "device.h"
#include <algorithm>
#include <atomic>

namespace lab {
class MockDevice final : public Device {
  std::string fault;
  bool loop = false;
  bool started = false;
  uint64_t timestamp = 1000;
public:
  explicit MockDevice(std::string f) : fault(std::move(f)) {}
  json inspect() override {
    if (fault == "no-device") { throw Failure("E_NO_DEVICE", "mock: 장치 없음", -7, "BLOCKED"); }
    if (fault == "permission") { throw Failure("E_OPEN", "mock: USB 접근 거부", -5, "BLOCKED"); }
    return {{"model", fault == "wrong-model" ? "bladeRF 2.0" : "bladeRF x40"},
            {"board", fault == "wrong-model" ? "bladerf2" : "bladerf1"},
            {"fpga_size", fault == "x115" ? 115 : 40}, {"firmware", fault == "firmware" ? "1.6.0" : "2.6.0"},
            {"fpga", fault == "fpga" ? "not-loaded" : "0.16.0"}, {"library", "2.6.0"},
            {"usb", fault == "usb2" ? "high-speed" : "super-speed"},
            {"rx_channels", 1}, {"tx_channels", 1}, {"sample_rate_min", 80000}, {"sample_rate_max", 40000000},
            {"sample_formats", {"SC16_Q11", "SC16_Q11_META"}}, {"firmware_loopback", true},
            {"timestamp_api", "MOCK"}, {"mock", true}};
  }
  void isolate() override { loop = true; }
  bool isolated() override { return loop && fault != "unsafe"; }
  void configure(Direction, bool) override {}
  void enable(Direction, bool value) override {
    if (value) { started = true; }
    if (!value && started && fault == "cleanup") { throw Failure("E_CLEANUP", "mock: disable 실패", -5); }
  }
  void transmit(const std::vector<int16_t>&) override {
    if (!isolated()) { throw Failure("E_ISOLATION", "mock: 격리 실패"); }
    if (fault == "disconnect") { throw Failure("E_USB", "mock: 연결 해제", -5); }
  }
  RxBlock receive(unsigned count, bool) override {
    if (fault == "timeout") { throw Failure("E_STREAM", "mock: 전송 timeout", -6); }
    RxBlock result;
    result.iq.resize(count * 2);
    for (size_t i = 0; i < result.iq.size(); ++i) { result.iq[i] = i % 2 ? 0x2cc : 0x2ee; }
    if (fault == "corrupt") { result.iq[0] = 0; }
    result.status = fault == "overrun" ? 1 : 0;
    result.timestamp = timestamp;
    timestamp += count + (fault == "timestamp" ? 1 : 0);
    return result;
  }
};
std::unique_ptr<Device> make_mock(const std::string& fault) {
  const std::vector<std::string> allowed{"none", "no-device", "permission", "wrong-model", "x115", "firmware", "fpga", "usb2", "unsafe", "disconnect", "timeout", "corrupt", "overrun", "timestamp", "cleanup"};
  if (std::find(allowed.begin(), allowed.end(), fault) == allowed.end()) { throw Failure("E_ARGUMENT", "알 수 없는 mock fault"); }
  return std::make_unique<MockDevice>(fault);
}
} // namespace lab
