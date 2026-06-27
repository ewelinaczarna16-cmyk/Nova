"""Nova entry point.

    python main.py            # text REPL (the brain + hands) — always available
    python main.py --voice    # push-to-talk voice (laptop: needs mic/speakers + keys)

Voice wraps the SAME core Agent; the text REPL is never replaced — it's the
permanent debug path and fallback.
"""
import sys


def main() -> None:
    if "--voice" in sys.argv[1:]:
        from voice.cli import main as voice_main
        voice_main()
    else:
        from core.cli import main as text_main
        text_main()


if __name__ == "__main__":
    main()
