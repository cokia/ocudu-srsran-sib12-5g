// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <complex>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace lab::radio {
using Sample = std::complex<int16_t>;
struct Error : std::runtime_error {
  std::string code;
  int         driver;
  Error(std::string c, std::string detail, int d = 0) :
    std::runtime_error(std::move(detail)), code(std::move(c)), driver(d)
  {
  }
};
struct Settings {
  double      rate = 23040000, tx_frequency = 1842500000, rx_frequency = 1747500000;
  double      tx_gain = 17, rx_gain = 0;
  std::string serial;
  unsigned    max_seconds = 20;
};
struct Received {
  uint64_t timestamp = 0;
  uint32_t status    = 0;
  unsigned count     = 0;
};
class Transport
{
public:
  virtual ~Transport()                                                                     = default;
  virtual uint64_t clock()                                                                 = 0;
  virtual void     start()                                                                 = 0;
  virtual void     stop() noexcept                                                         = 0;
  virtual uint32_t send(const int16_t* iq, unsigned count, uint64_t timestamp, bool first) = 0;
  virtual Received receive(int16_t* iq, unsigned count, uint64_t timestamp)                = 0;
};
std::unique_ptr<Transport> make_usb(const Settings& settings);
std::unique_ptr<Transport> make_mock(double rate);
void                       to_q11(const Sample* input, int16_t* output, unsigned count);
void                       from_q11(const int16_t* input, Sample* output, unsigned count);
} // namespace lab::radio
