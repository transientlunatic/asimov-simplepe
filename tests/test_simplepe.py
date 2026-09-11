"""Tests for the Simple-PE pipeline integration."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from asimov.pipeline import PipelineException

from asimov_simplepe import SimplePE


class TestSimplePEInit:
    """Test SimplePE initialization."""

    def test_init_success(self, mock_production, mock_config):
        pipeline = SimplePE(mock_production)
        assert pipeline.name == "SimplePE"
        assert pipeline.production == mock_production
        assert "wait" in pipeline.STATUS

    def test_init_wrong_pipeline(self, mock_production, mock_config):
        mock_production.pipeline = "bilby"
        with pytest.raises(PipelineException, match="Pipeline mismatch"):
            SimplePE(mock_production)

    def test_init_pipeline_check_is_case_insensitive(self, mock_production, mock_config):
        mock_production.pipeline = "SimplePE"
        SimplePE(mock_production)  # should not raise

    def test_init_sets_up_logger(self, mock_production, mock_config):
        pipeline = SimplePE(mock_production)
        assert pipeline.logger is not None


class TestConfigTemplate:
    """Test the config_template property used by asimov's `manage build`
    to render an ini when one doesn't already exist in the event
    repository."""

    def test_config_template_is_a_real_bundled_file(self, mock_production, mock_config):
        pipeline = SimplePE(mock_production)
        assert os.path.exists(pipeline.config_template)

    def test_config_template_is_named_simplepe_ini(self, mock_production, mock_config):
        pipeline = SimplePE(mock_production)
        assert os.path.basename(pipeline.config_template) == "simplepe.ini"


class TestBeforeConfig:
    """Test the trigger-parameters file written before the main ini is
    rendered."""

    def test_writes_trigger_parameters_file(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        pipeline.before_config()

        trigger_file = os.path.join(mock_production.rundir, "trigger_parameters.ini")
        assert os.path.exists(trigger_file)

    def test_trigger_parameters_contents(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        pipeline.before_config()

        from asimov.pipeline import Pipeline

        parser = Pipeline.read_ini(
            os.path.join(mock_production.rundir, "trigger_parameters.ini")
        )
        assert parser.get("parameters", "mass1") == "36"
        assert parser.get("parameters", "mass2") == "29"
        assert parser.get("parameters", "time") == "1126259462.4"

    def test_trigger_parameters_defaults_when_no_trigger_meta(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        mock_production.meta = dict(mock_production.meta)
        mock_production.meta.pop("trigger")
        pipeline = SimplePE(mock_production)

        pipeline.before_config()  # must not raise

        from asimov.pipeline import Pipeline

        parser = Pipeline.read_ini(
            os.path.join(mock_production.rundir, "trigger_parameters.ini")
        )
        assert parser.get("parameters", "spin1z") == "0"
        assert parser.get("parameters", "distance") == "400"

    def test_ensures_rundir_exists(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        pipeline.before_config()

        assert os.path.isdir(mock_production.rundir)


class TestBuildDag:
    """Test DAG construction via a real `simple_pe_pipe` subprocess call."""

    def test_build_dag_resolves_rundir(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        pipeline.build_dag(dryrun=True)

        assert os.path.isdir(mock_production.rundir)
        assert os.path.isabs(mock_production.rundir)

    def test_build_dag_falls_back_to_rundir_default(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = None
        mock_config.get = lambda section, key: (
            temp_dir if (section, key) == ("general", "rundir_default") else ""
        )
        pipeline = SimplePE(mock_production)

        pipeline.build_dag(dryrun=True)

        assert mock_production.rundir == os.path.join(
            temp_dir, mock_production.event.name, mock_production.name
        )

    def test_build_dag_dryrun_does_not_invoke_subprocess(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        with patch("asimov_simplepe.simplepe.subprocess.Popen") as mock_popen:
            pipeline.build_dag(dryrun=True)
            mock_popen.assert_not_called()

    def test_build_dag_dryrun_returns_ini_path(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        ini = pipeline.build_dag(dryrun=True)

        assert ini.endswith("TestProduction.ini")

    def test_build_dag_uses_simple_pe_pipe_executable(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        pipeline = SimplePE(mock_production)

        def fake_popen(command, **kwargs):
            open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()
            proc = MagicMock()
            proc.communicate.return_value = (b"", None)
            proc.returncode = 0
            return proc

        with patch(
            "asimov_simplepe.simplepe.shutil.which",
            return_value="/opt/conda/bin/simple_pe_pipe",
        ), patch(
            "asimov_simplepe.simplepe.subprocess.Popen", side_effect=fake_popen
        ) as mock_popen:
            pipeline.build_dag(dryrun=False)

        command = mock_popen.call_args[0][0]
        assert command[0] == "/opt/conda/bin/simple_pe_pipe"
        assert command[1].endswith("TestProduction.ini")

    def test_build_dag_success_returns_pipeline_logger(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        pipeline = SimplePE(mock_production)

        def fake_popen(command, **kwargs):
            open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()
            proc = MagicMock()
            proc.communicate.return_value = (b"Some output", None)
            proc.returncode = 0
            return proc

        with patch(
            "asimov_simplepe.simplepe.shutil.which",
            return_value="/opt/conda/bin/simple_pe_pipe",
        ), patch("asimov_simplepe.simplepe.subprocess.Popen", side_effect=fake_popen):
            result = pipeline.build_dag(dryrun=False)

        assert result is not None
        assert "Some output" in result.message

    def test_build_dag_nonzero_returncode_raises(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        pipeline = SimplePE(mock_production)

        def fake_popen(command, **kwargs):
            proc = MagicMock()
            proc.communicate.return_value = (b"some error", None)
            proc.returncode = 1
            return proc

        with patch(
            "asimov_simplepe.simplepe.shutil.which",
            return_value="/opt/conda/bin/simple_pe_pipe",
        ), patch("asimov_simplepe.simplepe.subprocess.Popen", side_effect=fake_popen):
            with pytest.raises(PipelineException):
                pipeline.build_dag(dryrun=False)

        assert mock_production.status == "stuck"

    def test_build_dag_success_exit_but_no_dag_file_raises(
        self, mock_production, mock_config, temp_dir
    ):
        # Zero exit code but simple_pe_pipe didn't actually write a .dag
        # file -- must not be treated as success.
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        pipeline = SimplePE(mock_production)

        def fake_popen(command, **kwargs):
            proc = MagicMock()
            proc.communicate.return_value = (b"", None)
            proc.returncode = 0
            return proc

        with patch(
            "asimov_simplepe.simplepe.shutil.which",
            return_value="/opt/conda/bin/simple_pe_pipe",
        ), patch("asimov_simplepe.simplepe.subprocess.Popen", side_effect=fake_popen):
            with pytest.raises(PipelineException, match="DAG file could not be created"):
                pipeline.build_dag(dryrun=False)

    def test_build_dag_missing_executable_raises_clear_exception(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = SimplePE(mock_production)

        with patch("asimov_simplepe.simplepe.shutil.which", return_value=None):
            with pytest.raises(PipelineException, match="simple_pe_pipe"):
                pipeline.build_dag(dryrun=False)

    def test_build_dag_no_repository_uses_bare_ini_name(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        mock_production.event.repository = None
        pipeline = SimplePE(mock_production)

        ini = pipeline.build_dag(dryrun=True)

        assert ini == "TestProduction.ini"

    def test_build_dag_no_config_in_repository_raises(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        mock_production.event.repository.find_prods.return_value = []
        pipeline = SimplePE(mock_production)

        with pytest.raises(PipelineException, match="No configuration file found"):
            pipeline.build_dag(dryrun=True)


class TestSubmitDag:
    """Test job submission via Asimov's scheduler abstraction
    (self.scheduler.submit_dag(...))."""

    def test_submit_dag_uses_scheduler_abstraction(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()
        pipeline._scheduler.submit_dag.return_value = 12345

        cluster_id = pipeline.submit_dag(dryrun=False)

        assert cluster_id == 12345
        assert mock_production.job_id == 12345
        assert mock_production.status == "running"
        pipeline._scheduler.submit_dag.assert_called_once()

    def test_submit_dag_uses_correct_dag_path(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        dag_path = os.path.join(mock_production.rundir, "simplepe.dag")
        open(dag_path, "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()
        pipeline._scheduler.submit_dag.return_value = 1

        pipeline.submit_dag(dryrun=False)

        kwargs = pipeline._scheduler.submit_dag.call_args.kwargs
        assert kwargs["dag_file"] == dag_path

    def test_submit_dag_batch_name_includes_event_and_production(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()
        pipeline._scheduler.submit_dag.return_value = 1

        pipeline.submit_dag(dryrun=False)

        kwargs = pipeline._scheduler.submit_dag.call_args.kwargs
        assert "GW150914" in kwargs["batch_name"]
        assert "TestProduction" in kwargs["batch_name"]

    def test_submit_dag_dryrun_does_not_call_scheduler(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()

        result = pipeline.submit_dag(dryrun=True)

        assert result is None
        pipeline._scheduler.submit_dag.assert_not_called()

    def test_submit_dag_missing_dag_file_raises(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()

        with pytest.raises(PipelineException, match="No DAG file found"):
            pipeline.submit_dag(dryrun=False)

    def test_submit_dag_scheduler_runtime_error_raises_pipeline_exception(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()
        pipeline._scheduler.submit_dag.side_effect = RuntimeError("could not submit")

        with pytest.raises(PipelineException, match="could not be submitted"):
            pipeline.submit_dag(dryrun=False)

    def test_submit_dag_scheduler_file_not_found_raises_pipeline_exception(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)
        open(os.path.join(mock_production.rundir, "simplepe.dag"), "w").close()

        pipeline = SimplePE(mock_production)
        pipeline._scheduler = Mock()
        pipeline._scheduler.submit_dag.side_effect = FileNotFoundError("no dag")

        with pytest.raises(PipelineException, match="could not be submitted"):
            pipeline.submit_dag(dryrun=False)


class TestDetectCompletionAndSamples:
    def test_no_output_returns_false(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = SimplePE(mock_production)
        assert pipeline.detect_completion() is False
        assert pipeline.samples() == []

    def test_posterior_samples_h5_detected(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        output = os.path.join(temp_dir, "posterior_samples.h5")
        open(output, "w").close()

        pipeline = SimplePE(mock_production)

        assert pipeline.detect_completion() is True
        assert pipeline.samples() == [output]

    def test_nested_posterior_file_detected(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        nested = os.path.join(temp_dir, "output")
        os.makedirs(nested)
        output = os.path.join(nested, "GW150914_posterior.dat")
        open(output, "w").close()

        pipeline = SimplePE(mock_production)

        assert pipeline.samples() == [output]

    def test_no_rundir_returns_no_samples(self, mock_production, mock_config):
        mock_production.rundir = None
        pipeline = SimplePE(mock_production)
        assert pipeline.samples() == []


class TestCollectAssets:
    def test_returns_samples_key(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = SimplePE(mock_production)
        with patch.object(pipeline, "samples", return_value=["a.h5"]):
            assets = pipeline.collect_assets()
        assert assets["samples"] == ["a.h5"]

    def test_returns_config_key(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = SimplePE(mock_production)
        with patch.object(pipeline, "samples", return_value=[]):
            assets = pipeline.collect_assets()
        assert assets["config"] == "TestProduction.ini"


class TestCollectLogs:
    def test_no_logs_returns_empty_dict(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = SimplePE(mock_production)
        assert pipeline.collect_logs() == {}

    def test_collects_err_out_log_files(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        with open(os.path.join(temp_dir, "job.err"), "w") as f:
            f.write("error content")

        pipeline = SimplePE(mock_production)
        logs = pipeline.collect_logs()

        assert logs["job.err"] == "error content"


class TestAfterCompletion:
    def test_marks_production_finished(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        mock_production.status = "running"
        pipeline = SimplePE(mock_production)

        pipeline.after_completion()

        assert mock_production.status == "finished"


class TestResurrect:
    def test_resurrect_resubmits_when_rescue_file_exists(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        mock_production.meta.pop("resurrections", None)
        submit_dir = os.path.join(temp_dir, "submit")
        os.makedirs(submit_dir)
        open(os.path.join(submit_dir, "simplepe.dag.rescue001"), "w").close()

        pipeline = SimplePE(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_called_once()
        assert mock_production.meta["resurrections"] == 1

    def test_resurrect_no_rescue_file_does_not_resubmit(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        pipeline = SimplePE(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_not_called()

    def test_resurrect_stops_after_five_attempts(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        mock_production.meta["resurrections"] = 5
        submit_dir = os.path.join(temp_dir, "submit")
        os.makedirs(submit_dir)
        open(os.path.join(submit_dir, "simplepe.dag.rescue001"), "w").close()

        pipeline = SimplePE(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_not_called()


class TestRealConfigRendering:
    """Exercise the real Liquid rendering path (asimov's own
    ``Analysis.make_config()``), rather than just checking that the
    template file exists -- this is what actually catches undefined-
    variable/syntax bugs in the bundled ini template."""

    def test_template_renders_a_valid_ini(self, mock_production, mock_config, temp_dir):
        from asimov import config as real_config
        from asimov.pipeline import Pipeline
        from liquid import Liquid

        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir)

        pipeline = SimplePE(mock_production)

        liq = Liquid(pipeline.config_template)
        rendered = liq.render(
            production=mock_production,
            analysis=mock_production,
            pipeline=pipeline,
            config=real_config,
        )

        cfg_path = os.path.join(temp_dir, "simplepe-test.ini")
        with open(cfg_path, "w") as f:
            f.write(rendered)

        parser = Pipeline.read_ini(cfg_path)
        assert parser.has_section("pipeline")
        assert parser.get("pipeline", "approximant") == mock_production.meta["waveform"][
            "approximant"
        ]
        assert parser.get("pipeline", "trigger_time") == str(
            mock_production.meta["event time"]
        )
        assert parser.get("pipeline", "outdir") == mock_production.rundir
        assert parser.get(
            "pipeline", "accounting_group"
        ) == mock_production.meta["scheduler"]["accounting group"]


def test_module_imports():
    from asimov_simplepe import SimplePE as _SimplePE
    from asimov_simplepe import __version__

    assert _SimplePE is not None
    assert __version__ is not None
