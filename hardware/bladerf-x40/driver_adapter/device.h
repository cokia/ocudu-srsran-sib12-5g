// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <nlohmann/json.hpp>
#include <chrono>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace lab {
using json = nlohmann::json;
enum class Direction { rx, tx };
struct Failure : std::runtime_error {
  std::string code;
  int driver_code;
  std::string status;
  Failure(std::string c, std::string detail, int driver = 0, std::string s = "FAIL") :
    std::runtime_error(detail), code(std::move(c)), driver_code(driver), status(std::move(s)) {}
};
struct RxBlock { std::vector<int16_t> iq; uint64_t timestamp = 0; uint32_t status = 0; };
class Device {
public:
  virtual ~Device() = default;
  virtual json inspect() = 0;
  virtual void isolate() = 0;
  virtual bool isolated() = 0;
  virtual void configure(Direction direction, bool metadata) = 0;
  virtual void enable(Direction direction, bool value) = 0;
  virtual void transmit(const std::vector<int16_t>& iq) = 0;
  virtual RxBlock receive(unsigned samples, bool metadata) = 0;
};
std::unique_ptr<Device> make_mock(const std::string& fault);
#ifdef LAB_WITH_BLADERF
json driver_info();
std::unique_ptr<Device> make_real(const std::string& serial);
#endif
void verify(const json& info);
json loopback(Device& device);
json rx_diagnostic(Device& device);
} // namespace lab
