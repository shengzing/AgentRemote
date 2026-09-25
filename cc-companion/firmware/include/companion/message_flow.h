#pragma once

#include <cstddef>
#include <cstdint>

namespace companion {

constexpr std::size_t kDraftCapacity = 161;
constexpr std::size_t kSendErrorCapacity = 33;

enum class MessageFlowState : std::uint8_t {
  kList,
  kRecording,
  kTranscribing,
  kConfirming,
  kSending,
  kSendSucceeded,
  kSendFailed,
};

struct PendingMessage {
  std::uint8_t cc_code;
  char text[kDraftCapacity];
};

class MessageFlow {
 public:
  MessageFlow();

  bool BeginRecording(std::uint8_t cc_code);
  bool FinishRecording();
  bool ReceiveTranscript(const char* text);
  bool BeginRerecording();
  bool BeginSend(PendingMessage* output);
  void ApplySendAcknowledgement(bool ok, const char* error);
  void ReturnToList();

  MessageFlowState state() const;
  std::uint8_t target_cc_code() const;
  const char* draft() const;
  const char* error() const;

 private:
  void CopyString(char* destination, std::size_t capacity, const char* source);

  MessageFlowState state_;
  std::uint8_t target_cc_code_;
  char draft_[kDraftCapacity];
  char error_[kSendErrorCapacity];
};

}  // namespace companion
