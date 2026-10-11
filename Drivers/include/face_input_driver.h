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

#define FID_ABI_VERSION 3u

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

typedef enum fid_pointer_mode {
    /* pointer_x/pointer_y are continuous direction and speed axes; 0.5 is neutral. */
    FID_POINTER_VELOCITY = 0,
    /* target_x/target_y are normalized display coordinates; target_speed is [0,1]. */
    FID_POINTER_TARGET = 1
} fid_pointer_mode;

typedef enum fid_event_type {
    FID_EVENT_MOVE = 1,
    FID_EVENT_SCROLL = 2,
    FID_EVENT_LEFT_CLICK = 3,
    FID_EVENT_RIGHT_CLICK = 4,
    FID_EVENT_DELETE = 5,
    FID_EVENT_INSERT = 6,
    FID_EVENT_KEY_DOWN = 7,
    FID_EVENT_KEY_UP = 8
} fid_event_type;

/* ABI v3 held-key state bits. A set bit means held; clearing it releases. */
enum fid_key {
    FID_KEY_W = 1u << 0,
    FID_KEY_A = 1u << 1,
    FID_KEY_S = 1u << 2,
    FID_KEY_D = 1u << 3,
    FID_KEY_SPACE = 1u << 4,
    FID_KEY_LEFT_SHIFT = 1u << 5,
    FID_KEY_MASK = (1u << 6) - 1
};

enum fid_capability {
    FID_CAP_POINTER = 1u << 0,
    FID_CAP_SCROLL = 1u << 1,
    FID_CAP_LEFT_CLICK = 1u << 2,
    FID_CAP_RIGHT_CLICK = 1u << 3,
    FID_CAP_DELETE = 1u << 4,
    FID_CAP_INSERT = 1u << 5,
    /* macOS emits the Help/Insert-position key, not guaranteed overwrite. */
    FID_CAP_INSERT_LIMITED = 1u << 6,
    FID_CAP_HELD_KEYS = 1u << 7
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
    double target_max_speed; /* Absolute target mode speed in display units/sec. */
} fid_config;

typedef struct fid_frame {
    double pointer_x; /* Velocity mode only: neutral-centered direction/speed axis. */
    double pointer_y;
    double scroll;
    double left_click;
    double right_click;
    double delete_key;
    double insert_key;
    uint32_t pointer_mode; /* fid_pointer_mode; defaults to velocity in fid_neutral_frame. */
    double target_x;       /* Target mode only: normalized primary-display coordinate. */
    double target_y;       /* Target mode only: normalized primary-display coordinate. */
    double target_speed;   /* Target mode only: fraction [0,1] of target_max_speed. */
    uint32_t keys_down;    /* Complete held-key snapshot; omitted bits are released. */
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
    uint32_t pointer_mode; /* Active frame mode. */
    uint32_t pointer_position_valid; /* Position fields are available when nonzero. */
    uint32_t target_reached; /* Current target is reached when nonzero. */
    uint32_t reserved;
    double pointer_position_x;
    double pointer_position_y;
    double target_x;
    double target_y;
    double target_speed;
    double pointer_velocity_x; /* Measured target-mode step velocity, display units/sec. */
    double pointer_velocity_y;
    uint32_t held_key_mask; /* Keys currently held by the driver; zero when paused. */
} fid_status;

typedef struct fid_event {
    uint32_t type;
    int32_t x;
    int32_t y;
    uint64_t monotonic_us;
} fid_event;

/* Live output is opt-in: defaults select dry-run and creation starts paused. */
FID_API uint32_t fid_abi_version(void);
FID_API void fid_default_config(fid_config *config);
FID_API void fid_neutral_frame(fid_frame *frame);
FID_API fid_result fid_create(const fid_config *config, fid_driver **out_driver);
FID_API fid_result fid_submit(fid_driver *driver, const fid_frame *frame);
/* For already-processed states: consume transitions synchronously, without a
 * latest-frame overwrite between worker ticks. Struct layouts remain ABI v3.
 * Use zero button dwell when the producer has already classified eye actions.
 * Invalid processed frames pause and release output immediately. */
FID_API fid_result fid_submit_processed(fid_driver *driver, const fid_frame *frame);
/* Enabling discards old frames; submit a fresh frame with no buttons or keys held.
 * ABI v3 adds complete held-key state to the v2 pointer and button contract. */
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
