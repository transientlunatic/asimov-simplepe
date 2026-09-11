# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Notes
- `simple_pe_pipe`'s exact ini schema and output filenames are not fully
  documented publicly; this plugin's `configs/simplepe.ini` template and
  `samples()` glob patterns are a best-effort match against the
  confirmed-public subset of `simple_pe_pipe`'s config keys (`trigger_time`,
  `trigger_parameters`, `outdir`, `channels`, `asd`, `f_low`, `f_high`,
  `approximant`, `accounting_group`, `accounting_group_user`,
  `generate_corner`) and the DAG/bash-script-generating behaviour described
  in its documentation. See the *Compatibility* section of the README for
  details, and please file an issue (or PR) if you find a mismatch against
  a real `simple_pe_pipe` release.
