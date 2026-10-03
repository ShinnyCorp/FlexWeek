"""Static checks for bounded Windows release workflow processes."""

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/release-windows.yml"


def workflow_step(name: str) -> str:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = f"      - name: {name}"
    start = lines.index(marker)
    run_line = next(
        i for i in range(start + 1, len(lines))
        if lines[i] == "        run: |" or lines[i].startswith("      - name:")
    )
    if lines[run_line] != "        run: |":
        raise AssertionError(f"step {name!r} has no multiline run script")
    script = []
    for line in lines[run_line + 1 :]:
        if line and len(line) - len(line.lstrip()) < 10:
            break
        script.append(line[10:] if line.startswith("          ") else line)
    return "\n".join(script)


class ReleaseTimeoutTests(unittest.TestCase):
    def test_both_jobs_have_runner_timeouts(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        for job in ("windows", "linux"):
            with self.subTest(job=job):
                self.assertRegex(content, rf"(?m)^  {job}:\n(?:    [^\n]*\n|\n)*?    timeout-minutes: 120$")

    def assert_bounded_process(self, script: str, context: str) -> None:
        self.assertIn(".WaitForExit(600000)", script, context)
        self.assertIn("Stop-Process -Id $proc.Id -Force", script, context)
        self.assertNotRegex(script, r"Start-Process[^\n]*\s-Wait(?:\s|$)", context)

    def test_package_smoke_wait_is_bounded_and_report_prints_in_finally(self) -> None:
        script = workflow_step("Smoke-test package layout and the setup Solve")
        self.assert_bounded_process(script, "package smoke step")
        self.assertIn("finally {", script)
        finalizer = script[script.index("finally {") :]
        self.assertIn("if (Test-Path $report) { Get-Content $report }", finalizer)
        self.assertIn("$proc.ExitCode -ne 0", script)

    def test_inno_installer_wait_is_bounded_and_success_code_is_checked(self) -> None:
        script = workflow_step("Install the installer tools")
        self.assert_bounded_process(script, "Inno Setup install step")
        self.assertIn("if ($proc.ExitCode -ne 0)", script)

    def test_install_and_smoke_processes_are_bounded_and_report_prints_in_finally(self) -> None:
        script = workflow_step("Install, open and uninstall each installer")
        self.assertEqual(script.count(".WaitForExit(600000)"), 2)
        self.assertEqual(script.count("Stop-Process -Id $proc.Id -Force"), 2)
        self.assertNotIn("Start-Process -Wait", script)
        self.assertIn("$proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010", script)
        self.assertIn("finally {", script)
        finalizer = script[script.index("finally {") :]
        self.assertIn("if (Test-Path $report) { Get-Content $report }", finalizer)
        self.assertIn("$name installed app smoke test timed out after 10 minutes", script)


if __name__ == "__main__":
    unittest.main()
