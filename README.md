# Firefox Audio Seek Readiness Study

This repository contains a small browser media experiment around post-seek
readiness with audible video.

The motivating observation: after Firefox's Bug 2049301 video-seek fixes,
Firefox Nightly can show the target video frame quickly, but YouTube may still
show a loading spinner during audible seeks. A local H.264/AAC control test
also shows Firefox Nightly behaving much closer to Chrome when muted than when
audible.

## Public Test Page

Open the self-running page and click **Run Test**:

```text
htmltests/bug_tests/audio_seek/seek-test.html
```

The page runs entirely in the browser. It loads the local test clip, runs
audible and muted seek loops, and prints a table plus raw JSON.

## Report

- `reports/audio-seek-readiness.md`: consolidated results and interpretation.
- `data/`: raw JSON for the report tables.
- `harness/`: optional Selenium harnesses used to collect the checked-in data.
- `local-tests/audio-seek-test.html`: local development version of the browser
  test page.
- `media/av-sync-h264-aac.mp4`: generated H.264/AAC test clip.

## Rerun The Selenium Harnesses

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Local audio-control test:

```sh
.venv/bin/python harness/local_audio_seek_harness.py \
  --browser firefox \
  --label firefox-nightly-local-audio-audible \
  --iterations 20

.venv/bin/python harness/local_audio_seek_harness.py \
  --browser firefox \
  --label firefox-nightly-local-audio-muted \
  --iterations 20 \
  --muted

.venv/bin/python harness/local_audio_seek_harness.py \
  --browser chrome \
  --label chrome-local-audio-audible \
  --iterations 20
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
