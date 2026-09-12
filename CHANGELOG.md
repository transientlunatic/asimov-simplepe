# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `tests/test_blueprints/fake_event.yaml`'s `waveform.approximant` is now
  `IMRPhenomXPHM`, not `IMRPhenomD` -- the actual root cause of the e2e
  test's reweighting crash, confirmed directly via this plugin's own
  e2e CI (not a genuine, unfixable upstream numerical-robustness bug as
  first assumed; see the entries below documenting that investigation).
  `IMRPhenomD` is a dominant-mode-only, non-precessing waveform model,
  but `simple_pe_analysis`'s reweighting step unconditionally measures
  the *observed* SNR in the (3,3)/(4,4) higher multipoles and in
  precession regardless of whether the approximant can represent them
  at all. Against `IMRPhenomD`, those observed SNRs came back `NaN`
  (confirmed directly: a real run's `peak_snrs.json` contained
  `"33": [nan], "44": [nan]`). Once `np.nan_to_num` zeroed those NaNs
  (per `scripts/patch_simple_pe_reweight_guard.py`, below), the
  reference (noncentral chi-squared) distribution used to weight each
  sample became a *central* one evaluated at the predicted higher-mode
  SNR for that sample -- which, given this test's inflated dominant-mode
  SNR (~113, from a synthetic near-design-sensitivity ASD combined with
  GW150914's real, close distance -- real GW150914's SNR is ~24),
  underflows to exactly `0.0` probability in float64 for essentially
  every sample, not just outliers, corrupting the whole reweighting
  step regardless of any inf/nan-weight guard. `IMRPhenomXPHM` matches
  `simple_pe_filter`'s/`simple_pe_analysis`'s own `--approximant`
  default (confirmed directly from their real source) and genuinely
  supports higher modes and precession, so the observed SNRs it
  produces are real, finite numbers instead of `NaN`.
- `resurrect()` now raises `PipelineException` instead of silently
  returning `None` once it can no longer usefully resubmit the DAG.
  Asimov's monitor loop (`RunningState._handle_no_condor_job` in asimov
  core) treats a `resurrect()` call that returns normally as "handled,
  keep waiting" -- so a production whose DAG had genuinely, permanently
  failed (as opposed to merely being evicted) previously resubmitted its
  rescue DAG up to five times and then silently did nothing at all: no
  status change, no message, indistinguishable from a healthy job still
  running indefinitely.
  - Two cases now raise, both confirmed directly via this plugin's own
    e2e CI investigation of a real reweighting failure: (1) the
    production's collected logs (`collect_logs()`) match a known,
    previously-confirmed upstream failure signature
    (`_KNOWN_FAILURE_SIGNATURES`) -- currently the pesummary
    `OverflowError: Range exceeds valid bounds` reweighting bug (see the
    "e2e test: the completion criterion..." entry below) -- in which
    case `resurrect()` raises *immediately*, without spending any of the
    retry budget, naming the known cause directly in the exception
    message; and (2) the retry budget (5 attempts) is exhausted without
    a known signature being found, in which case it raises a generic
    "exhausted N automatic rescue-DAG resubmission(s)" message. Case (1)
    matters because blind resubmission of this specific bug is
    guaranteed to fail identically every time, not just probably:
    `simple_pe_analysis --seed` (confirmed directly from its real
    source) defaults to a *fixed* value (`123456789`), not one derived
    from OS entropy, so re-running the exact same rendered ini/trigger-
    parameters reproduces the exact same "random" reweighting failure --
    burning through five identical, doomed resubmissions before giving
    up would waste real HTCondor compute time for zero chance of a
    different outcome.
  - The no-rescue-file case (the condor job disappeared without DAGMan
    ever writing a rescue file at all -- a genuinely different and more
    ambiguous situation, e.g. a transient job-tracking gap) is
    deliberately left as a no-op, not a raise, to avoid false "stuck"
    reports on jobs that are actually still fine.
- `configs/simplepe.ini` now sets `disable_pesummary = True`. Left at its
  default `False`, `simple_pe_pipe`'s own `main()` bakes a full PESummary
  post-processing job into its DAG as a child of the analysis node
  (confirmed directly from its real source) -- duplicating the separate,
  `needs:`-linked PESummary production this plugin's own design already
  assumes handles post-processing (see README's *Post-processing*
  section), and running PESummary twice for no benefit. This is a
  distinct DAG-construction option from the always-on, unconditional
  PESummary-based reweighting inside `simple_pe_analysis` itself
  (`simple_pe_analysis --help` doesn't even expose `disable_pesummary`),
  so it does not affect the separate, currently-unavoidable upstream
  reweighting bug documented elsewhere in this file.
- Addressed a GitHub Copilot code review of the initial PR:
  - `_ensure_rundir()`'s fallback branch (no `production.rundir` set) now
    resolves to an absolute path via `os.path.abspath()`, matching the
    explicit-rundir branch and this method's documented promise. A
    relative `[general] rundir_default` previously left the rendered
    `outdir`/trigger paths relative to the process's working directory.
  - `build_dag()` now snapshots any pre-existing DAG file (path + mtime)
    before invoking `simple_pe_pipe`, and treats an unchanged file as
    build failure rather than success: `_dag_file()` searches the whole
    rundir with no notion of "created by this invocation", so a retried
    `build_dag()` in a rundir that already contained a DAG from a
    previous run could otherwise report success against that stale file
    even when this run's `simple_pe_pipe` silently failed to (re)write
    one.
  - `samples()` now skips zero-byte matches: a truncated or
    still-being-written file (e.g. from an interrupted run) was
    previously indistinguishable from a genuine, complete samples file,
    so `detect_completion()` could report a production finished against
    an empty/invalid artifact.
  - `collect_logs()` now also matches `*.error`/`*.output`, not just
    `*.err`/`*.out`/`*.log`: `simple_pe_pipe`'s own generated DAG nodes
    write the former (confirmed directly via this plugin's own e2e CI,
    whose diagnostics read `error/*.error`/`output/*.output`), so this
    method previously never found the real Simple-PE node diagnostics.
  - `.github/actions/setup-simplepe-env`'s conda-env cache key is now
    keyed on `simple-pe-ref` resolved to an immutable commit SHA (via
    `git ls-remote`), not the ref name itself: keyed only on the name, a
    cache populated once for `simple-pe-ref: main` stayed a hit forever,
    so a later commit to upstream `main` would silently be skipped and
    the e2e job would keep testing a stale revision indefinitely.
  - `.github/workflows/e2e.yml`'s `push` trigger is now scoped to `main`
    only (matching `docs.yml`'s existing pattern), not every branch and
    tag: this is a real ~30-minute job against a real HTCondor scheduler
    and real GWOSC network access, so running it on every push to every
    branch burned substantial runner time and added real-network
    flakiness to routine, not-yet-reviewed development pushes; PR
    coverage is unaffected (`pull_request` still covers every open PR).
  - `.github/workflows/docs.yml`'s `build`/`deploy` job condition now
    also accepts `workflow_dispatch`, not just `push`: the workflow
    declares `workflow_dispatch` as a trigger, but the job itself only
    checked `github.event_name == 'push'`, so a manual dispatch silently
    built and deployed nothing.
  - `tests/test_blueprints/simplepe_production.yaml`'s `data.asd` paths
    are no longer hardcoded to this upstream repository's own
    `/__w/asimov-simplepe/asimov-simplepe` workspace path -- that broke
    on a fork or any runner whose workspace path differs (the Condor jobs
    would receive a nonexistent ASD file and fail before analysis). The
    blueprint now carries the literal placeholder `__ASD_PATH__`,
    substituted with the real, runner-specific
    `$GITHUB_WORKSPACE/e2e_project/aLIGO_asd.txt` path by a new e2e.yml
    step immediately before the blueprint is applied.
  - README.md/docs/index.rst's install instructions now also pin
    `numpy<2` (previously only `setuptools<82`), matching the constraint
    `setup-simplepe-env` actually applies and needs (see this file's
    existing "Fixed" entry on the real `filter`-node `TypeError` it
    avoids) -- following only the documented instructions previously
    risked hitting that same crash.
  - README.md's trigger-parameter fallback description now matches
    `before_config()`'s actual defaults (`mass1`/`mass2` to 1.4,
    `ra`/`dec` to 0) instead of claiming masses/sky location are "left
    blank".
  - README.md/CHANGELOG.md's e2e-test descriptions no longer claim it
    waits for a full, parseable posterior-samples file -- it currently
    waits for and validates `peak_parameters.json`/`peak_snrs.json`
    instead, per the upstream `pesummary` reweighting bug documented
    elsewhere in both files.
- e2e test: the "wait for real analysis output" step's `directory` now
  points at `.../simplepe-test/output`, not `.../simplepe-test` itself.
  `wait-for-files` matches patterns directly inside `directory`
  (non-recursively), but `simple_pe_analysis` writes
  `peak_parameters.json`/`peak_snrs.json` into its own `output/`
  subdirectory -- confirmed directly via a real e2e run: the step timed
  out after the full 600s logging "0/2 patterns matched" throughout,
  while its own post-timeout `ls -R` dump showed both files present in
  `output/` the entire time.
- e2e test: the completion criterion is now "real `peak_parameters.json`/
  `peak_snrs.json` written by the `analysis` DAG node", not "a posterior
  samples file exists" / "the production reaches `status: finished`".
  Confirmed directly via a real e2e run against real GWOSC data (after
  all the fixes below got `datafind` and `filter` completing successfully
  and `analysis` running its real Fisher-matrix metric peak-finding and
  SNR computation): the run then crashes inside PESummary's own
  subdominant-multipole rejection-sampling reweighting step --
  `pesummary.core.reweight.rejection_sampling()` does `weights >
  np.random.uniform(0, np.max(weights), len(weights))` with no guard
  against a non-finite weight, raising `OverflowError: Range exceeds
  valid bounds`; the real traceback shows a `RuntimeWarning: divide by
  zero encountered in divide` immediately beforehand in pycbc's `Array`
  division, consistent with an `inf` weight reaching `np.max()`. This is
  called unconditionally from `simple_pe.param_est.pe.
  reweight_based_on_observed_snrs()`, with no CLI flag to disable or
  adjust it (`--seed`/`--neffective`/`--nsamples`, confirmed from
  `simple_pe_analysis --help`, don't touch it) -- a genuine upstream
  numerical-robustness bug, not something this plugin's ini/config
  rendering can work around. `asimov_simplepe`'s own `detect_completion()`
  /`samples()` are deliberately unchanged: a real production that never
  produces posterior samples should keep reporting non-finished status.
  Only this plugin's own e2e test's verification approach changes, to
  check the DAG's real, currently-achievable on-disk output directly
  (which is exactly what this plugin's own config rendering, DAG
  building, and submission are responsible for getting right) instead of
  requiring output from a later pipeline stage this plugin doesn't
  control and that has a real upstream bug in it.
- e2e test: the generated ASD file now lives under
  `$GITHUB_WORKSPACE/e2e_project`, not `/tmp` -- confirmed directly via a
  real e2e run: the `filter` DAG node crashed with `FileNotFoundError:
  /tmp/aLIGO_asd.txt not found.`, unlike `datafind` (which declares
  `universe = "local"` and so shares the submit host's normal
  filesystem), consistent with HTCondor's default (non-local-universe)
  jobs running in a sandboxed execute directory that doesn't include
  `/tmp`. Every other input file this plugin/`simple_pe_pipe` uses
  already lives under the project's own working directory tree and is
  read by those same jobs without issue.
- `.github/actions/setup-simplepe-env` re-pins `numpy<2` (see "Fixed"
  below for the earlier attempt that was reverted). A real e2e run
  against `GWOSC` mode (after the `peak_finder`/`trigger_parameters.json`
  fixes below got the real `filter` DAG node running for the first
  time) hit the exact same `estimate_data_length_from_template_parameters`
  `TypeError` as before -- but this time via a different, genuinely
  unavoidable path: `simple_pe_filter`'s own
  `load_trigger_parameters_from_file()` wraps the loaded
  trigger-parameters dict in `SimplePESamples` *unconditionally*, on
  every real analysis regardless of channel mode, before passing it into
  the same broken function. This is different from the earlier,
  injection-only trigger for the same bug: `write_converted_injection_
  parameters()` is structurally unreachable now that this plugin's e2e
  test uses `GWOSC` (that function is only ever called when
  `--injection` is passed), so the earlier NaN-GPS-time infinite loop
  that made the first `numpy<2` attempt actively harmful cannot recur
  here -- confirmed by reasoning through the actual call graph, not
  reused as a blind retry of a previously-reverted fix.
- `before_config()`/`_trigger_parameters_file()`: the trigger-parameters
  file is now written as JSON (`trigger_parameters.json`), not an ini
  file -- confirmed directly from `simple_pe_filter`'s real source
  (`simple_pe.io.io.load_trigger_parameters_from_file()`, dumped via
  this plugin's own e2e CI): it does `json.load(f)` then
  `pe.SimplePESamples(data)` on whatever `--trigger_parameters` points
  at, and requires (case-sensitive, underscored LIGO convention)
  `mass_1`, `mass_2`, `spin_1z`, `spin_2z` and `time` keys. The old
  ini-format file (`configparser.RawConfigParser`, `[parameters]\nmass1
  = 36\n...`) crashed the real `filter` DAG node -- the first node
  downstream of `datafind` in the full analysis pipeline -- with
  `json.decoder.JSONDecodeError: Expecting value: line 1 column 2 (char
  1)`, confirmed via this plugin's own e2e CI once the `peak_finder` fix
  below got that node built and run for the first time.
- `config_template`: added `peak_finder = metric` (configurable via
  `production.meta['peak_finder']`), the actual root cause of the DAG
  containing only a `DataFindNode` job -- confirmed directly via this
  plugin's own e2e CI, using `simple_pe_pipe`'s real `logger.info(opts)`
  dump of its parsed argument `Namespace`. `--peak_finder` defaults to
  `[]` (confirmed directly from `--help`), and `simple_pe_pipe`'s
  `main()` builds every real analysis DAG node (`FilterNode`/
  `AnalysisNode`/`CornerNode`/`PostProcessingNode`) inside `for
  peak_finder in opts.peak_finder:` -- with an empty list that loop runs
  zero times, so those nodes silently never get created. There's no
  crash or warning of any kind: `simple_pe_pipe` exits 0 and writes a
  perfectly well-formed, valid single-node DAG, which is what made this
  so easy to miss and took several rounds of real e2e CI (culminating in
  re-running `simple_pe_pipe` directly to capture its own diagnostic
  output, since `asimov`'s `build_dag()` doesn't surface it) to actually
  find. `metric` is used as the default since it matches simple-pe's own
  Fisher-matrix design (its headline algorithm, per `--help`'s own
  examples).
- e2e test: switched from `data.channels.<IFO>: INJ` (a simulated
  injection) to `GWOSC` (real public strain data for GW150914, whose
  real GPS time and approximate parameters the test fixtures already
  used) -- `INJ` mode hits a genuine, currently-unworkaroundable
  upstream bug once any channel is `INJ`:
  `simple_pe_datafind.main()`'s `write_converted_injection_parameters()`
  wraps the injection dict in `SimplePESamples` (a pesummary-style
  samples container -- built for posterior *chains*, so even a single
  scalar comes back as a shape-`(1,)` array rather than a true 0-d
  array) before passing it to
  `estimate_data_length_from_template_parameters()`, which does
  `int(2**(np.ceil(np.log2(wf_len))))` on a value derived from it.
  First observed as `TypeError: only 0-dimensional arrays can be
  converted to Python scalars` -- NumPy hard-errors this exact implicit
  shape-`(1,)`-to-scalar conversion since 2.0 (a DeprecationWarning
  before that). Pinning `numpy<2` in `setup-simplepe-env` was tried
  first, and did make that particular `TypeError` go away -- but only
  by unmasking a worse failure one level deeper: with the `TypeError`
  no longer stopping it, the same malformed `SimplePESamples`-wrapped
  data propagates into a later multipole/precessing-SNR calculation
  and produces a NaN GPS time, which sends LALSuite's
  `XLALGPSSetREAL8()` into what is for all practical purposes an
  infinite loop (confirmed directly: over a million characters of
  identical `XLALGPSSetREAL8(): NaN ... Invalid floating point
  operation` log lines in under two seconds of wall-clock time, in a
  real e2e CI run, before the job was killed by its 30-minute
  timeout) -- so the numpy pin was reverted (see below) rather than
  kept as a fix for a problem it didn't actually fix. `GWOSC` mode
  (`get_gwosc_data()`) never calls `--injection`/
  `write_converted_injection_parameters()` at all, sidestepping this
  whole code path -- and is arguably a more meaningful genuine
  end-to-end test besides, exercising a real historical event's real
  detector data rather than a simulated one. `INJ` mode itself remains
  fully supported by this plugin (`SimplePE.uses_injection`,
  `_write_injection_parameters()`, unit-tested) for users who want it
  once the underlying `simple-pe` bug is fixed upstream, or against a
  `simple-pe` ref that doesn't hit it, via the `simple-pe-ref` input on
  `setup-simplepe-env` -- this plugin's own e2e test just no longer
  depends on that path working.
- Also extended the "Cache asimov-simplepe conda env" cache key to hash
  `setup-simplepe-env/action.yml` itself (previously only
  `conda/packages.txt`/`pyproject.toml`): confirmed directly, while
  investigating the numpy pin above, that a constraint change made only
  inside this action's own install steps would otherwise silently no-op
  on a cache hit restored from an earlier CI run in this same PR that
  predates it.
- e2e test / README / docs: `data.asd` must be a real, two-column
  (frequency, ASD) text file -- there is no analytic-PSD-model-name
  shortcut in `simple_pe_pipe`'s CLI, confirmed directly from `--help`
  ("ASD files to use for the analysis") and from a real e2e run: passing
  the model name `aLIGOZeroDetHighPower` as if it were a magic value (an
  earlier attempt, by analogy with `data.channels: INJ`) crashed with
  `FileNotFoundError: aLIGOZeroDetHighPower not found.` inside
  `numpy.loadtxt()` (via `pycbc.psd.read.from_txt()`), because
  `simple_pe_datafind` opens whatever string it's given as a literal
  path. `.github/workflows/e2e.yml` now generates a real ASD file at CI
  time from pycbc's own analytic `aLIGOZeroDetHighPower` model (pycbc is
  already installed there as a simple-pe dependency) rather than
  committing a static data file to the repository.
- `config_template`/`before_config()`: when any interferometer's
  `data.channels` value is the `INJ` magic value, `simple_pe_pipe`'s
  `datafind` node now gets a real `--injection` JSON file. Without it,
  `simple_pe_datafind.py`'s own per-ifo channel loop
  (`elif "inj" in value.lower(): if not os.path.isfile(opts.injection):`)
  crashes with `TypeError: stat: path should be string, bytes,
  os.PathLike or integer, not NoneType` instead of its intended
  `FileNotFoundError` -- confirmed directly from the real source (dumped
  in this plugin's own e2e CI, since `git.ligo.org` isn't reachable from
  where this plugin is authored): `--injection` defaults to `None` and
  that line never guards against it. `SimplePE.uses_injection` (a
  property, so `configs/simplepe.ini` can reference it as
  `pipeline.uses_injection`) detects this case with the same
  case-insensitive substring check as the real code;
  `before_config()`'s new `_write_injection_parameters()` writes
  `injection.json` from the production's `trigger` metadata, using the
  schema confirmed directly from `simple_pe_datafind.py`'s
  `get_injection_data()`: masses/spins in the underscored LIGO
  convention (`mass_1`/`mass_2`/`spin_1x` etc -- the only keys that
  function itself converts to `pycbc.waveform.get_td_waveform`'s
  convention), `delta_t` derived from this template's own `f_high` to
  stay consistent with it (the real code derives `f_high` *back* from
  `delta_t` as `1 / 2 / delta_t`), and `ra`/`dec`/`psi`/`time` passed
  through directly. A first version of the template-side conditional
  used `{% assign uses_injection = true %}` *inside* a Liquid `{% for
  %}` loop, which silently never took effect outside the loop -- a
  Jinja2 for-loop variable-scoping gotcha (asimov's "liquid" templating
  package is actually Jinja2-based), confirmed directly by rendering
  the template locally. Moving the check into a Python property fixed
  it for real.
- e2e test / README / docs: use `data.channels.<IFO>: INJ` (confirmed
  directly from `simple_pe_pipe --help`: a documented magic value
  meaning "simulate an injection, don't read real strain data") instead
  of a made-up literal channel name (`H1:FAKE-STRAIN`). With a literal
  name, `simple_pe_pipe` reads it as a real channel to look up via
  datafind -- confirmed directly via this plugin's own e2e CI, where the
  DAG's `datafind` node hung for the full job timeout trying to reach a
  real datafind service that doesn't exist in the sandboxed HTCondor
  container. `--help` also documents a `GWOSC` magic value for reading
  public GWOSC open data, now documented alongside `INJ`.
- `configs/simplepe.ini`: `channels`/`asd` now render in the one format
  that actually survives `simple_pe_pipe`'s real config-file handling --
  a brace-wrapped, comma-separated `{IFO:value,IFO:value}` string, with
  channel names *not* repeating the `IFO:` prefix already used as the
  dict key. `simple_pe_pipe --help` describes these as space-separated
  CLI tokens (`nargs='+'`), which is what the previous two attempts at
  this fix used -- but that only describes real command-line invocation.
  Reading the real installed `simple_pe_pipe` source (dumped in CI, since
  `git.ligo.org` isn't reachable from where this plugin is authored)
  showed its config-file handling is actually
  `pesummary.core.cli.actions.ConfigAction`, which does its own separate,
  ad-hoc ini-to-dict parsing (`dict_from_str()`) wherever a value
  contains `:` or `{`, entirely bypassing argparse's own nargs/type
  machinery for ini-sourced values. Confirmed directly against the real,
  installed `pesummary` package (a `simple-pe` dependency, and public on
  PyPI, unlike `simple-pe` itself) that `dict_from_str()` requires the
  brace-wrapped form and cannot handle a colon *inside* a value at all --
  matching `--help`'s own example (`H1:HWINJ_INJECTED`, not
  `H1:H1:HWINJ_INJECTED`) once actually read literally. Every other
  config key (`trigger_time`, `trigger_parameters`, `outdir`, `f_low`,
  `f_high`, `approximant`, `accounting_group`, `accounting_group_user`,
  `generate_corner`) was already correct, confirmed by `simple_pe_pipe`'s
  own printed argument `Namespace` in CI.

### Added
- `scripts/patch_simple_pe_reweight_guard.py`, a short-term stopgap for
  the confirmed upstream `pesummary` reweighting `OverflowError`
  documented under "Fixed" above (see the "e2e test: the completion
  criterion..." entry). Reading `simple_pe_analysis`'s complete, real
  argument list and `main()` (`simple_pe/cli/simple_pe_analysis.py`)
  confirmed there is genuinely no CLI/ini-level way to disable or route
  around its unconditional reweighting call -- so the only way to
  actually unblock full posterior-sample generation in the short term,
  rather than just fail cleanly (which is all the `resurrect()` fix
  above does), is to patch the bug itself. The script patches an
  installed `simple-pe`'s `reweight_based_on_observed_snrs()`
  (`simple_pe/param_est/pe.py`) in place, zeroing out any non-finite
  weight (`np.nan_to_num(..., nan=0.0, posinf=0.0, neginf=0.0)`) before
  it reaches `pesummary.core.reweight.rejection_sampling()` -- treating a
  numerically broken sample (one whose subdominant-SNR calculation hit
  the underlying divide-by-zero) as zero-probability (rejected) rather
  than crashing the whole run, or -- worse -- as *certain* (an
  unguarded `inf` weight always wins rejection sampling against every
  finite-weight sample, which would silently produce a degenerate,
  scientifically meaningless posterior even if it didn't crash first).
  Verified directly: reproduces the real `OverflowError` unpatched and
  confirms the guarded weights never select the broken (inf/nan) samples,
  against the exact `rejection_sampling()` logic from a real, freshly
  downloaded `pesummary` 1.7.0. The patch itself is idempotent (a no-op
  if already applied) and, deliberately, is not a blind `sed`: it matches
  the exact expected original source text and exits non-zero (rather
  than silently no-opping) if that text isn't found, so a future upstream
  change to this function surfaces as a clear CI failure instead of
  quietly leaving the crash unpatched. It also takes care to preserve the
  installed file's real CRLF line endings (confirmed directly: Python's
  default text-mode I/O would otherwise silently rewrite the *entire*
  file to LF on save, turning a small, precise one-function patch into a
  spurious file-wide diff). This can't be a plugin-level Python
  monkeypatch inside `asimov_simplepe` itself: the buggy code runs inside
  `simple_pe_analysis`'s own HTCondor subprocess, a completely separate
  Python process from asimov's, so patching the installed package is the
  only mechanism that actually reaches it. `.github/actions/
  setup-simplepe-env/action.yml` now applies this same script during
  environment setup (once per freshly-populated conda-env cache, matching
  the existing `setuptools`/`numpy` pin steps' pattern), and `e2e.yml`
  gained a new, deliberately non-blocking diagnostic step that reports
  whether this actually unblocks a real posterior-samples file against
  real GWOSC data, ahead of promoting that to a hard pass/fail
  requirement (and updating this plugin's own completion-criterion
  claims to match) in a follow-up change once confirmed by a real run.
  This is a stopgap, not a substitute for a real fix landing upstream in
  either `simple-pe` or `pesummary` -- see README.md's "Short-term
  workaround" note for user-facing instructions to apply the same patch
  to a real deployment environment.
- Initial release of the `asimov-simplepe` plugin, integrating
  [simple-pe](https://git.ligo.org/stephen-fairhurst/simple-pe) (a rapid,
  metric/Fisher-matrix-based parameter estimation code) with
  [Asimov](https://github.com/etive-io/asimov) 0.7+.
- `config_template` (`asimov_simplepe/configs/simplepe.ini`), a bundled
  Liquid template rendering a `simple_pe_pipe` ini from a production's
  ledger metadata (`data.channels`/`data.asd`, `waveform.approximant`,
  `likelihood.minimum frequency`, `scheduler.accounting group`), following
  the same `production.meta` key conventions as the sibling
  `asimov-pycbc`/`asimov-lalinference` plugins.
- `before_config()` writes a small `trigger_parameters.json` file (the
  approximate event parameters `simple_pe_pipe` uses to seed its local
  optimisation) into the run directory before the main ini is rendered.
- `build_dag()` shells out to `simple_pe_pipe`, which builds a real
  HTCondor DAG (and a companion local-run bash script); `submit_dag()`
  submits that DAG through Asimov's scheduler abstraction
  (`self.scheduler.submit_dag(...)`), supporting both HTCondor and Slurm --
  matching the pattern used by the sibling `asimov-lalinference` plugin
  (a `_pipe`-style DAG generator), rather than `asimov-pycbc`'s
  single-job submission (`pycbc_inference` has no separate DAG-building
  step of its own).
- `collect_assets()` advertises a completed job's samples (and rendered
  config) for any downstream production that declares a `needs:`
  dependency on it -- e.g. an
  [asimov-pesummary](https://github.com/etive-io/asimov-pesummary)
  post-processing production, resolved entirely by Asimov's own
  dependency graph. `after_completion()` itself does nothing beyond
  marking the production `finished`.
- DAG-rescue-aware `resurrect()`: a failed/evicted job leaves a DAGMan
  rescue file (`*.rescue*`) behind; resubmitting picks it up
  automatically, up to 5 attempts.
- Unit test suite (mocked `production`/`config` fixtures), plus a test
  that renders `configs/simplepe.ini` through the real Liquid engine.
- A genuine end-to-end test (`.github/workflows/e2e.yml`): a real
  `simple_pe_pipe` DAG built and submitted through a real HTCondor
  scheduler against real GW150914 GWOSC data, waiting for and validating
  the real `peak_parameters.json`/`peak_snrs.json` output its `analysis`
  node produces. It does not currently wait for a full posterior-samples
  file -- see the "Fixed" entries below documenting the confirmed upstream
  `pesummary` reweighting bug that blocks that output against this
  dataset.

### Fixed
- `.github/actions/setup-simplepe-env` now pins `setuptools<82` before
  installing `simple_pe_pipe`: `simple_pe_pipe` imports `pycbc.waveform`,
  whose `retrieve_waveform_plugins()` does a bare `import pkg_resources`
  (see [simple-pe issue #29](https://git.ligo.org/stephen-fairhurst/simple-pe/-/issues/29),
  still open upstream). `setuptools` removed the bundled `pkg_resources`
  module starting with 82.0.0 (confirmed directly: 81.0.0 still provides
  it, 82.0.0 doesn't); without the pin, `simple_pe_pipe` fails to even
  import (`ModuleNotFoundError: No module named 'pkg_resources'`) --
  confirmed directly via this plugin's own e2e CI run against the real,
  live `simple_pe_pipe`, which is exactly the failure this fix addresses.
  (An earlier, unpinned `pip install setuptools` fix looked plausible
  locally but didn't actually resolve this -- the environment already had
  `setuptools`, just a too-new version -- so this is a stricter follow-up,
  found by empirically bisecting setuptools releases with a real
  `import pkg_resources` check rather than assuming a specific version
  boundary.)

### Notes
- `configs/simplepe.ini`'s config keys (`trigger_time`, `trigger_parameters`,
  `outdir`, `channels`, `asd`, `f_low`, `f_high`, `approximant`,
  `accounting_group`, `accounting_group_user`, `generate_corner`) and
  value formats are now confirmed directly against a real, live
  `simple_pe_pipe --help` and a real successful DAG build in this
  plugin's own e2e CI, not just its public documentation/issue tracker.
  `samples()`'s output-filename glob patterns remain a best-effort guess,
  not yet confirmed against a real completed run -- please file an issue
  (or PR) if you find a mismatch there.
