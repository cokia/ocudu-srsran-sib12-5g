cmake_minimum_required(VERSION 3.22)
project(ocudu_pws_lab VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(LAB_WITH_BLADERF "실제 libbladeRF adapter 빌드" OFF)
option(LAB_ADAPTER_TESTS "libbladeRF C API 경계의 hardware-free contract 검사" OFF)
find_package(nlohmann_json 3.11 REQUIRED)
find_package(Threads REQUIRED)
add_executable(bladerf-x40-diag
  hardware/bladerf-x40/device_probe/main.cpp
  hardware/bladerf-x40/driver_adapter/mock_device.cpp
  hardware/bladerf-x40/loopback_tests/runner.cpp)
target_include_directories(bladerf-x40-diag PRIVATE hardware/bladerf-x40)
target_link_libraries(bladerf-x40-diag PRIVATE nlohmann_json::nlohmann_json Threads::Threads)
target_compile_options(bladerf-x40-diag PRIVATE -Wall -Wextra -Werror)
if(LAB_WITH_BLADERF)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(BLADERF REQUIRED IMPORTED_TARGET libbladeRF>=2.6.0)
  target_sources(bladerf-x40-diag PRIVATE hardware/bladerf-x40/driver_adapter/real_device.cpp)
  target_link_libraries(bladerf-x40-diag PRIVATE PkgConfig::BLADERF)
  target_compile_definitions(bladerf-x40-diag PRIVATE LAB_WITH_BLADERF=1)
endif()
if(LAB_ADAPTER_TESTS)
  if(NOT LAB_WITH_BLADERF OR NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR "adapter tests require Linux and LAB_WITH_BLADERF")
  endif()
  enable_testing()
  find_package(GTest REQUIRED)
  add_executable(bladerf-adapter-tests tests/libbladerf/adapter_test.cpp
    hardware/bladerf-x40/driver_adapter/real_device.cpp
    hardware/bladerf-x40/loopback_tests/runner.cpp)
  target_include_directories(bladerf-adapter-tests PRIVATE hardware/bladerf-x40)
  target_compile_definitions(bladerf-adapter-tests PRIVATE LAB_WITH_BLADERF=1)
  target_compile_options(bladerf-adapter-tests PRIVATE -Wall -Wextra -Werror)
  target_link_libraries(bladerf-adapter-tests PRIVATE GTest::gtest_main PkgConfig::BLADERF nlohmann_json::nlohmann_json Threads::Threads)
  foreach(fn set_usb_reset_on_open get_device_list free_device_list open_with_devinfo close
    get_devinfo fw_version fpga_version get_fpga_size is_fpga_configured get_board_name
    device_speed get_channel_count get_sample_rate_range get_loopback_modes
    is_loopback_mode_supported get_timestamp set_loopback get_loopback lms_read
    set_sample_rate sync_config enable_module sync_tx sync_rx)
    target_link_options(bladerf-adapter-tests PRIVATE "-Wl,--wrap=bladerf_${fn}")
  endforeach()
  add_test(NAME adapter-contract COMMAND bladerf-adapter-tests)
  set_tests_properties(adapter-contract PROPERTIES TIMEOUT 20)
endif()
install(TARGETS bladerf-x40-diag RUNTIME DESTINATION bin)
