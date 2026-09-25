#include <cstdlib>
#include <cstring>
#include <iostream>

#include "companion/app_state.h"
#include "companion/display_model.h"
#include "companion/input_alert.h"
#include "companion/message_flow.h"

namespace {

using companion::AppState;
using companion::CcRow;
using companion::CcState;
using companion::BuildListView;
using companion::AlertPolicy;
using companion::ButtonAction;
using companion::MainButton;
using companion::MessageFlow;
using companion::MessageFlowState;
using companion::PendingMessage;
using companion::Priority;
using companion::ReconnectBackoff;

int failures = 0;

void Expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    ++failures;
  }
}

CcRow Row(std::uint8_t code, CcState state, const char* summary) {
  CcRow row = {code, state, Priority::kNormal, 100, {0}};
  std::strncpy(row.summary, summary, sizeof(row.summary) - 1);
  return row;
}

void TestSnapshotAndSelection() {
  AppState state;
  const CcRow snapshot[] = {
      Row(2, CcState::kAwaitingConfirmation, "Allow Bash?"),
      Row(1, CcState::kWorking, "Refactor auth"),
  };

  Expect(state.ApplySnapshot(5, snapshot, 2), "accepts a valid snapshot");
  Expect(state.gateway_online(), "snapshot marks gateway online");
  Expect(state.revision() == 5, "snapshot stores revision");
  Expect(state.row_at(0)->cc_code == 1, "snapshot sorts rows by code");
  Expect(state.selected_row()->cc_code == 1, "initial selection picks first code");
  Expect(state.SelectNext(), "can choose next row");
  Expect(state.selected_row()->cc_code == 2, "next selection advances");

  const CcRow refreshed[] = {Row(1, CcState::kDone, "Done"), Row(2, CcState::kWorking, "Continue")};
  Expect(state.ApplySnapshot(6, refreshed, 2), "accepts newer snapshot");
  Expect(state.selected_row()->cc_code == 2, "snapshot preserves selection when target remains");
}

void TestDeltaAndStaleRevisions() {
  AppState state;
  const CcRow initial[] = {Row(1, CcState::kWorking, "Initial")};
  state.ApplySnapshot(2, initial, 1);

  Expect(!state.ApplyStateDelta(2, Row(1, CcState::kDone, "Stale")), "rejects same revision delta");
  Expect(!state.ApplySnapshot(1, initial, 1), "rejects stale snapshot");
  Expect(state.ApplyStateDelta(3, Row(2, CcState::kError, "Test failed")), "accepts new state delta");
  Expect(state.row_count() == 2, "delta adds unseen CC row");
  Expect(state.row_at(1)->cc_code == 2, "new row is sorted");

  state.MarkGatewayOffline();
  Expect(!state.gateway_online(), "offline status retains cache but changes connection state");
  Expect(state.row_count() == 2, "offline status keeps rows");
}

void TestInputValidation() {
  AppState state;
  CcRow duplicate[] = {Row(1, CcState::kWorking, "A"), Row(1, CcState::kDone, "B")};
  CcRow missing_terminator = Row(2, CcState::kWorking, "Valid");
  missing_terminator.summary[20] = 'x';

  Expect(!state.ApplySnapshot(1, duplicate, 2), "rejects duplicate CC codes");
  Expect(!state.ApplyStateDelta(1, missing_terminator), "rejects non-terminated summaries");
  Expect(!state.SelectNext(), "cannot select without rows");
}

void TestReconnectBackoff() {
  ReconnectBackoff backoff;
  Expect(backoff.CanAttempt(0), "first reconnect attempt is immediate");
  backoff.RecordAttempt(0);
  Expect(!backoff.CanAttempt(999), "first retry waits one second");
  Expect(backoff.CanAttempt(1000), "first retry becomes due after one second");
  Expect(backoff.next_delay_ms() == 2000, "delay doubles after first attempt");

  for (int index = 0; index < 10; ++index) {
    backoff.RecordAttempt(60000U * static_cast<std::uint32_t>(index + 1));
  }
  Expect(backoff.next_delay_ms() == 60000, "retry delay is capped at sixty seconds");
  backoff.Reset();
  Expect(backoff.CanAttempt(0), "successful connection reset allows immediate future retry");
  Expect(backoff.next_delay_ms() == 1000, "reset restores first retry delay");
}

void TestDisplayModel() {
  AppState state;
  CcRow rows[] = {
      Row(1, CcState::kWorking, "Refactor authentication module"),
      Row(2, CcState::kAwaitingConfirmation, "Allow Bash command?"),
  };
  rows[1].priority = Priority::kHigh;
  state.ApplySnapshot(1, rows, 2);
  state.SelectNext();

  const companion::ListView view = BuildListView(state);
  Expect(std::strcmp(view.header, "CC ->#2 online") == 0, "header identifies selected online target");
  Expect(std::strcmp(view.lines[0].text, "#1 > Refactor authenticat") == 0, "row has working marker and truncated summary");
  Expect(view.lines[1].selected, "selected target is highlighted in view model");
  Expect(view.lines[1].attention, "high-priority target has attention flag");

  state.MarkGatewayOffline();
  const companion::ListView offline = BuildListView(state);
  Expect(std::strcmp(offline.header, "CC ->#2 offline") == 0, "offline view retains selected target");
}

void TestButtonAndAlertPolicy() {
  MainButton button;
  Expect(button.Update(true, 100) == ButtonAction::kNone, "press does not immediately choose a target");
  Expect(button.Update(false, 300) == ButtonAction::kSelectNext, "short press selects next target");
  Expect(button.Update(true, 1000) == ButtonAction::kNone, "new press resets button state");
  Expect(button.Update(true, 1599) == ButtonAction::kNone, "press below long threshold does not record");
  Expect(button.Update(true, 1600) == ButtonAction::kBeginRecording, "long press starts recording once");
  Expect(button.Update(true, 1700) == ButtonAction::kNone, "continued long press does not repeat record action");
  Expect(button.Update(false, 1800) == ButtonAction::kFinishRecording, "release after long press stops recording");

  AlertPolicy policy;
  CcRow attention = Row(1, CcState::kAwaitingConfirmation, "Allow");
  attention.priority = Priority::kHigh;
  CcRow progress = Row(2, CcState::kWorking, "Work");
  progress.priority = Priority::kHigh;
  Expect(!policy.ShouldAlert(progress), "working updates never trigger attention alerts");
  Expect(policy.ShouldWakeScreen(attention), "high priority confirmation wakes screen");
  policy.SetDnd(true);
  Expect(!policy.ShouldAlert(progress), "DND suppresses sound alerts");
  Expect(!policy.ShouldWakeScreen(progress), "DND suppresses display wake");
}

void TestMessageFlow() {
  MessageFlow flow;
  PendingMessage message = {};
  Expect(!flow.FinishRecording(), "cannot finish recording before beginning one");
  Expect(flow.BeginRecording(2), "starts recording for selected target");
  Expect(flow.state() == MessageFlowState::kRecording, "recording state is visible");
  Expect(flow.FinishRecording(), "finishes recording into transcription state");
  Expect(flow.state() == MessageFlowState::kTranscribing, "transcription state is visible");
  Expect(!flow.ReceiveTranscript(""), "empty transcription is rejected");
  Expect(flow.ReceiveTranscript("Allow this command"), "accepts a non-empty transcript");
  Expect(flow.state() == MessageFlowState::kConfirming, "transcript requires explicit confirmation");
  Expect(flow.BeginSend(&message), "builds a send message after confirmation");
  Expect(message.cc_code == 2, "pending message keeps original selected target");
  Expect(std::strcmp(message.text, "Allow this command") == 0, "pending message keeps transcript");
  Expect(flow.state() == MessageFlowState::kSending, "send request blocks duplicate confirmation presses");
  Expect(!flow.BeginSend(&message), "cannot create a second send while acknowledgement is pending");

  flow.ApplySendAcknowledgement(false, "TARGET_UNREACHABLE");
  Expect(flow.state() == MessageFlowState::kSendFailed, "failure is displayed without losing draft");
  Expect(std::strcmp(flow.draft(), "Allow this command") == 0, "failed send preserves transcript");
  Expect(std::strcmp(flow.error(), "TARGET_UNREACHABLE") == 0, "failed send exposes actionable error");
  Expect(flow.BeginRerecording(), "failed send can begin a replacement recording");
  Expect(flow.state() == MessageFlowState::kRecording, "rerecording returns to recording state");

  flow.FinishRecording();
  flow.ReceiveTranscript("Continue work");
  flow.BeginSend(&message);
  flow.ApplySendAcknowledgement(true, nullptr);
  Expect(flow.state() == MessageFlowState::kSendSucceeded, "successful acknowledgement completes send");
  flow.ReturnToList();
  Expect(flow.state() == MessageFlowState::kList, "return clears temporary message state");
  Expect(flow.target_cc_code() == 0, "return clears target after completion");
}

}  // namespace

int main() {
  TestSnapshotAndSelection();
  TestDeltaAndStaleRevisions();
  TestInputValidation();
  TestReconnectBackoff();
  TestDisplayModel();
  TestButtonAndAlertPolicy();
  TestMessageFlow();
  if (failures != 0) {
    return EXIT_FAILURE;
  }
  std::cout << "All firmware state tests passed\n";
  return EXIT_SUCCESS;
}
