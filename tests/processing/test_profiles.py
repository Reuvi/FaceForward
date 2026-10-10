import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Processing.mouse.config import MouseConfig
from Processing.mouse.profiles import FORMAT, read_profile, write_profile


class ProfileStorageTests(unittest.TestCase):
    def profile(self):
        return {"format":FORMAT,"source_kind":"synthetic","detector":{"validated_by":"Vision"},
                "processing":MouseConfig().to_dict(),"preview":{"pointer_speed":900,"scroll_speed":450}}

    def test_roundtrip_and_private_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"nested"/"profile.json"
            write_profile(path,self.profile())
            self.assertEqual(read_profile(path),self.profile())
            self.assertEqual(path.stat().st_mode & 0o077,0)
            original=path.read_bytes()
            with patch("Processing.mouse.profiles.os.replace",side_effect=OSError("disk error")):
                with self.assertRaises(OSError):write_profile(path,self.profile())
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(path.parent.iterdir()),[path])

    def test_bad_version_settings_fields_nonfinite_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"profile.json"
            for mutate in (lambda d:d.update(format="v2"),lambda d:d.update(subject_id="someone"),
                           lambda d:d["processing"].update(mode="gamepad"),
                           lambda d:d["preview"].update(pointer_speed=float("nan"))):
                data=self.profile();mutate(data)
                with self.assertRaises(ValueError):write_profile(path,data)
                self.assertFalse(path.exists())
            path.write_bytes(b" "*262145)
            with self.assertRaises(ValueError):read_profile(path)
            path.write_bytes(b"{bad json")
            with self.assertRaises(ValueError):read_profile(path)
