# asimov-simplepe

An [Asimov](https://github.com/etive-io/asimov) plugin for running
[simple-pe](https://git.ligo.org/stephen-fairhurst/simple-pe), a rapid,
metric/Fisher-matrix-based parameter estimation code for gravitational-wave
signals from compact binary coalescences.

📚 **[Full documentation and tutorial](https://transientlunatic.github.io/asimov-simplepe/)**

## Overview

Unlike a full stochastic (MCMC/nested-sampling) parameter estimation
pipeline, `simple-pe` expands the likelihood locally around a matched-filter
trigger to produce an approximate posterior in CPU-minutes rather than
CPU-days -- useful for low-latency estimates, and as a fast cross-check or
seed for a more detailed run. This plugin enables Asimov to build and submit
`simple_pe_pipe` jobs for that analysis. It provides:

- **Configuration templating**: renders a `simple_pe_pipe` config file from
  a bundled Liquid template, populated from a production's ledger metadata
  (`config_template`), for use by `asimov manage build`.
- **Trigger-parameter seeding**: writes the small `trigger_parameters.ini`
  file `simple_pe_pipe` uses to seed its local optimisation, before the
  main config is rendered.
- **DAG generation and scheduler integration**: `simple_pe_pipe` builds a
  real HTCondor DAG (plus a companion local-run bash script); this plugin
  submits that DAG via Asimov's own scheduler abstraction (`self.scheduler`,
  from `asimov.pipeline.Pipeline`), which supports both HTCondor and
  Slurm -- rather than talking to a scheduler's API directly.
- **Status tracking**: monitors job completion by checking for a genuine
  posterior samples file.
- **DAG-rescue-aware resurrection**: like `lalinference_pipe`,
  `simple_pe_pipe` produces a real DAGMan workflow; an interrupted run
  leaves a rescue DAG behind, which is resubmitted automatically.
- **Dependency-driven post-processing**: once a job completes, its samples
  are available (via `collect_assets()`) to any downstream production with
  a `needs:` dependency on it -- for example an
  [asimov-pesummary](https://github.com/etive-io/asimov-pesummary)
  production. This plugin doesn't submit that job itself; Asimov's own
  dependency resolution does.

## Compatibility

Requires `asimov>=0.7`. This plugin does not depend on the `simple-pe`
Python package itself -- like the sibling `asimov-lalinference` and
`asimov-bayeswave` plugins, it shells out to the `simple_pe_pipe`
executable, which is expected to be installed separately in the environment
pointed at by Asimov's `[pipelines] environment` config option.

`simple-pe` is not currently distributed on PyPI or conda-forge; install it
from its GitLab repository (it depends on `pycbc` and `lalsuite`, both
available from conda-forge):

```bash
conda install -c conda-forge pycbc lalsuite
echo "setuptools<82" > constraints.txt  # see note below
pip install -c constraints.txt "setuptools<82"
pip install -c constraints.txt git+https://git.ligo.org/stephen-fairhurst/simple-pe.git
```

> **`pkg_resources` note.** `simple_pe_pipe` imports `pycbc.waveform`, which
> does a bare `import pkg_resources` in `retrieve_waveform_plugins()` (see
> [simple-pe issue #29](https://git.ligo.org/stephen-fairhurst/simple-pe/-/issues/29),
> still open upstream). `setuptools` removed the bundled `pkg_resources`
> module starting with 82.0.0 (confirmed directly: 81.0.0 still provides
> it, 82.0.0 doesn't), so `simple_pe_pipe` fails to even import with
> `ModuleNotFoundError: No module named 'pkg_resources'` against an
> unpinned (or too-recent) `setuptools` -- confirmed directly via this
> plugin's own CI. A bare `pip install "setuptools<82"` isn't enough on
> its own, either: installing `simple-pe` in a *separate* `pip install`
> right after it can silently re-resolve `setuptools` back past 82 as one
> of its own transitive dependencies (also confirmed directly). A
> constraints file applied to both commands, as above, is what actually
> holds the pin.

> **A note on the config schema below.** The keys used by this plugin's
> bundled template (`configs/simplepe.ini`) -- `trigger_time`,
> `trigger_parameters`, `outdir`, `channels`, `asd`, `f_low`, `f_high`,
> `approximant`, `accounting_group`, `accounting_group_user`,
> `generate_corner` -- and their value formats are confirmed directly
> against a real, live `simple_pe_pipe --help` and a real successful DAG
> build in this plugin's own end-to-end CI. Its output-file detection
> (`samples()`) is still an unconfirmed best-effort guess, though: it
> searches for common posterior/samples filenames rather than one exact
> confirmed name. If you hit a mismatch there (or anywhere else) against a
> real `simple_pe_pipe` release, please open an issue or PR.

## Installation

```bash
pip install asimov-simplepe
```

For development:
```bash
git clone https://github.com/transientlunatic/asimov-simplepe
cd asimov-simplepe
pip install -e ".[test]"
```

## Usage

Once installed, Asimov discovers this plugin automatically via its
`asimov.pipelines` entry point. Add a production to an event with
`pipeline: simplepe`:

```yaml
kind: analysis
name: simplepe-imrphenomxphm
pipeline: simplepe
waveform:
  approximant: IMRPhenomXPHM
likelihood:
  minimum frequency:
    H1: 20
    L1: 20
scheduler:
  accounting group: ligo.dev.o4.cbc.pe.simple_pe
```

`asimov manage build submit` will render a `simple_pe_pipe` ini (and the
accompanying trigger-parameters file) from the bundled template (unless a
config already exists in the event repository), build a DAG, and submit it.

### Data

Strain data is read from a production's `data` metadata, using the same
conventions as the other Asimov gravitational-wave pipeline plugins (e.g.
`asimov-gwdata`, `asimov-lalinference`, `asimov-pycbc`):

- `data.channels` -- per-interferometer strain channel name, *without*
  the leading `IFO:` (this plugin adds that itself when rendering the
  ini). `simple_pe_pipe` also recognises two special values here,
  confirmed directly from its own `--help` text: `GWOSC` to read public
  GWOSC open data instead of a private frame channel, and `INJ` to have
  `simple_pe_pipe` simulate an injection itself rather than reading any
  real strain data at all -- no datafind access needed (this is what
  this plugin's own end-to-end test uses). When any interferometer uses
  `INJ`, `before_config()` also writes an `injection.json` file from the
  production's `trigger` metadata and the ini references it via
  `injection = ...` -- `simple_pe_datafind` requires this unconditionally
  in that case (confirmed directly from its real source, via this
  plugin's own e2e CI).
- `data.asd` -- per-interferometer path to a real, two-column (frequency,
  ASD) text file. There is no analytic-PSD-model-name shortcut here --
  confirmed directly from `--help` ("ASD files to use for the analysis")
  and from this plugin's own e2e CI, which generates a real file from
  pycbc's analytic `aLIGOZeroDetHighPower` model for its `INJ`-mode test.

This means a production populated by a data-retrieval step (for example
[asimov-gwdata](https://github.com/etive-io/asimov-gwdata)) can be picked
up by making the `simplepe` production `needs:` that data-retrieval
production and mapping its output into `data.channels`/`data.asd` (stripping
the data-retrieval step's own `IFO:` channel prefix, if it includes one).

### Trigger parameters

`simple_pe_pipe` seeds its local optimisation from an approximate set of
trigger parameters (masses, spins, sky location). Supply these via a
`trigger` block on the production:

```yaml
trigger:
  mass1: 36
  mass2: 29
  spin1z: 0.0
  spin2z: 0.0
  ra: 1.95
  dec: -1.27
  distance: 440
  phase: 0
  psi: 0
```

Any parameter left unset falls back to a sensible default (masses/sky
location are otherwise left blank, spins/phase/psi default to 0, distance
defaults to 400 Mpc); `time` is always taken from the event's `event time`.

### Post-processing

This plugin does not run PESummary (or anything else) itself. When a
`simplepe` production completes, `after_completion()` only marks it
`finished` -- post-processing is expressed as a separate production with a
`needs:` dependency on it, e.g.:

```yaml
kind: analysis
name: simplepe-test-pesummary
pipeline: pesummary
needs:
  - simplepe-imrphenomxphm
postprocessing:
  pesummary:
    multiprocess: 2
```

Asimov's own dependency resolution builds and submits
`simplepe-test-pesummary` once `simplepe-imrphenomxphm` reaches `finished`;
PESummary picks up its samples via `simplepe-imrphenomxphm`'s
`collect_assets()` (through `production._previous_assets()`).

## Testing

Unit tests (mocked, no external dependencies):

```bash
pip install -e ".[test]"
pytest
```

`.github/workflows/e2e.yml` also runs a genuine end-to-end test: a real
`simple_pe_pipe` DAG built and submitted through a real HTCondor scheduler,
waiting for a real, parseable posterior samples file.

`.github/workflows/docs.yml` also checks that the subcommand and flags used
by every `asimov ...` command shown in `docs/*.rst` still exist on the live,
installed asimov CLI, on every pull request
(`scripts/lint_tutorial_commands.py`).

## Contributing

Contributions welcome! Please submit issues or pull requests to
[transientlunatic/asimov-simplepe](https://github.com/transientlunatic/asimov-simplepe).

## License

MIT -- see [LICENSE](LICENSE).
