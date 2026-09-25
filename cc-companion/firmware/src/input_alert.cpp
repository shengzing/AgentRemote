#include "companion/input_alert.h"

namespace companion {

namespace {

constexpr std::uint32_t kLongPressMs = 600;

}  // namespace

ButtonAction MainButton::Update(bool pressed, std::uint32_t now_ms) {
  if (pressed && !is_pressed_) {
    is_pressed_ = true;
    recording_started_ = false;
    pressed_at_ms_ = now_ms;
    return ButtonAction::kNone;
  }
  if (pressed && is_pressed_ && !recording_started_ && now_ms - pressed_at_ms_ >= kLongPressMs) {
    recording_started_ = true;
    return ButtonAction::kBeginRecording;
  }
  if (!pressed && is_pressed_) {
    is_pressed_ = false;
    if (recording_started_) {
      recording_started_ = false;
      return ButtonAction::kFinishRecording;
    }
    return ButtonAction::kSelectNext;
  }
  return ButtonAction::kNone;
}

void AlertPolicy::SetDnd(bool enabled) {
  dnd_enabled_ = enabled;
}

bool AlertPolicy::dnd_enabled() const {
  return dnd_enabled_;
}

bool AlertPolicy::ShouldAlert(const CcRow& row) const {
  return !dnd_enabled_ && IsAttention(row);
}

bool AlertPolicy::ShouldWakeScreen(const CcRow& row) const {
  return !dnd_enabled_ && IsAttention(row);
}

bool IsAttention(const CcRow& row) {
  return row.priority == Priority::kHigh &&
         (row.state == CcState::kAwaitingConfirmation || row.state == CcState::kAwaitingInput);
}

}  // namespace companion
