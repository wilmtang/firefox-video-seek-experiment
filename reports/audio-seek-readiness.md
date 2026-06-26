# Audio Seek Readiness Results

## Finding

Firefox Nightly's remaining seek problem is not simply "the target video frame is late."

In the visible YouTube run, Firefox Nightly reached the first target video frame in
roughly 36-42 ms, but YouTube's loading spinner stayed visible for roughly
208-240 ms on almost every seek. Chrome showed no spinner in the same test.

The local H.264/AAC control test removes YouTube, network, ads, and adaptive
streaming. There, Firefox Nightly was close to Chrome when muted, but about 2x
slower when audible. That points toward post-seek audible media readiness:
audio sink preroll, A/V clock synchronization, or Firefox media event/readiness
state after a seek.

## Browser Versions

| Browser | Version | Notes |
|---|---:|---|
| Firefox Nightly | 154.0a1 | Fresh Selenium/WebDriver session |
| Chrome | 149.0.7827.156 | Fresh Selenium/WebDriver session |

## Local H.264/AAC Control

The local test clip is generated media:

- Video: H.264 High, 640x360, 30 fps, 60 s
- Audio: AAC, 48 kHz, mono, 60 s
- Seek pattern: buffered `currentTime = target`, +10 s and -10 s
- Rows show medians across 20 runs per direction

### First Target Video Frame

Measured with `requestVideoFrameCallback()`. Lower is better.

| Direction | Firefox audible | Firefox muted | Chrome audible |
|---:|---:|---:|---:|
| +10 | 66.0 ms | 32.5 ms | 33.1 ms |
| -10 | 66.0 ms | 33.0 ms | 27.7 ms |

### Playable Enough For Continued Playback

First sampled moment where the media element was no longer seeking and
`readyState >= HAVE_FUTURE_DATA` (`3`). Lower is better.

| Direction | Firefox audible | Firefox muted | Chrome audible |
|---:|---:|---:|---:|
| +10 | 62.0 ms | 29.5 ms | 25.2 ms |
| -10 | 62.5 ms | 28.5 ms | 25.1 ms |

### Media Events

| Direction | Browser/audio | `seeked` | `waiting` |
|---:|---|---:|---:|
| +10 | Firefox audible | 58.0 ms | 32.0 ms |
| -10 | Firefox audible | 56.5 ms | 32.0 ms |
| +10 | Firefox muted | 25.5 ms | 1.0 ms |
| -10 | Firefox muted | 26.0 ms | 1.0 ms |
| +10 | Chrome audible | 22.9 ms | 0.4 ms |
| -10 | Chrome audible | 20.8 ms | 0.3 ms |

This is the cleanest signal in the repository: muting Firefox Nightly makes its
seek readiness close to Chrome, while audible Firefox remains substantially
slower.

## YouTube Visible Audible Test

Video:

```text
https://www.youtube.com/watch?v=hF8swzNR1-o
```

YouTube selected different AV1 representations:

| Browser | Stream reported by YouTube |
|---|---|
| Firefox Nightly | `av01.0.05M.08 (398) / opus (251)`, `1280x720@30 / 1920x1080@30` |
| Chrome | `av01.0.08M.08 (399) / opus (251)`, `640x360@30 / 1920x1080@30` |

Rows show medians across 20 runs per method/direction.

### First Target Video Frame

| Method | Direction | Firefox Nightly | Chrome |
|---|---:|---:|---:|
| `currentTime` | +10 | 35.5 ms | 15.6 ms |
| `currentTime` | -10 | 36.5 ms | 13.0 ms |
| YouTube native arrows | +10-ish | 36.5 ms | 30.1 ms |
| YouTube native arrows | -10-ish | 42.0 ms | 12.0 ms |

### Playable Enough

| Method | Direction | Firefox Nightly | Chrome |
|---|---:|---:|---:|
| `currentTime` | +10 | 36.0 ms | 17.1 ms |
| `currentTime` | -10 | 44.0 ms | 16.6 ms |
| YouTube native arrows | +10-ish | 37.0 ms | 32.8 ms |
| YouTube native arrows | -10-ish | 49.0 ms | 32.8 ms |

### YouTube Spinner

| Method | Direction | Firefox spinner runs | Firefox spinner visible | Chrome spinner runs | Chrome spinner visible |
|---|---:|---:|---:|---:|---:|
| `currentTime` | +10 | 19/20 | 224 ms | 0/20 | 0 ms |
| `currentTime` | -10 | 18/20 | 240 ms | 0/20 | 0 ms |
| YouTube native arrows | +10-ish | 20/20 | 224 ms | 0/20 | 0 ms |
| YouTube native arrows | -10-ish | 20/20 | 208 ms | 0/20 | 0 ms |

The spinner outlives Firefox's first target frame by a wide margin. That makes
the visible symptom look more like a short buffering/readiness state that
YouTube turns into UI, not pure video-frame decode latency.

## Relation To Bug 2049301

Bug 2049301's landed patches are video-seek optimizations: preserving a seek
decode threshold, pipelining macOS post-seek video re-decode, and skipping image
surface production for dropped video frames during seek skip.

Those changes can fix the old "first video frame after seek is slow" path while
leaving an audible media readiness issue. Audio does not have the same
keyframe-to-target image-output problem; the likely area is the audio sink,
audio preroll, A/V clock readiness, or how those states surface as `waiting` /
readiness events after a seek.

## Raw Data

- `data/local-audio-seek-firefox-nightly-local-audio-audible.json`
- `data/local-audio-seek-firefox-nightly-local-audio-muted.json`
- `data/local-audio-seek-chrome-local-audio-audible.json`
- `data/youtube-spinner-firefox-nightly-hF8-audible-visible-playable.json`
- `data/youtube-spinner-chrome-hF8-audible-visible-playable.json`
