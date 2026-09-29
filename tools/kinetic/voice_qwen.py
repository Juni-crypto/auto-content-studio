"""House voice: Qwen3-TTS 1.7B CustomVoice "Aiden" (Apache-2.0), creator style.

  ../../.venv-mlxaudio/bin/python voice_qwen.py spec.json OUT_DIR          (Mac: MLX)
  /opt/studio/venvs/qwen/bin/python voice_qwen.py spec.json OUT_DIR        (studio server: PyTorch on CPU, ~5x real time)

The whole script is voiced in ONE pass (natural rhythm across sentences), best of N takes scored by whisper against
the captions (a take that really laughs on "haha" is preferred), then cut into beats at the pauses between them.
spec["voice"] = {"engine": "qwen3", "speaker": "Aiden", "style": "<how to say it>", "takes": 3}
Beats: "tts" (what is said; respell tricky names, e.g. "Tak-shun") + "caption" (what is shown).
Writes OUT_DIR/vo-NN.wav + timing.json ([{n, dur, words:[{w,s,e}], cont: true}]); cont = play beats back to back.
"""
import difflib, json, os, pathlib, subprocess, sys, tempfile, time
import numpy as np, soundfile as sf

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from timing import norm, align

SR = 24000
MODEL_MLX = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16"
MODEL_HF = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
WHISPER = pathlib.Path(os.environ.get("WHISPER_MODEL", "~/.cache/whisper/ggml-base.bin")).expanduser()
FILLERS = ("haha", "hmm", "hmmm", "sooo", "laughs", "laughing", "huh", "ha")


def load_voice():
    """Returns gen(text, voice_spec, seed) -> float32 audio at SR. MLX on Apple Silicon, PyTorch on CPU elsewhere."""
    try:
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model
    except ImportError:
        import torch
        from qwen_tts import Qwen3TTSModel
        torch.set_num_threads(os.cpu_count() or 4)
        m = Qwen3TTSModel.from_pretrained(MODEL_HF, device_map="cpu", dtype=torch.bfloat16)

        def gen(text, v, seed):
            torch.manual_seed(seed)
            wavs, sr = m.generate_custom_voice(text=text, speaker=v.get("speaker", "Aiden"), language="English", instruct=v["style"],
                                               temperature=v.get("temperature", 0.85), top_p=0.95)
            a = np.asarray(wavs[0], dtype=np.float32)
            return a if sr == SR else np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a).astype(np.float32)
        return gen
    m = load_model(MODEL_MLX)

    def gen(text, v, seed):
        mx.random.seed(seed)
        r = list(m.generate(text=text, voice=v.get("speaker", "Aiden"), instruct=v["style"], temperature=v.get("temperature", 0.85),
                            top_p=0.95, lang_code="english"))
        return np.concatenate([np.array(x.audio) for x in r]).astype(np.float32)
    return gen


def heard_words(wav):
    w16 = wav.with_suffix(".16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-ar", "16000", "-ac", "1", w16], check=True)
    subprocess.run(["whisper-cli", "-m", str(WHISPER), "-l", "en", "-f", str(w16), "-ml", "1", "-sow", "-oj", "-of", str(w16.with_suffix(""))],
                   check=True, capture_output=True)
    d = json.loads(w16.with_suffix(".json").read_text()); w16.unlink(); w16.with_suffix(".json").unlink()
    return [(s["text"].strip(), s["offsets"]["from"] / 1000, s["offsets"]["to"] / 1000) for s in d["transcription"] if s["text"].strip()]


def score(caption, heard, want_laugh):
    a = [norm(w) for w in caption.split() if norm(w) and norm(w) not in FILLERS]
    b = [norm(w) for w, _, _ in heard if norm(w) and norm(w) not in FILLERS]
    s = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    laughed = any("laugh" in w.lower() or w.lower().strip(".,!?()") in ("haha", "ha") for w, _, _ in heard)
    return s + (0.06 if (want_laugh and laughed) else 0), laughed


def pace(a, n_words, v):
    """Creator pace: cap long silences at a natural breath, then time-stretch (pitch kept) toward the target words-per-minute."""
    fr = 240; env = np.array([np.abs(a[i:i + fr]).mean() for i in range(0, len(a) - fr, fr)]); quiet = env < 0.012 * env.max()
    keep, k, cap = [], 0, int(v.get("max_pause", 0.32) * SR / fr)
    while k < len(quiet):
        if quiet[k]:
            j = k
            while j < len(quiet) and quiet[j]: j += 1
            run = j - k
            keep.append(a[k * fr: (k + min(run, cap)) * fr]); k = j
        else:
            j = k
            while j < len(quiet) and not quiet[j]: j += 1
            keep.append(a[k * fr: j * fr]); k = j
    a = np.concatenate(keep)
    wpm = n_words / (len(a) / SR / 60); tempo = min(max(v.get("wpm", 175) / wpm, 1.0), v.get("max_tempo", 1.18))
    if tempo > 1.01:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = pathlib.Path(tmp) / "in.wav", pathlib.Path(tmp) / "out.wav"
            sf.write(src, a, SR)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", f"atempo={tempo:.3f}", "-ar", str(SR), dst], check=True)
            a, _ = sf.read(dst, dtype="float32")
    return a.astype(np.float32), wpm, tempo


def split(a, beats, out, note=""):
    caption = " ".join(b["caption"] for b in beats); dur = len(a) / SR
    tmp = out / "full.wav"; sf.write(tmp, a, SR); heard = heard_words(tmp)
    words = align(caption.split(), heard, dur)
    t = 0.0   # monotonic, every word at least 0.12 s, so captions can never collapse or run backwards
    for w in words:
        w["s"] = round(max(w["s"], t), 3); w["e"] = round(max(w["e"], w["s"] + 0.12), 3); t = w["e"]
    if t > dur:
        k = dur / t
        for w in words: w["s"], w["e"] = round(w["s"] * k, 3), round(w["e"] * k, 3)
    counts = [len(b["caption"].split()) for b in beats]; idx = np.cumsum(counts)
    cuts = [0.0]
    for i in range(len(beats) - 1):
        e, s_ = words[idx[i] - 1]["e"], words[idx[i]]["s"]
        cuts.append(max(cuts[-1] + 0.3, (e + s_) / 2 if s_ > e else s_ - 0.03))
    cuts.append(dur); timing = []; w0 = 0
    for i, b in enumerate(beats):
        c0, c1 = cuts[i], cuts[i + 1]
        sf.write(out / f"vo-{i + 1:02d}.wav", a[int(c0 * SR): int(c1 * SR)], SR)
        bw = [{"w": x["w"], "s": round(max(0.0, x["s"] - c0), 3), "e": round(max(0.0, x["e"] - c0), 3)} for x in words[w0: w0 + counts[i]]]
        w0 += counts[i]
        timing.append({"n": i + 1, "dur": round(c1 - c0, 3), "words": bw, "cont": True})
    (out / "timing.json").write_text(json.dumps(timing, indent=1))
    (out / "heard.txt").write_text(" ".join(w for w, _, _ in heard))
    print(f"{out}: {dur:.1f}s, {len(beats)} beats {note}")


def repace(spec_path, out_dir):
    """Re-pace an existing take (the vo-NN.wav files are contiguous) without regenerating it."""
    spec = json.loads(pathlib.Path(spec_path).read_text()); out = pathlib.Path(out_dir)
    src = out / "raw.wav"
    if not src.exists():
        sf.write(src, np.concatenate([sf.read(f, dtype="float32")[0] for f in sorted(out.glob("vo-*.wav"))]), SR)
    a, _ = sf.read(src, dtype="float32")
    n = sum(len([w for w in b["caption"].split() if norm(w)]) for b in spec["beats"])
    a, wpm, tempo = pace(a, n, spec["voice"])
    split(a, spec["beats"], out, f"(was {wpm:.0f} wpm, tempo x{tempo:.2f})")


def main(spec_path, out_dir):
    spec = json.loads(pathlib.Path(spec_path).read_text()); v = spec["voice"]
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    beats = spec["beats"]; text = " ".join(b["tts"] for b in beats); caption = " ".join(b["caption"] for b in beats)
    want_laugh = "haha" in text.lower()
    gen = load_voice(); best = None; t0 = time.time()
    for k in range(v.get("takes", 3)):
        a = gen(text, v, v.get("seed", 3) + 17 * k)
        env = np.convolve(np.abs(a), np.ones(240) / 240, mode="same"); on = np.where(env > 0.01 * env.max())[0]
        a = a[max(0, on[0] - 1200): on[-1] + 3600]
        tmp = out / f"take{k}.wav"; sf.write(tmp, a, SR)
        heard = heard_words(tmp); sc, laughed = score(caption, heard, want_laugh)
        print(f"  take {k}: match {sc:.3f}{' +laugh' if laughed else ''}  {len(a) / SR:.1f}s", flush=True)
        if best is None or sc > best[0]: best = (sc, a, heard, k)
    for f in out.glob("take*.wav"): f.unlink()
    sc, a, heard, k = best
    sf.write(out / "raw.wav", a, SR)
    n = sum(len([w for w in b["caption"].split() if norm(w)]) for b in beats)
    a, wpm, tempo = pace(a, n, v)
    split(a, beats, out, f"(take {k}, match {sc:.3f}, was {wpm:.0f} wpm, tempo x{tempo:.2f}, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    (repace if "--repace" in sys.argv else main)(*[x for x in sys.argv[1:] if not x.startswith("--")][:2])
