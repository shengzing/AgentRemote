#pragma once

#include <cstddef>
#include <cstdint>

namespace companion {

constexpr std::size_t kMaxSessions = 8;
constexpr std::size_t kSummaryCapacity = 21;

enum class CcState : std::uint8_t {
  kWorking,
  kAwaitingConfirmation,
  kAwaitingInput,
  kDone,
  kError,
  kIdle,
};

enum class Priority : std::uint8_t {
  kNormal,
  kHigh,
};

struct CcRow {
  std::uint8_t cc_code;
  CcState state;
  Priority priority;
  std::uint32_t timestamp;
  char summary[kSummaryCapacity];
};

}  // namespace companion
