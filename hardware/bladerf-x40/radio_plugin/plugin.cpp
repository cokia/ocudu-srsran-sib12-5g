// SPDX-License-Identifier: BSD-3-Clause
#include "stream.h"
#include "ocudu/gateways/baseband/baseband_gateway_receiver.h"
#include "ocudu/gateways/baseband/baseband_gateway_transmitter.h"
#include "ocudu/gateways/baseband/buffer/baseband_gateway_buffer_reader.h"
#include "ocudu/gateways/baseband/buffer/baseband_gateway_buffer_writer.h"
#include "ocudu/radio/radio_factory.h"
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <limits>
#include <map>
#include <mutex>
#include <sstream>
#include <thread>

namespace lab::radio {
using namespace ocudu;
namespace {
constexpr unsigned max_block = 65536;
struct Options {
  Settings settings;
  bool     hardware = false;
};
Options parse(const radio_configuration::radio& c)
{
  using namespace radio_configuration;
  if (c.tx_streams.size() != 1 || c.rx_streams.size() != 1 || c.tx_streams[0].channels.size() != 1 ||
      c.rx_streams[0].channels.size() != 1) {
    throw Error("E_CHANNELS", "x40는 1 TX/1 RX stream만 지원합니다.");
  }
  if (!std::isfinite(c.sampling_rate_Hz) || c.sampling_rate_Hz < 80000 || c.sampling_rate_Hz > 40000000 ||
      std::floor(c.sampling_rate_Hz) != c.sampling_rate_Hz) {
    throw Error("E_RATE", "integer sample rate 80 kS/s..40 MS/s가 필요합니다.");
  }
  if (c.tx_mode != transmission_mode::continuous || c.power_ramping_us != 0) {
    throw Error("E_TX_MODE", "continuous FDD stream만 지원합니다.");
  }
  if (c.otw_format != over_the_wire_format::DEFAULT && c.otw_format != over_the_wire_format::SC16) {
    throw Error("E_FORMAT", "SC16_Q11 transport만 지원합니다.");
  }
  for (auto source : {c.clock.clock, c.clock.sync}) {
    if (source != clock_sources::source::DEFAULT && source != clock_sources::source::INTERNAL) {
      throw Error("E_CLOCK", "internal clock만 지원합니다.");
    }
  }
  std::map<std::string, std::string> args;
  std::istringstream                 input(c.args);
  std::string                        token;
  while (std::getline(input, token, ',')) {
    auto equals = token.find('=');
    if (equals == std::string::npos || !args.emplace(token.substr(0, equals), token.substr(equals + 1)).second) {
      throw Error("E_ARGS", "key=value 및 고유 key가 필요합니다.");
    }
  }
  for (const auto& item : args) {
    if (item.first != "mode" && item.first != "rf" && item.first != "serial" && item.first != "max_seconds") {
      throw Error("E_ARGS", "지원하지 않는 device argument: " + item.first);
    }
  }
  Options           o;
  const std::string mode = args.count("mode") ? args.at("mode") : "mock";
  if (mode != "mock" && mode != "hardware") {
    throw Error("E_MODE", "mode=mock|hardware가 필요합니다.");
  }
  o.hardware           = mode == "hardware";
  const std::string rf = args.count("rf") ? args.at("rf") : "off";
  if (rf != "off" && rf != "on") {
    throw Error("E_RF", "rf=off|on이 필요합니다.");
  }
  if (o.hardware && rf != "on") {
    throw Error("E_RF_DISABLED", "hardware는 명시적인 rf=on이 필요합니다.");
  }
  if (!o.hardware && rf != "off") {
    throw Error("E_RF", "mock에서는 rf=off가 필요합니다.");
  }
  if (args.count("serial")) {
    o.settings.serial = args.at("serial");
  }
  if (o.hardware && o.settings.serial.size() != 32) {
    throw Error("E_SERIAL", "hardware serial이 필요합니다.");
  }
  if (args.count("max_seconds")) {
    const auto& value = args.at("max_seconds");
    if (value.empty() || value.size() > 2 || value.find_first_not_of("0123456789") != std::string::npos) {
      throw Error("E_DURATION", "1..60초가 필요합니다.");
    }
    o.settings.max_seconds = static_cast<unsigned>(std::stoul(value));
    if (o.settings.max_seconds < 1 || o.settings.max_seconds > 60) {
      throw Error("E_DURATION", "1..60초가 필요합니다.");
    }
  }
  o.settings.rate = c.sampling_rate_Hz;
  const auto& tx  = c.tx_streams[0].channels[0];
  const auto& rx  = c.rx_streams[0].channels[0];
  for (const auto* channel : {&tx, &rx}) {
    if (!channel->args.empty() || channel->freq.lo_frequency_Hz != 0 ||
        !std::isfinite(channel->freq.center_frequency_Hz) || channel->freq.center_frequency_Hz < 237500000 ||
        channel->freq.center_frequency_Hz > 3800000000.0 || !std::isfinite(channel->gain_dB) ||
        channel->gain_dB < -100 || channel->gain_dB > 100 || std::floor(channel->gain_dB) != channel->gain_dB) {
      throw Error("E_CHANNEL_CONFIG", "x40 frequency/gain 또는 channel arguments가 지원 범위를 벗어났습니다.");
    }
  }
  if (!c.tx_streams[0].args.empty() || !c.rx_streams[0].args.empty()) {
    throw Error("E_STREAM_ARGS", "stream arguments는 지원하지 않습니다.");
  }
  o.settings.tx_frequency = tx.freq.center_frequency_Hz;
  o.settings.rx_frequency = rx.freq.center_frequency_Hz;
  o.settings.tx_gain      = tx.gain_dB;
  o.settings.rx_gain      = rx.gain_dB;
  return o;
}
void diagnostic(const Error& e)
{
  std::fprintf(stderr, "bladeRF x40 plugin: %s driver=%d %s\n", e.code.c_str(), e.driver, e.what());
}
class Validator final : public radio_configuration::validator
{
  bool is_configuration_valid(const radio_configuration::radio& c) const override
  {
    try {
      (void)parse(c);
      return true;
    } catch (const Error& e) {
      diagnostic(e);
      return false;
    }
  }
};
class Session final : public radio_session,
                      public radio_management_plane,
                      public baseband_gateway,
                      public baseband_gateway_receiver,
                      public baseband_gateway_transmitter
{
  std::unique_ptr<Transport> transport;
  radio_event_notifier&      notifier;
  std::chrono::seconds       duration;
  std::atomic<bool>          running{false};
  bool                       started = false, first_tx = true;
  bool                       hardware = false;
  std::atomic<uint64_t>      tx_samples{0}, rx_samples{0};
  std::atomic<uint64_t>      errors{0}, late{0}, overflow{0}, underflow{0};
  uint64_t                   rx_next = 0, tx_next = 0;
  std::vector<int16_t>       tx_iq = std::vector<int16_t>(2 * max_block), rx_iq = std::vector<int16_t>(2 * max_block);
  std::mutex                 tx_mutex, rx_mutex, timer_mutex;
  std::condition_variable    timer;
  std::thread                watchdog;
  void                       event(radio_event_source source, radio_event_type type, uint64_t timestamp)
  {
    if (type == radio_event_type::LATE) {
      ++late;
    } else if (type == radio_event_type::OVERFLOW) {
      ++overflow;
    } else if (type == radio_event_type::UNDERFLOW) {
      ++underflow;
    }
    notifier.on_radio_rt_event({0, 0, source, type, timestamp});
  }
  void halt() noexcept
  {
    running = false;
    std::scoped_lock lock(tx_mutex, rx_mutex);
    transport->stop();
  }

public:
  Session(Options options, radio_event_notifier& events) :
    transport(options.hardware ? make_usb(options.settings) : make_mock(options.settings.rate)),
    notifier(events),
    duration(options.settings.max_seconds),
    hardware(options.hardware)
  {
  }
  ~Session() override
  {
    stop();
    std::fprintf(stderr,
                 "LAB_RADIO_STOP hardware=%u tx_samples=%llu rx_samples=%llu "
                 "errors=%llu late=%llu overflow=%llu underflow=%llu\n",
                 unsigned(hardware),
                 static_cast<unsigned long long>(tx_samples.load()),
                 static_cast<unsigned long long>(rx_samples.load()),
                 static_cast<unsigned long long>(errors.load()),
                 static_cast<unsigned long long>(late.load()),
                 static_cast<unsigned long long>(overflow.load()),
                 static_cast<unsigned long long>(underflow.load()));
  }
  radio_management_plane& get_management_plane() override { return *this; }
  baseband_gateway&       get_baseband_gateway(unsigned stream) override
  {
    if (stream != 0) {
      throw Error("E_STREAM", "stream 0만 지원합니다.");
    }
    return *this;
  }
  baseband_gateway_transmitter& get_transmitter() override { return *this; }
  baseband_gateway_receiver&    get_receiver() override { return *this; }
  unsigned                      get_transmitter_optimal_buffer_size() const override { return 4096; }
  unsigned                      get_receiver_optimal_buffer_size() const override { return 4096; }
  baseband_gateway_timestamp    read_current_time() override
  {
    std::lock_guard<std::mutex> lock(rx_mutex);
    return started && !running ? rx_next : transport->clock();
  }
  void start(baseband_gateway_timestamp timestamp) override
  {
    if (started) {
      throw Error("E_STATE", "start는 한 번만 호출할 수 있습니다.");
    }
    transport->start();
    started  = true;
    rx_next  = timestamp;
    tx_next  = timestamp;
    running  = true;
    watchdog = std::thread([this] {
      std::unique_lock<std::mutex> lock(timer_mutex);
      const bool                   expired = !timer.wait_for(lock, duration, [this] { return !running.load(); });
      lock.unlock();
      halt();
      if (expired) {
        ++errors;
        event(radio_event_source::OTHER, radio_event_type::OTHER, 0);
        std::fprintf(stderr, "bladeRF x40 plugin: E_DURATION stream stopped\n");
      }
    });
  }
  void stop() override
  {
    halt();
    timer.notify_all();
    if (watchdog.joinable()) {
      watchdog.join();
    }
  }
  void transmit(const baseband_gateway_buffer_reader&        data,
                const baseband_gateway_transmitter_metadata& metadata) override
  {
    std::lock_guard<std::mutex> lock(tx_mutex);
    if (!running) {
      return;
    }
    try {
      const unsigned count = data.get_nof_samples();
      if (data.get_nof_channels() != 1 || count == 0 || count > max_block ||
          metadata.ts > std::numeric_limits<uint64_t>::max() - count) {
        throw Error("E_BUFFER", "TX buffer 범위 오류");
      }
      if (metadata.ts < tx_next) {
        event(radio_event_source::TRANSMIT, radio_event_type::LATE, metadata.ts);
        return;
      }
      unsigned begin = metadata.tx_start.value_or(0), end = metadata.tx_end.value_or(count);
      if (begin > end || end > count) {
        throw Error("E_BUFFER", "TX 활성 구간 오류");
      }
      std::fill_n(tx_iq.data(), 2 * count, 0);
      if (!metadata.is_empty) {
        to_q11(data.get_channel_buffer(0).data() + begin, tx_iq.data() + 2 * begin, end - begin);
      }
      const auto status = transport->send(tx_iq.data(), count, metadata.ts, first_tx);
      if (status & 2U) {
        event(radio_event_source::TRANSMIT, radio_event_type::UNDERFLOW, metadata.ts);
      }
      first_tx = false;
      tx_next  = metadata.ts + count;
      tx_samples += count;
    } catch (const Error& e) {
      ++errors;
      diagnostic(e);
      running = false;
      timer.notify_all();
      event(radio_event_source::TRANSMIT,
            e.code == "E_LATE" ? radio_event_type::LATE : radio_event_type::OTHER,
            metadata.ts);
    }
  }
  metadata receive(baseband_gateway_buffer_writer& data) override
  {
    std::lock_guard<std::mutex> lock(rx_mutex);
    const uint64_t              expected = rx_next;
    for (unsigned i = 0; i < data.get_nof_channels(); ++i) {
      std::fill(data.get_channel_buffer(i).begin(), data.get_channel_buffer(i).end(), Sample{});
    }
    if (!running) {
      return {expected};
    }
    try {
      unsigned count = data.get_nof_samples();
      if (data.get_nof_channels() != 1 || count == 0 || count > max_block ||
          expected > std::numeric_limits<uint64_t>::max() - count) {
        throw Error("E_BUFFER", "RX buffer 범위 오류");
      }
      auto got = transport->receive(rx_iq.data(), count, expected);
      if (got.status & 1U) {
        event(radio_event_source::RECEIVE, radio_event_type::OVERFLOW, got.timestamp);
      }
      if (got.count != count || got.timestamp < expected ||
          got.timestamp > std::numeric_limits<uint64_t>::max() - count) {
        throw Error("E_RX_CONTINUITY", "RX actual_count/timestamp 오류");
      }
      if (got.timestamp != expected) {
        event(radio_event_source::RECEIVE, radio_event_type::OVERFLOW, got.timestamp);
      }
      from_q11(rx_iq.data(), data.get_channel_buffer(0).data(), count);
      rx_next = got.timestamp + count;
      rx_samples += count;
      return {got.timestamp};
    } catch (const Error& e) {
      ++errors;
      diagnostic(e);
      running = false;
      timer.notify_all();
      event(radio_event_source::RECEIVE, radio_event_type::OTHER, expected);
      return {expected};
    }
  }
  // Stream 중 주파수/gain 변경은 동기화 계약을 검증하지 않아 거부한다.
  bool set_tx_gain(unsigned, double) override { return false; }
  bool set_rx_gain(unsigned, double) override { return false; }
  bool set_tx_freq(unsigned, double) override { return false; }
  bool set_rx_freq(unsigned, double) override { return false; }
};
class Factory final : public radio_factory
{
  Validator validator;

public:
  const radio_configuration::validator& get_configuration_validator() const override { return validator; }
  std::unique_ptr<radio_session>
  create(const radio_configuration::radio& config, task_executor&, radio_event_notifier& notifier) override
  {
    try {
      return std::make_unique<Session>(parse(config), notifier);
    } catch (const Error& e) {
      diagnostic(e);
      return nullptr;
    }
  }
};
} // namespace
} // namespace lab::radio
namespace ocudu {
std::unique_ptr<radio_factory> create_dynamic_radio_factory()
{
  return std::make_unique<lab::radio::Factory>();
}
} // namespace ocudu
