# Firefox Audio Seek Readiness Study

This repository contains a small browser media experiment around post-seek
readiness with audible video.

The motivating observation: after Firefox's Bug 2049301 video-seek fixes,
Firefox Nightly can show the target video frame quickly, but YouTube may still
show a loading spinner during audible seeks. A local H.264/AAC control test
also shows Firefox Nightly behaving much closer to Chrome when muted than when
audible.

## Public Test Page

Open the upstream-shaped Bug 2049301 page and click **Run measurement**:

```text
htmltests/bug_tests/bug2049301/seek-test.html
```

The page runs entirely in the browser. It compares progressive playback with an
MSE path that appends separate video/audio buffers, and it has a muted toggle
for the same seek loop.

## How The Seek Pipeline Is Modeled

The harness treats a seek as several related but separate browser signals. They
usually happen in this rough order, but browsers may reorder or skip some events
depending on whether playback was already running and whether `readyState`
actually dropped:

1. JS sets `video.currentTime = target`.
2. The media element fires `seeking`; `currentTime` often reports the target
   quickly, but that does not mean the target frame is decoded or visible.
3. The browser demuxes, finds a keyframe, decodes around the target, and may
   refill audio/video queues.
4. If playback cannot continue during that refill, `waiting` may fire.
5. `readyState` may recover to `HAVE_FUTURE_DATA` (`3`), meaning the media
   element believes it has current and near-future data to advance playback.
6. `seeked` fires when the browser considers the seek operation complete.
7. `requestVideoFrameCallback` reports when the target video frame is actually
   presented.
8. Playback really feels resumed only once the element is playing, not seeking,
   has future data, and `currentTime` advances beyond the seek target.

`waiting` is not guaranteed on every seek. A fast buffered seek may go straight
from `seeking` to `seeked` and continue playback without a meaningful blocked
state. When `waiting` does appear, the important question is not just whether it
fired, but when it fired and how long playback stayed blocked afterward. A
near-zero `waitingMs` can be harmless event noise; a delayed `waitingMs` paired
with delayed `futureDataMs` or `resumedMs` is stronger evidence of user-visible
post-seek readiness lag.

`HAVE_FUTURE_DATA` is useful, but it is not perfect proof that synchronized
sound reached the speakers. It is an HTML media readiness state, not a direct
probe of the OS audio device. Audio sink preroll means the browser has decoded
and queued enough audio into the audio output path to start smoothly and align
with the playback clock. That lower-level audio-device scheduling is not exposed
directly to page JS without changing the pipeline, for example by routing audio
through Web Audio.

## Local Audio/Video Metrics

The local harness uses the Bug 2049301-style page in
`htmltests/bug_tests/bug2049301/seek-test.html`. The Selenium runner currently
automates the YouTube-like MSE path only: separate video and audio
`SourceBuffer`s appended into one `MediaSource`.

## How The Local MSE Media Is Built

The committed media under `htmltests/bug_tests/bug2049301/` starts from three
normal muxed test clips:

- `h264.mp4`: H.264 video + AAC audio
- `vp9.webm`: VP9 video + Opus audio
- `av1.mp4`: AV1 video + AAC audio

`make-media.sh` then creates fragmented/split inputs for MSE:

- `mse-h264-video.mp4`: H.264 video-only fragmented MP4
- `mse-av1-video.mp4`: AV1 video-only fragmented MP4
- `mse-vp9-video.webm`: VP9 video-only WebM
- `mse-aac-audio.mp4`: AAC audio-only fragmented MP4
- `mse-opus-audio.webm`: Opus audio-only WebM

The page glues audio and video together in the browser, not by remuxing a new
file. For the MSE path it:

1. Creates one `MediaSource`.
2. Sets `video.src = URL.createObjectURL(mediaSource)`.
3. Waits for `sourceopen`.
4. Adds one video `SourceBuffer` with a video MIME/codec string.
5. Adds one audio `SourceBuffer` with an audio MIME/codec string.
6. Fetches the split video and audio files as `ArrayBuffer`s.
7. Calls `appendBuffer()` on both SourceBuffers.
8. Calls `mediaSource.endOfStream()` once both appends finish.

That mirrors the important shape of an adaptive site like YouTube: video and
audio arrive as separate tracks, then the player attaches them to one media
element through MSE.

Every local metric is measured from the same baseline:

```js
const t0 = performance.now();
video.currentTime = target;
```

The raw row fields are:

- `seekedMs`: `currentTime = target` to the `seeked` event.
- `firstFrameAfterTargetMs`: `currentTime = target` to the first
  `requestVideoFrameCallback` whose `mediaTime` is at/after the target for
  forward seeks or at/before the target for backward seeks.
- `futureDataMs`: `currentTime = target` to the first observed poll/event where
  `!video.seeking && video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA`.
- `playingMs`: `currentTime = target` to the `playing` event, when one fires.
  This is recorded but not used as the main resume signal because a seek during
  already-playing playback may not produce a clean new `playing` event.
- `resumedMs`: `currentTime = target` to the first observed poll where the
  element is not paused, not seeking, has `readyState >= HAVE_FUTURE_DATA`, and
  `currentTime` has advanced at least 20 ms past the seek target. This is the
  closest native proxy in the harness for "video + audio playback started moving
  again."
- `waitingMs`: `currentTime = target` to the first `waiting` event. This is
  waiting onset, not waiting duration.

The summary rows report medians for each codec, pipeline, playback mode, and
seek direction. For the current split-MSE report, each checked-in JSON file has
72 raw rows: 3 codecs x 2 directions x 12 iterations.

## Report

- `reports/audio-seek-readiness.md`: consolidated results and interpretation.
- `reports/bug2049301-split-mse-report.md`: latest split-MSE local report,
  including `futureDataMs` and `resumedMs`.
- `data/`: raw JSON for the report tables.
- `harness/`: optional Selenium harnesses used to collect the checked-in data.
- `htmltests/bug_tests/bug2049301/`: upstream Bug 2049301-style harness plus
  generated media.
- `media/av-sync-h264-aac.mp4`: older generated H.264/AAC control clip.

## YouTube Spinner Metrics

`harness/youtube_spinner_harness.py` injects a small measurement payload into
the actual YouTube page. It is deliberately separate from the local harness: the
local harness isolates browser media readiness, while the YouTube harness tests
whether YouTube's visible loading spinner appears during real page seeks.

The YouTube harness records:

- `firstFrameAfterTargetMs`: seek command to the first target frame observed by
  `requestVideoFrameCallback`.
- `playableEnoughMs`: seek command to the first sampled state where
  `!video.seeking && video.readyState >= 3`.
- `seekedMs`: seek command to the `seeked` event.
- `waitingMs`: seek command to the first `waiting` event.
- `spinnerEver`: whether a visible YouTube spinner DOM node was seen in any
  sample.
- `spinnerVisibleMs`: number of spinner-visible samples multiplied by the
  sampling interval.
- `spinnerMaxContiguousMs`: longest continuous spinner-visible run.
- `spinnerFirstMs` / `spinnerLastMs`: first and last sampled spinner visibility
  timestamps.
- `spinnerAfterFirstFrameMs`: spinner-visible time after the target frame was
  already reported by `requestVideoFrameCallback`.
- `minReadyState`: lowest sampled media `readyState` during the measurement
  window.

The YouTube spinner metrics answer a different question from the local metrics:
"did the real page show a loading spinner, and for how long?" They should not be
used as a clean browser-media benchmark because YouTube can vary codecs,
resolution, buffering, ads, UI state, and player behavior between browsers.

## Rerun The Selenium Harnesses

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Local split-MSE audio/video test:

```sh
.venv/bin/python harness/local_audio_seek_harness.py \
  --browser firefox \
  --label firefox-nightly-split-mse-audible \
  --iterations 12

.venv/bin/python harness/local_audio_seek_harness.py \
  --browser firefox \
  --label firefox-nightly-split-mse-muted \
  --iterations 12 \
  --muted

.venv/bin/python harness/local_audio_seek_harness.py \
  --browser chrome \
  --label chrome-split-mse-audible \
  --iterations 12

.venv/bin/python harness/local_audio_seek_harness.py \
  --browser chrome \
  --label chrome-split-mse-muted \
  --iterations 12 \
  --muted
```

YouTube visible/audible spinner test:

```sh
YOUTUBE_URL='https://www.youtube.com/watch?v=hF8swzNR1-o' \
.venv/bin/python harness/youtube_spinner_harness.py \
  --browser firefox \
  --label firefox-nightly-hF8-audible-visible-playable \
  --iterations 20 \
  --native \
  --audible

YOUTUBE_URL='https://www.youtube.com/watch?v=hF8swzNR1-o' \
.venv/bin/python harness/youtube_spinner_harness.py \
  --browser chrome \
  --label chrome-hF8-audible-visible-playable \
  --iterations 20 \
  --native \
  --audible
```

Set `FIREFOX_BINARY`, `CHROME_BINARY`, or `GECKODRIVER` if your local paths are
not discoverable from `PATH`.
