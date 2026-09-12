"""Tests for scripts/patch_simple_pe_reweight_guard.py -- the short-term
stopgap patch for the confirmed upstream pesummary reweighting
OverflowError (see README.md's "Known issue" / CHANGELOG.md)."""

import importlib.util
import os
import sys
from unittest.mock import patch

import pytest

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "patch_simple_pe_reweight_guard.py"
)
_spec = importlib.util.spec_from_file_location(
    "patch_simple_pe_reweight_guard", SCRIPT_PATH
)
patch_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patch_module)


ORIGINAL_PE_PY = (
    "def reweight_based_on_observed_snrs(samples, **kwargs):\r\n"
    "    from pesummary.core.reweight import rejection_sampling\r\n"
    "    if not isinstance(samples, SimplePESamples):\r\n"
    "        samples = SimplePESamples(samples)\r\n"
    "    samples.calculate_subdominant_probs(**kwargs)\r\n"
    "    return rejection_sampling(samples, samples['weight'])\r\n"
)


class TestFindPePy:
    def test_returns_none_when_distribution_missing(self):
        with patch.object(
            patch_module.importlib.metadata,
            "distribution",
            side_effect=patch_module.importlib.metadata.PackageNotFoundError,
        ):
            assert patch_module._find_pe_py() is None

    def test_locates_pe_py_from_distribution_files(self):
        fake_file = type(
            "FakePath", (), {"as_posix": lambda self: "simple_pe/param_est/pe.py"}
        )()
        fake_dist = type(
            "FakeDist",
            (),
            {
                "files": [fake_file],
                "locate_file": lambda self, f: "/env/site-packages/simple_pe/param_est/pe.py",
            },
        )()
        with patch.object(
            patch_module.importlib.metadata, "distribution", return_value=fake_dist
        ):
            assert (
                patch_module._find_pe_py()
                == "/env/site-packages/simple_pe/param_est/pe.py"
            )


class TestMain:
    def test_missing_distribution_exits_nonzero(self, capsys):
        with patch.object(patch_module, "_find_pe_py", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                patch_module.main()
        assert exc_info.value.code == 1
        assert "Could not locate" in capsys.readouterr().err

    def test_patches_original_source_and_preserves_crlf(self, tmp_path):
        pe_py = tmp_path / "pe.py"
        pe_py.write_bytes(ORIGINAL_PE_PY.encode("utf-8"))

        with patch.object(patch_module, "_find_pe_py", return_value=str(pe_py)):
            patch_module.main()

        patched_bytes = pe_py.read_bytes()
        assert b"\r\n" in patched_bytes
        patched_text = patched_bytes.decode("utf-8")
        assert "np.nan_to_num(" in patched_text
        assert "posinf=0.0, neginf=0.0" in patched_text
        assert "return rejection_sampling(samples, weights)" in patched_text
        # The unguarded call to the raw, unsanitised weight must be gone.
        assert "rejection_sampling(samples, samples['weight'])" not in patched_text

    def test_second_run_is_idempotent_noop(self, tmp_path, capsys):
        pe_py = tmp_path / "pe.py"
        pe_py.write_bytes(ORIGINAL_PE_PY.encode("utf-8"))

        with patch.object(patch_module, "_find_pe_py", return_value=str(pe_py)):
            patch_module.main()
            first_pass_bytes = pe_py.read_bytes()
            patch_module.main()

        assert pe_py.read_bytes() == first_pass_bytes
        assert "already patched" in capsys.readouterr().out

    def test_unexpected_source_exits_nonzero_instead_of_silently_noop(
        self, tmp_path, capsys
    ):
        pe_py = tmp_path / "pe.py"
        pe_py.write_text(
            "def reweight_based_on_observed_snrs(samples, **kwargs):\n"
            "    return 'this has changed upstream'\n"
        )

        with patch.object(patch_module, "_find_pe_py", return_value=str(pe_py)):
            with pytest.raises(SystemExit) as exc_info:
                patch_module.main()

        assert exc_info.value.code == 1
        assert "source not found" in capsys.readouterr().err
        # Must not have touched the file at all.
        assert "this has changed upstream" in pe_py.read_text()


def test_guard_excludes_broken_samples_instead_of_crashing():
    """Functional check that the exact guard expression used by the patch
    reproduces the real crash when absent, and correctly zeroes out (never
    favours) non-finite weights when present -- mirroring pesummary's real
    `rejection_sampling()` shape without requiring pesummary/simple-pe to
    be installed in the test environment."""
    np = pytest.importorskip("numpy")

    def rejection_sampling(weights):
        weights = np.asarray(weights)
        return weights > np.random.uniform(0, np.max(weights), len(weights))

    weights = np.array([0.1, 0.5, np.inf, 0.3, np.nan, 0.9])

    with pytest.raises(OverflowError):
        rejection_sampling(weights)

    guarded = np.nan_to_num(
        np.asarray(weights, dtype=float), nan=0.0, posinf=0.0, neginf=0.0
    )
    idx = rejection_sampling(guarded)
    assert not idx[2]  # the inf sample must never be selected
    assert not idx[4]  # the nan sample must never be selected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
