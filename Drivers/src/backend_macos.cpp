#include "backend.hpp"
#include <ApplicationServices/ApplicationServices.h>
#include <algorithm>
#include <cmath>
#include <memory>

namespace fid {
namespace {
struct EventDeleter { void operator()(CGEventRef event) const { if (event) CFRelease(event); } };
using Event = std::unique_ptr<__CGEvent, EventDeleter>;

CGKeyCode mac_key_code(uint32_t key) {
    // Virtual key codes from HIToolbox/Events.h (US keyboard layout codes).
    switch (key) {
        case FID_KEY_W: return 13;
        case FID_KEY_A: return 0;
        case FID_KEY_S: return 1;
        case FID_KEY_D: return 2;
        case FID_KEY_SPACE: return 49;
        case FID_KEY_LEFT_SHIFT: return 56;
        default: return UINT16_MAX;
    }
}

class MacBackend final : public Backend {
public:
    fid_result ready() const override {
        return CGPreflightPostEventAccess() ? FID_OK : FID_PERMISSION_DENIED;
    }
    uint32_t capabilities() const override { return base_capabilities | FID_CAP_INSERT_LIMITED | FID_CAP_UNICODE_TEXT; }
    bool supports_target_pointer() const override { return true; }
    fid_result pointer_position(double &x, double &y) const override {
        Event current(CGEventCreate(nullptr));
        if (!current) return FID_INTERNAL_ERROR;
        const CGPoint point = CGEventGetLocation(current.get());
        const CGRect screen = CGDisplayBounds(CGMainDisplayID());
        const double width = CGRectGetWidth(screen), height = CGRectGetHeight(screen);
        if (width <= 1 || height <= 1) return FID_BACKEND_UNAVAILABLE;
        x = std::clamp((point.x - CGRectGetMinX(screen)) / (width - 1), 0.0, 1.0);
        y = std::clamp((point.y - CGRectGetMinY(screen)) / (height - 1), 0.0, 1.0);
        return FID_OK;
    }
    fid_result move_toward(double tx, double ty, double speed, double dt,
                           bool &reached, int32_t &dx, int32_t &dy) override {
        const auto access = ready();
        if (access != FID_OK) return access;
        Event current(CGEventCreate(nullptr));
        if (!current) return FID_INTERNAL_ERROR;
        const CGPoint point = CGEventGetLocation(current.get());
        const CGRect screen = CGDisplayBounds(CGMainDisplayID());
        const double width = CGRectGetWidth(screen), height = CGRectGetHeight(screen);
        CGPoint target{CGRectGetMinX(screen) + tx * (width - 1),
                       CGRectGetMinY(screen) + ty * (height - 1)};
        const double vx = target.x - point.x, vy = target.y - point.y;
        const double distance = std::hypot(vx, vy);
        const double step = std::min(distance, speed * dt);
        if (distance > 0 && step > 0) {
            target.x = point.x + vx / distance * step;
            target.y = point.y + vy / distance * step;
        } else {
            target = point;
        }
        reached = distance < 0.5 || (speed > 0 && distance <= speed * dt);
        if (reached) target = {CGRectGetMinX(screen) + tx * (width - 1),
                               CGRectGetMinY(screen) + ty * (height - 1)};
        Event move(CGEventCreateMouseEvent(nullptr, drag_left_ ? kCGEventLeftMouseDragged : kCGEventMouseMoved, target, kCGMouseButtonLeft));
        if (!move) return FID_INTERNAL_ERROR;
        CGEventPost(kCGHIDEventTap, move.get());
        dx = static_cast<int32_t>(std::lround(target.x - point.x));
        dy = static_cast<int32_t>(std::lround(target.y - point.y));
        return FID_OK;
    }
    fid_result release() override {
        fid_result result = FID_OK;
        for (uint32_t key = 1; key <= FID_KEY_LEFT_SHIFT; key <<= 1) {
            if (!(held_keys_ & key)) continue;
            Event up(CGEventCreateKeyboardEvent(nullptr, mac_key_code(key), false));
            if (!up) { result = FID_INTERNAL_ERROR; continue; }
            CGEventPost(kCGHIDEventTap, up.get());
            held_keys_ &= ~key;
        }
        if (drag_left_) {
            Event current(CGEventCreate(nullptr));
            if (!current) return FID_INTERNAL_ERROR;
            Event up(CGEventCreateMouseEvent(nullptr, kCGEventLeftMouseUp,
                      CGEventGetLocation(current.get()), kCGMouseButtonLeft));
            if (!up) return FID_INTERNAL_ERROR;
            CGEventPost(kCGHIDEventTap, up.get());
            drag_left_ = false;
        }
        return result;
    }
    fid_result emit(const fid_event &event) override {
        const auto access = ready();
        if (access != FID_OK) return access;
        if (event.type == FID_EVENT_ENTER || event.type == FID_EVENT_TEXT) {
            // Main Return (kVK_Return), not numeric-keypad Enter (0x4c).
            constexpr CGKeyCode return_key = 0x24;
            Event down(CGEventCreateKeyboardEvent(nullptr, event.type == FID_EVENT_ENTER ? return_key : 0, true));
            Event up(CGEventCreateKeyboardEvent(nullptr, event.type == FID_EVENT_ENTER ? return_key : 0, false));
            if (event.type == FID_EVENT_TEXT && down && up) {
                uint32_t scalar = static_cast<uint32_t>(event.x);
                UniChar units[2]; size_t count = 1;
                if (scalar <= 0xffff) units[0] = static_cast<UniChar>(scalar);
                else { scalar -= 0x10000; units[0] = 0xd800+(scalar >> 10); units[1] = 0xdc00+(scalar & 0x3ff); count = 2; }
                CGEventKeyboardSetUnicodeString(down.get(), count, units);
                CGEventKeyboardSetUnicodeString(up.get(), count, units);
            }
            return post_pair(down, up);
        }
        if (event.type == FID_EVENT_DELETE || event.type == FID_EVENT_INSERT) {
            // macOS SDK: kVK_ForwardDelete=0x75, kVK_Help=0x72.
            // Help occupies the PC Insert key position; its behavior is limited.
            const CGKeyCode code = event.type == FID_EVENT_DELETE ? 0x75 : 0x72;
            Event down(CGEventCreateKeyboardEvent(nullptr, code, true));
            Event up(CGEventCreateKeyboardEvent(nullptr, code, false));
            return post_pair(down, up);
        }
        if (event.type == FID_EVENT_KEY_DOWN || event.type == FID_EVENT_KEY_UP) {
            const auto key = static_cast<uint32_t>(event.x);
            const auto code = mac_key_code(key);
            if (code == UINT16_MAX || (key & (key - 1))) return FID_INVALID_ARGUMENT;
            const bool down = event.type == FID_EVENT_KEY_DOWN;
            const bool was_down = (held_keys_ & key) != 0;
            if (down == was_down) return FID_OK;
            Event key_event(CGEventCreateKeyboardEvent(nullptr, code, down));
            if (!key_event) return FID_INTERNAL_ERROR;
            CGEventPost(kCGHIDEventTap, key_event.get());
            held_keys_ = down ? held_keys_ | key : held_keys_ & ~key;
            return FID_OK;
        }
        if (event.type == FID_EVENT_SCROLL) {
            // Quartz positive wheel delta is up; our public positive is down.
            Event scroll(CGEventCreateScrollWheelEvent(nullptr, kCGScrollEventUnitLine,
                                                       1, -event.y));
            if (!scroll) return FID_INTERNAL_ERROR;
            CGEventPost(kCGHIDEventTap, scroll.get());
            return FID_OK;
        }
        Event current(CGEventCreate(nullptr));
        if (!current) return FID_INTERNAL_ERROR;
        CGPoint point = CGEventGetLocation(current.get());
        if (event.type == FID_EVENT_LEFT_DOWN || event.type == FID_EVENT_LEFT_UP) {
            const bool down = event.type == FID_EVENT_LEFT_DOWN;
            Event button(CGEventCreateMouseEvent(nullptr, down ? kCGEventLeftMouseDown : kCGEventLeftMouseUp,
                                                 point, kCGMouseButtonLeft));
            if (!button) return FID_INTERNAL_ERROR;
            CGEventSetIntegerValueField(button.get(), kCGMouseEventClickState, 1);
            CGEventPost(kCGHIDEventTap, button.get());
            drag_left_ = down;
            return FID_OK;
        }
        if (event.type == FID_EVENT_MOVE) {
            // Advance the visible cursor for ordinary desktop use, while also
            // supplying explicit deltas for applications that lock the cursor.
            const CGRect screen = CGDisplayBounds(CGMainDisplayID());
            point.x = std::clamp(point.x + event.x, CGRectGetMinX(screen), CGRectGetMaxX(screen) - 1);
            point.y = std::clamp(point.y + event.y, CGRectGetMinY(screen), CGRectGetMaxY(screen) - 1);
            Event move(CGEventCreateMouseEvent(nullptr, drag_left_ ? kCGEventLeftMouseDragged : kCGEventMouseMoved, point, kCGMouseButtonLeft));
            if (!move) return FID_INTERNAL_ERROR;
            CGEventSetIntegerValueField(move.get(), kCGMouseEventDeltaX, event.x);
            CGEventSetIntegerValueField(move.get(), kCGMouseEventDeltaY, event.y);
            CGEventPost(kCGHIDEventTap, move.get());
            return FID_OK;
        }
        if (event.type == FID_EVENT_LEFT_CLICK || event.type == FID_EVENT_RIGHT_CLICK) {
            const bool left = event.type == FID_EVENT_LEFT_CLICK;
            const auto button = left ? kCGMouseButtonLeft : kCGMouseButtonRight;
            Event down(CGEventCreateMouseEvent(nullptr, left ? kCGEventLeftMouseDown : kCGEventRightMouseDown,
                                               point, button));
            Event up(CGEventCreateMouseEvent(nullptr, left ? kCGEventLeftMouseUp : kCGEventRightMouseUp,
                                             point, button));
            if (down) CGEventSetIntegerValueField(down.get(), kCGMouseEventClickState, 1);
            if (up) CGEventSetIntegerValueField(up.get(), kCGMouseEventClickState, 1);
            return post_pair(down, up);
        }
        return FID_UNSUPPORTED;
    }
private:
    static fid_result post_pair(const Event &down, const Event &up) {
        if (!down || !up) return FID_INTERNAL_ERROR;
        CGEventSetFlags(down.get(), 0);
        CGEventSetFlags(up.get(), 0);
        CGEventPost(kCGHIDEventTap, down.get());
        CGEventPost(kCGHIDEventTap, up.get());
        return FID_OK;
    }
    uint32_t held_keys_ = 0;
    bool drag_left_ = false;
};
} // namespace

std::unique_ptr<Backend> make_native_backend(fid_result &result) {
    auto backend = std::make_unique<MacBackend>();
    if (!CGPreflightPostEventAccess()) {
        // Native creation is explicit; allow the OS permission prompt, but
        // do not continue until the permission is actually granted.
        CGRequestPostEventAccess();
    }
    result = backend->ready();
    if (result != FID_OK) return nullptr;
    return backend;
}
} // namespace fid
