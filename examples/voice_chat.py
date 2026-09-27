"""Speak to the harness through the laptop mic, before the phone line exists.

    mic -> faster-whisper (GPU) -> IntakeSession + local Ollama model -> spoken reply

    pip install -e ".[voice]"
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12     # CUDA libs for faster-whisper
    ollama pull qwen3:8b
    python examples/voice_chat.py                        # English
    python examples/voice_chat.py --language sw          # Swahili
    python examples/voice_chat.py --device cpu --whisper-model small --compute-type int8

Push-to-talk: press Enter to start speaking, Enter again to stop.
Type q then Enter (or Ctrl+C) to hang up. Prints timings and the final ticket.
"""

from __future__ import annotations

import argparse
import json
import os
import time

SAMPLE_RATE = 16_000  # what Whisper expects


def add_cuda_dll_dirs() -> None:
    """Make pip-installed cuBLAS/cuDNN (nvidia-*-cu12 wheels) visible to CTranslate2."""
    for name in ("cublas", "cudnn"):
        try:
            module = __import__(f"nvidia.{name}", fromlist=["_"])
        except ImportError:
            continue
        for base in module.__path__:
            for sub in ("bin", "lib"):
                path = os.path.join(base, sub)
                if os.path.isdir(path):
                    os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                    if hasattr(os, "add_dll_directory"):  # Windows
                        os.add_dll_directory(path)


def record(sd, np):
    """Push-to-talk capture. Returns mono float32 audio, or None to hang up."""
    if input("\n[Enter] to talk, q to hang up: ").strip().lower() == "q":
        return None
    chunks = []

    def callback(indata, frames, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback):
        input("  recording... [Enter] to stop")
    if not chunks:
        return np.zeros(0, dtype="float32")
    return np.concatenate(chunks)[:, 0]


def speak(text: str, enabled: bool) -> None:
    print(f"AGENT : {text}")
    if not enabled:
        return
    import pyttsx3

    engine = pyttsx3.init()  # fresh engine per line avoids a known Windows hang
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--whisper-model", default="large-v3-turbo")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--compute-type", default=None, help="default: float16 on cuda, int8 on cpu")
    parser.add_argument("--language", default="en", help="en, sw, or auto")
    parser.add_argument("--llm-model", default="qwen3:8b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--omit-think", action="store_true")
    parser.add_argument("--no-tts", action="store_true", help="print replies instead of speaking them")
    args = parser.parse_args()

    if args.device == "cuda":
        add_cuda_dll_dirs()
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel

    from triage import IntakeSession
    from triage.adapters import OllamaClient

    compute_type = args.compute_type or ("float16" if args.device == "cuda" else "int8")
    language = None if args.language == "auto" else args.language

    print(f"Loading Whisper {args.whisper_model} on {args.device} ({compute_type})...")
    whisper = WhisperModel(args.whisper_model, device=args.device, compute_type=compute_type)
    list(whisper.transcribe(np.zeros(SAMPLE_RATE, dtype="float32"), language=language or "en")[0])

    def transcribe(audio) -> str:
        segments, _ = whisper.transcribe(
            audio,
            language=language,
            beam_size=1,  # greedy decoding: much faster, little accuracy loss on short turns
            vad_filter=True,  # skip silence at the start and end of the clip
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    llm = OllamaClient(args.llm_model, args.host, think=None if args.omit_think else False)
    session = IntakeSession(llm)
    speak(session.opening_line(), not args.no_tts)

    try:
        while True:
            audio = record(sd, np)
            if audio is None:
                break
            start = time.perf_counter()
            text = transcribe(audio) if audio.size else ""
            stt_seconds = time.perf_counter() - start
            if not text:
                print("  (nothing heard, try again)")
                continue
            print(f"CALLER: {text}")

            start = time.perf_counter()
            result = session.handle_utterance(text)
            llm_seconds = time.perf_counter() - start
            print(f"  [speech-to-text {stt_seconds:.2f}s | harness+LLM {llm_seconds:.2f}s]")
            speak(result.reply_text, not args.no_tts)
            if result.done:
                break
    except (KeyboardInterrupt, EOFError):
        print()
    print("TICKET:", json.dumps(session.finalize().to_dict(), indent=2))


if __name__ == "__main__":
    main()
