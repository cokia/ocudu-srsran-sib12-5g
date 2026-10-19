// SPDX-License-Identifier: BSD-3-Clause
#include "ocudu/gateways/baseband/baseband_gateway_receiver.h"
#include "ocudu/gateways/baseband/baseband_gateway_transmitter.h"
#include "ocudu/gateways/baseband/buffer/baseband_gateway_buffer_dynamic.h"
#include "ocudu/radio/radio_factory.h"
#include <dlfcn.h>
#include <gtest/gtest.h>
#include <mutex>
#include <thread>
using namespace ocudu;
namespace {
struct Executor : task_executor {
  bool execute(unique_task task) override
  {
    task();
    return true;
  }
  bool defer(unique_task task) override
  {
    task();
    return true;
  }
};
struct Events : radio_event_notifier {
  std::mutex                     mutex;
  std::vector<event_description> events;
  void                           on_radio_rt_event(const event_description& event) override
  {
    std::lock_guard<std::mutex> lock(mutex);
    events.push_back(event);
  }
};
radio_configuration::radio config()
{
  radio_configuration::radio c{};
  c.sampling_rate_Hz = 23040000;
  c.args             = "mode=mock,rf=off,max_seconds=2";
  radio_configuration::stream tx{}, rx{};
  tx.channels.push_back({{1842500000, 0}, 0, {}});
  rx.channels.push_back({{1747500000, 0}, 0, {}});
  c.tx_streams.push_back(tx);
  c.rx_streams.push_back(rx);
  return c;
}
TEST(RadioPlugin, DynamicSymbolMatchesUpstreamLoader)
{
  void* h = dlopen("libocudu_radio_bladerf_x40.so", RTLD_NOW);
  ASSERT_NE(h, nullptr) << dlerror();
  ASSERT_NE(dlsym(h, "_ZN5ocudu28create_dynamic_radio_factoryEv"), nullptr);
  dlclose(h);
}
TEST(RadioPlugin, ValidatesShapeClockFormatAndExplicitRfOptIn)
{
  auto f = create_dynamic_radio_factory();
  auto c = config();
  EXPECT_TRUE(f->get_configuration_validator().is_configuration_valid(c));
  c.rx_streams.clear();
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c      = config();
  c.args = "mode=hardware,rf=off";
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c      = config();
  c.args = "mode=mock,unknown=1";
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c      = config();
  c.args = "mode=mock,mode=mock";
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c             = config();
  c.clock.clock = radio_configuration::clock_sources::source::EXTERNAL;
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c            = config();
  c.otw_format = radio_configuration::over_the_wire_format::SC8;
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c                  = config();
  c.sampling_rate_Hz = 50000000;
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
  c      = config();
  c.args = "max_seconds=0";
  EXPECT_FALSE(f->get_configuration_validator().is_configuration_valid(c));
}
TEST(RadioPlugin, TimedSamplesConvertAndRoundTrip)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     s = f->create(config(), executor, events);
  ASSERT_NE(s, nullptr);
  s->start(10000);
  baseband_gateway_buffer_dynamic tx(1, 8), rx(1, 8);
  for (unsigned i = 0; i < 8; ++i) {
    tx[0][i] = {static_cast<int16_t>(i * 4096), static_cast<int16_t>(-static_cast<int>(i) * 4096)};
  }
  auto& g = s->get_baseband_gateway(0);
  g.get_transmitter().transmit(tx.get_reader(), {10000, false, {}, {}});
  auto meta = g.get_receiver().receive(rx.get_writer());
  EXPECT_EQ(meta.ts, 10000U);
  for (unsigned i = 0; i < 8; ++i) {
    EXPECT_NEAR(rx[0][i].real(), tx[0][i].real(), 16);
    EXPECT_NEAR(rx[0][i].imag(), tx[0][i].imag(), 16);
  }
  EXPECT_EQ(s->read_current_time(), 10008U);
  s->stop();
  EXPECT_TRUE(events.events.empty());
  g.get_receiver().receive(rx.get_writer());
  for (auto v : rx[0]) {
    EXPECT_EQ(v, ci16_t{});
  }
}
TEST(RadioPlugin, EmptyAndPartialTransmitAreZeroFilled)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     s = f->create(config(), executor, events);
  s->start(100);
  baseband_gateway_buffer_dynamic tx(1, 8), rx(1, 8);
  for (auto& v : tx[0]) {
    v = {32767, -32768};
  }
  auto& g = s->get_baseband_gateway(0);
  g.get_transmitter().transmit(tx.get_reader(), {100, false, 2, 5});
  g.get_receiver().receive(rx.get_writer());
  for (unsigned i = 0; i < 8; ++i) {
    if (i >= 2 && i < 5) {
      EXPECT_GT(rx[0][i].real(), 32000);
    } else {
      EXPECT_EQ(rx[0][i], ci16_t{});
    }
  }
  g.get_transmitter().transmit(tx.get_reader(), {108, true, {}, {}});
  g.get_receiver().receive(rx.get_writer());
  for (auto v : rx[0]) {
    EXPECT_EQ(v, ci16_t{});
  }
  s->stop();
}
TEST(RadioPlugin, LateTransmissionRaisesEvent)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     s = f->create(config(), executor, events);
  testing::internal::CaptureStderr();
  s->start(100);
  baseband_gateway_buffer_dynamic tx(1, 8);
  s->get_baseband_gateway(0).get_transmitter().transmit(tx.get_reader(), {99, false, {}, {}});
  s->stop();
  s.reset();
  auto log = testing::internal::GetCapturedStderr();
  EXPECT_NE(log.find("errors=0 late=1 overflow=0 underflow=0"), std::string::npos);
  ASSERT_EQ(events.events.size(), 1U);
  EXPECT_EQ(events.events[0].type, radio_event_type::LATE);
}
TEST(RadioPlugin, WatchdogStopsStream)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     c = config();
  c.args     = "mode=mock,max_seconds=1";
  auto s     = f->create(c, executor, events);
  testing::internal::CaptureStderr();
  s->start(100);
  std::this_thread::sleep_for(std::chrono::milliseconds(1100));
  s->stop();
  s.reset();
  auto log = testing::internal::GetCapturedStderr();
  EXPECT_NE(log.find("errors=1 late=0 overflow=0 underflow=0"), std::string::npos);
  ASSERT_EQ(events.events.size(), 1U);
  EXPECT_EQ(events.events[0].source, radio_event_source::OTHER);
}
TEST(RadioPlugin, FatalTransmitAfterValidSamplesIsReportedAndStopsStream)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     s = f->create(config(), executor, events);
  testing::internal::CaptureStderr();
  s->start(100);
  baseband_gateway_buffer_dynamic tx(1, 8), rx(1, 8);
  auto&                           g = s->get_baseband_gateway(0);
  g.get_transmitter().transmit(tx.get_reader(), {100, false, {}, {}});
  g.get_receiver().receive(rx.get_writer());
  g.get_transmitter().transmit(tx.get_reader(), {108, false, 5, 2});
  g.get_transmitter().transmit(tx.get_reader(), {108, false, {}, {}});
  s->stop();
  s.reset();
  auto log = testing::internal::GetCapturedStderr();
  EXPECT_NE(log.find("E_BUFFER"), std::string::npos);
  EXPECT_NE(log.find("tx_samples=8 rx_samples=8 errors=1"), std::string::npos);
  ASSERT_EQ(events.events.size(), 1U);
  EXPECT_EQ(events.events[0].type, radio_event_type::OTHER);
}
TEST(RadioPlugin, FatalReceiveAfterValidSamplesIsReportedAndZeroFilled)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     s = f->create(config(), executor, events);
  testing::internal::CaptureStderr();
  s->start(100);
  baseband_gateway_buffer_dynamic tx(1, 8), rx(1, 8), invalid(2, 8);
  auto&                           g = s->get_baseband_gateway(0);
  g.get_transmitter().transmit(tx.get_reader(), {100, false, {}, {}});
  g.get_receiver().receive(rx.get_writer());
  for (auto& sample : invalid[0]) {
    sample = {1, 1};
  }
  g.get_receiver().receive(invalid.get_writer());
  s->stop();
  s.reset();
  auto log = testing::internal::GetCapturedStderr();
  EXPECT_NE(log.find("E_BUFFER"), std::string::npos);
  EXPECT_NE(log.find("tx_samples=8 rx_samples=8 errors=1"), std::string::npos);
  for (auto sample : invalid[0]) {
    EXPECT_EQ(sample, ci16_t{});
  }
}
#ifndef LAB_ENABLE_BLADERF_RF
TEST(RadioPlugin, HardwareDisabledBuildDoesNotOpenUsb)
{
  Executor executor;
  Events   events;
  auto     f = create_dynamic_radio_factory();
  auto     c = config();
  c.args     = "mode=hardware,rf=on,serial=0123456789abcdef0123456789abcdef,max_seconds=1";
  EXPECT_EQ(f->create(c, executor, events), nullptr);
}
#endif
} // namespace
