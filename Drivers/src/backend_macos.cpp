#include "backend.hpp"
#include <ApplicationServices/ApplicationServices.h>
#include <algorithm>
#include <memory>

namespace fid {
namespace {
struct EventDeleter { void operator()(CGEventRef event) const { if (event) CFRelease(event); } };
using Event = std::unique_ptr<__CGEvent, EventDeleter>;

class MacBackend final : public Backend {
public:
    fid_result ready() const override {
        return CGPreflightPostEventAccess() ? FID_OK : FID_PERMISSION_DENIED;
    }
    uint32_t capabilities() const override { return base_capabilities | FID_CAP_INSERT_LIMITED; }
    fid_result release() override {
        // Every action allocates both halves first and posts a complete pair
        // synchronously. This backend never intentionally holds a key/button.
        return FID_OK;
    }
    fid_result emit(const fid_event &event) override {
        const auto access = ready();
        if (access != FID_OK) return access;
        if (event.type == FID_EVENT_DELETE || event.type == FID_EVENT_INSERT) {
            // macOS SDK: kVK_ForwardDelete=0x75, kVK_Help=0x72.
            // Help occupies the PC Insert key position; its behavior is limited.
            const CGKeyCode code = event.type == FID_EVENT_DELETE ? 0x75 : 0x72;
            Event down(CGEventCreateKeyboardEvent(nullptr, code, true));
            Event up(CGEventCreateKeyboardEvent(nullptr, code, false));
            return post_pair(down, up);
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
        if (event.type == FID_EVENT_MOVE) {
            const CGRect screen = CGDisplayBounds(CGMainDisplayID());
            point.x = std::clamp(point.x + event.x, CGRectGetMinX(screen), CGRectGetMaxX(screen) - 1);
            point.y = std::clamp(point.y + event.y, CGRectGetMinY(screen), CGRectGetMaxY(screen) - 1);
            Event move(CGEventCreateMouseEvent(nullptr, kCGEventMouseMoved, point, kCGMouseButtonLeft));
            if (!move) return FID_INTERNAL_ERROR;
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
