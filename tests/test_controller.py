import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lab.smoke import main


class ControllerTests(unittest.TestCase):
    def test_timeout_removes_container_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LAB_RUNS_DIR": directory}), \
                 patch("sys.argv", ["smoke", "--timeout", "1"]), \
                 patch("lab.smoke.subprocess.run", side_effect=[
                     subprocess.TimeoutExpired("docker compose run", 1),
                     subprocess.CompletedProcess([], 0),
                 ]) as run, patch("builtins.print"):
                with self.assertRaises(SystemExit) as raised:
                    main()
            self.assertEqual(raised.exception.code, 1)
            cleanup = run.call_args_list[1].args[0]
            self.assertEqual(cleanup[:3], ["docker", "rm", "-f"])
            self.assertTrue(cleanup[3].startswith("dsh-lab-smoke-"))
            records = list(Path(directory).glob("*.controller.json"))
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0].read_text())["status"], "timeout")
