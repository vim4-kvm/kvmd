import asyncio
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kvmd import vim4video
from kvmd.clients.streamer import MemsinkStreamerClient, StreamerFormats, StreamerPermError
from kvmd.apps.media.server import MediaServer, _Client, _Source
from kvmd.apps.kvmd.api.streamer import StreamerApi
from kvmd.apps.kvmd.server import KvmdServer
from kvmd.aiotools import AioNotifier
from kvmd.validators import ValidatorError


class DirectVideoTest(unittest.IsolatedAsyncioTestCase):
    async def test_output_height_change_restarts_only_video_once_and_rejects_invalid_height(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(vim4video, 'HEIGHT_PATH', root / 'video-output-height'))
        self.enterContext(patch('kvmd.apps.kvmd.api.streamer.env.VIM4', True))
        self.enterContext(patch.dict('os.environ', {'VIM4_SUPERVISOR_PID': '123'}))
        signal = self.enterContext(patch('kvmd.apps.kvmd.api.streamer.os.kill'))
        restart = MagicMock()
        streamer = AsyncMock()
        api = StreamerApi(streamer, None, restart)
        req = MagicMock()
        req.query = {'height': '719'}
        with self.assertRaises(ValidatorError):
            await api._StreamerApi__set_output_height_handler(req)
        signal.assert_not_called()
        self.assertFalse(vim4video.HEIGHT_PATH.exists())
        req.query = {'height': '720'}
        await api._StreamerApi__set_output_height_handler(req)
        await api._StreamerApi__set_output_height_handler(req)
        self.assertEqual(vim4video.read_output_height(), 720)
        signal.assert_called_once()
        restart.assert_called_once_with()
        streamer.ensure_restart.assert_not_awaited()

    def make_streamer(self, fmt):
        return MemsinkStreamerClient(fmt, 'test', 1, 1, 0)

    async def test_overflow_discards_dependencies_until_a_fresh_keyframe(self):
        client = _Client(MagicMock(), _Source(self.make_streamer(StreamerFormats.H265)), None)
        await client.put_frame({'key': True, 'data': b'old-key'})
        for _ in range(31):
            await client.put_frame({'key': False, 'data': b'old-delta'})
        self.assertTrue(await client.put_frame({'key': False, 'data': b'overflow'}))
        await client.put_frame({'key': False, 'data': b'broken-dependency'})
        await client.put_frame({'key': True, 'data': b'new-key'})
        await client.put_frame({'key': False, 'data': b'new-delta'})
        self.assertEqual((await client.get_frame())['data'], b'new-key')
        self.assertEqual((await client.get_frame())['data'], b'new-delta')

    async def test_media_handshake_refuses_deflate_and_preserves_binary_protocol(self):
        server = MediaServer(None, None, self.make_streamer(StreamerFormats.H265))
        server._HttpServer__ws_heartbeat = 10
        app = web.Application()
        server._HttpServer__app = app
        server._add_exposed(server)
        async with TestClient(TestServer(app)) as client:
            async with client.ws_connect('/ws', compress=15) as ws:
                self.assertEqual(ws.compress, 0)
                self.assertNotIn('Sec-WebSocket-Extensions', ws._response.headers)
                self.assertIn('h265', (await ws.receive_json())['event']['video'])
                await ws.send_bytes(b'\x00')
                self.assertEqual(await ws.receive_bytes(timeout=2), b'\xff')

    async def test_hevc_requests_keyframes_and_rejects_stale_h264(self):
        streamer = self.make_streamer(StreamerFormats.H265)
        with patch('kvmd.clients.streamer.ustreamer.Memsink') as factory:
            sink = factory.return_value.__enter__.return_value
            sink.wait_frame.return_value = {'format': StreamerFormats.H265, 'key': True, 'data': b'hevc'}
            async with streamer.reading() as read_frame:
                self.assertEqual((await read_frame(True))['data'], b'hevc')
                sink.wait_frame.assert_called_once_with(True)
                sink.wait_frame.return_value = {'format': StreamerFormats.H264}
                with self.assertRaises(StreamerPermError):
                    await read_frame(False)

    async def test_direct_hevc_advertises_format_and_waits_for_keyframe(self):
        streamer = self.make_streamer(StreamerFormats.H265)
        server = MediaServer(None, None, streamer)
        info = server._MediaServer__get_media_info()
        self.assertEqual(set(info['video']), {'h265'})
        sent = []

        async def send_bin(op, data):
            sent.append((op, data))
            if len(sent) == 2:
                raise asyncio.CancelledError

        ws = MagicMock()
        ws.kwargs = {'pure': False}
        ws.send_bin = send_bin
        src = _Source(streamer)
        client = _Client(ws, src, None)
        for key, data in [(False, b'before'), (True, b'key'), (False, b'after')]:
            await client.put_frame({'key': key, 'data': data})
        with self.assertRaises(asyncio.CancelledError):
            await server._MediaServer__sender(client)
        self.assertTrue(src.key_required)
        self.assertEqual(sent, [(1, b'\x01key'), (1, b'\x00after')])


class CodecApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_codec_restart_waits_for_viewer_start_to_finish(self):
        started, release, restarted = asyncio.Event(), asyncio.Event(), asyncio.Event()
        order = []

        async def start():
            order.append('starting')
            started.set()
            await release.wait()
            order.append('started')

        async def restart():
            order.append('restart')
            if order.count('restart') == 1:
                server._KvmdServer__request_streamer_reset()
            else:
                restarted.set()

        server = object.__new__(KvmdServer)
        server._KvmdServer__get_stream_clients = lambda: 1
        server._broadcast_ws_event = AsyncMock()
        server._KvmdServer__snapshoter = MagicMock()
        server._KvmdServer__stream_forever = False
        server._KvmdServer__streamer = AsyncMock()
        server._KvmdServer__streamer.ensure_start.side_effect = start
        server._KvmdServer__streamer.ensure_restart.side_effect = restart
        server._KvmdServer__streamer_notifier = AioNotifier()
        server._KvmdServer__new_streamer_params = {}
        server._KvmdServer__reset_streamer = False
        task = asyncio.create_task(server._KvmdServer__stream_controller())
        try:
            await asyncio.wait_for(started.wait(), 1)
            server._KvmdServer__request_streamer_reset()
            self.assertFalse(restarted.is_set())
            release.set()
            await asyncio.wait_for(restarted.wait(), 1)
            self.assertEqual(order, ['starting', 'started', 'restart', 'restart'])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_invalid_and_repeated_selections_do_not_restart_video(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(vim4video, 'CODEC_PATH', root / 'video-codec'))
        self.enterContext(patch('kvmd.apps.kvmd.api.streamer.env.VIM4', True))
        self.enterContext(patch.dict('os.environ', {'VIM4_SUPERVISOR_PID': '123', 'VIM4_VIDEO_CODEC': 'h264'}))
        signal = self.enterContext(patch('kvmd.apps.kvmd.api.streamer.os.kill'))
        streamer = AsyncMock()
        request_restart = MagicMock()
        api = StreamerApi(streamer, None, request_restart)
        req = MagicMock()
        req.query = {'codec': 'invalid'}
        with self.assertRaises(ValidatorError):
            await api._StreamerApi__set_codec_handler(req)
        signal.assert_not_called()
        self.assertFalse(vim4video.CODEC_PATH.exists())
        req.query = {'codec': 'h265'}
        await api._StreamerApi__set_codec_handler(req)
        await api._StreamerApi__set_codec_handler(req)
        self.assertEqual(vim4video.read_codec('h264'), 'h265')
        signal.assert_called_once()
        request_restart.assert_called_once_with()
        streamer.ensure_restart.assert_not_awaited()
        self.assertEqual(streamer.trigger_state.await_count, 2)
