"""Nova entry point. For now: the text REPL (the brain + hands).

    python main.py

Voice, memory, and heartbeat tiers add their own entry points / flags later, all
wrapping the same core Agent.
"""
from core.cli import main

if __name__ == "__main__":
    main()
