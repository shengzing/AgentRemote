#include "companion/message_flow.h"

#include <cstring>

namespace companion {

MessageFlow::MessageFlow() : state_(MessageFlowState::kList), target_cc_code_(0), draft_{0}, error_{0} {}

bool MessageFlow::BeginRecording(std::uint8_t cc_code) {
  if (cc_code == 0 || (state_ != MessageFlowState::kList && state_ != MessageFlowState::kSendSucceeded)) {
    return false;
  }
  target_cc_code_ = cc_code;
  draft_[0] = '\0';
  error_[0] = '\0';
  state_ = MessageFlowState::kRecording;
  return true;
}

bool MessageFlow::FinishRecording() {
  if (state_ != MessageFlowState::kRecording) {
    return false;
  }
  state_ = MessageFlowState::kTranscribing;
  return true;
}

bool MessageFlow::ReceiveTranscript(const char* text) {
  if (state_ != MessageFlowState::kTranscribing || text == nullptr || text[0] == '\0') {
    return false;
  }
  CopyString(draft_, sizeof(draft_), text);
  error_[0] = '\0';
  state_ = MessageFlowState::kConfirming;
  return true;
}

bool MessageFlow::BeginRerecording() {
  if (state_ != MessageFlowState::kConfirming && state_ != MessageFlowState::kSendFailed) {
    return false;
  }
  draft_[0] = '\0';
  error_[0] = '\0';
  state_ = MessageFlowState::kRecording;
  return true;
}

bool MessageFlow::BeginSend(PendingMessage* output) {
  if (state_ != MessageFlowState::kConfirming || output == nullptr || draft_[0] == '\0') {
    return false;
  }
  output->cc_code = target_cc_code_;
  CopyString(output->text, sizeof(output->text), draft_);
  state_ = MessageFlowState::kSending;
  return true;
}

void MessageFlow::ApplySendAcknowledgement(bool ok, const char* error) {
  if (state_ != MessageFlowState::kSending) {
    return;
  }
  if (ok) {
    error_[0] = '\0';
    state_ = MessageFlowState::kSendSucceeded;
    return;
  }
  CopyString(error_, sizeof(error_), error == nullptr ? "SEND_FAILED" : error);
  state_ = MessageFlowState::kSendFailed;
}

void MessageFlow::ReturnToList() {
  state_ = MessageFlowState::kList;
  target_cc_code_ = 0;
  draft_[0] = '\0';
  error_[0] = '\0';
}

MessageFlowState MessageFlow::state() const {
  return state_;
}

std::uint8_t MessageFlow::target_cc_code() const {
  return target_cc_code_;
}

const char* MessageFlow::draft() const {
  return draft_;
}

const char* MessageFlow::error() const {
  return error_;
}

void MessageFlow::CopyString(char* destination, std::size_t capacity, const char* source) {
  std::strncpy(destination, source, capacity - 1);
  destination[capacity - 1] = '\0';
}

}  // namespace companion
