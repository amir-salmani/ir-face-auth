#!/usr/bin/env bash
# Fetch the ONNX models from OpenCV Zoo.
#
# These are kept out of git deliberately: SFace alone is 37MB, and binary blobs
# in git history are permanent. Packaging should ship them as a data file or
# depend on a distro package instead of vendoring them here.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models"
BASE="https://github.com/opencv/opencv_zoo/raw/main/models"

mkdir -p "$DIR"
for m in \
  "face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  "face_recognition_sface/face_recognition_sface_2021dec.onnx"
do
  out="$DIR/$(basename "$m")"
  if [[ -f "$out" ]]; then
    echo "have $(basename "$m")"
    continue
  fi
  echo "fetching $(basename "$m")"
  curl -sSL --fail -o "$out" "$BASE/$m"
done
echo "models ready in $DIR"
