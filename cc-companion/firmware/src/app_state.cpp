#include "companion/app_state.h"

#include <cstring>

namespace companion {

namespace {

constexpr std::uint32_t kInitialReconnectDelayMs = 1000;
constexpr std::uint32_t kMaxReconnectDelayMs = 60000;
constexpr std::size_t kNotFound = kMaxSessions;

}  // namespace

AppState::AppState()
    : row_count_(0), selected_cc_code_(0), revision_(0), gateway_online_(false) {
  std::memset(rows_, 0, sizeof(rows_));
}

bool AppState::ApplySnapshot(std::uint32_t revision, const CcRow* rows, std::size_t count) {
  if (revision < revision_ || !ValidateRows(rows, count)) {
    return false;
  }

  const std::uint8_t previous_selection = selected_cc_code_;
  if (count > 0) {
    std::memcpy(rows_, rows, count * sizeof(CcRow));
  }
  row_count_ = count;
  revision_ = revision;
  gateway_online_ = true;
  SortRows();
  PreserveOrChooseSelection(previous_selection);
  return true;
}

bool AppState::ApplyStateDelta(std::uint32_t revision, const CcRow& row) {
  if (revision <= revision_ || !ValidateRow(row)) {
    return false;
  }

  const std::uint8_t previous_selection = selected_cc_code_;
  const std::size_t existing = FindRow(row.cc_code);
  if (existing != kNotFound) {
    rows_[existing] = row;
  } else {
    if (row_count_ == kMaxSessions) {
      return false;
    }
    rows_[row_count_++] = row;
  }
  revision_ = revision;
  gateway_online_ = true;
  SortRows();
  PreserveOrChooseSelection(previous_selection);
  return true;
}

void AppState::MarkGatewayOffline() {
  gateway_online_ = false;
}

bool AppState::SelectNext() {
  if (row_count_ == 0) {
    return false;
  }
  const std::size_t selected_index = FindRow(selected_cc_code_);
  const std::size_t next_index = selected_index == kNotFound ? 0 : (selected_index + 1) % row_count_;
  selected_cc_code_ = rows_[next_index].cc_code;
  return true;
}

bool AppState::gateway_online() const {
  return gateway_online_;
}

std::uint32_t AppState::revision() const {
  return revision_;
}

std::size_t AppState::row_count() const {
  return row_count_;
}

const CcRow* AppState::row_at(std::size_t index) const {
  return index < row_count_ ? &rows_[index] : nullptr;
}

const CcRow* AppState::selected_row() const {
  const std::size_t index = FindRow(selected_cc_code_);
  return index == kNotFound ? nullptr : &rows_[index];
}

bool AppState::ValidateRow(const CcRow& row) const {
  return row.cc_code >= 1 && row.cc_code <= kMaxSessions && row.summary[kSummaryCapacity - 1] == '\0';
}

bool AppState::ValidateRows(const CcRow* rows, std::size_t count) const {
  if (count > kMaxSessions || (count > 0 && rows == nullptr)) {
    return false;
  }
  for (std::size_t index = 0; index < count; ++index) {
    if (!ValidateRow(rows[index])) {
      return false;
    }
    for (std::size_t prior = 0; prior < index; ++prior) {
      if (rows[prior].cc_code == rows[index].cc_code) {
        return false;
      }
    }
  }
  return true;
}

void AppState::SortRows() {
  for (std::size_t index = 1; index < row_count_; ++index) {
    CcRow value = rows_[index];
    std::size_t position = index;
    while (position > 0 && rows_[position - 1].cc_code > value.cc_code) {
      rows_[position] = rows_[position - 1];
      --position;
    }
    rows_[position] = value;
  }
}

void AppState::PreserveOrChooseSelection(std::uint8_t previous_selection) {
  selected_cc_code_ = FindRow(previous_selection) != kNotFound
                          ? previous_selection
                          : (row_count_ > 0 ? rows_[0].cc_code : 0);
}

std::size_t AppState::FindRow(std::uint8_t cc_code) const {
  for (std::size_t index = 0; index < row_count_; ++index) {
    if (rows_[index].cc_code == cc_code) {
      return index;
    }
  }
  return kNotFound;
}

ReconnectBackoff::ReconnectBackoff()
    : next_attempt_at_ms_(0), next_delay_ms_(kInitialReconnectDelayMs) {}

void ReconnectBackoff::Reset() {
  next_attempt_at_ms_ = 0;
  next_delay_ms_ = kInitialReconnectDelayMs;
}

bool ReconnectBackoff::CanAttempt(std::uint32_t now_ms) const {
  return now_ms >= next_attempt_at_ms_;
}

void ReconnectBackoff::RecordAttempt(std::uint32_t now_ms) {
  next_attempt_at_ms_ = now_ms + next_delay_ms_;
  next_delay_ms_ = next_delay_ms_ >= kMaxReconnectDelayMs / 2
                       ? kMaxReconnectDelayMs
                       : next_delay_ms_ * 2;
}

std::uint32_t ReconnectBackoff::next_delay_ms() const {
  return next_delay_ms_;
}

}  // namespace companion
