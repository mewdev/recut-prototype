import subprocess

from recut import sync


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def make_data_repo(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    repo = tmp_path / "recut-data"
    subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True, capture_output=True)
    git("config", "user.email", "t@t", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    (repo / "tickets").mkdir()
    return remote, repo


def test_sync_commits_and_pushes_without_audio(tmp_path):
    remote, repo = make_data_repo(tmp_path)
    t = repo / "tickets" / "20261114-abcd"
    (t / "inputs").mkdir(parents=True)
    (t / "request.json").write_text("{}")
    (t / "inputs" / "a.mp3").write_bytes(b"ID3")
    (t / "audio.wav").write_bytes(b"RIFF")

    res = sync.sync(repo / "tickets", message="sync: test")
    assert res["status"] == "pushed" and res["committed"]
    files = git("ls-tree", "-r", "--name-only", "main", cwd=remote).split()
    assert "tickets/20261114-abcd/request.json" in files and ".gitignore" in files
    assert not any(f.endswith((".mp3", ".wav")) for f in files)

    assert sync.sync(repo / "tickets")["status"] == "pushed"  # nothing new: still fine
    assert int(git("rev-list", "--count", "main", cwd=remote)) == 1


def test_sync_rebases_on_other_machines_push(tmp_path):
    remote, repo = make_data_repo(tmp_path)
    (repo / "tickets" / "a.json").write_text("1")
    sync.sync(repo / "tickets")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True, capture_output=True)
    git("config", "user.email", "o@o", cwd=other)
    git("config", "user.name", "o", cwd=other)
    (other / "tickets" / "b.json").write_text("2")
    sync.sync(other / "tickets")
    (repo / "tickets" / "c.json").write_text("3")
    assert sync.sync(repo / "tickets")["status"] == "pushed"
    files = git("ls-tree", "-r", "--name-only", "main", cwd=remote).split()
    assert {"tickets/a.json", "tickets/b.json", "tickets/c.json"} <= set(files)


def test_no_data_repo_is_a_noop(tmp_path):
    (tmp_path / "tickets").mkdir()
    assert sync.sync(tmp_path / "tickets")["status"] == "no-data-repo"


def test_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RECUT_AUTOSYNC", "0")
    assert sync.request_sync("x", tmp_path, wait=True) is None
