import importlib.machinery
import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
import sys
from contextlib import nullcontext
from unittest.mock import patch

board_spec = importlib.util.spec_from_file_location('vim4media', Path(__file__).resolve().parents[3] / 'board/vim4media.py')
vim4media = importlib.util.module_from_spec(board_spec)
sys.modules['vim4media'] = vim4media
board_spec.loader.exec_module(vim4media)

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
        self.enterContext(patch.object(vim4media, 'IMAGE_ROOTS', {'pikvm': self.images}))
        self.enterContext(patch.object(vim4media, 'media_locks', side_effect=lambda wait=False: nullcontext()))
        lun = self.root / 'lun'
        lun.mkdir()
        (lun / 'file').write_text('')
        self.enterContext(patch.object(media, 'LUN', lun))
        self.writes = self.enterContext(patch.object(media, 'write'))

    def test_insert_pins_regular_image_descriptor(self):
        image = self.images / 'test.iso'
        image.write_bytes(b'i' * 512)
        observed = []
        self.writes.side_effect = lambda name, value: observed.append((name, os.read(int(value.rsplit('/', 1)[1]), 512))) if name == 'file' else None
        media.insert(str(image))
        self.assertEqual(observed, [('file', b'i' * 512)])
        self.assertIn(unittest.mock.call('ro', '1'), self.writes.call_args_list)

    def test_occupied_lun_is_not_replaced(self):
        (media.LUN / 'file').write_text('/other.img')
        with self.assertRaises(ValueError):
            media.insert('data/test.img')
        self.writes.assert_not_called()

    def test_data_edit_lock_and_foreign_flags(self):
        import fcntl
        disk = self.images / 'disk.img'
        disk.write_bytes(b'd' * 512)
        self.enterContext(patch.object(vim4media, 'DATA_DIR', self.images))
        with disk.open('r+b') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, '正在管理面板中编辑'):
                media.insert('data/disk.img')
            self.writes.assert_not_called()
        media.insert('data/disk.img')
        self.assertIn(unittest.mock.call('ro', '1'), self.writes.call_args_list)
        self.assertIn(unittest.mock.call('cdrom', '0'), self.writes.call_args_list)

    def test_lock_contention_prevents_insert(self):
        vim4media.media_locks.side_effect = BlockingIOError
        with self.assertRaises(BlockingIOError):
            media.insert('data/disk.img')
        self.writes.assert_not_called()

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
