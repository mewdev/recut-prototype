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


def test_sync_adds_new_ignore_patterns_to_an_older_gitignore(tmp_path):
    """A data repo set up by an older recut keeps its .gitignore; patterns added since (the
    machine-local agent session pointers) must still be ignored, never committed."""
    remote, repo = make_data_repo(tmp_path)
    (repo / ".gitignore").write_text("# old header, Written by recut.sync.\n*.wav\n*.mp3\nmine.txt\n")
    (repo / "tickets" / ".agent_sessions").mkdir()
    (repo / "tickets" / ".agent_sessions" / "abc-123").write_text("/some/session\n")
    (repo / "tickets" / "a.json").write_text("1")
    sync.sync(repo / "tickets")
    files = git("ls-tree", "-r", "--name-only", "main", cwd=remote).split()
    assert "tickets/a.json" in files and not any(".agent_sessions" in f for f in files)
    lines = (repo / ".gitignore").read_text().splitlines()
    assert "mine.txt" in lines and lines.count("*.wav") == 1 and ".agent_sessions/" in lines
    sync.sync(repo / "tickets")
    assert (repo / ".gitignore").read_text().splitlines() == lines  # added once, not on every sync


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


def _write_after_commit(monkeypatch, path, text):
    """Simulate another process (a render, the server, the CLI) writing a ticket file after the
    sync has committed but before it has pulled/pushed: the window where data used to be lost."""
    real = sync._git
    state = {"done": False}

    def wrapped(repo, *args, **kw):
        r = real(repo, *args, **kw)
        if args and args[0] == "commit" and not state["done"]:
            state["done"] = True
            path.write_text(text)
            state["inode"] = path.stat().st_ino
        return r

    monkeypatch.setattr(sync, "_git", wrapped)
    return state


def _assert_no_git_leftovers(repo):
    assert not (repo / ".git" / "rebase-merge").exists() and not (repo / ".git" / "rebase-apply").exists()
    assert git("stash", "list", cwd=repo).strip() == ""


def test_sync_never_moves_a_file_written_during_the_sync(tmp_path, monkeypatch):
    """`pull --autostash` stashed a plan.json edit made mid-sync; the rebase then stopped and the
    edit was never restored. The sync must leave uncommitted files exactly where they are."""
    remote, repo = make_data_repo(tmp_path)
    plan = repo / "tickets" / "plan.json"
    plan.write_text("v1")
    sync.sync(repo / "tickets")
    written = _write_after_commit(monkeypatch, plan, "v2")
    (repo / "tickets" / "render.json").write_text("r")
    res = sync.sync(repo / "tickets")
    assert res["status"] == "pushed"
    assert plan.read_text() == "v2" and plan.stat().st_ino == written["inode"]  # not rewritten
    _assert_no_git_leftovers(repo)
    monkeypatch.undo()
    sync.sync(repo / "tickets")  # the next sync commits the edit
    assert git("show", "main:tickets/plan.json", cwd=remote) == "v2"


def test_sync_commits_a_mid_sync_write_before_rebasing_on_another_push(tmp_path, monkeypatch):
    remote, repo = make_data_repo(tmp_path)
    plan = repo / "tickets" / "plan.json"
    plan.write_text("v1")
    sync.sync(repo / "tickets")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True, capture_output=True)
    git("config", "user.email", "o@o", cwd=other)
    git("config", "user.name", "o", cwd=other)
    (other / "tickets" / "b.json").write_text("2")
    sync.sync(other / "tickets")

    _write_after_commit(monkeypatch, plan, "v2")
    (repo / "tickets" / "render.json").write_text("r")
    assert sync.sync(repo / "tickets")["status"] == "pushed"
    assert plan.read_text() == "v2"
    assert git("show", "main:tickets/plan.json", cwd=remote) == "v2"
    assert "tickets/b.json" in git("ls-tree", "-r", "--name-only", "main", cwd=remote).split()
    _assert_no_git_leftovers(repo)


def test_sync_unreachable_remote_leaves_tree_and_git_state_alone(tmp_path):
    remote, repo = make_data_repo(tmp_path)
    (repo / "tickets" / "a.json").write_text("1")
    sync.sync(repo / "tickets")
    git("remote", "set-url", "origin", str(tmp_path / "missing.git"), cwd=repo)
    (repo / "tickets" / "a.json").write_text("2")
    res = sync.sync(repo / "tickets")
    assert res["status"] == "push-failed" and res["committed"]
    assert (repo / "tickets" / "a.json").read_text() == "2"
    _assert_no_git_leftovers(repo)
