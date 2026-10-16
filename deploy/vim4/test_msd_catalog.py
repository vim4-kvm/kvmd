from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from kvmd.aiotools import AioNotifier
from kvmd.plugins.msd import MsdImageExistsError, MsdImageStaticError
from kvmd.plugins.msd.otg import Plugin, _State, _VirtualDrive
from kvmd.plugins.msd.otg.storage import Storage
from kvmd.plugins.msd.otg.vim4 import CatalogImage


class CatalogTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = dict(id='data/disk.img', name='disk.img', source='data', size=4096, cdrom=False)
        self.image = CatalogImage(self.entry)
        self.catalog = self.enterContext(patch('kvmd.plugins.msd.otg.vim4.catalog', new_callable=AsyncMock))
        self.catalog.return_value = [self.entry]
        self.enterContext(patch('kvmd.env.VIM4', True))

    async def test_root_only_images_are_listed_without_write_or_delete_rights(self):
        storage = Storage([])
        storage._Storage__images = {}
        storage._Storage__parts = {}
        await storage.reload_catalog()
        state = storage.get_state()['images']['VIM4/data/disk.img']
        self.assertEqual(state['source'], 'data')
        self.assertEqual(state['size'], 4096)
        self.assertTrue(state['complete'])
        self.assertFalse(state['writable'])
        self.assertFalse(state['removable'])
        image = await storage.get_image_by_name('VIM4/data/disk.img')
        self.assertTrue(await image.exists())
        with self.assertRaises(MsdImageExistsError):
            await storage.make_image(image.name)
        self.assertFalse(await storage.reload_catalog(), 'unchanged catalog must not notify clients')
        self.catalog.return_value = []
        self.assertTrue(await storage.reload_catalog())
        self.assertEqual(storage.get_state()['images'], {})
        self.assertFalse(await image.exists())

    async def test_live_foreign_mount_requires_process_ownership(self):
        plugin = Plugin.__new__(Plugin)
        plugin._Plugin__drive = Mock()
        plugin._Plugin__drive.get_image_path.return_value = self.image.path
        plugin._Plugin__drive.get_cdrom_flag.return_value = False
        plugin._Plugin__drive.get_rw_flag.return_value = False
        plugin._Plugin__storage = Mock()
        plugin._Plugin__storage.get_image_by_path = AsyncMock(return_value=self.image)
        plugin._Plugin__nbd = SimpleNamespace(image=None)
        plugin._Plugin__nr = Mock()
        plugin._Plugin__state = SimpleNamespace(vd=None)
        await plugin._Plugin__update_vd()
        self.assertFalse(plugin._Plugin__state.vd.image.in_storage)
        plugin._Plugin__state.vd = _VirtualDrive(self.image, True, False, False)
        await plugin._Plugin__update_vd()
        self.assertIsInstance(plugin._Plugin__state.vd.image, CatalogImage)
        plugin._Plugin__drive.get_image_path.return_value = ''
        await plugin._Plugin__update_vd()
        self.assertFalse(plugin._Plugin__state.vd.connected)
        plugin._Plugin__drive.get_image_path.return_value = self.image.path
        await plugin._Plugin__update_vd()
        self.assertFalse(plugin._Plugin__state.vd.image.in_storage)

    async def test_remove_rejects_foreign_images_before_filesystem_mutation(self):
        plugin = Plugin.__new__(Plugin)
        plugin._Plugin__state = _State(AioNotifier())
        plugin._Plugin__drive = Mock()
        plugin._Plugin__drive.get_image_path.return_value = ''
        async with plugin._Plugin__state.locked_only():
            plugin._Plugin__state.vd = _VirtualDrive(None, False, False, False)
        plugin._Plugin__storage = Mock()
        plugin._Plugin__storage.get_image_by_name = AsyncMock(return_value=self.image)
        with self.assertRaises(MsdImageStaticError):
            await plugin.remove(self.image.name)
        plugin._Plugin__storage.remove_image.assert_not_called()
        plugin._Plugin__storage.remount_rw.assert_not_called()
