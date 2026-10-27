import asyncio
import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kvmd import vim4video


loader = importlib.machinery.SourceFileLoader('supervisor', str(Path(__file__).with_name('vim4-pikvm-run')))
spec = importlib.util.spec_from_loader(loader.name, loader)
supervisor = importlib.util.module_from_spec(spec)
loader.exec_module(supervisor)


class CodecTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root / 'video-codec'
        self.enterContext(patch.object(vim4video, 'CODEC_PATH', self.path))
        self.enterContext(patch.object(vim4video, 'HEIGHT_PATH', self.root / 'video-output-height'))

    def test_output_height_persists_and_invalid_selection_preserves_previous_value(self):
        self.assertEqual(vim4video.read_output_height(), 0)
        vim4video.write_output_height(720)
        self.assertEqual(vim4video.read_output_height(), 720)
        with self.assertRaises(ValueError):
            vim4video.write_output_height(719)
        self.assertEqual(vim4video.read_output_height(), 720)

    def test_selection_survives_restart_and_invalid_write_preserves_it(self):
        self.assertEqual(vim4video.read_codec('h264'), 'h264')
        vim4video.write_codec('h265')
        self.assertEqual(vim4video.read_codec('h264'), 'h265')
        with self.assertRaises(ValueError):
            vim4video.write_codec('invalid')
        self.assertEqual(vim4video.read_codec('h264'), 'h265')

    def test_failed_replace_preserves_previous_selection_and_cleans_tempfile(self):
        vim4video.write_codec('h264')
        with patch.object(vim4video.os, 'replace', side_effect=OSError), self.assertRaises(OSError):
            vim4video.write_codec('h265')
        self.assertEqual(vim4video.read_codec('h265'), 'h264')
        self.assertEqual(list(self.root.iterdir()), [self.path])


class Child:
    def __init__(self):
        self.returncode = None
        self.exited = asyncio.Event()

    async def wait(self):
        await self.exited.wait()
        return self.returncode

    def terminate(self):
        self.returncode = 0
        self.exited.set()


class SupervisorTest(unittest.IsolatedAsyncioTestCase):
    async def test_reload_replaces_video_children_with_selected_codec(self):
        stopped = asyncio.Event()
        reload_requested = asyncio.Event()
        children = []
        codecs = []

        async def spawn(*_, env):
            if len(children) == 2:
                self.assertTrue(all(child.returncode == 0 for child in children))
            children.append(Child())
            codecs.append(env['VIM4_VIDEO_CODEC'])
            if len(children) == 2:
                reload_requested.set()
            if len(children) == 4:
                stopped.set()
            return children[-1]

        with patch.object(supervisor.asyncio, 'create_subprocess_exec', spawn), \
                patch.object(supervisor, 'read_codec', side_effect=['h264', 'h265']):
            await supervisor.run_video_components([['media'], ['janus']], stopped, reload_requested, 'h264')
        self.assertEqual(codecs, ['h264', 'h264', 'h265', 'h265'])
        self.assertTrue(all(child.returncode == 0 for child in children))

    async def test_reload_waits_for_all_old_children(self):
        reload_requested = asyncio.Event()
        children = []

        async def spawn(*_, **kwargs):
            children.append(Child())
            if len(children) == 3:
                reload_requested.set()
            return children[-1]

        with patch.object(supervisor.asyncio, 'create_subprocess_exec', spawn):
            await supervisor.run_components([['kvmd'], ['media'], ['janus']], asyncio.Event(), reload_requested)
        self.assertTrue(all(child.returncode == 0 for child in children))

    async def test_spawn_failure_stops_already_started_children(self):
        child = Child()
        calls = 0

        async def spawn(*_, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('failed to spawn')
            return child

        with patch.object(supervisor.asyncio, 'create_subprocess_exec', spawn), self.assertRaises(OSError):
            await supervisor.run_components([['kvmd'], ['media']], asyncio.Event(), asyncio.Event())
        self.assertEqual(child.returncode, 0)
