# Local tongue segmentation weights

Source: [zzqsld tongue analysis API v3.0 release](https://github.com/zzqsld/zzqsld-tongue-analysis-api/releases/tag/v3.0),
asset `tongue_seg_v8n_onnx.zip`, model `tongue_seg.onnx`.
Weights: YOLOv8n-seg trained by the release author on TonguExpert tongue photographs.
The release licenses the weights under **CC BY-NC 4.0**, for research/noncommercial
use. [License terms](https://creativecommons.org/licenses/by-nc/4.0/).
No weights or upstream implementation code are committed to this repository.
Our decoder uses ONNX Runtime locally; it does not start the upstream API service.
No medical/color diagnosis components are used.

Pinned model SHA256:
`885ecd06ec97fee5ed3959c85590c7a3dc3d10f134c7dc821c3b99f45506c35e`
Size: 13,287,587 bytes. Fixed input: RGB float32 1×3×640×640, divided by 255.
Outputs: predictions 1×37×8400 (xywh, one class score, 32 mask coefficients),
prototypes 1×32×160×160. The 160px square mouth crop is resized directly to 640;
it requires no letterboxing because it is already square.

Setup, explicitly run once from the repository root:

```sh
Vision/.venv/bin/python -m pip install -r Vision/requirements-tongue.txt
Vision/.venv/bin/python -m Vision.setup_tongue_model
```

The setup command downloads the release archive and verifies the extracted ONNX
hash before replacing the local file. Runtime never downloads anything. Model
loading/inference runs on the capture worker, not Tk. It uses CPU execution,
4 intra-op threads and 1 inter-op thread. A loading error stays visible until
reload/restart; it does not retry an expensive load every frame or use a color fallback.
A missing model disables tongue only; eyes, pupils and head remain available.

The author's photograph-dataset metrics do not establish live webcam or pointer
accuracy. Observe tongue-absent false masks, lips/gums, small protrusions, movement,
blur and boundary quality in the lab. New model hashes require a decoder review,
new measurement contract and fresh personal calibration.
