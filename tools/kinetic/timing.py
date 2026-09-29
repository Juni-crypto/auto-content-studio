"""Word timings for a voiced beat: whisper.cpp word stamps aligned to the caption words (no TTS imports here)."""
import difflib, json, pathlib, re, subprocess

WHISPER = pathlib.Path("~/.cache/whisper/ggml-base.bin").expanduser()
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())


def word_times(wav):
    wav16 = wav.with_suffix(".16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-ar", "16000", "-ac", "1", wav16], check=True)
    subprocess.run(["whisper-cli", "-m", str(WHISPER), "-l", "en", "-f", str(wav16), "-ml", "1", "-sow", "-oj",
                    "-of", str(wav16.with_suffix(""))], check=True, capture_output=True)
    data = json.loads(wav16.with_suffix(".json").read_text())
    words = [(s["text"].strip(), s["offsets"]["from"] / 1000, s["offsets"]["to"] / 1000)
             for s in data["transcription"] if s["text"].strip()]
    wav16.unlink(); wav16.with_suffix(".json").unlink()
    return words


def align(script_words, heard, dur):
    """Give every caption word a start/end using whisper's timings where the words match, interpolating the rest."""
    a = [norm(w) for w in script_words]; b = [norm(w) for w, _, _ in heard]
    t = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            t[blk.a + k] = (heard[blk.b + k][1], heard[blk.b + k][2])
    known = [i for i, x in enumerate(t) if x]
    for i in range(len(a)):
        if t[i] is None:
            prev = max([k for k in known if k < i], default=None); nxt = min([k for k in known if k > i], default=None)
            s = t[prev][1] if prev is not None else 0.0
            e = t[nxt][0] if nxt is not None else dur
            gap = list(range(prev + 1 if prev is not None else 0, nxt if nxt is not None else len(a)))
            wts = [len(a[j]) + 2 for j in gap]; unit = (e - s) / max(sum(wts), 1)   # longer words take longer to say
            k = gap.index(i); s0 = s + sum(wts[:k]) * unit
            t[i] = (s0, s0 + wts[k] * unit)
    return [{"w": w, "s": round(x[0], 3), "e": round(x[1], 3)} for w, x in zip(script_words, t)]


