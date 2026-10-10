"""Benchmark selected-face pixel measurements only; excludes ML, capture and UI."""

import argparse
import json
from time import perf_counter

import numpy as np

from .demo_detection import demo_image
from .features import DetectionConfig, analyze_features
from .tongue import TongueModel, mouth_crop, sample_colors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames",type=int,default=500)
    args=parser.parse_args()
    if args.frames < 1:
        parser.error("frames must be positive")
    config=DetectionConfig()
    bgr,obs=demo_image(tongue=True)
    negative,nobs=demo_image()
    crop,_=mouth_crop(bgr,obs[0],config)
    ncrop,_=mouth_crop(negative,nobs[0],config)
    model=TongueModel.fit(sample_colors(crop,xy=(.5,.5)),sample_colors(ncrop))
    timings=[]
    for i in range(args.frames+50):
        start=perf_counter()
        analyze_features(bgr,obs[0],config)
        current,_=mouth_crop(bgr,obs[0],config)
        model.detect(current,config)
        if i>=50:timings.append((perf_counter()-start)*1000)
    print(json.dumps({"synthetic":True,"frames":args.frames,"mean_ms":float(np.mean(timings)),
                      "p95_ms":float(np.quantile(timings,.95)),"max_ms":max(timings),
                      "excludes":"neural inference, capture, tracking, frame construction, UI, OS output"},indent=2))


if __name__=="__main__":
    main()
