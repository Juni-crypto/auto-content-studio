"""Voice a reel spec with Chatterbox (MIT, local; expressive) and get word timings from whisper.cpp.

  ../../.venv-chatter/bin/python voice_cb.py spec.json OUT_DIR [beat numbers to redo, e.g. 6,7]

spec["voice"] = {"engine": "chatterbox", "ref": "voice reference wav (path relative to the spec)", "exaggeration": 0.5-0.9,
                 "cfg": 0.3-0.5}. Beats: "tts" (spoken) + "caption" (shown). Writes vo-NN.wav + timing.json like voice.py.
Higher exaggeration = more energy; lower cfg = faster, looser delivery.
"""
import json, pathlib, sys, time
import torch, torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from timing import word_times, align, norm
import difflib


def match(caption, heard):
    a = [norm(w) for w in caption.split() if norm(w)]; b = [norm(w) for w, _, _ in heard if norm(w)]
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def main(spec_path, out_dir, only=None):
    spec_path = pathlib.Path(spec_path).resolve(); spec = json.loads(spec_path.read_text()); v = spec["voice"]
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    dev = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    m = ChatterboxTTS.from_pretrained(device=dev)
    ref = str((spec_path.parent / v["ref"]).resolve()) if v.get("ref") else None
    torch.manual_seed(v.get("seed", 7))
    timing, t_gen = [], 0.0
    old = {b["n"]: b for b in json.loads((out / "timing.json").read_text())} if only and (out / "timing.json").exists() else {}
    for n, beat in enumerate(spec["beats"], 1):
        if only and n not in only and n in old:   # keep beats that aren't being redone
            timing.append(old[n]); continue
        wav = out / f"vo-{n:02d}.wav"; t0 = time.time(); best = None
        for take in range(v.get("takes", 3)):   # best of N: keep the take whose transcript matches the script best
            torch.manual_seed(v.get("seed", 7) + 101 * take + n)
            a = m.generate(beat["tts"], audio_prompt_path=ref, exaggeration=v.get("exaggeration", 0.6), cfg_weight=v.get("cfg", 0.4))
            x = a[0]; env = torch.nn.functional.avg_pool1d(x.abs()[None, None], 480, 120)[0, 0]; on = (env > 0.02 * env.max()).nonzero()
            if len(on): x = x[max(0, int(on[0]) * 120 - 1200): int(on[-1]) * 120 + 480 + 3600]
            tmp = out / f"take-{n:02d}-{take}.wav"; ta.save(str(tmp), x[None], m.sr)
            heard = word_times(tmp); score = match(beat["caption"], heard)
            if best is None or score > best[0]: best = (score, tmp, x, heard)
            if score >= 0.92: break
        for f in out.glob(f"take-{n:02d}-*.wav"):
            if f != best[1]: f.unlink()
        best[1].rename(wav); t_gen += time.time() - t0
        x, heard = best[2], best[3]; dur = x.shape[-1] / m.sr
        timing.append({"n": n, "dur": round(dur, 3), "words": align(beat["caption"].split(), heard, dur),
                       "heard": " ".join(w for w, _, _ in heard), "match": round(best[0], 2), "takes": take + 1})
    (out / "timing.json").write_text(json.dumps(timing, indent=1))
    print(f"{out.name}: chatterbox ex{v.get('exaggeration', 0.6)} cfg{v.get('cfg', 0.4)} ref={v.get('ref')}, "
          f"{sum(b['dur'] for b in timing):.1f}s narration in {t_gen:.0f}s on {dev}")
    for b in timing: print(f"  {b['n']} (match {b['match']}, {b['takes']} take{'s' if b['takes'] > 1 else ''}): {b['heard']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None)
