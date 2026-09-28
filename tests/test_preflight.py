import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab.upcloud import quota_blockers, read_token


class PreflightTests(unittest.TestCase):
    def test_trial_limits_block_l40s(self):
        blockers = quota_blockers({"resource_limits": {"gpus": 0, "cores": 6, "memory": 12288}},
                                  {"gpu_amount": 1, "core_number": 8, "memory_amount": 65536})
        self.assertEqual({b["resource"] for b in blockers}, {"gpus", "cores", "memory"})

    def test_unknown_quota_is_not_assumed_unlimited(self):
        self.assertEqual(len(quota_blockers({}, {"gpu_amount": 1, "core_number": 8, "memory_amount": 65536})), 3)

    def test_credential_is_parsed_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "credentials.env"
            path.write_text('# example\nexport UPCLOUD_TOKEN="literal-$(false)" # comment\n')
            self.assertEqual(read_token(path), "literal-$(false)")
