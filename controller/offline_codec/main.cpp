// SPDX-License-Identifier: BSD-3-Clause
#include "lib/cu_cp/routines/pws_sib_encoder.h"
#include "ocudu/asn1/rrc_nr/sys_info.h"
#include "ocudu/asn1/rrc_nr/rrc_nr.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cctype>
#include <iostream>
#include <stdexcept>
#include <string>

using json = nlohmann::json;
using ocudu::byte_buffer;
namespace {
constexpr size_t max_payload = 1246;
constexpr size_t max_input = 65536;
constexpr uint16_t lab_message_id = 0x111c; // TS 23.041: CMAS test message 식별자.
constexpr uint16_t lab_serial = 0;
constexpr uint8_t ucs2_dcs = 0x48;

void require(bool value, const char* error)
{
  if (!value) { throw std::runtime_error(error); }
}

std::vector<uint8_t> unhex(const std::string& value, size_t limit)
{
  require(!value.empty() && value.size() % 2 == 0 && value.size() <= limit * 2, "E_HEX_LENGTH");
  std::vector<uint8_t> out;
  for (size_t i = 0; i < value.size(); i += 2) {
    require(std::isxdigit(static_cast<unsigned char>(value[i])) &&
                std::isxdigit(static_cast<unsigned char>(value[i + 1])), "E_HEX");
    out.push_back(static_cast<uint8_t>(std::stoul(value.substr(i, 2), nullptr, 16)));
  }
  return out;
}

template <typename T> std::string hex(const T& bytes)
{
  constexpr char digits[] = "0123456789abcdef";
  std::string out;
  for (uint8_t b : bytes) { out += digits[b >> 4]; out += digits[b & 15]; }
  return out;
}

byte_buffer buffer(const std::vector<uint8_t>& bytes)
{
  byte_buffer out;
  require(out.append(ocudu::span<const uint8_t>(bytes.data(), bytes.size())), "E_ALLOCATION");
  return out;
}

template <typename T> byte_buffer pack(const T& value)
{
  byte_buffer out;
  asn1::bit_ref bits(out);
  require(value.pack(bits) == asn1::OCUDUASN_SUCCESS, "E_ASN1_ENCODE");
  return out;
}

template <typename T> T unpack(const std::string& encoded)
{
  const auto bytes = buffer(unhex(encoded, 2048));
  asn1::cbit_ref bits(bytes);
  T value;
  require(value.unpack(bits) == asn1::OCUDUASN_SUCCESS, "E_ASN1_DECODE");
  // 비정규 padding, trailing bytes 및 지원하지 않는 확장을 거부한다.
  require(hex(pack(value)) == hex(bytes), "E_NONCANONICAL");
  return value;
}

json decode_sib8(const json& segments)
{
  require(segments.is_array() && !segments.empty() && segments.size() <= 64, "E_SEGMENTS");
  std::vector<uint8_t> payload;
  json structures = json::array();
  for (size_t i = 0; i < segments.size(); ++i) {
    auto sib = unpack<asn1::rrc_nr::sib8_s>(segments.at(i).get<std::string>());
    require(!sib.ext && sib.late_non_crit_ext.size() == 0 && sib.warning_area_coordinates_segment.size() == 0,
            "E_PROFILE_EXTENSION");
    require(sib.msg_id.to_number() == lab_message_id && sib.serial_num.to_number() == lab_serial, "E_IDENTIFIERS");
    require(sib.warning_msg_segment_num == i, "E_SEGMENT_ORDER");
    bool last = sib.warning_msg_segment_type.value == asn1::rrc_nr::sib8_s::warning_msg_segment_type_opts::last_segment;
    require(last == (i + 1 == segments.size()), "E_SEGMENT_LAST");
    require(sib.data_coding_scheme_present == (i == 0), "E_DCS_PRESENCE");
    if (i == 0) { require(sib.data_coding_scheme.to_number() == ucs2_dcs, "E_DCS"); }
    require(sib.warning_msg_segment.size() > 0, "E_EMPTY_SEGMENT");
    for (size_t j = 0; j < sib.warning_msg_segment.size(); ++j) { payload.push_back(sib.warning_msg_segment[j]); }
    require(payload.size() <= max_payload, "E_PAYLOAD_LENGTH");
    asn1::json_writer writer;
    sib.to_json(writer);
    structures.push_back(json::parse(writer.to_string()));
  }
  return {{"asn1_type", "NR-SIB8"}, {"payload_hex", hex(payload)}, {"structures", structures}};
}

json process(const json& input)
{
  std::string op = input.at("operation").get<std::string>();
  if (op == "encode-sib8") {
    auto payload = unhex(input.at("payload_hex").get<std::string>(), max_payload);
    auto segment_size = input.at("segment_bytes").get<int>();
    require(segment_size >= 20 && segment_size <= 256, "E_SEGMENT_SIZE");
    auto encoded = ocudu::ocucp::encode_sib8(lab_message_id, lab_serial, ucs2_dcs, buffer(payload), segment_size);
    require(encoded.has_value(), "E_ASN1_ENCODE");
    json segments = json::array();
    for (const auto& part : *encoded) { segments.push_back(hex(part)); }
    auto result = decode_sib8(segments);
    require(result.at("payload_hex") == hex(payload), "E_ROUND_TRIP");
    result["segments"] = segments;
    result["message_identifier"] = lab_message_id;
    result["serial_number"] = lab_serial;
    result["data_coding_scheme"] = ucs2_dcs;
    return result;
  }
  if (op == "decode-sib8") { return decode_sib8(input.at("segments")); }
  if (op == "inspect-sib12") {
    // NR SIB12는 CMAS가 아니다. 모든 optional 필드가 없는 유효한 SIB12-IEs 구조를 검사한다.
    asn1::rrc_nr::sib12_r16_s value;
    value.segment_num_r16 = 0;
    value.segment_type_r16 = asn1::rrc_nr::sib12_r16_s::segment_type_r16_opts::last_segment;
    asn1::rrc_nr::sib12_ies_r16_s ies;
    const auto inner = pack(ies);
    auto decoded_ies = unpack<asn1::rrc_nr::sib12_ies_r16_s>(hex(inner));
    (void)decoded_ies;
    std::vector<uint8_t> bytes(inner.begin(), inner.end());
    value.segment_container_r16.from_bytes(ocudu::span<const uint8_t>(bytes.data(), bytes.size()));
    const auto encoded = hex(pack(value));
    const auto decoded = unpack<asn1::rrc_nr::sib12_r16_s>(encoded);
    asn1::json_writer writer;
    decoded.to_json(writer);
    return {{"asn1_type", "NR-SIB12-r16"}, {"purpose", "sidelink-structure-only"},
            {"cmas", false}, {"payload_semantics_verified", false}, {"inner_asn1_round_trip", true}, {"encoded_hex", encoded},
            {"structure", json::parse(writer.to_string())}};
  }
  throw std::runtime_error("E_OPERATION");
}
} // namespace

int main()
{
  try {
    std::string input;
    char c;
    while (std::cin.get(c)) {
      require(input.size() < max_input, "E_INPUT_SIZE");
      input.push_back(c);
    }
    auto result = process(json::parse(input));
    result["status"] = "PASS";
    std::cout << result.dump() << '\n';
    return 0;
  } catch (const std::exception& ex) {
    std::cout << json({{"status", "FAIL"}, {"error", ex.what()}}).dump() << '\n';
    return 2;
  }
}
