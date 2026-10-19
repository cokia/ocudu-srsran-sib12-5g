// SPDX-License-Identifier: BSD-3-Clause
#include "device.h"
#include <libbladeRF.h>
#include <bladeRF1.h>
#include <algorithm>
#include <cctype>

namespace lab {
namespace {
void check(int code, const char* operation) {
  if (code < 0) { throw Failure("E_DRIVER", std::string(operation) + ": " + bladerf_strerror(code), code); }
}
std::string version(const struct bladerf_version& v) {
  return std::to_string(v.major) + "." + std::to_string(v.minor) + "." + std::to_string(v.patch);
}
bladerf_channel channel(Direction d) { return d == Direction::rx ? BLADERF_CHANNEL_RX(0) : BLADERF_CHANNEL_TX(0); }
}
json driver_info() {
  struct bladerf_version v{};
  bladerf_version(&v);
  return {{"available", true}, {"version", version(v)}, {"description", v.describe}};
}
class RealDevice final : public Device {
  bladerf* handle = nullptr;
  bool streaming_owned = false;
public:
  explicit RealDevice(const std::string& serial) {
    if (!serial.empty() && (serial.size() != 32 || !std::all_of(serial.begin(), serial.end(), [](unsigned char c) { return std::isxdigit(c); }))) {
      throw Failure("E_SERIAL", "32자리 hexadecimal serial이 필요합니다.");
    }
    std::string requested_serial = serial;
    // libbladeRF devinfo parser와 같은 소문자 hex 정규화를 적용한다.
    std::transform(requested_serial.begin(), requested_serial.end(), requested_serial.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    bladerf_set_usb_reset_on_open(false);
    bladerf_devinfo* list = nullptr;
    int count = bladerf_get_device_list(&list);
    if (count < 0) { throw Failure("E_DISCOVERY", bladerf_strerror(count), count, "BLOCKED"); }
    if (count == 0) { throw Failure("E_NO_DEVICE", "USB 장치를 찾지 못했습니다.", BLADERF_ERR_NODEV, "BLOCKED"); }
    if (serial.empty() && count != 1) {
      bladerf_free_device_list(list);
      throw Failure("E_DEVICE_SELECTION", "여러 장치가 있습니다. --serial이 필요합니다.", 0, "BLOCKED");
    }
    bladerf_devinfo selected{};
    bool found = false;
    for (int i = 0; i < count; ++i) {
      if (requested_serial.empty() || requested_serial == list[i].serial) { selected = list[i]; found = true; break; }
    }
    bladerf_free_device_list(list);
    if (!found) { throw Failure("E_NO_DEVICE", "선택한 serial을 찾지 못했습니다.", BLADERF_ERR_NODEV, "BLOCKED"); }
    int rc = bladerf_open_with_devinfo(&handle, &selected);
    if (rc < 0) { throw Failure("E_OPEN", bladerf_strerror(rc), rc, "BLOCKED"); }
  }
  ~RealDevice() override {
    if (handle) {
      if (streaming_owned) {
        bladerf_enable_module(handle, BLADERF_CHANNEL_TX(0), false);
        bladerf_enable_module(handle, BLADERF_CHANNEL_RX(0), false);
      }
      bladerf_close(handle);
    }
  }
  json inspect() override {
    struct bladerf_version library{}, firmware{}, fpga{};
    bladerf_version(&library);
    check(bladerf_fw_version(handle, &firmware), "fw_version");
    bladerf_fpga_size size = BLADERF_FPGA_UNKNOWN;
    check(bladerf_get_fpga_size(handle, &size), "fpga_size");
    int loaded = bladerf_is_fpga_configured(handle);
    check(loaded, "fpga_configured");
    if (loaded) { check(bladerf_fpga_version(handle, &fpga), "fpga_version"); }
    bladerf_devinfo info{};
    check(bladerf_get_devinfo(handle, &info), "devinfo");
    std::string board = bladerf_get_board_name(handle);
    json result{{"model", board == "bladerf1" && size == BLADERF_FPGA_40KLE ? "bladeRF x40" : "unsupported"},
                {"board", board}, {"product", info.product}, {"manufacturer", info.manufacturer},
                {"serial", info.serial}, {"usb_bus", info.usb_bus}, {"usb_address", info.usb_addr},
                {"firmware", version(firmware)}, {"fpga", loaded ? version(fpga) : "not-loaded"},
                {"fpga_size", static_cast<int>(size)}, {"library", version(library)}, {"library_description", library.describe},
                {"usb", bladerf_device_speed(handle) == BLADERF_DEVICE_SPEED_SUPER ? "super-speed" : "high-speed-or-unknown"},
                {"rx_channels", bladerf_get_channel_count(handle, BLADERF_RX)},
                {"tx_channels", bladerf_get_channel_count(handle, BLADERF_TX)}, {"mock", false},
                {"sample_formats", {"SC16_Q11", "SC16_Q11_META"}},
                {"sample_formats_evidence", "libbladeRF 2.6.0 bladerf1 source; stream 사용 여부는 별도 결과"}};
    if (loaded) {
      const bladerf_range* range = nullptr;
      check(bladerf_get_sample_rate_range(handle, BLADERF_CHANNEL_RX(0), &range), "sample_rate_range");
      result["sample_rate_min"] = range->min * range->scale;
      result["sample_rate_max"] = range->max * range->scale;
      const bladerf_loopback_modes* modes = nullptr;
      int count = bladerf_get_loopback_modes(handle, &modes);
      check(count, "loopback_modes");
      result["loopback_modes"] = json::array();
      for (int i = 0; i < count; ++i) { result["loopback_modes"].push_back(modes[i].name); }
      result["firmware_loopback"] = bladerf_is_loopback_mode_supported(handle, BLADERF_LB_FIRMWARE);
      bladerf_timestamp timestamp = 0;
      int rc = bladerf_get_timestamp(handle, BLADERF_RX, &timestamp);
      result["timestamp_api"] = rc == 0 ? "PASS" : "NOT VERIFIED";
      result["timestamp_value"] = timestamp;
      result["timestamp_driver_code"] = rc;
    }
    return result;
  }
  void isolate() override {
    if (!bladerf_is_loopback_mode_supported(handle, BLADERF_LB_FIRMWARE)) {
      throw Failure("E_ISOLATION", "firmware loopback 미지원", 0, "SKIP");
    }
    check(bladerf_set_loopback(handle, BLADERF_LB_FIRMWARE), "set_firmware_loopback");
  }
  bool isolated() override {
    bladerf_loopback mode = BLADERF_LB_NONE;
    uint8_t pa = 0;
    check(bladerf_get_loopback(handle, &mode), "get_loopback");
    check(bladerf_lms_read(handle, 0x44, &pa), "read_pa_register");
    // LMS PA1/PA2 비활성화 + FX3 firmware bypass를 모두 확인한다.
    return mode == BLADERF_LB_FIRMWARE && (pa & 0x1c) == 0;
  }
  void configure(Direction direction, bool metadata) override {
    if (direction == Direction::tx && !isolated()) { throw Failure("E_ISOLATION", "TX 구성 전 격리 실패"); }
    if (metadata) {
      bladerf_loopback mode = BLADERF_LB_NONE;
      check(bladerf_get_loopback(handle, &mode), "get_loopback");
      if (mode != BLADERF_LB_NONE) { throw Failure("E_RX_MODE", "RX timestamp 검사는 전원 재연결 후 normal mode에서 실행합니다.", 0, "SKIP"); }
    }
    unsigned actual = 0;
    check(bladerf_set_sample_rate(handle, channel(direction), 1000000, &actual), "set_sample_rate");
    if (actual != 1000000) { throw Failure("E_SAMPLE_RATE", "1 MS/s 설정 불일치"); }
    check(bladerf_sync_config(handle, direction == Direction::rx ? BLADERF_RX_X1 : BLADERF_TX_X1,
                              metadata ? BLADERF_FORMAT_SC16_Q11_META : BLADERF_FORMAT_SC16_Q11,
                              8, 4096, 4, 1000), "sync_config");
  }
  void enable(Direction direction, bool value) override {
    if (direction == Direction::tx && value && !isolated()) { throw Failure("E_ISOLATION", "TX enable 전 격리 실패"); }
    streaming_owned = true;
    check(bladerf_enable_module(handle, channel(direction), value), "enable_module");
  }
  void transmit(const std::vector<int16_t>& iq) override {
    if (!isolated()) { throw Failure("E_ISOLATION", "TX 전 격리 실패"); }
    check(bladerf_sync_tx(handle, iq.data(), static_cast<unsigned>(iq.size() / 2), nullptr, 2000), "sync_tx");
  }
  RxBlock receive(unsigned samples, bool metadata) override {
    RxBlock result;
    result.iq.resize(samples * 2);
    bladerf_metadata meta{};
    meta.flags = BLADERF_META_FLAG_RX_NOW;
    check(bladerf_sync_rx(handle, result.iq.data(), samples, metadata ? &meta : nullptr, 2000), "sync_rx");
    if (metadata && meta.actual_count != samples) { throw Failure("E_SAMPLES", "RX actual_count 불일치"); }
    result.timestamp = meta.timestamp;
    result.status = meta.status;
    return result;
  }
};
std::unique_ptr<Device> make_real(const std::string& serial) { return std::make_unique<RealDevice>(serial); }
} // namespace lab
