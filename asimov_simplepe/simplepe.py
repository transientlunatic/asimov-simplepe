"""Simple-PE Pipeline specification for Asimov.

`simple-pe <https://git.ligo.org/stephen-fairhurst/simple-pe>`_ is a rapid,
metric/Fisher-matrix-based parameter estimation code for gravitational-wave
signals from compact binary coalescences: rather than a full stochastic
(MCMC/nested-sampling) exploration of the likelihood, it expands the
likelihood locally around a matched-filter trigger to produce an approximate
posterior in CPU-minutes. Its pipeline generator, ``simple_pe_pipe``, reads
an ini file and builds both a real HTCondor DAG (submittable via a
scheduler) and a companion bash script for a local run -- the same shape as
the sibling ``lalinference_pipe``/``bayeswave_pipe`` tools, which is the
pattern this plugin follows (see ``asimov_lalinference`` for the closest
sibling): shell out to build a DAG, then submit it through Asimov's own
scheduler abstraction rather than talking to HTCondor/Slurm directly.
"""

import configparser
import glob
import importlib.resources
import os
import shutil
import subprocess

from asimov import config
from asimov.pipeline import Pipeline, PipelineException, PipelineLogger
from asimov.utils import set_directory


class SimplePE(Pipeline):
    """
    The Simple-PE pipeline integration for Asimov.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "analyses".
    """

    name = "SimplePE"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(SimplePE, self).__init__(production, category)
        if not production.pipeline.lower() == "simplepe":
            raise PipelineException("Pipeline mismatch")

    @property
    def config_template(self):
        """
        The bundled Liquid template used to render a production's ``.ini``
        file when one doesn't already exist in the event repository.

        Asimov's generic ``manage build`` step calls ``production.make_config()``,
        which looks for this attribute on the pipeline (see
        ``Analysis.make_config`` in asimov core) before falling back to a
        template bundled inside asimov's own package -- which doesn't ship
        a Simple-PE template.
        """
        return str(
            importlib.resources.files("asimov_simplepe").joinpath(
                "configs/simplepe.ini"
            )
        )

    def _ensure_rundir(self):
        """
        Resolve ``self.production.rundir`` to an absolute path (falling back
        to Asimov's configured default run directory if the production
        doesn't already have one) and make sure it exists on disk.
        """
        if self.production.rundir:
            self.production.rundir = os.path.abspath(self.production.rundir)
        else:
            self.production.rundir = os.path.join(
                config.get("general", "rundir_default"),
                self.production.event.name,
                self.production.name,
            )
        os.makedirs(self.production.rundir, exist_ok=True)
        return self.production.rundir

    def _trigger_parameters_file(self):
        """
        The path to the small ini file listing the approximate trigger
        parameters (masses, spins, sky location, ...) that seeds
        ``simple_pe_pipe``'s local optimisation -- referenced by the
        ``trigger_parameters`` key in the main config
        (``configs/simplepe.ini``).
        """
        return os.path.join(self.production.rundir, "trigger_parameters.ini")

    def before_config(self, dryrun=False):
        """
        Write the trigger-parameters file before Asimov renders this
        production's main ``.ini`` from ``config_template``.

        Called by Asimov's ``manage build`` step (``production.pipeline.before_config()``)
        immediately before ``production.make_config()``, so the rundir (and
        therefore the trigger-parameters path the template renders into
        ``trigger_parameters =``) already exists on disk by the time the
        template is rendered.
        """
        self._ensure_rundir()
        trigger = self.production.meta.get("trigger", {})
        parser = configparser.RawConfigParser()
        parser.add_section("parameters")
        values = {
            "time": self.production.meta.get("event time", ""),
            "mass1": trigger.get("mass1", ""),
            "mass2": trigger.get("mass2", ""),
            "spin1z": trigger.get("spin1z", 0),
            "spin2z": trigger.get("spin2z", 0),
            "ra": trigger.get("ra", 0),
            "dec": trigger.get("dec", 0),
            "distance": trigger.get("distance", 400),
            "phase": trigger.get("phase", 0),
            "psi": trigger.get("psi", 0),
        }
        for key, value in values.items():
            parser.set("parameters", key, str(value))
        with open(self._trigger_parameters_file(), "w") as trigger_file:
            parser.write(trigger_file)

    def _executable(self):
        """
        Resolve the ``simple_pe_pipe`` executable.

        Resolved defensively rather than assuming
        ``config["pipelines"]["environment"]/bin/simple_pe_pipe`` exists
        (matching the approach used by the sibling asimov-pycbc/
        asimov-lalinference plugins): in minimal/containerised environments
        that config value may not point at the active environment.
        ``shutil.which`` also picks up an explicit per-production override
        via ``production.meta["executable"]``.
        """
        default_executable = os.path.join(
            config.get("pipelines", "environment"), "bin", "simple_pe_pipe"
        )
        executable = self.production.meta.get("executable", default_executable)
        executable = shutil.which(executable) or shutil.which("simple_pe_pipe")
        if executable is None:
            raise PipelineException(
                "Cannot find the simple_pe_pipe executable",
                production=self.production.name,
            )
        return executable

    def _dag_file(self):
        """
        Locate the HTCondor DAG file ``simple_pe_pipe`` writes into the run
        directory. Located by glob rather than a fixed filename, since
        ``simple_pe_pipe`` (like ``lalinference_pipe``) may nest it inside a
        ``submit``-style subdirectory.
        """
        direct = glob.glob(os.path.join(self.production.rundir, "*.dag"))
        if direct:
            return sorted(direct)[0]
        nested = glob.glob(
            os.path.join(self.production.rundir, "**", "*.dag"), recursive=True
        )
        return sorted(nested)[0] if nested else None

    def build_dag(self, dryrun=False):
        """
        Run ``simple_pe_pipe`` against this production's ini file to build
        an HTCondor DAG.

        Parameters
        ----------
        dryrun : bool, optional
           If True then the command will not be run, but will be printed to
           standard output. Defaults to False.

        Raises
        ------
        PipelineException
           Raised if the construction of the DAG fails, or if
           ``simple_pe_pipe`` exits successfully but no DAG file is found.
        """
        self._ensure_rundir()

        if self.production.event.repository:
            configs = self.production.event.repository.find_prods(
                self.production.name, self.category
            )
            if not configs:
                raise PipelineException(
                    f"No configuration file found for {self.production.name} "
                    f"in the event repository's '{self.category}' directory.",
                    production=self.production.name,
                )
            ini = os.path.join(
                self.production.event.repository.directory, self.category, configs[0]
            )
        else:
            ini = f"{self.production.name}.ini"

        if dryrun:
            print(f"simple_pe_pipe {ini}")
            return ini

        command = [self._executable(), ini]
        self.logger.info(" ".join(command))
        try:
            pipe = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.production.rundir,
            )
        except FileNotFoundError as error:
            raise PipelineException(
                f"simple_pe_pipe not found at {command[0]}. "
                "Check that [pipelines] environment is set correctly.",
                production=self.production.name,
            ) from error

        out, _ = pipe.communicate()
        out = out.decode(errors="replace") if isinstance(out, bytes) else out

        dag_file = self._dag_file()
        if pipe.returncode != 0 or dag_file is None:
            self.production.status = "stuck"
            self.logger.error(f"DAG file could not be created.\n{command}\n{out}")
            raise PipelineException(
                f"DAG file could not be created.\n{command}\n{out}",
                production=self.production.name,
            )

        self.logger.info(f"DAG created: {dag_file}")
        return PipelineLogger(message=out, production=self.production.name)

    def submit_dag(self, dryrun=False):
        """
        Submit the DAG built by :meth:`build_dag` to the scheduler.

        Uses Asimov's scheduler abstraction (``self.scheduler``, HTCondor
        or Slurm) rather than hand-rolling ``htcondor``/``htcondor2`` calls
        directly.

        Parameters
        ----------
        dryrun : bool, optional
           If True then the job will not be submitted, but the command will
           be printed to standard output.

        Returns
        -------
        int
           The cluster ID assigned to the submitted DAG.

        Raises
        ------
        PipelineException
           This will be raised if the pipeline fails to submit the job.
        """
        with set_directory(self.production.rundir):
            self.before_submit(dryrun=dryrun)

            dag_path = self._dag_file()
            batch_name = f"SimplePE/{self.production.event.name}/{self.production.name}"

            if dag_path is None:
                raise PipelineException(
                    f"No DAG file found in {self.production.rundir}; "
                    "build_dag() must be run (and succeed) first.",
                    production=self.production.name,
                )

            if dryrun:
                print(f"Would submit DAG: {dag_path} with batch name: {batch_name}")
                return None

            try:
                cluster_id = self.scheduler.submit_dag(
                    dag_file=dag_path, batch_name=batch_name
                )
            except (FileNotFoundError, RuntimeError) as error:
                raise PipelineException(
                    f"The DAG file could not be submitted: {error}",
                    production=self.production.name,
                ) from error

        self.production.status = "running"
        self.production.job_id = cluster_id
        self.logger.info(f"Submitted SimplePE DAG: {self.production.job_id}")
        return cluster_id

    def samples(self):
        """
        Collect the posterior samples file(s) produced by this run, for
        PESummary (or any other downstream consumer wired up via
        ``needs:``) to pick up.

        ``simple_pe_pipe``'s exact output filename isn't fixed by this
        plugin -- it's located by searching the run directory for a
        recognisable posterior/samples file, broadest match first.
        """
        if not self.production.rundir:
            return []
        patterns = (
            "posterior_samples.h5",
            "posterior_samples.dat",
            "*posterior*.h5",
            "*posterior*.dat",
            "*samples*.h5",
            "*samples*.dat",
        )
        for pattern in patterns:
            matches = sorted(
                glob.glob(
                    os.path.join(self.production.rundir, "**", pattern),
                    recursive=True,
                )
            )
            if matches:
                return matches
        return []

    def detect_completion(self):
        """
        Check for the production of a posterior samples file to signal that
        the job has completed.
        """
        return bool(self.samples())

    def collect_assets(self):
        """
        Gather the results assets for this job, so that a downstream
        production (for example a PESummary post-processing production
        wired up via ``needs:``) can pick them up through
        ``production._previous_assets()``.
        """
        assets = {"samples": self.samples()}
        if self.production.event.repository:
            configs = self.production.event.repository.find_prods(
                self.production.name, self.category
            )
            if configs:
                assets["config"] = configs[0]
        return assets

    def collect_logs(self):
        """
        Collect all of the log files which have been produced by this
        production and return their contents as a dictionary.
        """
        logs = (
            glob.glob(os.path.join(self.production.rundir, "**", "*.err"), recursive=True)
            + glob.glob(os.path.join(self.production.rundir, "**", "*.out"), recursive=True)
            + glob.glob(os.path.join(self.production.rundir, "**", "*.log"), recursive=True)
        )
        messages = {}
        for log in logs:
            with open(log, "r") as log_f:
                messages[os.path.basename(log)] = log_f.read()
        return messages

    def after_completion(self):
        """
        Mark this production as finished once its job has completed.

        This deliberately does *not* reach out and submit a PESummary (or
        any other) post-processing job itself. Post-processing is instead
        expressed as its own, separate production with a ``needs:``
        dependency on this one (see e.g.
        `asimov-pesummary <https://github.com/etive-io/asimov-pesummary>`_):
        Asimov's own dependency resolution builds and submits that
        production once this one reaches ``finished``, and it picks up
        this production's samples via ``collect_assets()`` through
        ``production._previous_assets()``. This matches the pattern used
        by the sibling ``asimov-pycbc``/``asimov-lalinference`` plugins.
        """
        super().after_completion()

    def resurrect(self):
        """
        Attempt to resurrect a failed or evicted job by resubmitting its
        DAG.

        Like ``lalinference_pipe``, ``simple_pe_pipe`` builds a real
        HTCondor DAG, so an interrupted run leaves a DAGMan rescue file
        (``*.rescue*``) behind; resubmitting picks it up automatically.
        """
        try:
            count = self.production.meta["resurrections"]
        except KeyError:
            count = 0
        rescue_files = glob.glob(
            os.path.join(self.production.rundir, "**", "*.rescue*"), recursive=True
        )
        if count < 5 and rescue_files:
            count += 1
            self.production.meta["resurrections"] = count
            self.submit_dag()
