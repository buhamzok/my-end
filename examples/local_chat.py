"""Talk to the harness in the terminal, backed by a local Ollama model.

    ollama pull qwen3:8b
    python examples/local_chat.py                 # type what the caller says
    python examples/local_chat.py --model gemma3:12b --omit-think

Empty line or Ctrl+C = caller hangs up. Prints per-turn latency and the ticket.
"""

from __future__ import annotations

import argparse
import json
import time

from triage import IntakeSession
from triage.adapters import OllamaClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument(
        "--omit-think",
        action="store_true",
        help="don't send think=false (for models without a thinking mode that reject it)",
    )
    args = parser.parse_args()

    llm = OllamaClient(args.model, args.host, think=None if args.omit_think else False)
    session = IntakeSession(llm)
    print(f"AGENT : {session.opening_line()}")
    try:
        while True:
            text = input("CALLER: ").strip()
            if not text:
                break
            start = time.perf_counter()
            result = session.handle_utterance(text)
            elapsed = time.perf_counter() - start
            print(f"AGENT : {result.reply_text}   [{elapsed:.2f}s]")
            if result.done:
                break
    except (KeyboardInterrupt, EOFError):
        print()
    print("TICKET:", json.dumps(session.finalize().to_dict(), indent=2))


if __name__ == "__main__":
    main()
