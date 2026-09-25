#include "companion/display_model.h"
#include "companion/input_alert.h"

#include <cstdio>

namespace companion {

namespace {

const char* StateMarker(CcState state) {
  switch (state) {
    case CcState::kWorking:
      return ">";
    case CcState::kAwaitingConfirmation:
      return "?";
    case CcState::kAwaitingInput:
      return ".";
    case CcState::kDone:
      return "+";
    case CcState::kError:
      return "!";
    case CcState::kIdle:
      return "-";
  }
  return "-";
}

}  // namespace

ListView BuildListView(const AppState& state) {
  ListView view = {};
  view.gateway_online = state.gateway_online();
  view.line_count = state.row_count();

  const CcRow* selected = state.selected_row();
  if (selected == nullptr) {
    std::snprintf(view.header, sizeof(view.header), "CC %s", state.gateway_online() ? "no sessions" : "gateway offline");
  } else {
    std::snprintf(
        view.header,
        sizeof(view.header),
        "CC ->#%u %s",
        static_cast<unsigned>(selected->cc_code),
        state.gateway_online() ? "online" : "offline");
  }

  for (std::size_t index = 0; index < view.line_count; ++index) {
    const CcRow* row = state.row_at(index);
    DisplayLine& line = view.lines[index];
    line.selected = selected != nullptr && row->cc_code == selected->cc_code;
    line.attention = IsAttention(*row);
    std::snprintf(
        line.text,
        sizeof(line.text),
        "#%u %s %.20s",
        static_cast<unsigned>(row->cc_code),
        StateMarker(row->state),
        row->summary);
  }
  return view;
}

}  // namespace companion
