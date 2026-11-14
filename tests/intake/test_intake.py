"""Q0 intake check: synthetic files (numpy + soundfile + ffmpeg), CLI refusal/override, API 422/override."""

import json
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from scipy import signal

from recut import intake, tickets
from recut.cli import main
from recut.paths import TICKETS_DIR
from recut.server.app import create_app

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg needed")
SR = 44100


def noise(seconds=40, cutoff=None, seed=0, stereo=True):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((2 if stereo else 1, int(seconds * SR)))
    if cutoff:
        sos = signal.butter(10, cutoff, fs=SR, output="sos")
        x = signal.sosfiltfilt(sos, x, axis=-1)
    return (0.2 * x / x.std()).astype(np.float32)


def wav(path, x):
    sf.write(str(path), x.T, SR, subtype="PCM_16")
    return path


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("intake")
    f = {"clean": wav(d / "clean.wav", noise())}
    f["lp15"] = wav(d / "lp15.wav", noise(cutoff=15000))
    f["mp3_128"] = d / "c128.mp3"
    ffmpeg("-i", f["clean"], "-b:a", "128k", f["mp3_128"])
    f["fake320"] = d / "fake320.mp3"  # 320 container, 128 content
    ffmpeg("-i", f["mp3_128"], "-b:a", "320k", f["fake320"])
    f["short"] = wav(d / "short.wav", noise(seconds=10))
    f["mono_as_stereo"] = wav(d / "ms.wav", np.repeat(noise(stereo=False), 2, axis=0))
    f["clipped"] = wav(d / "clip.wav", np.clip(noise() * 6, -1, 1))
    f["junk"] = d / "junk.mp3"
    f["junk"].write_bytes(b"not audio at all" * 100)
    return f


def codes(res):
    return {p["code"] for p in res.problems}


def test_clean_wav_ok(files):
    r = intake.check_audio(files["clean"])
    assert r.ok and not r.problems, r.problems
    assert r.info["bandwidth_hz"] > 18000 and r.info["lossless"]


def test_lowpassed_noise_is_low_bandwidth(files):
    r = intake.check_audio(files["lp15"])
    assert not r.ok and codes(r) == {"low_bandwidth"}
    assert 14000 < r.info["bandwidth_hz"] < 17500 and "nothing above" in r.problems[0]["message"]


def test_128k_mp3_is_low_bitrate_and_bandwidth(files):
    r = intake.check_audio(files["mp3_128"])
    assert {"low_bitrate", "low_bandwidth"} <= codes(r)
    assert "128 kbps" in next(p for p in r.problems if p["code"] == "low_bitrate")["message"]


def test_fake_320_caught_by_real_bandwidth(files):
    r = intake.check_audio(files["fake320"])
    assert r.info["bitrate_kbps"] >= 300
    assert codes(r) == {"low_bandwidth"}


def test_good_mp3_320_passes(files, tmp_path):
    p = tmp_path / "good.mp3"
    ffmpeg("-i", files["clean"], "-b:a", "320k", p)
    assert intake.check_audio(p).ok


def test_too_short_and_info_problems_do_not_block(files):
    assert codes(intake.check_audio(files["short"])) == {"too_short"}
    r = intake.check_audio(files["mono_as_stereo"])
    assert r.ok and codes(r) == {"fake_stereo"}
    r = intake.check_audio(files["clipped"])
    assert "clipped_source" in codes(r)
    assert not any(p["blocking"] for p in r.problems if p["code"] == "clipped_source")


def test_low_samplerate_and_too_long(tmp_path):
    p = tmp_path / "sr.wav"
    sf.write(str(p), noise(seconds=30)[:, : 30 * 22050].T, 22050)
    assert "low_samplerate" in codes(intake.check_audio(p))
    p2 = tmp_path / "long.wav"
    sf.write(str(p2), np.zeros((16000 * 16 * 60, 1), dtype="float32") + 0.01, 16000)
    assert "too_long" in codes(intake.check_audio(p2))


def test_undecodable(files, tmp_path):
    assert codes(intake.check_audio(files["junk"])) == {"undecodable"}
    assert codes(intake.check_audio(tmp_path / "missing.wav")) == {"undecodable"}


def test_five_minute_file_under_one_second(tmp_path):
    p = wav(tmp_path / "five.wav", noise(seconds=300))
    intake.check_audio(p)  # warm imports
    t = time.perf_counter()
    r = intake.check_audio(p)
    dt = time.perf_counter() - t
    assert r.ok and dt < 1.0, dt
    mp3 = tmp_path / "five.mp3"
    ffmpeg("-i", p, "-b:a", "320k", mp3)
    t = time.perf_counter()
    intake.check_audio(mp3)
    assert time.perf_counter() - t < 1.0


def test_works_without_ffprobe(files, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert intake.check_audio(files["clean"]).ok
    assert codes(intake.check_audio(files["lp15"])) == {"low_bandwidth"}


# ---- CLI ----------------------------------------------------------------------------------


def ids():
    return {r.id for r in tickets.list_tickets(TICKETS_DIR)}


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["recut", *args])
    main()


def test_check_audio_cli(files, monkeypatch, capsys):
    run(monkeypatch, "check-audio", str(files["clean"]))
    assert "OK" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        run(monkeypatch, "check-audio", str(files["lp15"]))
    assert "low_bandwidth" in capsys.readouterr().out


def test_ticket_new_refuses_then_overrides(files, monkeypatch, capsys):
    before = ids()
    with pytest.raises(SystemExit):
        run(monkeypatch, "ticket", "new", str(files["lp15"]), "--text", "x")
    out = capsys.readouterr().out
    assert "nothing above" in out and "--override" in out
    assert ids() == before

    run(monkeypatch, "ticket", "new", str(files["lp15"]), "--text", "x", "--override")
    (tid,) = ids() - before
    rec = json.loads((TICKETS_DIR / tid / "intake.json").read_text())
    assert rec["override"] is True and rec["problems"][0]["code"] == "low_bandwidth"
    ev = [e for e in tickets.ticket_timeline(tid, TICKETS_DIR) if e["op"] == "intake"][0]
    assert ev["override"] is True and ev["problems"][0]["code"] == "low_bandwidth"


def test_ticket_new_clean_records_no_override(files, monkeypatch):
    before = ids()
    run(monkeypatch, "ticket", "new", str(files["clean"]), "--text", "x")
    (tid,) = ids() - before
    rec = json.loads((TICKETS_DIR / tid / "intake.json").read_text())
    assert rec["override"] is False and rec["problems"] == []


# ---- API ----------------------------------------------------------------------------------


def test_api_422_then_override(files):
    c = TestClient(create_app(TICKETS_DIR))

    def up(**extra):
        return c.post("/api/tickets", data={"text": "x", **extra},
                      files=[("files", ("lp.wav", files["lp15"].read_bytes(), "audio/wav"))])

    before = ids()
    r = up()
    assert r.status_code == 422
    p = r.json()["detail"]["problems"][0]
    assert p["code"] == "low_bandwidth" and p["file"] == "lp.wav"
    assert ids() == before
    r = up(override="true")
    assert r.status_code == 200
    tid = r.json()["id"]
    assert json.loads((TICKETS_DIR / tid / "intake.json").read_text())["override"] is True


def test_api_clean_file_creates(files):
    c = TestClient(create_app(TICKETS_DIR))
    r = c.post("/api/tickets", data={"text": "x"},
               files=[("files", ("clean.wav", files["clean"].read_bytes(), "audio/wav"))])
    assert r.status_code == 200
