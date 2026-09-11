# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
  scheduler, waiting for a real, parseable posterior samples file.

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
