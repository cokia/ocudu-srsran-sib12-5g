// SPDX-License-Identifier: BSD-3-Clause
#include "stream.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <mutex>
#include <thread>
namespace lab::radio {
void to_q11(const Sample* input, int16_t* output, unsigned count)
{
  for (unsigned i = 0; i != count; ++i) {
    output[2 * i] = static_cast<int16_t>(std::clamp(std::lround(input[i].real() * (2048.0 / 32767.0)), -2048L, 2047L));
    output[2 * i + 1] =
        static_cast<int16_t>(std::clamp(std::lround(input[i].imag() * (2048.0 / 32767.0)), -2048L, 2047L));
  }
}
void from_q11(const int16_t* input, Sample* output, unsigned count)
{
  for (unsigned i = 0; i != count; ++i) {
    const auto convert = [](int16_t v) {
      return static_cast<int16_t>(std::clamp(std::lround(v * (32767.0 / 2048.0)), -32768L, 32767L));
    };
    output[i] = {convert(input[2 * i]), convert(input[2 * i + 1])};
  }
}
class Mock final : public Transport
{
  std::mutex                            mutex;
  uint64_t                              ticks = 0, tx_at = 0;
  bool                                  running = false;
  std::vector<int16_t>                  last;
  double                                rate;
  bool                                  first_rx = true;
  uint64_t                              origin   = 0;
  std::chrono::steady_clock::time_point wall;

public:
  explicit Mock(double sample_rate) : rate(sample_rate) {}
  uint64_t clock() override
  {
    std::lock_guard<std::mutex> lock(mutex);
    return ticks;
  }
  void start() override
  {
    std::lock_guard<std::mutex> lock(mutex);
    running = true;
  }
  void stop() noexcept override
  {
    std::lock_guard<std::mutex> lock(mutex);
    running = false;
  }
  uint32_t send(const int16_t* iq, unsigned count, uint64_t timestamp, bool) override
  {
    std::lock_guard<std::mutex> lock(mutex);
    if (!running) {
      throw Error("E_STOPPED", "stream stopped");
    }
    last.assign(iq, iq + 2 * count);
    tx_at = timestamp;
    return 0;
  }
  Received receive(int16_t* iq, unsigned count, uint64_t timestamp) override
  {
    std::lock_guard<std::mutex> lock(mutex);
    if (!running) {
      throw Error("E_STOPPED", "stream stopped");
    }
    if (first_rx) {
      wall     = std::chrono::steady_clock::now();
      origin   = timestamp;
      first_rx = false;
    }
    std::this_thread::sleep_until(wall + std::chrono::duration<double>((timestamp + count - origin) / rate));
    std::fill_n(iq, 2 * count, 0);
    if (timestamp == tx_at && last.size() == 2 * count) {
      std::copy(last.begin(), last.end(), iq);
    }
    ticks = timestamp + count;
    return {timestamp, 0, count};
  }
};
std::unique_ptr<Transport> make_mock(double rate)
{
  return std::make_unique<Mock>(rate);
}
} // namespace lab::radio
