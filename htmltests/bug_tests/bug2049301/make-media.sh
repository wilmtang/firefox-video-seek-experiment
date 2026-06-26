#!/usr/bin/env bash
# Generate the test clips the seek harness needs, for bug 2049301.
#
# Same 40 s, 1280x720@60, 2 s GOP (g=120) content in three codecs, with a
# burned-in timecode so each frame is visually distinct:
#   h264.mp4  - H.264 High  (AppleVTDecoder / VideoToolbox on macOS)
#   vp9.webm  - VP9
#   av1.mp4   - AV1
#
# Also writes split MSE files: video-only buffers plus audio-only buffers. The
# test page appends those into separate SourceBuffers to match adaptive players.
# Requires ffmpeg (brew install ffmpeg). Run once from this directory.
set -euo pipefail
cd "$(dirname "$0")"

# testsrc renders its own per-frame timestamp, so frames stay visually distinct
# without the drawtext filter (which needs a freetype-enabled ffmpeg build).
SRC_V=(-f lavfi -i testsrc=size=1280x720:rate=60:duration=40)
SRC_A=(-f lavfi -i sine=frequency=440:duration=40)

echo "encoding h264.mp4 ..."
ffmpeg -y -hide_banner -loglevel error "${SRC_V[@]}" "${SRC_A[@]}" \
  -c:v libx264 -preset veryfast -g 120 -keyint_min 120 -sc_threshold 0 -pix_fmt yuv420p \
  -c:a aac -movflags +faststart h264.mp4

echo "encoding vp9.webm ..."
ffmpeg -y -hide_banner -loglevel error "${SRC_V[@]}" "${SRC_A[@]}" \
  -c:v libvpx-vp9 -b:v 2M -g 120 -keyint_min 120 -deadline good -cpu-used 4 \
  -row-mt 1 -pix_fmt yuv420p \
  -c:a libopus vp9.webm

echo "encoding av1.mp4 ..."
ffmpeg -y -hide_banner -loglevel error "${SRC_V[@]}" "${SRC_A[@]}" \
  -c:v libsvtav1 -preset 8 -crf 35 -g 120 -svtav1-params "keyint=120" -pix_fmt yuv420p \
  -c:a aac -movflags +faststart av1.mp4

echo "writing split MSE files ..."
ffmpeg -y -hide_banner -loglevel error -i h264.mp4 -map 0:v:0 \
  -c copy -movflags frag_keyframe+empty_moov+default_base_moof mse-h264-video.mp4
ffmpeg -y -hide_banner -loglevel error -i av1.mp4 -map 0:v:0 \
  -c copy -movflags frag_keyframe+empty_moov+default_base_moof mse-av1-video.mp4
ffmpeg -y -hide_banner -loglevel error -i vp9.webm -map 0:v:0 \
  -c copy mse-vp9-video.webm
ffmpeg -y -hide_banner -loglevel error -i h264.mp4 -map 0:a:0 \
  -c copy -movflags frag_keyframe+empty_moov+default_base_moof mse-aac-audio.mp4
ffmpeg -y -hide_banner -loglevel error -i vp9.webm -map 0:a:0 \
  -c copy mse-opus-audio.webm

echo "wrote: $(ls -1 h264.mp4 vp9.webm av1.mp4 mse-*-video.* mse-*-audio.*)"
