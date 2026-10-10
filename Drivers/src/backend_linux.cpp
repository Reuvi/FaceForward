#include "backend.hpp"
#include <cerrno>
#include <linux/input.h>
#include <libevdev/libevdev.h>
#include <libevdev/libevdev-uinput.h>

namespace fid {
namespace {
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
    }
    fid_result initialize() {
        auto result = create_device(true, &mouse_);
        if (result != FID_OK) return result;
        return create_device(false, &keyboard_);
    }
    fid_result ready() const override {
        return mouse_ && keyboard_ ? FID_OK : FID_BACKEND_UNAVAILABLE;
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
};
} // namespace

std::unique_ptr<Backend> make_native_backend(fid_result &result) {
    auto backend = std::make_unique<LinuxBackend>();
    result = backend->initialize();
    if (result != FID_OK) return nullptr;
    return backend;
}
} // namespace fid
