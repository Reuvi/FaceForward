#include "face_input_driver.h"

int main(void) {
    fid_config config;
    fid_default_config(&config);
    fid_driver *driver = NULL;
    if (fid_create(&config, &driver) != FID_OK) return 1;
    fid_frame frame;
    fid_neutral_frame(&frame);
    fid_result result = fid_submit(driver, &frame);
    fid_destroy(driver);
    return result == FID_OK ? 0 : 1;
}
