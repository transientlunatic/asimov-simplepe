#!/usr/bin/env python3
"""Short-term stopgap for the confirmed upstream reweighting crash
documented in this repo's README.md/CHANGELOG.md (the "Known issue" under
*Post-processing*).

``simple_pe.param_est.pe.reweight_based_on_observed_snrs()`` passes
``samples['weight']`` straight into
``pesummary.core.reweight.rejection_sampling()``, which has no guard
against a non-finite weight and crashes with ``OverflowError: Range
exceeds valid bounds``. The non-finite weight comes from a divide-by-zero
encountered in simple-pe's own subdominant-SNR calculation (higher
multipoles/precession/second-polarisation/eccentricity) for a handful of
samples -- confirmed directly via this plugin's own e2e CI (see
CHANGELOG.md for the full trail).

This script patches the installed ``simple_pe/param_est/pe.py`` in place,
zeroing out any non-finite weight before it reaches ``rejection_sampling``
-- treating a numerically broken sample as zero-probability (rejected)
rather than crashing the whole run, or (worse) treating it as *certain*
(an `inf` weight, left unguarded, would otherwise always win rejection
sampling against every finite-weight sample). This is deliberately NOT
something ``asimov_simplepe`` applies for you at import time: the buggy
code runs inside ``simple_pe_analysis``'s own HTCondor subprocess, a
completely separate Python process from asimov's, so a plugin-level
monkeypatch would never reach it. It has to be applied to the installed
``simple-pe`` package itself, in whatever environment actually runs the
analysis jobs.

This is a stopgap, not a real fix: the correct fix belongs upstream, in
either simple-pe (guard the SNR calculation against the divide-by-zero
directly) or pesummary (guard ``rejection_sampling()`` itself, since any
of its other callers could hit the same crash). Drop this once one of
those lands and you upgrade past it.

Usage
-----
Run inside the same Python environment ``simple_pe_analysis`` runs in
(i.e. after installing ``simple-pe``, before running any real analysis)::

    python patch_simple_pe_reweight_guard.py

Idempotent: running it again on an already-patched installation is a
no-op. Exits non-zero (loudly) if the expected, exact original source
text isn't found in the installed file, rather than silently doing
nothing -- so a future upstream change to this function surfaces here as
a clear failure instead of quietly leaving the crash unpatched.
"""
import importlib.metadata
import sys


def _find_pe_py():
    """Locate the installed ``simple_pe/param_est/pe.py`` via the
    ``simple-pe`` distribution's own file manifest, rather than
    ``importlib.import_module``/``find_spec`` -- importing ``simple_pe``
    pulls in its real runtime dependencies (``pycbc``, ``lalsuite``)
    transitively through ``simple_pe.param_est.__init__``, which this
    script has no need to actually exercise just to locate one file."""
    try:
        dist = importlib.metadata.distribution("simple-pe")
    except importlib.metadata.PackageNotFoundError:
        return None
    for file in dist.files or ():
        if file.as_posix().endswith("simple_pe/param_est/pe.py"):
            return str(dist.locate_file(file))
    return None

ORIGINAL = (
    "    samples.calculate_subdominant_probs(**kwargs)\n"
    "    return rejection_sampling(samples, samples['weight'])\n"
)
PATCHED = (
    "    samples.calculate_subdominant_probs(**kwargs)\n"
    "    # --- asimov-simplepe short-term patch: see\n"
    "    # scripts/patch_simple_pe_reweight_guard.py in\n"
    "    # https://github.com/transientlunatic/asimov-simplepe ---\n"
    "    # A divide-by-zero in the subdominant-SNR calculation above can\n"
    "    # leave a non-finite weight for a handful of samples, which\n"
    "    # rejection_sampling() below has no guard against and crashes on\n"
    "    # (OverflowError: Range exceeds valid bounds). Treat a\n"
    "    # numerically broken sample as zero-probability (rejected)\n"
    "    # rather than crashing, or worse, treating it as certain.\n"
    "    weights = np.nan_to_num(\n"
    "        np.asarray(samples['weight'], dtype=float),\n"
    "        nan=0.0, posinf=0.0, neginf=0.0,\n"
    "    )\n"
    "    # --- end asimov-simplepe short-term patch ---\n"
    "    return rejection_sampling(samples, weights)\n"
)


def main():
    path = _find_pe_py()
    if path is None:
        print(
            "::error::Could not locate simple_pe/param_est/pe.py via the "
            "installed 'simple-pe' distribution's file manifest; is "
            "simple-pe installed in this Python environment?",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read/write raw bytes and handle the newline convention ourselves,
    # rather than relying on Python's default text-mode universal-newline
    # translation: the real installed file (confirmed directly) uses CRLF
    # line endings throughout, and open(path, "w") in default text mode
    # would silently rewrite every line in the file to LF on save -- a
    # spurious, file-wide diff for what should be a small, precise patch.
    with open(path, "rb") as source_file:
        raw = source_file.read()
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    source = raw.decode("utf-8").replace("\r\n", "\n")

    if PATCHED in source:
        print(f"{path} is already patched; nothing to do.")
        return

    if ORIGINAL not in source:
        print(
            "::error::Expected original reweight_based_on_observed_snrs() "
            f"source not found in {path}. simple-pe's source has likely "
            "changed since this patch was written against it -- update or "
            "drop this patch rather than applying it blindly.",
            file=sys.stderr,
        )
        sys.exit(1)

    patched_source = source.replace(ORIGINAL, PATCHED, 1)
    with open(path, "wb") as source_file:
        source_file.write(patched_source.replace("\n", newline.decode()).encode("utf-8"))
    print(
        f"Patched {path}: reweight_based_on_observed_snrs() now zeroes out "
        "non-finite weights before rejection sampling."
    )


if __name__ == "__main__":
    main()
