// SPDX-License-Identifier: BSD-3-Clause
#include "stream.h"
#include <libbladeRF.h>

// bladeRF1.h는 libbladeRF.h의 API_EXPORT 및 공통 type 정의가 필요하다.
#include <bladeRF1.h>
#include <cstring>
#include <gtest/gtest.h>
#include <limits>
using namespace lab::radio;
namespace {
struct State {
  unsigned opens = 0, closes = 0, configs = 0, enabled = 0, disabled = 0, tx_flags = 0, rx_flags = 0;
  int      rate_error = 0, tx_error = 0, rx_error = 0, enable_error = 0;
  bool     wrong_board = false, wrong_fpga = false, wrong_rate = false, short_rx = false;
  uint64_t tx_time = 0, rx_time = 0;
  uint32_t status = 0;
} state;
int token;
class UsbTest : public testing::Test
{
  void SetUp() override { state = {}; }
};
Settings settings()
{
  Settings s;
  s.serial = "0123456789abcdef0123456789abcdef";
  return s;
}
template <class F>
void failure(F action, const char* code)
{
  try {
    action();
    FAIL();
  } catch (const Error& e) {
    EXPECT_EQ(e.code, code);
  }
}
} // namespace
extern "C" {
void __wrap_bladerf_set_usb_reset_on_open(bool v)
{
  EXPECT_FALSE(v);
}
int __wrap_bladerf_open(bladerf** d, const char* selector)
{
  EXPECT_STREQ(selector, "*:serial=0123456789abcdef0123456789abcdef");
  *d = reinterpret_cast<bladerf*>(&token);
  ++state.opens;
  return 0;
}
void __wrap_bladerf_close(bladerf*)
{
  ++state.closes;
}
int __wrap_bladerf_get_fpga_size(bladerf*, bladerf_fpga_size* s)
{
  *s = state.wrong_fpga ? BLADERF_FPGA_115KLE : BLADERF_FPGA_40KLE;
  return 0;
}
const char* __wrap_bladerf_get_board_name(bladerf*)
{
  return state.wrong_board ? "bladerf2" : "bladerf1";
}
bladerf_dev_speed __wrap_bladerf_device_speed(bladerf*)
{
  return BLADERF_DEVICE_SPEED_SUPER;
}
int __wrap_bladerf_fw_version(bladerf*, struct bladerf_version* v)
{
  *v = {2, 6, 0, "double"};
  return 0;
}
int __wrap_bladerf_fpga_version(bladerf*, struct bladerf_version* v)
{
  *v = {0, 16, 0, "double"};
  return 0;
}
int __wrap_bladerf_get_loopback(bladerf*, bladerf_loopback* m)
{
  *m = BLADERF_LB_NONE;
  return 0;
}
int __wrap_bladerf_enable_module(bladerf*, bladerf_channel channel, bool enabled)
{
  if (enabled) {
    ++state.enabled;
    if (channel == BLADERF_CHANNEL_TX(0)) {
      return state.enable_error;
    }
  } else {
    ++state.disabled;
  }
  return 0;
}
int __wrap_bladerf_set_sample_rate(bladerf*, bladerf_channel, unsigned rate, unsigned* actual)
{
  *actual = state.wrong_rate ? rate - 1 : rate;
  return state.rate_error;
}
int __wrap_bladerf_set_frequency(bladerf*, bladerf_channel, bladerf_frequency f)
{
  EXPECT_GT(f, 237500000U);
  return 0;
}
int __wrap_bladerf_set_gain(bladerf*, bladerf_channel, int)
{
  return 0;
}
int __wrap_bladerf_set_bandwidth(bladerf*, bladerf_channel, unsigned b, unsigned* actual)
{
  *actual = b;
  return 0;
}
int __wrap_bladerf_sync_config(bladerf*,
                               bladerf_channel_layout layout,
                               bladerf_format         f,
                               unsigned               buffers,
                               unsigned               size,
                               unsigned               transfers,
                               unsigned               timeout)
{
  EXPECT_TRUE(layout == BLADERF_RX_X1 || layout == BLADERF_TX_X1);
  EXPECT_EQ(f, BLADERF_FORMAT_SC16_Q11_META);
  EXPECT_EQ(buffers, 16U);
  EXPECT_EQ(size, 4096U);
  EXPECT_EQ(transfers, 8U);
  EXPECT_EQ(timeout, 250U);
  ++state.configs;
  return 0;
}
int __wrap_bladerf_get_timestamp(bladerf*, bladerf_direction, bladerf_timestamp* t)
{
  *t = 100000;
  return 0;
}
int __wrap_bladerf_sync_tx(bladerf*, const void*, unsigned, bladerf_metadata* m, unsigned timeout)
{
  state.tx_flags = m->flags;
  state.tx_time  = m->timestamp;
  m->status      = state.status;
  EXPECT_EQ(timeout, 250U);
  return state.tx_error;
}
int __wrap_bladerf_sync_rx(bladerf*, void* data, unsigned count, bladerf_metadata* m, unsigned timeout)
{
  state.rx_flags  = m->flags;
  state.rx_time   = m->timestamp;
  m->actual_count = state.short_rx ? count - 1 : count;
  m->status       = state.status;
  std::memset(data, 0, count * 2 * sizeof(int16_t));
  EXPECT_EQ(timeout, 250U);
  return state.rx_error;
}
}
TEST_F(UsbTest, ActualLibraryVersionAndConfigureWithoutEnable)
{
  struct bladerf_version v {};
  bladerf_version(&v);
  ASSERT_EQ(v.major, 2);
  ASSERT_EQ(v.minor, 6);
  {
    auto usb = make_usb(settings());
    EXPECT_EQ(state.configs, 2U);
    EXPECT_EQ(state.enabled, 0U);
    EXPECT_EQ(usb->clock(), 100000U);
  }
  EXPECT_EQ(state.closes, 1U);
}
TEST_F(UsbTest, TimedMetadataAndNoTxNowOrPerBlockBurstEnd)
{
  auto usb = make_usb(settings());
  usb->start();
  int16_t iq[16]{};
  usb->send(iq, 8, 101000, true);
  EXPECT_EQ(state.tx_flags, BLADERF_META_FLAG_TX_BURST_START);
  EXPECT_EQ(state.tx_time, 101000U);
  usb->send(iq, 8, 101008, false);
  EXPECT_EQ(state.tx_flags, BLADERF_META_FLAG_TX_UPDATE_TIMESTAMP);
  auto got = usb->receive(iq, 8, 101000);
  EXPECT_EQ(state.rx_flags, 0U);
  EXPECT_EQ(state.rx_time, 101000U);
  EXPECT_EQ(got.timestamp, 101000U);
  EXPECT_EQ(got.count, 8U);
}
TEST_F(UsbTest, VersionModelAndRateFailuresCloseDevice)
{
  state.wrong_fpga = true;
  failure([] { make_usb(settings()); }, "E_MODEL");
  EXPECT_EQ(state.closes, 1U);
  EXPECT_EQ(state.enabled, 0U);
  state            = {};
  state.wrong_rate = true;
  failure([] { make_usb(settings()); }, "E_SAMPLE_RATE");
  EXPECT_EQ(state.closes, 1U);
}
TEST_F(UsbTest, InvalidSerialFailsBeforeOpen)
{
  auto s   = settings();
  s.serial = "invalid";
  failure([&] { make_usb(s); }, "E_SERIAL");
  EXPECT_EQ(state.opens, 0U);
}
TEST_F(UsbTest, EnableFailureDisablesBothDirections)
{
  auto     usb       = make_usb(settings());
  unsigned before    = state.disabled;
  state.enable_error = BLADERF_ERR_IO;
  failure([&] { usb->start(); }, "E_USB");
  EXPECT_GE(state.disabled, before + 2);
}
TEST_F(UsbTest, LateTimestampAndDisconnectedDeviceAreExplicit)
{
  auto    usb = make_usb(settings());
  int16_t iq[16]{};
  state.tx_error = BLADERF_ERR_TIME_PAST;
  failure([&] { usb->send(iq, 8, 1, true); }, "E_LATE");
  state.rx_error = BLADERF_ERR_NODEV;
  failure([&] { usb->receive(iq, 8, 1); }, "E_USB");
}
TEST_F(UsbTest, ShortReceiveAndOverrunStatusReachSession)
{
  auto    usb = make_usb(settings());
  int16_t iq[16]{};
  state.short_rx = true;
  state.status   = BLADERF_META_STATUS_OVERRUN;
  auto got       = usb->receive(iq, 8, 100);
  EXPECT_EQ(got.count, 7U);
  EXPECT_EQ(got.status, BLADERF_META_STATUS_OVERRUN);
}
TEST_F(UsbTest, Q11SaturationAndIntegerScale)
{
  Sample  input[] = {{32767, -32768}, {0, 16384}};
  int16_t iq[4]{};
  to_q11(input, iq, 2);
  EXPECT_EQ(iq[0], 2047);
  EXPECT_EQ(iq[1], -2048);
  EXPECT_EQ(iq[2], 0);
  EXPECT_EQ(iq[3], 1024);
  Sample output[2];
  from_q11(iq, output, 2);
  EXPECT_EQ(output[0].imag(), -32767);
  EXPECT_EQ(output[1].real(), 0);
}
