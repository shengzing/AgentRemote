#pragma once

#include <cstdint>

#include "companion/protocol_models.h"

namespace companion {

enum class ButtonAction : std::uint8_t {
  kNone,
  kSelectNext,
  kBeginRecording,
  kFinishRecording,
};

class MainButton {
 public:
  ButtonAction Update(bool pressed, std::uint32_t now_ms);

 private:
  bool is_pressed_ = false;
  bool recording_started_ = false;
  std::uint32_t pressed_at_ms_ = 0;
};

class AlertPolicy {
 public:
  void SetDnd(bool enabled);
  bool dnd_enabled() const;
  bool ShouldAlert(const CcRow& row) const;
  bool ShouldWakeScreen(const CcRow& row) const;

 private:
  bool dnd_enabled_ = false;
};

bool IsAttention(const CcRow& row);

}  // namespace companion
