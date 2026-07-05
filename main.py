"""Nova entry point.

    python main.py            # text REPL (the brain + hands) — always available
    python main.py --serve    # browser voice UI (Chromebook-friendly): open in Chrome
    python main.py --voice    # native push-to-talk (needs PortAudio mic + speakers)

Every mode wraps the SAME core Agent; the text REPL is never replaced — it's the
permanent debug path and fallback.
"""
import sys


def main() -> None:
    args = sys.argv[1:]
    if "--serve" in args:
        from voice.webserver import build_and_serve
        build_and_serve()
    elif "--voice" in args:
        from voice.cli import main as voice_main
        voice_main()
    else:
        from core.cli import main as text_main
        text_main()


if __name__ == "__main__":
    main()
