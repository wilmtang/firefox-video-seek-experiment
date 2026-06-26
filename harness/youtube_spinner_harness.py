import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data"
OUT_DIR.mkdir(exist_ok=True)

YOUTUBE_URL = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
GECKODRIVER = os.environ.get("GECKODRIVER", "geckodriver")

JS = r"""
(() => {
  if (window.__spinnerHarness) return true;

  const ranges = (r) => Array.from({ length: r.length }, (_, i) => [r.start(i), r.end(i)]);
  const visible = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return cs.display !== "none" && cs.visibility !== "hidden" &&
      Number(cs.opacity || 1) > 0.01 && rect.width > 4 && rect.height > 4;
  };
  const spinnerVisible = () => {
    const player = document.querySelector("#movie_player");
    if (player?.classList?.contains("ytp-spinner")) return true;
    return Array.from(document.querySelectorAll(".ytp-spinner, .ytp-spinner-container, .ytp-spinner-rotator"))
      .some(visible);
  };
  const video = () => Array.from(document.querySelectorAll("video"))
    .sort((a, b) => (b.videoWidth * b.videoHeight) - (a.videoWidth * a.videoHeight))[0] || null;

  window.__spinnerHarness = {
    adState() {
      const player = document.querySelector("#movie_player");
      const skipButton = document.querySelector(".ytp-ad-skip-button-modern, .ytp-ad-skip-button, .ytp-skip-ad-button");
      return {
        showing: !!player?.classList?.contains("ad-showing"),
        skipVisible: visible(skipButton),
      };
    },
    skipAd() {
      const skipButton = document.querySelector(".ytp-ad-skip-button-modern, .ytp-ad-skip-button, .ytp-skip-ad-button");
      if (visible(skipButton)) {
        skipButton.click();
        return true;
      }
      return false;
    },
    meta() {
      const v = video();
      const yt = document.querySelector("#movie_player");
      let stats = null;
      try { stats = yt?.getStatsForNerds?.(); } catch (e) {}
      return {
        title: document.title,
        url: location.href,
        userAgent: navigator.userAgent,
        hasVideo: !!v,
        currentTime: v?.currentTime ?? null,
        duration: v?.duration ?? null,
        readyState: v?.readyState ?? null,
        paused: v?.paused ?? null,
        videoWidth: v?.videoWidth ?? null,
        videoHeight: v?.videoHeight ?? null,
        buffered: v ? ranges(v.buffered) : [],
        spinnerVisible: spinnerVisible(),
        ytStatsForNerds: stats,
        playbackQuality: v?.getVideoPlaybackQuality?.() || null,
      };
    },
    prepare(start, muted = true) {
      const v = video();
      if (!v) throw new Error("no video");
      v.muted = muted;
      v.volume = muted ? 0 : 1;
      v.playsInline = true;
      try { v.play(); } catch (e) {}
      if (Math.abs(v.currentTime - start) > 0.5) v.currentTime = start;
      return true;
    },
    async measure({ delta = 10, sampleMs = 16, windowMs = 1800, method = "currentTime" }) {
      const v = video();
      if (!v) throw new Error("no video");

      const startedAt = performance.now();
      const startTime = v.currentTime;
      const target = startTime + delta;
      const events = [];
      const samples = [];
      let firstFrameAfterTarget = null;
      let doneResolve;

      const eventNames = ["seeking", "seeked", "waiting", "playing", "canplay", "stalled", "timeupdate"];
      const onEvent = (type) => events.push({
        type,
        t: performance.now() - startedAt,
        currentTime: v.currentTime,
        readyState: v.readyState,
        seeking: v.seeking,
      });
      const listeners = eventNames.map((name) => {
        const fn = () => onEvent(name);
        v.addEventListener(name, fn, true);
        return [name, fn];
      });

      if (typeof v.requestVideoFrameCallback === "function") {
        const loop = (_now, md) => {
          if (!firstFrameAfterTarget && md.mediaTime >= target - 0.05) {
            firstFrameAfterTarget = {
              t: performance.now() - startedAt,
              mediaTime: md.mediaTime,
              presentedFrames: md.presentedFrames,
            };
          }
          if (!doneResolve) v.requestVideoFrameCallback(loop);
        };
        v.requestVideoFrameCallback(loop);
      }

      const interval = setInterval(() => {
        samples.push({
          t: performance.now() - startedAt,
          spinner: spinnerVisible(),
          currentTime: v.currentTime,
          readyState: v.readyState,
          seeking: v.seeking,
        });
      }, sampleMs);

      onEvent("before-seek");
      if (method === "currentTime") {
        v.currentTime = target;
      } else {
        // Native key modes are triggered from Selenium after this async task starts.
      }

      await new Promise((resolve) => {
        doneResolve = resolve;
        setTimeout(resolve, windowMs);
      });
      clearInterval(interval);
      doneResolve = null;
      for (const [name, fn] of listeners) v.removeEventListener(name, fn, true);

      const spinnerSamples = samples.filter(s => s.spinner);
      const playableSample = samples.find(s => !s.seeking && s.readyState >= 3);
      let maxRun = 0;
      let currentRun = 0;
      for (const sample of samples) {
        if (sample.spinner) {
          currentRun += sampleMs;
          maxRun = Math.max(maxRun, currentRun);
        } else {
          currentRun = 0;
        }
      }
      const eventTime = (name) => events.find(e => e.type === name)?.t ?? null;
      const firstFrameMs = firstFrameAfterTarget?.t ?? null;
      return {
        method,
        delta,
        startTime,
        target,
        endTime: v.currentTime,
        actualDelta: v.currentTime - startTime,
        firstFrameAfterTargetMs: firstFrameMs,
        playableEnoughMs: playableSample?.t ?? null,
        seekedMs: eventTime("seeked"),
        waitingMs: eventTime("waiting"),
        canplayMs: eventTime("canplay"),
        spinnerEver: spinnerSamples.length > 0,
        spinnerVisibleMs: spinnerSamples.length * sampleMs,
        spinnerMaxContiguousMs: maxRun,
        spinnerFirstMs: spinnerSamples[0]?.t ?? null,
        spinnerLastMs: spinnerSamples.at(-1)?.t ?? null,
        spinnerAfterFirstFrameMs: firstFrameMs == null ? null :
          samples.filter(s => s.spinner && s.t >= firstFrameMs).length * sampleMs,
        minReadyState: samples.reduce((m, s) => Math.min(m, s.readyState), v.readyState),
        events,
      };
    },
  };
  return true;
})();
"""


def driver_for(browser, headless=False, muted=True):
    if browser == "chrome":
        opts = ChromeOptions()
        opts.binary_location = os.environ.get("CHROME_BINARY", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--autoplay-policy=no-user-gesture-required")
        if muted:
            opts.add_argument("--mute-audio")
        opts.add_argument("--no-first-run")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--window-size=1280,900")
        return webdriver.Chrome(options=opts)

    opts = FirefoxOptions()
    opts.binary_location = os.environ.get("FIREFOX_BINARY", "/Applications/Firefox Nightly.app/Contents/MacOS/firefox")
    opts.add_argument("-profile")
    opts.add_argument(tempfile.mkdtemp(prefix="seek-spinner-firefox-"))
    if headless:
        opts.add_argument("-headless")
    opts.set_preference("media.autoplay.default", 0)
    opts.set_preference("media.autoplay.blocking_policy", 0)
    opts.set_preference("permissions.default.desktop-notification", 2)
    opts.set_preference("dom.webnotifications.enabled", False)
    driver = webdriver.Firefox(service=FirefoxService(GECKODRIVER), options=opts)
    driver.set_window_size(1280, 900)
    return driver


def execute(driver, script, *args):
    return driver.execute_script(script, *args)


def install(driver):
    execute(driver, "return " + JS.strip())
    if not execute(driver, "return !!window.__spinnerHarness?.prepare;"):
        raise RuntimeError("spinner harness did not install")


def wait_out_ads(driver, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        install(driver)
        state = execute(driver, "window.__spinnerHarness.skipAd(); return window.__spinnerHarness.adState();")
        if not state.get("showing"):
            return
        time.sleep(0.25)
    raise RuntimeError("YouTube ad did not finish or become skippable")


def wait_for_video(driver):
    WebDriverWait(driver, 45).until(lambda d: execute(d, """
      const v = Array.from(document.querySelectorAll('video'))[0];
      return !!v && Number.isFinite(v.duration) && v.duration > 20 && v.readyState >= 1;
    """))
    install(driver)
    wait_out_ads(driver)


def prepare(driver, start, muted=True):
    deadline = time.time() + 4
    last_error = None
    while time.time() < deadline:
        try:
            install(driver)
            wait_out_ads(driver, timeout=10)
            execute(driver, "return window.__spinnerHarness.prepare(arguments[0], arguments[1]);", start, muted)
            meta = execute(driver, "return window.__spinnerHarness.meta();")
            if abs((meta.get("currentTime") or 0) - start) < 1.0 and meta.get("readyState", 0) >= 2:
                return meta
        except JavascriptException as e:
            last_error = e
        time.sleep(0.05)
    if last_error:
        raise last_error
    return execute(driver, "return window.__spinnerHarness.meta();")


def one(driver, method, delta, start, sample_ms, window_ms, muted=True):
    prepare(driver, start, muted=muted)
    if method == "currentTime":
        return execute(driver, "return window.__spinnerHarness.measure(arguments[0]);", {
            "method": method, "delta": delta, "sampleMs": sample_ms, "windowMs": window_ms
        })

    promise = execute(driver, """
      window.__lastSpinnerPromise = window.__spinnerHarness.measure(arguments[0]);
      return true;
    """, {"method": method, "delta": delta, "sampleMs": sample_ms, "windowMs": window_ms})
    del promise
    key = "\ue014" if delta > 0 else "\ue012"
    ActionChains(driver).send_keys(key).send_keys(key).perform()
    return execute(driver, "return window.__lastSpinnerPromise;")


def median(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(values) if values else None


def summarize(results):
    out = {}
    for row in results:
        key = (row["method"], row["direction"])
        out.setdefault(key, []).append(row)
    return [{
        "method": method,
        "direction": direction,
        "n": len(rows),
        "spinnerCount": sum(1 for r in rows if r.get("spinnerEver")),
        "medianSpinnerVisibleMs": median([r.get("spinnerVisibleMs") for r in rows]),
        "medianSpinnerMaxContiguousMs": median([r.get("spinnerMaxContiguousMs") for r in rows]),
        "medianSpinnerAfterFirstFrameMs": median([r.get("spinnerAfterFirstFrameMs") for r in rows]),
        "medianFirstFrameAfterTargetMs": median([r.get("firstFrameAfterTargetMs") for r in rows]),
        "medianPlayableEnoughMs": median([r.get("playableEnoughMs") for r in rows]),
        "medianSeekedMs": median([r.get("seekedMs") for r in rows]),
        "medianWaitingMs": median([r.get("waitingMs") for r in rows]),
    } for (method, direction), rows in sorted(out.items())]


def run(args):
    label = args.label or args.browser
    muted = not args.audible
    driver = driver_for(args.browser, headless=args.headless, muted=muted)
    raw = {
        "browser": label,
        "url": YOUTUBE_URL,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": [],
    }
    try:
        driver.get(YOUTUBE_URL)
        wait_for_video(driver)
        raw["muted"] = muted
        raw["meta"] = prepare(driver, 5, muted=muted)
        methods = [("currentTime", 10, "+10", 5), ("currentTime", -10, "-10", 15)]
        if args.native:
            methods += [("native-arrow-rightx2", 10, "+10-ish", 5), ("native-arrow-leftx2", -10, "-10-ish", 15)]
        for method, delta, direction, start in methods:
            for i in range(args.iterations):
                try:
                    row = one(driver, method, delta, start, args.sample_ms, args.window_ms, muted=muted)
                    row.update({"browser": label, "browserVersion": driver.capabilities.get("browserVersion"),
                                "method": method, "direction": direction, "iteration": i + 1})
                except Exception as e:
                    row = {"browser": label, "method": method, "direction": direction,
                           "iteration": i + 1, "error": f"{type(e).__name__}: {e}"}
                raw["results"].append(row)
                print(f"{label} {method} {direction} {i + 1}/{args.iterations}")
                sys.stdout.flush()
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass

    raw["summaries"] = summarize(raw["results"])
    out = OUT_DIR / f"youtube-spinner-{label}.json"
    out.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["firefox", "chrome"], required=True)
    parser.add_argument("--label")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--native", action="store_true", help="Also measure YouTube native arrow-key seek.")
    parser.add_argument("--sample-ms", type=int, default=16)
    parser.add_argument("--window-ms", type=int, default=1800)
    parser.add_argument("--headless", action="store_true", help="Run without opening foreground browser windows.")
    parser.add_argument("--audible", action="store_true", help="Do not mute the video during measurement.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
