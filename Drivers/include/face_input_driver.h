#ifndef FACE_INPUT_DRIVER_H
#define FACE_INPUT_DRIVER_H

#include <stddef.h>
#include <stdint.h>

#if defined(__GNUC__) || defined(__clang__)
#define FID_API __attribute__((visibility("default")))
#else
#define FID_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define FID_ABI_VERSION 1u

typedef struct fid_driver fid_driver;

typedef enum fid_result {
    FID_OK = 0,
    FID_INVALID_ARGUMENT = 1,
    FID_UNSUPPORTED = 2,
    FID_PERMISSION_DENIED = 3,
    FID_BACKEND_UNAVAILABLE = 4,
    FID_IO_ERROR = 5,
    FID_INTERNAL_ERROR = 6
} fid_result;

typedef enum fid_backend_kind { FID_DRY_RUN = 0, FID_NATIVE = 1 } fid_backend_kind;

typedef enum fid_event_type {
    FID_EVENT_MOVE = 1,
    FID_EVENT_SCROLL = 2,
    FID_EVENT_LEFT_CLICK = 3,
    FID_EVENT_RIGHT_CLICK = 4,
    FID_EVENT_DELETE = 5,
    FID_EVENT_INSERT = 6
} fid_event_type;

enum fid_capability {
    FID_CAP_POINTER = 1u << 0,
    FID_CAP_SCROLL = 1u << 1,
    FID_CAP_LEFT_CLICK = 1u << 2,
    FID_CAP_RIGHT_CLICK = 1u << 3,
    FID_CAP_DELETE = 1u << 4,
    FID_CAP_INSERT = 1u << 5,
    /* macOS emits the Help/Insert-position key, not guaranteed overwrite. */
    FID_CAP_INSERT_LIMITED = 1u << 6
};

typedef struct fid_axis_config {
    double neutral;
    double dead_zone; /* Half width around neutral, in normalized units. */
    double max_speed; /* Pointer units/sec or scroll detents/sec. */
    uint32_t inverted;
} fid_axis_config;

typedef struct fid_button_config {
    double activation_threshold; /* Strictly greater activates. */
    double release_threshold;    /* Strictly less rearms. */
    uint32_t dwell_ms;
} fid_button_config;

typedef struct fid_config {
    uint32_t abi_version;
    uint32_t backend;
    uint32_t tick_hz;
    uint32_t stale_timeout_ms;
    fid_axis_config pointer_x;
    fid_axis_config pointer_y;
    fid_axis_config scroll;
    fid_button_config buttons[4]; /* Left, right, Delete, Insert. */
} fid_config;

typedef struct fid_frame {
    double pointer_x;
    double pointer_y;
    double scroll;
    double left_click;
    double right_click;
    double delete_key;
    double insert_key;
} fid_frame;

typedef struct fid_status {
    uint32_t enabled;
    uint32_t awaiting_neutral;
    uint32_t timed_out;
    uint32_t last_error;
    uint32_t capabilities;
    uint32_t backend;
    uint64_t accepted_frames;
    uint64_t rejected_frames;
    uint64_t emitted_events;
    uint64_t dropped_log_events;
} fid_status;

typedef struct fid_event {
    uint32_t type;
    int32_t x;
    int32_t y;
    uint64_t monotonic_us;
} fid_event;

/* Live output is opt-in: defaults select dry-run and creation starts paused. */
FID_API void fid_default_config(fid_config *config);
FID_API void fid_neutral_frame(fid_frame *frame);
FID_API fid_result fid_create(const fid_config *config, fid_driver **out_driver);
FID_API fid_result fid_submit(fid_driver *driver, const fid_frame *frame);
/* Enabling discards old frames; submit a fresh, neutral-button frame next. */
FID_API fid_result fid_enable(fid_driver *driver);
FID_API fid_result fid_pause(fid_driver *driver);
FID_API fid_result fid_get_status(fid_driver *driver, fid_status *status);
/* Bounded, destructive event journal. Works for dry-run and native backends. */
FID_API fid_result fid_drain_events(fid_driver *driver, fid_event *events,
                                  size_t capacity, size_t *out_count);
FID_API void fid_destroy(fid_driver *driver);
FID_API const char *fid_result_string(fid_result result);

/* All operations are serialized internally. Destroy requires callers to stop
 * using the handle first. No C++ exceptions cross this API. Configuration is
 * immutable after create; pause/destroy/recreate to change it. */

#ifdef __cplusplus
}
#endif
#endif
