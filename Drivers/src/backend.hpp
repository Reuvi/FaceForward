#pragma once

#include "face_input_driver.h"
#include <memory>

namespace fid {
constexpr uint32_t base_capabilities = FID_CAP_POINTER | FID_CAP_SCROLL |
    FID_CAP_LEFT_CLICK | FID_CAP_RIGHT_CLICK | FID_CAP_DELETE | FID_CAP_INSERT;

class Backend {
public:
    virtual ~Backend() = default;
    virtual fid_result ready() const = 0;
    virtual fid_result emit(const fid_event &event) = 0;
    virtual fid_result release() = 0;
    virtual uint32_t capabilities() const { return base_capabilities; }
};

std::unique_ptr<Backend> make_native_backend(fid_result &result);
} // namespace fid
