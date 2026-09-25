#pragma once

#include <cstddef>
#include <cstdint>

#include "companion/protocol_models.h"

namespace companion {

class AppState {
 public:
  AppState();

  bool ApplySnapshot(std::uint32_t revision, const CcRow* rows, std::size_t count);
  bool ApplyStateDelta(std::uint32_t revision, const CcRow& row);
  void MarkGatewayOffline();
  bool SelectNext();

  bool gateway_online() const;
  std::uint32_t revision() const;
  std::size_t row_count() const;
  const CcRow* row_at(std::size_t index) const;
  const CcRow* selected_row() const;

 private:
  bool ValidateRow(const CcRow& row) const;
  bool ValidateRows(const CcRow* rows, std::size_t count) const;
  void SortRows();
  void PreserveOrChooseSelection(std::uint8_t previous_selection);
  std::size_t FindRow(std::uint8_t cc_code) const;

  CcRow rows_[kMaxSessions];
  std::size_t row_count_;
  std::uint8_t selected_cc_code_;
  std::uint32_t revision_;
  bool gateway_online_;
};

class ReconnectBackoff {
 public:
  ReconnectBackoff();

  void Reset();
  bool CanAttempt(std::uint32_t now_ms) const;
  void RecordAttempt(std::uint32_t now_ms);
  std::uint32_t next_delay_ms() const;

 private:
  std::uint32_t next_attempt_at_ms_;
  std::uint32_t next_delay_ms_;
};

}  // namespace companion
