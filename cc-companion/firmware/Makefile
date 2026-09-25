CXX ?= g++
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -pedantic -Iinclude
BUILD_DIR := build
TEST_BIN := $(BUILD_DIR)/test_app_state

.PHONY: test clean

test: $(TEST_BIN)
	$(TEST_BIN)

$(TEST_BIN): src/app_state.cpp src/display_model.cpp src/input_alert.cpp src/message_flow.cpp test/test_app_state.cpp include/companion/app_state.h include/companion/display_model.h include/companion/input_alert.h include/companion/message_flow.h include/companion/protocol_models.h
	mkdir -p $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) src/app_state.cpp src/display_model.cpp src/input_alert.cpp src/message_flow.cpp test/test_app_state.cpp -o $(TEST_BIN)

clean:
	rm -rf $(BUILD_DIR)
