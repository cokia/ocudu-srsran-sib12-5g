// SPDX-License-Identifier: BSD-3-Clause
#include "stream.h"
#include <libbladeRF.h>

// bladeRF1.h는 libbladeRF.h의 API_EXPORT 및 공통 type 정의가 필요하다.
#include <bladeRF1.h>
#include <algorithm>
#include <cctype>
#include <cmath>
namespace lab::radio {
namespace {
void check(int rc, const char* operation)
{
  if (rc < 0) {
    throw Error(
        rc == BLADERF_ERR_TIME_PAST ? "E_LATE" : "E_USB", std::string(operation) + ": " + bladerf_strerror(rc), rc);
  }
}
class Usb final : public Transport
{
  bladerf* device = nullptr;

public:
  explicit Usb(const Settings& s)
  {
#ifndef LAB_ENABLE_BLADERF_RF
    (void)s;
    throw Error("E_RF_BUILD_DISABLED", "실물 RF는 기본 build에서 비활성화되어 있습니다.");
#else
    if (s.serial.size() != 32 ||
        !std::all_of(s.serial.begin(), s.serial.end(), [](unsigned char c) { return std::isxdigit(c); })) {
      throw Error("E_SERIAL", "명시적인 x40 serial 32 hex 문자가 필요합니다.");
    }
    std::string serial = s.serial;
    std::transform(serial.begin(), serial.end(), serial.begin(), [](unsigned char c) { return std::tolower(c); });
    bladerf_set_usb_reset_on_open(false);
    check(bladerf_open(&device, ("*:serial=" + serial).c_str()), "open");
    try {
      bladerf_fpga_size size{};
      check(bladerf_get_fpga_size(device, &size), "fpga-size");
      if (std::string(bladerf_get_board_name(device)) != "bladerf1" || size != BLADERF_FPGA_40KLE) {
        throw Error("E_MODEL", "bladeRF x40만 지원합니다.");
      }
      if (bladerf_device_speed(device) != BLADERF_DEVICE_SPEED_SUPER) {
        throw Error("E_USB_SPEED", "USB SuperSpeed가 필요합니다.");
      }
      struct bladerf_version lib {
      }, fw{}, fpga{};
      bladerf_version(&lib);
      check(bladerf_fw_version(device, &fw), "firmware");
      check(bladerf_fpga_version(device, &fpga), "fpga");
      if (lib.major != 2 || lib.minor != 6 || lib.patch != 0 || fw.major != 2 || fw.minor != 6 || fw.patch != 0 ||
          fpga.major != 0 || fpga.minor != 16 || fpga.patch != 0) {
        throw Error("E_VERSION", "검증 대상은 lib/FW 2.6.0, FPGA 0.16.0입니다.");
      }
      bladerf_loopback loop{};
      check(bladerf_get_loopback(device, &loop), "loopback");
      if (loop != BLADERF_LB_NONE) {
        throw Error("E_LOOPBACK", "timed RF는 normal device 상태가 필요합니다.");
      }
      for (auto channel : {BLADERF_CHANNEL_RX(0), BLADERF_CHANNEL_TX(0)}) {
        check(bladerf_enable_module(device, channel, false), "disable");
        unsigned actual = 0;
        check(bladerf_set_sample_rate(device, channel, static_cast<unsigned>(s.rate), &actual), "sample-rate");
        if (actual != s.rate) {
          throw Error("E_SAMPLE_RATE", "RX/TX sample rate가 요청과 다릅니다.");
        }
        const bool tx = channel == BLADERF_CHANNEL_TX(0);
        check(bladerf_set_frequency(device, channel, static_cast<uint64_t>(tx ? s.tx_frequency : s.rx_frequency)),
              "frequency");
        check(bladerf_set_gain(device, channel, static_cast<int>(tx ? s.tx_gain : s.rx_gain)), "gain");
        check(
            bladerf_set_bandwidth(device, channel, static_cast<unsigned>(std::min(28000000.0, s.rate * 0.8)), &actual),
            "bandwidth");
        check(bladerf_sync_config(
                  device, tx ? BLADERF_TX_X1 : BLADERF_RX_X1, BLADERF_FORMAT_SC16_Q11_META, 16, 4096, 8, 250),
              "sync-config");
      }
    } catch (...) {
      stop();
      bladerf_close(device);
      device = nullptr;
      throw;
    }
#endif
  }
  ~Usb() override
  {
    if (device) {
      stop();
      bladerf_close(device);
    }
  }
  uint64_t clock() override
  {
    bladerf_timestamp tick{};
    check(bladerf_get_timestamp(device, BLADERF_RX, &tick), "timestamp");
    return tick;
  }
  void start() override
  {
    try {
      check(bladerf_enable_module(device, BLADERF_CHANNEL_RX(0), true), "enable-rx");
      check(bladerf_enable_module(device, BLADERF_CHANNEL_TX(0), true), "enable-tx");
    } catch (...) {
      stop();
      throw;
    }
  }
  void stop() noexcept override
  {
    if (device) {
      bladerf_enable_module(device, BLADERF_CHANNEL_TX(0), false);
      bladerf_enable_module(device, BLADERF_CHANNEL_RX(0), false);
    }
  }
  uint32_t send(const int16_t* iq, unsigned count, uint64_t timestamp, bool first) override
  {
    bladerf_metadata metadata{};
    metadata.timestamp = timestamp;
    // BURST_END는 USB buffer flush gap을 만들므로 연속 gNB stream 중에는 사용하지 않는다.
    metadata.flags = first ? BLADERF_META_FLAG_TX_BURST_START : BLADERF_META_FLAG_TX_UPDATE_TIMESTAMP;
    check(bladerf_sync_tx(device, iq, count, &metadata, 250), "sync-tx");
    return metadata.status;
  }
  Received receive(int16_t* iq, unsigned count, uint64_t timestamp) override
  {
    bladerf_metadata metadata{};
    metadata.timestamp = timestamp;
    check(bladerf_sync_rx(device, iq, count, &metadata, 250), "sync-rx");
    return {metadata.timestamp, metadata.status, metadata.actual_count};
  }
};
} // namespace
std::unique_ptr<Transport> make_usb(const Settings& settings)
{
  return std::make_unique<Usb>(settings);
}
} // namespace lab::radio
