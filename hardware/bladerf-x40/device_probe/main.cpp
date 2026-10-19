// SPDX-License-Identifier: BSD-3-Clause
#include "driver_adapter/device.h"
#include <iostream>

int main(int argc, char** argv) {
  using namespace lab;
  json result{{"status", "FAIL"}, {"mock", false}, {"hardware_verified", false},
              {"samples_processed", nullptr}, {"streaming_errors", nullptr}, {"buffer_errors", nullptr}};
#ifdef LAB_WITH_BLADERF
  result["driver"] = driver_info();
#else
  result["driver"] = {{"available", false}};
#endif
  int exit_code = 1;
  try {
    if (argc < 2) { throw Failure("E_ARGUMENT", "info|capabilities|verify|loopback|rx [--mock] [--fault NAME] [--serial SERIAL] [--hardware]"); }
    std::string command = argv[1], serial, fault = "none";
    bool mock = false, hardware = false;
    for (int i = 2; i < argc; ++i) {
      std::string arg = argv[i];
      if (arg == "--mock") { mock = true; }
      else if (arg == "--hardware") { hardware = true; }
      else if ((arg == "--serial" || arg == "--fault") && i + 1 < argc) {
        if (arg == "--serial") { serial = argv[++i]; } else { fault = argv[++i]; }
      } else { throw Failure("E_ARGUMENT", "알 수 없거나 불완전한 옵션"); }
    }
    if (command != "info" && command != "capabilities" && command != "verify" && command != "loopback" && command != "rx") {
      throw Failure("E_ARGUMENT", "지원하지 않는 명령");
    }
    if (mock && hardware) { throw Failure("E_ARGUMENT", "--mock과 --hardware는 함께 사용할 수 없습니다."); }
    if (!mock && fault != "none") { throw Failure("E_ARGUMENT", "--fault는 mock 전용입니다."); }
    result["mock"] = mock;
    result["command"] = command;
    std::unique_ptr<Device> device;
    if (mock) { device = make_mock(fault); }
    else {
      if (!hardware) { throw Failure("E_HARDWARE_OPT_IN", "실제 USB 접근에는 --hardware가 필요합니다.", 0, "BLOCKED"); }
#ifdef LAB_WITH_BLADERF
      device = make_real(serial);
#else
      throw Failure("E_DRIVER_UNAVAILABLE", "libbladeRF adapter가 빌드되지 않았습니다.", 0, "BLOCKED");
#endif
    }
    result["device"] = device->inspect();
    if (result["device"]["board"] != "bladerf1" || result["device"]["fpga_size"] != 40) { throw Failure("E_MODEL", "bladeRF x40가 아닙니다."); }
    if (command == "verify") { verify(result["device"]); }
    if (command == "loopback") { result["diagnostics"] = loopback(*device); }
    if (command == "rx") { result["diagnostics"] = rx_diagnostic(*device); }
    if (result.contains("diagnostics")) {
      for (const auto* field : {"samples_processed", "streaming_errors", "buffer_errors"}) {
        result[field] = result["diagnostics"][field];
      }
    } else { result["samples_processed"] = 0; }
    result["status"] = "PASS";
    result["hardware_verified"] = !mock;
    exit_code = 0;
  } catch (const Failure& error) {
    result["status"] = error.status;
    result["error"] = {{"code", error.code}, {"detail", error.what()}, {"driver_code", error.driver_code}};
    exit_code = error.status == "SKIP" ? 77 : (error.status == "BLOCKED" ? 3 : 1);
  } catch (const std::exception& error) {
    result["error"] = {{"code", "E_INTERNAL"}, {"detail", error.what()}};
  }
  std::cerr << (result["mock"].get<bool>() ? "[MOCK] " : "[HARDWARE] ")
            << result.value("command", "diagnostic") << ": " << result["status"].get<std::string>() << '\n';
  for (const auto* section : {"driver", "device", "diagnostics", "error"}) {
    if (!result.contains(section)) { continue; }
    std::cerr << section << '\n';
    for (auto it = result[section].begin(); it != result[section].end(); ++it) {
      std::cerr << "  " << it.key() << ": " << it.value().dump() << '\n';
    }
  }
  std::cout << result.dump() << '\n';
  return exit_code;
}
