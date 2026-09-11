# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `configs/simplepe.ini`: `channels`/`asd` now render as `simple_pe_pipe`'s
  own `--help` says they must be -- space-separated `IFO:VALUE` tokens
  (e.g. `H1:path/to/file L1:path/to/file`), not a Python dict literal.
  Confirmed directly via this plugin's own e2e CI run against the real,
  live `simple_pe_pipe`: with the dict-literal form, `simple_pe_pipe`
  actually ran (this is what confirmed every other config key --
  `trigger_time`, `trigger_parameters`, `outdir`, `f_low`, `f_high`,
  `approximant`, `accounting_group`, `accounting_group_user`,
  `generate_corner` -- was already correct) but crashed with
  `AttributeError: 'str' object has no attribute 'items'` while building
  its argument list, because `--asd`'s dict-literal string happened to
  parse via `ast.literal_eval` while `--channels`'s didn't.

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
