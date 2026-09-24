"""Install a built wheel under .venv and exercise its entrypoint outside checkout.

Run with .venv/bin/python tools/package_smoke.py. No dependencies are downloaded.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    wheels = sorted((ROOT / "dist").glob("anno-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise SystemExit("Build the wheel first: .venv/bin/python -m build --no-isolation")
    with tempfile.TemporaryDirectory(prefix="package-smoke-", dir=ROOT / ".venv") as install:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                install,
                str(wheels[-1]),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        environment = {**os.environ, "PYTHONPATH": install, "PYTHONDONTWRITEBYTECODE": "1"}
        with tempfile.TemporaryDirectory(prefix="anno-package-project-") as project:
            project = Path(project)
            probe = subprocess.run(
                [sys.executable, "-c", "import anno; print(anno.__file__)"],
                cwd=project,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            assert Path(probe.stdout.strip()).is_relative_to(install), probe.stdout
            entrypoint = Path(install) / "bin/anno"

            def run(*args):
                result = subprocess.run(
                    [str(entrypoint), *args],
                    cwd=project,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert result.returncode == 0, (args, result.stdout, result.stderr)
                return json.loads(result.stdout)

            run("init")
            (project / "dataset/data.yaml").write_text("names: [car]\n")
            (project / "label.md").write_text(
                "Annotate visible cars, using tight boxes around visible parts."
            )
            (project / ".anno/skills/anno-class/SKILL.md").write_text(
                "# Classes\n0: car. Visible parts only."
            )
            from PIL import Image

            path = "dataset/images/car.png"
            Image.new("RGB", (800, 800), "white").save(project / path)
            assert run("doctor")["ready"]
            capabilities = run("capabilities")
            for schema in capabilities["schemas"].values():
                run("schema", schema)
            run("label", "grid", path)
            local = path
            Image.new("RGB", (720, 1280), "white").save(project / local)
            for command, expected in (("grid", [270, 480]), ("select", [378, 672])):
                rendered = run("label", command, local, "--cells", "G4")
                assert rendered["scale"] == 3
                assert rendered["render_size"] == expected
                with Image.open(project / rendered["artifact_path"]) as artifact:
                    assert list(artifact.size) == expected
            token = run("label", "verify", path, "--class", "0", "--cells", "B2:C3")["verification_id"]
            run("label", "bbox", "add", path, "--class", "0", "--cells", "B2:C3", "--verification-id", token)
            run("review", "audit")
            run("review", "overview", path)
            run("review", "inspect", path, "--index", "0")
            run("review", "mark", path, "--verdict", "approved", "--notes", "Synthetic package smoke")
            assert run("review", "next")["done"]
            print(
                "Wheel install, isolated import, entrypoint, all schemas and labeling/review lifecycle: PASS"
            )


if __name__ == "__main__":
    main()
