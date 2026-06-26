import argparse
import http.server
import json
import socketserver
import statistics
import threading
import time
from functools import partial
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait

from youtube_spinner_harness import OUT_DIR, driver_for


ROOT = Path(__file__).resolve().parents[1]


def median(rows, key):
    values = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    return statistics.median(values) if values else None


def summarize(results):
    out = []
    for direction in sorted({r["direction"] for r in results}):
        rows = [r for r in results if r["direction"] == direction]
        out.append({
            "direction": direction,
            "n": len(rows),
            "medianFirstFrameAfterTargetMs": median(rows, "firstFrameAfterTargetMs"),
            "medianPlayableEnoughMs": median(rows, "playableEnoughMs"),
            "medianSeekedMs": median(rows, "seekedMs"),
            "medianWaitingMs": median(rows, "waitingMs"),
            "medianMinReadyState": median(rows, "minReadyState"),
            "waitingCount": sum(r.get("waitingMs") is not None for r in rows),
        })
    return out


def serve():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run(args):
    server = serve()
    muted = args.muted
    driver = driver_for(args.browser, headless=args.headless, muted=muted)
    driver.set_script_timeout(args.script_timeout)
    label = args.label or f"{args.browser}-local-audio-{'muted' if muted else 'audible'}"
    try:
        driver.get(
            f"http://127.0.0.1:{server.server_address[1]}/"
            "htmltests/bug_tests/audio_seek/seek-test.html"
        )
        WebDriverWait(driver, 30).until(lambda d: d.execute_script("""
          const v = document.querySelector('video');
          return !!window.runAudioSeek && !!v && v.readyState >= 2;
        """))
        result = driver.execute_async_script("""
          const done = arguments[arguments.length - 1];
          window.runAudioSeek(arguments[0]).then(done, (e) => done({ error: String(e) }));
        """, {"muted": muted, "iterations": args.iterations, "sampleMs": args.sample_ms, "windowMs": args.window_ms})
        result.update({
            "browser": label,
            "browserVersion": driver.capabilities.get("browserVersion"),
            "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "muted": muted,
            "summaries": summarize(result.get("results", [])),
        })
    finally:
        driver.quit()
        server.shutdown()

    out = OUT_DIR / f"local-audio-seek-{label}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summaries"], indent=2))
    print(f"Wrote {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["firefox", "chrome"], required=True)
    parser.add_argument("--label")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--sample-ms", type=int, default=8)
    parser.add_argument("--window-ms", type=int, default=1200)
    parser.add_argument("--script-timeout", type=int, default=180)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--muted", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
