#include "face_input_driver.h"

int main(void) {
    fid_config config;
    fid_default_config(&config);
    if (config.abi_version != 3) return 1;
    fid_driver *driver = NULL;
    if (fid_create(&config, &driver) != FID_OK) return 1;
    fid_frame frame;
    fid_neutral_frame(&frame);
    if (frame.keys_down != 0 || (FID_KEY_W | FID_KEY_A | FID_KEY_S | FID_KEY_D |
                                 FID_KEY_SPACE | FID_KEY_LEFT_SHIFT) != FID_KEY_MASK) return 1;
    fid_result result = fid_submit(driver, &frame);
    fid_destroy(driver);
    return result == FID_OK ? 0 : 1;
}
