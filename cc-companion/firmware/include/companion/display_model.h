#pragma once

#include <cstddef>

#include "companion/app_state.h"

namespace companion {

constexpr std::size_t kDisplayLineCapacity = 31;

struct DisplayLine {
  bool selected;
  bool attention;
  char text[kDisplayLineCapacity];
};

struct ListView {
  bool gateway_online;
  std::size_t line_count;
  char header[kDisplayLineCapacity];
  DisplayLine lines[kMaxSessions];
};

// Converts state to LCD-ready ASCII data. M5Unified can render it with any chosen font.
ListView BuildListView(const AppState& state);

}  // namespace companion
