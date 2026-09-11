# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
- `before_config()` writes a small `trigger_parameters.ini` file (the
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
