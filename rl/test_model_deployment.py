"""Tests de configuration et de copie, sans serveur ni connexion distante."""

import ast
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from rl.model_config import parse_model_spec, public_bot_models
from rl.sync_models import REMOTE_LIST, sync_models, validate_manifest, validate_source, validate_zip


ROOT = Path(__file__).resolve().parents[1]


class ModelConfigTest(unittest.TestCase):
    def test_defaults_overrides_and_allowlist(self) -> None:
        defaults = public_bot_models({})
        self.assertEqual(set(defaults), set(public_bot_models(json.loads(
            (ROOT / "config/conffile.json").read_text()))))
        self.assertEqual("aisub_v15_scripted", defaults["bot_rl_sub"])
        self.assertEqual("aidest_v3_scripted", defaults["bot_rl_destroyer"])
        config = dict(defaults, bot_rl_destroyer="aidest_v4_scripted:policy_250000_steps", secret="hidden")
        self.assertEqual(config["bot_rl_destroyer"], public_bot_models(config)["bot_rl_destroyer"])
        self.assertNotIn("secret", public_bot_models(config))

    def test_bad_identifiers_fail_closed(self) -> None:
        for value in (None, 3, "", ".", "..", "../run", "/run", "run/child", "run:",
                      "run:../policy", "run:x:y", "run\\x", "run\n", "run:.."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                public_bot_models({"bot_rl_sub": value})
        self.assertEqual(("run", "policy.zip"), parse_model_spec("run:policy.zip"))

    def test_bootstrap_and_ui_contract(self) -> None:
        tree = ast.parse((ROOT / "server.py").read_text())
        payload = next(node.value for node in ast.walk(tree)
                       if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "_init_payload" for t in node.targets))
        value = next(value for key, value in zip(payload.keys, payload.values)
                     if isinstance(key, ast.Constant) and key.value == "botRlModels")
        self.assertEqual("BOT_RL_MODELS", value.id)
        client = (ROOT / "static/game.js").read_text()
        self.assertIn("botRlModels = data.botRlModels || {};", client)
        self.assertIn('case "rlsub":    boatType = "submarine"; finalAi = botRlModels.bot_rl_sub;', client)
        self.assertIn('case "rldest":   boatType = "destroyer"; finalAi = botRlModels.bot_rl_destroyer;', client)
        self.assertNotIn("rl_aisub_v", client)
        self.assertNotIn("rl_aidest_v", client)

    def test_runtime_checkpoint_and_symlink_escape(self) -> None:
        from rl import rl_runtime
        with TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            checkpoint = models / "run/checkpoints/policy.zip"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.touch()
            with patch.object(rl_runtime, "MODELS_DIR", models):
                self.assertEqual(checkpoint, rl_runtime.resolve_model_path("rl_run:policy"))
                outside = root / "outside.zip"
                outside.touch()
                checkpoint.unlink()
                checkpoint.symlink_to(outside)
                with self.assertRaises(ValueError):
                    rl_runtime.resolve_model_path("rl_run:policy")
                with self.assertRaises(FileNotFoundError):
                    rl_runtime.resolve_model_path("rl_missing")

    def test_runtime_rejects_wrong_boat_spaces(self) -> None:
        from rl import rl_runtime
        model = SimpleNamespace(observation_space=SimpleNamespace(shape=(32,)),
                                action_space=SimpleNamespace(nvec=[5, 5, 5, 3, 2]))
        with patch.object(rl_runtime, "resolve_model_path", return_value=Path("fake.zip")), \
                patch.dict(rl_runtime._MODEL_CACHE, {Path("fake.zip"): model}, clear=True):
            with self.assertRaises(ValueError):
                rl_runtime.load_model("rl_run", "destroyer")


class SyncModelsTest(unittest.TestCase):
    def test_untrusted_paths_and_source(self) -> None:
        for manifest in ([], {}, ["../run/a.zip"], ["/run/a.zip"], ["run//a.zip"],
                         ["run/../a.zip"], ["run/a.zip", "run/a.zip"], ["run/a;bad.zip"]):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                validate_manifest(manifest)
        for host, root in (("-oProxyCommand=x", "/tmp"), ("host;id", "/tmp"),
                           ("host", "/tmp/../secret"), ("host", "/tmp/a b")):
            with self.assertRaises(ValueError):
                validate_source(host, root)

    def test_all_versions_atomic_validation_and_no_delete(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source/rl/models_rl"
            names = ["v1/best/best_model.zip", "v2/checkpoints/policy_1.zip",
                     "v2/policy_final.zip", "v2/league/policy.zip", "v2/archive/old.zip"]
            for name in names:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("data", "{}")
                    archive.writestr("policy.pth", name)
            (source / "v2/monitor.csv").write_text("not transferred")
            target = root / "target"
            target.mkdir()
            (target / "local.txt").write_text("keep")
            listing = subprocess.run(["python3", "-", str(root / "source")],
                                     input=REMOTE_LIST, text=True, capture_output=True, check=True)
            self.assertEqual(sorted(names), sorted(json.loads(listing.stdout)))

            def transfer(args, **kwargs):
                if args[0] == "ssh":
                    return listing
                name = args[2].split("/rl/models_rl/", 1)[1]
                Path(args[3]).write_bytes((source / name).read_bytes())
                return SimpleNamespace(returncode=0)

            with patch("rl.sync_models.subprocess.run", side_effect=transfer):
                self.assertEqual(len(names), sync_models("user@host", "/source", target))
                for name in names:
                    self.assertEqual((source / name).read_bytes(), (target / name).read_bytes())
                self.assertEqual("keep", (target / "local.txt").read_text())
                self.assertFalse((target / "v2/monitor.csv").exists())
                before = {name: (target / name).read_bytes() for name in names}
                with zipfile.ZipFile(source / names[0], "w") as archive:
                    archive.writestr("data", "{}")
                    archive.writestr("policy.pth", "new weights")
                def failed_transfer(args, **kwargs):
                    if args[0] == "ssh":
                        return listing
                    raise subprocess.CalledProcessError(1, args)

                with patch("rl.sync_models.subprocess.run", side_effect=failed_transfer):
                    with self.assertRaises(subprocess.CalledProcessError):
                        sync_models("user@host", "/source", target)
                self.assertEqual(before, {name: (target / name).read_bytes() for name in names})
                (source / names[-1]).write_bytes(b"broken zip")
                with self.assertRaises(zipfile.BadZipFile):
                    sync_models("user@host", "/source", target)
                self.assertEqual(before, {name: (target / name).read_bytes() for name in names})
                self.assertEqual([], list(target.glob(".sync-*")))
                (target / "v1/best/best_model.zip").unlink()
                (target / "v1/best/best_model.zip").symlink_to(root / "outside")
                with self.assertRaises(ValueError):
                    sync_models("user@host", "/source", target)

    def test_non_model_and_crc_failure(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("unrelated", "data")
            with self.assertRaises(ValueError):
                validate_zip(path)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("data", "{}")
                archive.writestr("policy.pth", "weights")
            with patch.object(zipfile.ZipFile, "testzip", return_value="policy.pth"):
                with self.assertRaises(ValueError):
                    validate_zip(path)


if __name__ == "__main__":
    unittest.main()
