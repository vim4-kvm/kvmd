import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from kvmd.apps.kvmd.info.system import SystemInfoSubmanager


class StreamerInfoTest(unittest.IsolatedAsyncioTestCase):
    async def test_cpu_wrapper_does_not_replace_the_reported_streamer_capabilities(self):
        from kvmd.apps.kvmd.info import system
        with tempfile.TemporaryDirectory() as directory:
            platform = Path(directory) / 'platform'
            platform.write_text('PIKVM_MODEL=VIM4\nPIKVM_VIDEO=HDMI\nPIKVM_BOARD=Khadas VIM4\n')
            calls = []
            async def read_process(args, **kwargs):
                calls.append(args)
                return (0, '7.11' if args[-1] == '--version' else '+ WITH_JANUS\n- WITH_GPIO')
            manager = SystemInfoSubmanager(str(platform),
                ['/usr/bin/taskset', '--cpu-list', '1-7', '/usr/bin/ustreamer'])
            with patch.object(system.env, 'VIM4', True), \
                    patch.object(system.aioproc, 'read_process', side_effect=read_process):
                state = await manager.get_state()
            self.assertEqual(state['streamer']['app'], 'ustreamer')
            self.assertEqual(state['streamer']['version'], '7.11')
            self.assertEqual(state['streamer']['features'], {'WITH_JANUS': True, 'WITH_GPIO': False})
            self.assertTrue(all(args[0] == '/usr/bin/ustreamer' for args in calls))
