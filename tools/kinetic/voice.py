"""Voice a reel spec with Kokoro (CPU, 2 threads) and get word timings from local whisper.cpp.

  ../../.venv-voice/bin/python voice.py spec.json OUT_DIR

spec["voice"] = {"lang": "a"|"b"|"h", "voice": "af_heart", "speed": 1.0, "pause": 0.25 (breath between sentences)}; every beat has "tts" (what is spoken; may carry
Devanagari for Hindi words or spelled-out numbers) and "caption" (what is shown, romanised). Give both as parallel
lists of phrases for "phrase mode" (Hinglish): exact phrase timings without whisper, which can't time Hindi speech.
Writes OUT_DIR/vo-NN.wav and OUT_DIR/timing.json ([{n, dur, words:[{w,s,e}], heard}]).
"""
import json, pathlib, re, sys, time
import numpy as np, soundfile as sf, torch
torch.set_num_threads(2)
from kokoro import KPipeline

from timing import WHISPER, norm, word_times, align


def tidy(words, dur, least=0.12):
    """Monotonic word times, each at least `least` long, so no caption or cue can collapse onto its neighbour."""
    t = 0.0
    for w in words:
        w["s"] = round(max(w["s"], t), 3); w["e"] = round(max(w["e"], w["s"] + least), 3); t = w["e"]
    over = t - dur
    if over > 0:   # squeeze back inside the audio, proportionally
        k = dur / t
        for w in words: w["s"], w["e"] = round(w["s"] * k, 3), round(w["e"] * k, 3)
    return words


def phrase_mode(pipe, beat, v):
    """Voice each (tts, caption) phrase separately, trim it to its speech, spread its caption words by spoken length."""
    chunks, words, t = [], [], 0.0
    spoken = lambda w: len(re.sub(r"[^a-z]", "", w.lower())) + 2 + 3 * sum(ch.isdigit() for ch in w)   # digits are said as words
    for k, (tts, cap) in enumerate(zip(beat["tts"], beat["caption"])):
        a = np.concatenate([x.numpy() for _, _, x in pipe(tts, voice=v["voice"], speed=v.get("speed", 1.0))])
        env = np.convolve(np.abs(a), np.ones(240) / 240, mode="same"); on = np.where(env > 0.02 * env.max())[0]
        if len(on): a = a[max(0, on[0] - 1200): on[-1] + 2400]            # 50 ms lead-in, 100 ms tail
        cw = cap.split(); wts = [spoken(w) for w in cw]; unit = (len(a) / 24000 - 0.15) / sum(wts); acc = t + 0.05
        for w, n in zip(cw, wts):
            words.append({"w": w, "s": round(acc, 3), "e": round(acc + n * unit, 3)}); acc += n * unit
        pause = 0.22 if cap.rstrip().endswith((".", "!", "?")) else 0.1
        chunks += [a, np.zeros(int(pause * 24000), dtype=a.dtype)]; t += len(a) / 24000 + pause
    return np.concatenate(chunks[:-1]), words


def main(spec_path, out_dir):
    spec = json.loads(pathlib.Path(spec_path).read_text()); v = spec["voice"]
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    pipe = KPipeline(lang_code=v.get("lang", "a"), device="cpu")
    timing, t_gen = [], 0.0
    for n, beat in enumerate(spec["beats"], 1):
        wav = out / f"vo-{n:02d}.wav"
        t0 = time.time()
        if isinstance(beat["tts"], list):   # phrase mode (Hinglish etc.): exact phrase bounds, no whisper needed
            audio, words = phrase_mode(pipe, beat, v)
            sf.write(wav, audio, 24000); t_gen += time.time() - t0
            timing.append({"n": n, "dur": round(len(audio) / 24000, 3), "words": words, "heard": "(phrase mode)"})
            continue
        if v.get("pause"):   # voice the whole beat in one pass (Kokoro is weak on short fragments), then
            # lengthen the pauses the model already left — splicing silence mid-sound is audible, stretching a gap isn't
            a = np.concatenate([x.numpy() for _, _, x in pipe(beat["tts"], voice=v["voice"], speed=v.get("speed", 1.0))])
            fr = 240; env = np.array([np.abs(a[i:i + fr]).mean() for i in range(0, len(a), fr)]); quiet = env < 0.012 * env.max()
            on = np.where(~quiet)[0]; a0, a1 = on[0] * fr, (on[-1] + 1) * fr
            spans, pieces, k, last = [], [], on[0], a0
            while k <= on[-1]:
                if quiet[k]:
                    j = k
                    while j <= on[-1] and quiet[j]: j += 1
                    gap_s = (j - k) * fr / 24000
                    if gap_s >= 0.15:   # sentence-sized gap: add a breath in its middle
                        mid = (k + (j - k) // 2) * fr
                        pieces.append(a[last:mid]); pieces.append(np.zeros(int(v["pause"] * 24000), dtype=a.dtype)); last = mid
                    elif gap_s >= 0.07:  # clause gap: a little air
                        mid = (k + (j - k) // 2) * fr
                        pieces.append(a[last:mid]); pieces.append(np.zeros(int(v["pause"] * 0.25 * 24000), dtype=a.dtype)); last = mid
                    k = j
                else:
                    k += 1
            pieces.append(a[last:min(len(a), a1 + 4800)])
            audio = np.concatenate([np.zeros(1400, dtype=a.dtype)] + pieces); spans = []
        else:
            audio = np.concatenate([a.numpy() for _, _, a in pipe(beat["tts"], voice=v["voice"], speed=v.get("speed", 1.0))])
        sf.write(wav, audio, 24000); t_gen += time.time() - t0
        dur = len(audio) / 24000
        heard = word_times(wav)
        caps = [x for x in re.split(r"(?<=[.?!])\s+", beat["caption"]) if x.strip()]
        if spans and len(caps) == len(spans):   # align sentence by sentence inside known spans
            words = []
            for cap, (a0, a1) in zip(caps, spans):
                inside = [(w, max(s0, a0) - a0, min(e0, a1) - a0) for w, s0, e0 in heard if s0 >= a0 - 0.15 and s0 < a1]
                words += [{"w": x["w"], "s": round(x["s"] + a0, 3), "e": round(x["e"] + a0, 3)} for x in align(cap.split(), inside, a1 - a0)]
        else:
            words = align(beat["caption"].split(), heard, dur)
        words = tidy(words, dur)
        timing.append({"n": n, "dur": round(dur, 3), "words": words, "heard": " ".join(w for w, _, _ in heard)})
    (out / "timing.json").write_text(json.dumps(timing, indent=1))
    total = sum(b["dur"] for b in timing)
    print(f"{out.name}: {v['voice']} x{v.get('speed', 1.0)}, {total:.1f}s narration, generated in {t_gen:.1f}s on 2 CPU threads")
    for b in timing: print(f"  {b['n']}: {b['heard']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
