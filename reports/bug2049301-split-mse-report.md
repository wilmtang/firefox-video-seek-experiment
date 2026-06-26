# Bug 2049301 Split-MSE Audio Seek Report

Date: 2026-06-26

## Scope

This run tests the local Bug 2049301-style harness in the YouTube-like path only:
MediaSource with separate video and audio SourceBuffers.

Dormant seeks were not run. Progressive `src` playback was not included in the
automated comparison because the question here is the split audio/video pipeline.

## Environment

- macOS 15.7.7 (24G720)
- Chrome 149.0.7827.201
- Firefox Nightly 154.0a1
- geckodriver 0.37.0
- Harness: `htmltests/bug_tests/bug2049301/seek-test.html`
- Iterations: 12 playback seeks per codec and direction
- Matrix: browser x audible/muted x codec x +10/-10 seek

## Commands

```sh
python3 harness/local_audio_seek_harness.py \
  --browser chrome \
  --iterations 12 \
  --label chrome-split-mse-audible

python3 harness/local_audio_seek_harness.py \
  --browser chrome \
  --iterations 12 \
  --muted \
  --label chrome-split-mse-muted

GECKODRIVER=/opt/homebrew/bin/geckodriver \
python3 harness/local_audio_seek_harness.py \
  --browser firefox \
  --iterations 12 \
  --label firefox-nightly-split-mse-audible

GECKODRIVER=/opt/homebrew/bin/geckodriver \
python3 harness/local_audio_seek_harness.py \
  --browser firefox \
  --iterations 12 \
  --muted \
  --label firefox-nightly-split-mse-muted
```

## Raw Data

- `data/local-audio-seek-chrome-split-mse-audible.json`
- `data/local-audio-seek-chrome-split-mse-muted.json`
- `data/local-audio-seek-firefox-nightly-split-mse-audible.json`
- `data/local-audio-seek-firefox-nightly-split-mse-muted.json`

Each file contains 72 raw rows: 3 codecs x 2 seek directions x 12 iterations.
No codec or MSE pipeline was reported unsupported.

## Metrics

- `firstFrame`: seek command to first target video frame reported by
  `requestVideoFrameCallback`.
- `futureData`: seek command to `readyState >= HAVE_FUTURE_DATA` while not
  seeking.
- `resumed`: seek command to the first poll where the media element is not
  paused, not seeking, has `readyState >= HAVE_FUTURE_DATA`, and `currentTime`
  has advanced at least 20 ms past the seek target.
- `waiting`: seek command to the first `waiting` event. This is waiting onset,
  not waiting duration.

`resumed` is the closest metric in this harness to "the video+audio playback
started moving again." It still cannot prove sound reached the speakers; doing
that from JS would require routing through Web Audio, which would alter the
pipeline under test.

## Results

Values below average the +10 and -10 medians for each codec.

First frame ms:

| Codec | Chrome audible | Chrome muted | Firefox Nightly audible | Firefox Nightly muted |
|---|---:|---:|---:|---:|
| H.264/AAC | 16.6 | 15.9 | 64.0 | 22.0 |
| VP9/Opus | 36.4 | 31.2 | 77.0 | 32.0 |
| AV1/Opus | 19.9 | 19.7 | 66.8 | 24.8 |

Future data ms:

| Codec | Chrome audible | Chrome muted | Firefox Nightly audible | Firefox Nightly muted |
|---|---:|---:|---:|---:|
| H.264/AAC | 16.3 | 15.3 | 64.0 | 20.0 |
| VP9/Opus | 31.8 | 29.9 | 77.0 | 31.8 |
| AV1/Opus | 21.1 | 19.5 | 67.0 | 22.0 |

Resumed ms:

| Codec | Chrome audible | Chrome muted | Firefox Nightly audible | Firefox Nightly muted |
|---|---:|---:|---:|---:|
| H.264/AAC | 83.7 | 47.1 | 161.0 | 68.0 |
| VP9/Opus | 91.1 | 63.0 | 178.2 | 82.5 |
| AV1/Opus | 80.9 | 41.3 | 166.0 | 72.2 |

Waiting onset ms:

| Codec | Chrome audible | Chrome muted | Firefox Nightly audible | Firefox Nightly muted |
|---|---:|---:|---:|---:|
| H.264/AAC | 0.2 | 0.2 | 44.0 | 1.0 |
| VP9/Opus | 0.2 | 0.2 | 46.0 | 0.5 |
| AV1/Opus | 0.2 | 0.2 | 46.5 | 0.0 |

Overall split-MSE means across all codecs and directions:

| Metric | Chrome audible | Chrome muted | Firefox Nightly audible | Firefox Nightly muted |
|---|---:|---:|---:|---:|
| First frame ms | 24.3 | 22.3 | 69.2 | 26.2 |
| Future data ms | 23.1 | 21.6 | 69.3 | 24.6 |
| Resumed ms | 85.2 | 50.5 | 168.4 | 74.2 |
| Waiting onset ms | 0.2 | 0.2 | 45.5 | 0.5 |

## Future Data To Resumed Gap

The gap between `futureData` and `resumed` means the media element has reported
that it is no longer seeking and has at least near-future data, but the playback
timeline has not yet advanced 20 ms past the seek target.

Overall gaps in this run:

| Condition | Future data ms | Resumed ms | Gap ms |
|---|---:|---:|---:|
| Chrome audible | 23.1 | 85.2 | 62.1 |
| Chrome muted | 21.6 | 50.5 | 28.9 |
| Firefox Nightly audible | 69.3 | 168.4 | 99.1 |
| Firefox Nightly muted | 24.6 | 74.2 | 49.6 |

Some of this gap is expected. The harness waits for real timeline advancement,
and media does not advance continuously at infinite precision; frame cadence,
polling granularity, and scheduling all add time. At 30 fps, one frame is about
33 ms.

The larger Firefox Nightly audible gap is the interesting signal. After
`HAVE_FUTURE_DATA`, the browser may still be restarting the playback clock,
prerolling audio into the output sink, aligning audio/video clocks, refilling
decoder queues, or waiting on media-thread scheduling before allowing the media
timeline to move. This does not prove which internal step is responsible, but it
is consistent with extra audible media pipeline work after the media element
already reports future data.

## Muted Audio Interpretation

Muting the element does not mean the audio track disappears. In this local MSE
test, the audio SourceBuffer is still created and appended when `video.muted =
true`; the media element still sees a combined audio/video resource.

The muted control is useful because it keeps the audio bytes in the test while
changing the audible output path. If Firefox Nightly muted is much faster than
Firefox Nightly audible with the same split audio buffer present, the result is
less consistent with "audio was not loaded" and more consistent with audible
audio output work being on the critical path: audio sink startup/preroll,
audio-clock restart, or A/V sync policy before allowing playback to resume.

In this run, Firefox Nightly muted reached the `resumed` proxy at 74.2 ms while
Firefox Nightly audible reached it at 168.4 ms. That gap is the main reason the
audio-output interpretation is plausible.

## Firefox Profiler Captures

Planned capture target: one codec through the split-MSE path, using Firefox
Nightly's Media profiler preset equivalent:

- features: `js,stackwalk,cpu,audiocallbacktracing,ipcmessages,processcpu,memory`
- thread filters include: `GeckoMain`, `Compositor`, `Renderer`, `AudioIPC`,
  `MediaDecoderStateMachine`, `MediaPlayback`, `MediaTimer`, `media`, `audio`,
  `cubeb`, `decoder`, and related media threads.

Capture URLs will be added here after the GitHub Pages version is published and
the audible/muted profiles are collected.

## Findings

1. Firefox Nightly audible split-MSE seeking is materially slower than Firefox
   Nightly muted seeking. Overall first-frame latency rises from 26.2 ms muted
   to 69.2 ms audible, and the playback-resumed proxy rises from 74.2 ms to
   168.4 ms.

2. Chrome does not show the same first-frame/future-data audio penalty. Chrome
   first-frame latency is 22.3 ms muted vs 24.3 ms audible. The stricter
   resumed metric is higher audible than muted, but remains far below Firefox
   Nightly audible.

3. Firefox Nightly audible also emits a delayed `waiting` signal around 45-48 ms
   for every codec. Firefox muted and Chrome audible/muted are near zero.

4. The effect appears codec-independent in Firefox Nightly audible. H.264, VP9,
   and AV1 all show the same broad class of delay, with VP9 slowest in this run.

## Caveats

- This is not a YouTube spinner test. It tests local media readiness in a
  YouTube-like split audio/video MSE pipeline.
- The observed Firefox audible penalty is around 40-45 ms above muted for
  first-frame/future-data readiness and around 94 ms above muted for the
  playback-resumed proxy. The resumed value is closer to a user-perceived
  "playback continues" metric, but it is still not direct speaker-output proof.
- All four JSON files have 72 raw rows, no unsupported MSE entries, and no null
  `futureDataMs` or `resumedMs` rows.
- The page still supports progressive `src` manually, but the automated harness
  was narrowed to MSE-only for this report.

## Conclusion

This run supports the audio-latency hypothesis for Firefox Nightly. Audible
split-MSE seeks are consistently slower than muted split-MSE seeks and slower
than Chrome. Using the user-facing playback-resumed proxy, Firefox Nightly
audible reaches about 168 ms overall, which is much closer to a visible spinner
threshold than the first-frame-only metric, though still below 200 ms in this
run.
