#pragma once

#include "face_input_driver.h"
#include <array>
#include <vector>

namespace fid {
using Time = double; // Monotonic seconds; injectable in deterministic tests.

bool valid_config(const fid_config &config);
bool valid_frame(const fid_frame &frame);
double axis_velocity(double value, const fid_axis_config &config);

struct ButtonState {
    bool latched = false;
    bool dwelling = false;
    Time since = 0;
};

class Control {
public:
    explicit Control(const fid_config &config) : config_(config) {}
    void enable(Time now);
    void pause();
    void submit(const fid_frame &frame, Time now);
    std::vector<fid_event> tick(Time now);
    bool enabled() const { return enabled_; }
    bool awaiting_neutral() const { return awaiting_neutral_; }
    bool timed_out() const { return timed_out_; }

private:
    fid_config config_;
    fid_frame frame_{};
    std::array<ButtonState, 4> buttons_{};
    std::array<double, 3> fractions_{};
    bool enabled_ = false;
    bool awaiting_neutral_ = false;
    bool timed_out_ = false;
    bool have_frame_ = false;
    Time enabled_at_ = 0;
    Time received_at_ = 0;
    Time last_tick_ = 0;
};
} // namespace fid
