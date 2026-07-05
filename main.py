"""Nova entry point.

    python main.py             # text REPL (the brain + hands) — always available
    python main.py --serve     # browser voice UI (Chromebook-friendly): open in Chrome
    python main.py --voice     # native push-to-talk (needs PortAudio mic + speakers)
    python main.py --heartbeat # run the background heartbeat loop (Tier 5)
    python main.py --digest-now # send today's digest once, right now (verify the channel)

Every mode wraps the SAME core Agent / tools; the text REPL is never replaced — it's
the permanent debug path and fallback.
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
    elif "--heartbeat" in args or "--digest-now" in args:
        import config
        from heartbeat.scheduler import build_from_config
        from tools import ToolRegistry
        from tools.builtin import register_builtin_tools
        registry = ToolRegistry()
        register_builtin_tools(registry)
        hb = build_from_config(tools=registry)
        if "--digest-now" in args:
            hb.trigger("daily_digest")     # fire once, respecting quiet hours
        else:
            hb.run_forever(tick_seconds=config.get("heartbeat", "tick_seconds", default=30))
    else:
        from core.cli import main as text_main
        text_main()


if __name__ == "__main__":
    main()
