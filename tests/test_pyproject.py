"""pyproject.toml must be valid for strict build backends (setuptools validates PEP 508)."""

from pathlib import Path

import tomllib
from packaging.markers import Marker
from packaging.requirements import Requirement

PYPROJECT = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())


def all_requirements():
    proj = PYPROJECT["project"]
    yield from proj.get("dependencies", [])
    for reqs in proj.get("optional-dependencies", {}).values():
        yield from reqs


def test_every_requirement_is_pep508():
    for spec in all_requirements():
        Requirement(spec)  # raises InvalidRequirement on e.g. a `not (...)` marker


def test_essentia_extra_skips_intel_macs_only():
    req = next(Requirement(s) for s in PYPROJECT["project"]["optional-dependencies"]["qc"]
               if s.startswith("essentia"))
    env = lambda plat, mach: {"sys_platform": plat, "platform_machine": mach}  # noqa: E731
    assert not req.marker.evaluate(env("darwin", "x86_64"))
    assert req.marker.evaluate(env("darwin", "arm64"))
    assert req.marker.evaluate(env("linux", "x86_64"))
    assert isinstance(req.marker, Marker)
