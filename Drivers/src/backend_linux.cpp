#include "backend.hpp"
#include <cerrno>
#include <linux/input.h>
#include <libevdev/libevdev.h>
#include <libevdev/libevdev-uinput.h>
#ifdef FID_HAS_X11
#include <X11/Xlib.h>
#ifdef FID_HAS_XRANDR
#include <X11/extensions/Xrandr.h>
#endif
#endif
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <string>

namespace fid {
namespace {
unsigned linux_key_code(uint32_t key) {
    switch (key) {
        case FID_KEY_W: return KEY_W;
        case FID_KEY_A: return KEY_A;
        case FID_KEY_S: return KEY_S;
        case FID_KEY_D: return KEY_D;
        case FID_KEY_SPACE: return KEY_SPACE;
        case FID_KEY_LEFT_SHIFT: return KEY_LEFTSHIFT;
        default: return 0;
    }
}
fid_result translate(int error) {
    if (!error) return FID_OK;
    if (error == -EACCES || error == -EPERM) return FID_PERMISSION_DENIED;
    if (error == -ENOENT || error == -ENODEV) return FID_BACKEND_UNAVAILABLE;
    return FID_IO_ERROR;
}

class LinuxBackend final : public Backend {
public:
    ~LinuxBackend() override {
        release();
        if (mouse_) libevdev_uinput_destroy(mouse_);
        if (keyboard_) libevdev_uinput_destroy(keyboard_);
#ifdef FID_HAS_X11
        if (display_) XCloseDisplay(display_);
#endif
    }
    fid_result initialize() {
        auto result = create_device(true, &mouse_);
        if (result != FID_OK) return result;
        result = create_device(false, &keyboard_);
        if (result != FID_OK) return result;
#ifdef FID_HAS_X11
        const char *session = std::getenv("XDG_SESSION_TYPE");
        const char *wayland = std::getenv("WAYLAND_DISPLAY");
        if ((session && std::string(session) == "wayland") || wayland) return FID_OK;
        display_ = XOpenDisplay(nullptr);
        if (display_) {
            root_ = DefaultRootWindow(display_);
#ifdef FID_HAS_XRANDR
            width_ = 0; height_ = 0;
#else
            width_ = DisplayWidth(display_, DefaultScreen(display_));
            height_ = DisplayHeight(display_, DefaultScreen(display_));
#endif
#ifdef FID_HAS_XRANDR
            int count = 0;
            XRRMonitorInfo *monitors = XRRGetMonitors(display_, root_, True, &count);
            if (monitors) {
                for (int i = 0; i < count; ++i) {
                    if (monitors[i].primary) {
                        origin_x_ = monitors[i].x; origin_y_ = monitors[i].y;
                        width_ = monitors[i].width; height_ = monitors[i].height;
                        break;
                    }
                }
                XRRFreeMonitors(monitors);
            }
#endif
        }
#endif
        return FID_OK;
    }
    fid_result ready() const override {
        return mouse_ && keyboard_ ? FID_OK : FID_BACKEND_UNAVAILABLE;
    }
    bool supports_target_pointer() const override {
#if defined(FID_HAS_X11) && defined(FID_HAS_XRANDR)
        return display_ && width_ > 1 && height_ > 1;
#else
        return false;
#endif
    }
    fid_result pointer_position(double &x, double &y) const override {
        if (!supports_target_pointer()) return FID_UNSUPPORTED;
#ifdef FID_HAS_X11
        Window root_return, child_return;
        int root_x, root_y, win_x, win_y;
        unsigned mask;
        if (!XQueryPointer(display_, root_, &root_return, &child_return,
                           &root_x, &root_y, &win_x, &win_y, &mask)) return FID_IO_ERROR;
        x = std::clamp((root_x - origin_x_) / static_cast<double>(width_ - 1), 0.0, 1.0);
        y = std::clamp((root_y - origin_y_) / static_cast<double>(height_ - 1), 0.0, 1.0);
        return FID_OK;
#else
        (void)x; (void)y; return FID_UNSUPPORTED;
#endif
    }
    fid_result move_toward(double tx, double ty, double speed, double dt,
                           bool &reached, int32_t &dx, int32_t &dy) override {
        if (!supports_target_pointer()) return FID_UNSUPPORTED;
#ifdef FID_HAS_X11
        Window root_return, child_return;
        int root_x, root_y, win_x, win_y;
        unsigned mask;
        if (!XQueryPointer(display_, root_, &root_return, &child_return,
                           &root_x, &root_y, &win_x, &win_y, &mask)) return FID_IO_ERROR;
        const double target_x = origin_x_ + tx * (width_ - 1);
        const double target_y = origin_y_ + ty * (height_ - 1);
        const double vx = target_x - root_x, vy = target_y - root_y;
        const double distance = std::hypot(vx, vy);
        const double step = std::min(distance, speed * dt);
        double next_x = root_x, next_y = root_y;
        if (distance > 0 && step > 0) {
            next_x += vx / distance * step; next_y += vy / distance * step;
        }
        reached = distance < 0.5 || (speed > 0 && distance <= speed * dt);
        if (reached) { next_x = target_x; next_y = target_y; }
        const int dest_x = static_cast<int>(std::lround(next_x));
        const int dest_y = static_cast<int>(std::lround(next_y));
        XWarpPointer(display_, None, root_, 0, 0, 0, 0, dest_x, dest_y);
        XFlush(display_);
        dx = dest_x - root_x; dy = dest_y - root_y;
        return FID_OK;
#else
        (void)tx; (void)ty; (void)speed; (void)dt; (void)reached; (void)dx; (void)dy;
        return FID_UNSUPPORTED;
#endif
    }
    fid_result emit(const fid_event &event) override {
        switch (event.type) {
            case FID_EVENT_MOVE: {
                auto r = write(mouse_, EV_REL, REL_X, event.x);
                if (r == FID_OK) r = write(mouse_, EV_REL, REL_Y, event.y);
                // Flush any successfully written partial movement as well.
                auto sync_result = sync(mouse_);
                return r != FID_OK ? r : sync_result;
            }
            case FID_EVENT_SCROLL: {
                // Shared convention: positive is down. Linux wheel positive is up.
                auto r = write(mouse_, EV_REL, REL_WHEEL, -event.y);
                auto sync_result = sync(mouse_);
                return r != FID_OK ? r : sync_result;
            }
            case FID_EVENT_LEFT_CLICK: return tap(mouse_, BTN_LEFT, 0);
            case FID_EVENT_RIGHT_CLICK: return tap(mouse_, BTN_RIGHT, 1);
            case FID_EVENT_DELETE: return tap(keyboard_, KEY_DELETE, 2);
            case FID_EVENT_INSERT: return tap(keyboard_, KEY_INSERT, 3);
            case FID_EVENT_KEY_DOWN:
            case FID_EVENT_KEY_UP: {
                const auto key = static_cast<uint32_t>(event.x);
                const auto code = linux_key_code(key);
                if (!code || (key & (key - 1))) return FID_INVALID_ARGUMENT;
                const bool down = event.type == FID_EVENT_KEY_DOWN;
                const bool was_down = (held_keys_ & key) != 0;
                if (down == was_down) return FID_OK;
                // Remember a possibly successful key-down even if syncing
                // fails, so release() can make a best-effort cleanup. Keep a
                // key marked held until its key-up write and sync both pass.
                if (down) held_keys_ |= key;
                auto r = write(keyboard_, EV_KEY, code, down ? 1 : 0);
                if (r == FID_OK) r = sync(keyboard_);
                if (r == FID_OK && !down) held_keys_ &= ~key;
                return r;
            }
            default: return FID_UNSUPPORTED;
        }
    }
    fid_result release() override {
        fid_result result = FID_OK;
        const unsigned codes[] = {BTN_LEFT, BTN_RIGHT, KEY_DELETE, KEY_INSERT};
        for (size_t i = 0; i < 4; ++i) {
            if (!held_[i]) continue;
            auto *device = i < 2 ? mouse_ : keyboard_;
            auto r = write(device, EV_KEY, codes[i], 0);
            const auto s = sync(device);
            if (r == FID_OK) r = s;
            if (r == FID_OK) held_[i] = false;
            else result = r;
        }
        for (uint32_t key = 1; key <= FID_KEY_LEFT_SHIFT; key <<= 1) {
            if (!(held_keys_ & key)) continue;
            const auto code = linux_key_code(key);
            auto r = write(keyboard_, EV_KEY, code, 0);
            const auto s = sync(keyboard_);
            if (r == FID_OK) r = s;
            if (r == FID_OK) held_keys_ &= ~key;
            else result = r;
        }
        return result;
    }

private:
    static fid_result create_device(bool mouse, libevdev_uinput **out) {
        std::unique_ptr<libevdev, decltype(&libevdev_free)> device(libevdev_new(), libevdev_free);
        if (!device) return FID_INTERNAL_ERROR;
        libevdev_set_name(device.get(), mouse ? "Face Input MVP Mouse" : "Face Input MVP Keyboard");
        libevdev_set_id_bustype(device.get(), BUS_VIRTUAL);
        const unsigned mouse_keys[] = {BTN_LEFT, BTN_RIGHT};
        const unsigned keyboard_keys[] = {KEY_DELETE, KEY_INSERT};
        const unsigned *keys = mouse ? mouse_keys : keyboard_keys;
        for (size_t i = 0; i < 2; ++i) {
            auto r = libevdev_enable_event_code(device.get(), EV_KEY, keys[i], nullptr);
            if (r < 0) return translate(r);
        }
        if (!mouse) {
            // udev recognizes a full keyboard from the initial standard key
            // capability block. Advertise it for compositor identification;
            // the driver still emits only Delete/Insert.
            // https://github.com/systemd/systemd/blob/main/src/udev/udev-builtin-input_id.c
            for (unsigned code = KEY_ESC; code <= KEY_CAPSLOCK; ++code) {
                const auto r = libevdev_enable_event_code(device.get(), EV_KEY, code, nullptr);
                if (r < 0) return translate(r);
            }
        }
        if (mouse) {
            auto r = libevdev_enable_property(device.get(), INPUT_PROP_POINTER);
            if (r < 0) return translate(r);
            const unsigned relative_codes[] = {REL_X, REL_Y, REL_WHEEL};
            for (unsigned code : relative_codes) {
                r = libevdev_enable_event_code(device.get(), EV_REL, code, nullptr);
                if (r < 0) return translate(r);
            }
        }
        return translate(libevdev_uinput_create_from_device(
            device.get(), LIBEVDEV_UINPUT_OPEN_MANAGED, out));
    }
    static fid_result write(libevdev_uinput *device, unsigned type, unsigned code, int value) {
        if (!device) return FID_BACKEND_UNAVAILABLE;
        return translate(libevdev_uinput_write_event(device, type, code, value));
    }
    static fid_result sync(libevdev_uinput *device) {
        return write(device, EV_SYN, SYN_REPORT, 0);
    }
    fid_result tap(libevdev_uinput *device, unsigned code, size_t index) {
        // Mark ownership before writing, so an ambiguous write failure still
        // receives a best-effort release during pause/teardown.
        held_[index] = true;
        auto r = write(device, EV_KEY, code, 1);
        if (r == FID_OK) r = sync(device);
        if (r != FID_OK) return r;
        r = write(device, EV_KEY, code, 0);
        if (r == FID_OK) r = sync(device);
        if (r == FID_OK) held_[index] = false;
        return r;
    }
    libevdev_uinput *mouse_ = nullptr;
    libevdev_uinput *keyboard_ = nullptr;
    bool held_[4]{};
    uint32_t held_keys_ = 0;
#ifdef FID_HAS_X11
    Display *display_ = nullptr;
    Window root_ = 0;
    int origin_x_ = 0, origin_y_ = 0, width_ = 0, height_ = 0;
#endif
};
} // namespace

std::unique_ptr<Backend> make_native_backend(fid_result &result) {
    auto backend = std::make_unique<LinuxBackend>();
    result = backend->initialize();
    if (result != FID_OK) return nullptr;
    return backend;
}
} // namespace fid
