// SPDX-License-Identifier: BSD-3-Clause
// 실제 RealDevice를 사용하되 USB를 여는 C API만 linker boundary에서 대체한다.
#include "driver_adapter/device.h"
#include <libbladeRF.h>
#include <bladeRF1.h>
#include <gtest/gtest.h>
#include <algorithm>
#include <cstdlib>
#include <cstring>

namespace {
struct State {
  int count = 1, open_error = 0, rx_error = 0, lists = 0, closes = 0;
  unsigned tx_calls = 0, configs = 0, enables = 0;
  bool reset = true, supported = true, tx = false, rx = false, short_read = false;
  bool wrong_rate = false, isolation_lost_after_enable = false;
  uint32_t rx_status = 0;
  bladerf_format rx_format = BLADERF_FORMAT_SC16_Q11;
  uint8_t pa = 0;
  uint64_t timestamp = 1000;
  bladerf_loopback mode = BLADERF_LB_NONE;
} state;
int token;
constexpr const char* serial = "0123456789abcdef0123456789abcdef";
class Adapter : public testing::Test {
  void SetUp() override { state = State{}; }
  void TearDown() override { EXPECT_EQ(state.lists, 0); }
};
template <typename F> void failure(F action, const char* code, int driver = 0) {
  try { action(); FAIL() << "오류 없이 종료"; }
  catch (const lab::Failure& e) { EXPECT_EQ(e.code, code); EXPECT_EQ(e.driver_code, driver); }
}
}

extern "C" {
void __wrap_bladerf_set_usb_reset_on_open(bool enabled) { state.reset = enabled; }
int __wrap_bladerf_get_device_list(bladerf_devinfo** list) {
  if (state.count <= 0) { *list = nullptr; return state.count; }
  *list = static_cast<bladerf_devinfo*>(std::calloc(state.count, sizeof(bladerf_devinfo)));
  ++state.lists;
  for (int i = 0; i < state.count; ++i) { std::strcpy((*list)[i].serial, serial); (*list)[i].instance = i; }
  return state.count;
}
void __wrap_bladerf_free_device_list(bladerf_devinfo* list) { if (list) { --state.lists; std::free(list); } }
int __wrap_bladerf_open_with_devinfo(bladerf** handle, bladerf_devinfo* info) {
  EXPECT_STREQ(info->serial, serial);
  if (state.open_error) { return state.open_error; }
  *handle = reinterpret_cast<bladerf*>(&token); return 0;
}
void __wrap_bladerf_close(bladerf*) { ++state.closes; }
int __wrap_bladerf_get_devinfo(bladerf*, bladerf_devinfo* info) {
  *info = {}; std::strcpy(info->serial, serial); std::strcpy(info->product, "C API TEST DOUBLE"); return 0;
}
int __wrap_bladerf_fw_version(bladerf*, struct bladerf_version* v) { *v = {2, 6, 0, "test"}; return 0; }
int __wrap_bladerf_fpga_version(bladerf*, struct bladerf_version* v) { *v = {0, 16, 0, "test"}; return 0; }
int __wrap_bladerf_get_fpga_size(bladerf*, bladerf_fpga_size* s) { *s = BLADERF_FPGA_40KLE; return 0; }
int __wrap_bladerf_is_fpga_configured(bladerf*) { return 1; }
const char* __wrap_bladerf_get_board_name(bladerf*) { return "bladerf1"; }
bladerf_dev_speed __wrap_bladerf_device_speed(bladerf*) { return BLADERF_DEVICE_SPEED_SUPER; }
size_t __wrap_bladerf_get_channel_count(bladerf*, bladerf_direction) { return 1; }
int __wrap_bladerf_get_sample_rate_range(bladerf*, bladerf_channel, const bladerf_range** r) {
  static const bladerf_range range{80000, 40000000, 1, 1}; *r = &range; return 0;
}
int __wrap_bladerf_get_loopback_modes(bladerf*, const bladerf_loopback_modes** m) {
  static const bladerf_loopback_modes modes[] = {{"firmware", BLADERF_LB_FIRMWARE}}; *m = modes; return 1;
}
bool __wrap_bladerf_is_loopback_mode_supported(bladerf*, bladerf_loopback m) { return state.supported && m == BLADERF_LB_FIRMWARE; }
int __wrap_bladerf_get_timestamp(bladerf*, bladerf_direction, bladerf_timestamp* t) { *t = state.timestamp; return 0; }
int __wrap_bladerf_set_loopback(bladerf*, bladerf_loopback m) { state.mode = m; return 0; }
int __wrap_bladerf_get_loopback(bladerf*, bladerf_loopback* m) { *m = state.mode; return 0; }
int __wrap_bladerf_lms_read(bladerf*, uint8_t address, uint8_t* value) { EXPECT_EQ(address, 0x44); *value = state.pa; return 0; }
int __wrap_bladerf_set_sample_rate(bladerf*, bladerf_channel, bladerf_sample_rate rate, bladerf_sample_rate* actual) {
  EXPECT_EQ(rate, 1000000u); *actual = state.wrong_rate ? rate - 1 : rate; return 0;
}
int __wrap_bladerf_sync_config(bladerf*, bladerf_channel_layout layout, bladerf_format format,
                             unsigned buffers, unsigned size, unsigned transfers, unsigned timeout) {
  EXPECT_TRUE(layout == BLADERF_RX_X1 || layout == BLADERF_TX_X1);
  EXPECT_TRUE(format == BLADERF_FORMAT_SC16_Q11 || format == BLADERF_FORMAT_SC16_Q11_META);
  if (layout == BLADERF_RX_X1) { state.rx_format = format; }
  else { EXPECT_EQ(format, BLADERF_FORMAT_SC16_Q11); }
  EXPECT_EQ(buffers, 8u); EXPECT_EQ(size, 4096u); EXPECT_EQ(transfers, 4u); EXPECT_EQ(timeout, 1000u);
  ++state.configs; return 0;
}
int __wrap_bladerf_enable_module(bladerf*, bladerf_channel channel, bool enabled) {
  if (channel == BLADERF_CHANNEL_TX(0)) {
    if (enabled) { EXPECT_EQ(state.mode, BLADERF_LB_FIRMWARE); EXPECT_EQ(state.pa & 0x1c, 0); ++state.enables; }
    state.tx = enabled;
    if (enabled && state.isolation_lost_after_enable) { state.pa = 0x08; }
  } else { state.rx = enabled; }
  return 0;
}
int __wrap_bladerf_sync_tx(bladerf*, const void*, unsigned samples, bladerf_metadata* meta, unsigned timeout) {
  EXPECT_TRUE(state.tx); EXPECT_EQ(samples, 65536u); EXPECT_EQ(meta, nullptr); EXPECT_EQ(timeout, 2000u);
  ++state.tx_calls; return 0;
}
int __wrap_bladerf_sync_rx(bladerf*, void* samples, unsigned count, bladerf_metadata* meta, unsigned timeout) {
  EXPECT_TRUE(state.rx); EXPECT_EQ(timeout, 2000u);
  EXPECT_EQ(state.rx_format, meta ? BLADERF_FORMAT_SC16_Q11_META : BLADERF_FORMAT_SC16_Q11);
  if (state.rx_error) { return state.rx_error; }
  auto* iq = static_cast<int16_t*>(samples);
  for (unsigned i = 0; i < count * 2; ++i) { iq[i] = i % 2 ? 0x2cc : 0x2ee; }
  if (meta) {
    EXPECT_EQ(meta->flags, BLADERF_META_FLAG_RX_NOW);
    meta->actual_count = state.short_read ? count - 1 : count; meta->timestamp = state.timestamp; state.timestamp += count;
    meta->status = state.rx_status;
  }
  return 0;
}
}

TEST_F(Adapter, ActualLibraryVersionAndParser) {
  EXPECT_EQ(lab::driver_info()["version"], "2.6.0");
  bladerf_devinfo info{};
  EXPECT_EQ(bladerf_get_devinfo_from_str("*:serial=0123456789abcdef0123456789abcdef", &info), 0);
  EXPECT_STREQ(info.serial, serial);
  EXPECT_LT(bladerf_get_devinfo_from_str("invalid-backend:", &info), 0);
}
TEST_F(Adapter, DiscoveryError) { state.count = BLADERF_ERR_NODEV; failure([] { lab::make_real(""); }, "E_DISCOVERY", BLADERF_ERR_NODEV); }
TEST_F(Adapter, EmptyDiscovery) { state.count = 0; failure([] { lab::make_real(""); }, "E_NO_DEVICE", BLADERF_ERR_NODEV); }
TEST_F(Adapter, AmbiguousDevices) { state.count = 2; failure([] { lab::make_real(""); }, "E_DEVICE_SELECTION"); }
TEST_F(Adapter, InvalidSerial) { failure([] { lab::make_real("invalid"); }, "E_SERIAL"); }
TEST_F(Adapter, InvalidSerialRejectedBeforeUsbDiscovery) {
  state.count = 0; failure([] { lab::make_real("invalid"); }, "E_SERIAL");
}
TEST_F(Adapter, HexSerialIsCaseInsensitive) {
  auto d = lab::make_real("0123456789ABCDEF0123456789ABCDEF");
  EXPECT_EQ(d->inspect()["serial"], serial);
}
TEST_F(Adapter, MissingSerial) { failure([] { lab::make_real(std::string(32, 'f')); }, "E_NO_DEVICE", BLADERF_ERR_NODEV); }
TEST_F(Adapter, OpenFailure) { state.open_error = BLADERF_ERR_PERMISSION; failure([] { lab::make_real(""); }, "E_OPEN", BLADERF_ERR_PERMISSION); }
TEST_F(Adapter, ProbeDoesNotStream) {
  { auto d = lab::make_real(serial); lab::verify(d->inspect()); EXPECT_FALSE(state.reset); EXPECT_EQ(state.configs, 0u); EXPECT_EQ(state.enables, 0u); }
  EXPECT_EQ(state.closes, 1);
}
TEST_F(Adapter, TxRequiresIsolationAtEveryBoundary) {
  auto d = lab::make_real("");
  failure([&] { d->configure(lab::Direction::tx, false); }, "E_ISOLATION");
  failure([&] { d->enable(lab::Direction::tx, true); }, "E_ISOLATION");
  failure([&] { d->transmit({1, 2}); }, "E_ISOLATION");
  EXPECT_EQ(state.configs, 0u); EXPECT_EQ(state.enables, 0u); EXPECT_EQ(state.tx_calls, 0u);
}
TEST_F(Adapter, UnsupportedFirmwareLoopbackNeverEnablesTx) {
  state.supported = false; auto d = lab::make_real("");
  failure([&] { lab::loopback(*d); }, "E_ISOLATION"); EXPECT_EQ(state.enables, 0u);
}
TEST_F(Adapter, AnyExternalPaBitBlocksLoopback) {
  for (auto bit : {0x04, 0x08, 0x10}) {
    state.pa = bit; auto d = lab::make_real("");
    failure([&] { lab::loopback(*d); }, "E_ISOLATION"); EXPECT_EQ(state.enables, 0u);
  }
}
TEST_F(Adapter, LoopbackUsesBoundedProfileAndCleansUp) {
  auto d = lab::make_real(""); auto r = lab::loopback(*d);
  EXPECT_EQ(r["samples_processed"], 65536); EXPECT_EQ(state.tx_calls, 1u); EXPECT_FALSE(state.tx); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, RxUsesMetadataAndNeverEnablesTx) {
  auto d = lab::make_real(""); EXPECT_EQ(lab::rx_diagnostic(*d)["timestamp_consistency"], "PASS");
  EXPECT_EQ(state.enables, 0u); EXPECT_EQ(state.tx_calls, 0u); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, ShortReadRejectedAndCleanupRuns) {
  state.short_read = true; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_SAMPLES"); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, UsbTimeoutPreservedAndCleanupRuns) {
  state.rx_error = BLADERF_ERR_TIMEOUT; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_DRIVER", BLADERF_ERR_TIMEOUT); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, FirmwareModeCannotFakeTimestampTest) {
  state.mode = BLADERF_LB_FIRMWARE; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_RX_MODE"); EXPECT_EQ(state.configs, 0u);
}
TEST_F(Adapter, RxOverrunRejected) {
  state.rx_status = BLADERF_META_STATUS_OVERRUN; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_BUFFER", BLADERF_META_STATUS_OVERRUN); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, DisconnectPreservesDriverCode) {
  state.rx_error = BLADERF_ERR_NODEV; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_DRIVER", BLADERF_ERR_NODEV); EXPECT_FALSE(state.rx);
}
TEST_F(Adapter, ActualSampleRateMustMatchRequestedRate) {
  state.wrong_rate = true; auto d = lab::make_real("");
  failure([&] { lab::rx_diagnostic(*d); }, "E_SAMPLE_RATE"); EXPECT_EQ(state.configs, 0u);
}
TEST_F(Adapter, IsolationLostAfterEnableBlocksSampleTransfer) {
  state.isolation_lost_after_enable = true; auto d = lab::make_real("");
  failure([&] { lab::loopback(*d); }, "E_ISOLATION");
  EXPECT_EQ(state.tx_calls, 0u); EXPECT_FALSE(state.tx); EXPECT_FALSE(state.rx);
}
