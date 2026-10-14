import importlib.machinery
import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('media', str(Path(__file__).with_name('vim4-pikvm-media')))
spec = importlib.util.spec_from_loader(loader.name, loader)
media = importlib.util.module_from_spec(spec)
loader.exec_module(media)


class MediaTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.images = self.root / 'images'
        self.images.mkdir()
        self.enterContext(patch.object(media, 'IMAGES', self.images))
        self.writes = self.enterContext(patch.object(media, 'write'))

    def test_insert_pins_regular_image_descriptor(self):
        image = self.images / 'test.iso'
        image.write_bytes(b'iso contents')
        observed = []
        self.writes.side_effect = lambda name, value: observed.append((name, os.read(int(value.rsplit('/', 1)[1]), 100)))
        media.insert(str(image))
        self.assertEqual(observed, [('file', b'iso contents')])

    def test_rejects_escape_symlink_directory_and_hardlink(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'private')
        (self.images / 'link.iso').symlink_to(outside)
        (self.images / 'directory').symlink_to(self.root, target_is_directory=True)
        os.link(outside, self.images / 'hard.iso')
        for path in [outside, self.images / '../outside', self.images / 'link.iso',
                     self.images / 'directory/outside', self.images / 'hard.iso', self.images]:
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                media.insert(str(path))
        self.writes.assert_not_called()

    def test_prepare_and_restore_preserve_original_profile(self):
        gadget = self.root / 'gadget'
        profile = gadget / 'configs/c.1'
        lun = gadget / 'functions/mass_storage.disk0/lun.0'
        profile.mkdir(parents=True)
        lun.mkdir(parents=True)
        (gadget / 'functions/ncm.usb0').mkdir()
        (gadget / 'UDC').write_text('controller\n')
        for name, value in [('file', ''), ('ro', '1'), ('cdrom', '0')]:
            (lun / name).write_text(value)
        (profile / media.NETWORK).symlink_to(gadget / 'functions/ncm.usb0')
        for name, value in [('GADGET', gadget), ('PROFILE', profile), ('LUN', lun),
                            ('STATE', self.root / 'state/state.json')]:
            self.enterContext(patch.object(media, name, value))
        media.prepare()
        self.assertTrue((profile / media.DISK).is_symlink())
        self.assertFalse((profile / media.NETWORK).exists())
        media.restore()
        self.assertFalse((profile / media.DISK).exists())
        self.assertTrue((profile / media.NETWORK).is_symlink())
        self.assertEqual((gadget / 'UDC').read_text().strip(), 'controller')
        self.assertFalse(media.STATE.exists())


if __name__ == '__main__':
    unittest.main()
