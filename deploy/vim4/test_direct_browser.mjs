// Offline decoder integration: pass an Annex B HEVC recording as argv[2].
// PLAYWRIGHT_MODULE can point to an existing Playwright installation.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const recording = await readFile(process.argv[2]);
let pictures = 0;
let end = recording.length;
for (let i = 0; i + 6 < recording.length; i++) {
    const size = recording[i] === 0 && recording[i + 1] === 0
        ? (recording[i + 2] === 1 ? 3 : (recording[i + 2] === 0 && recording[i + 3] === 1 ? 4 : 0)) : 0;
    if (!size) continue;
    const type = (recording[i + size] >> 1) & 63;
    if (type < 32 && (recording[i + size + 2] & 0x80) && ++pictures === 2) {
        end = i;
        break;
    }
    i += size - 1;
}
assert(pictures > 0, 'Recording must contain a coded picture');
const frame = Buffer.concat([Buffer.from([1, 1]), recording.subarray(0, end)]);
const root = fileURLToPath(new URL('../../web/', import.meta.url));
const server = createServer(async (req, res) => {
    try {
        if (req.url === '/') {
            res.setHeader('Content-Type', 'text/html');
            res.end('<video id="stream-video" autoplay playsinline></video><canvas id="stream-canvas"></canvas>' +
                ['orient', 'multimedia', 'audio', 'mic', 'mic-raw', 'camera']
                    .map(name => `<div id="stream-${name}"></div>`).join(''));
        } else if (req.url === '/ui') {
            res.setHeader('Content-Type', 'text/html');
            res.end((await readFile(path.join(root, 'kvm/index.html'), 'utf8'))
                .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, ''));
        } else {
            const filename = path.resolve(root, '.' + req.url);
            assert(filename.startsWith(root));
            res.setHeader('Content-Type', 'text/javascript');
            res.end(await readFile(filename));
        }
    } catch {
        res.writeHead(404).end();
    }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({channel: 'chrome', headless: true});
try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let connections = 0;
    await page.routeWebSocket('**/api/media/ws', ws => {
        connections++;
        ws.send(JSON.stringify({event_type: 'media', event: {video: {h265: {}}}}));
        ws.onMessage(message => {
            if (typeof message === 'string') {
                const event = JSON.parse(message);
                assert.equal(event.event.format, 'h265');
                ws.send(frame);
            } else if (message[0] === 0) {
                ws.send(Buffer.from([255]));
            }
        });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.evaluate(async () => {
        const {MediaStreamer} = await import('/share/js/kvm/stream_media.js');
        window.activeFrames = 0;
        window.streamer = new MediaStreamer(() => window.activeFrames++, () => {}, () => {}, () => {}, () => {}, 'h265');
        window.streamer.ensureStream({source: {online: true}});
    });
    await page.waitForFunction(() => window.activeFrames > 0 && document.querySelector('canvas').width > 300);
    await page.evaluate(() => {
        window.streamer.stopStream();
        window.streamer.ensureStream({source: {online: true}});
    });
    await page.waitForFunction(() => window.activeFrames >= 2);
    assert.equal(connections, 2);
    assert.deepEqual(errors, []);
    console.log('Direct H.265 decoded recorded HEVC and reconnected:', await page.evaluate(() => ({
        name: window.streamer.getName(), width: document.querySelector('canvas').width,
        height: document.querySelector('canvas').height,
    })));

    const selections = [];
    const heights = [];
    await page.route('**/api/streamer/set_output_height?*', async route => {
        heights.push(new URL(route.request().url()).searchParams.get('height'));
        await route.fulfill({json: {ok: true, result: {}}});
    });
    await page.route('**/api/streamer/set_codec?*', async route => {
        selections.push(new URL(route.request().url()).searchParams.get('codec'));
        await route.fulfill({json: {ok: true, result: {}}});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/ui`);
    await page.evaluate(async () => {
        const {initWindowManager} = await import('/share/js/wm.js');
        const {tools} = await import('/share/js/tools.js');
        const {setRootPrefix} = await import('/share/js/vars.js');
        const {JanusStreamer} = await import('/share/js/kvm/stream_janus.js');
        const {Streamer} = await import('/share/js/kvm/stream.js');
        setRootPrefix('/');
        initWindowManager();
        tools.storage.set('stream.mode', 'mjpeg');
        // This test exercises the real menu and Direct transport without a Janus server.
        JanusStreamer.ensure_janus = cb => cb(false);
        window.ui = new Streamer();
        window.ui.ensureDeps(() => {});
        window.stateForCodec = codec => ({
            features: {h264: true, h265: true, video_codec: codec, quality: true,
                output_height: 0, output_heights: [0, 480, 720, 1080, 1440, 1700, 2160]},
            limits: {desired_fps: {min: 0, max: 60}, h264_bitrate: {min: 1000, max: 60000}, h264_gop: {min: 1, max: 60}},
        });
        document.querySelector('#stream-window').classList.remove('hidden');
        window.ui.setState(window.stateForCodec('h264'));
        document.querySelector('#stream-mode-radio-media-h265').click();
    });
    await page.waitForResponse('**/api/streamer/set_codec?*');
    assert.deepEqual(selections, ['h265']);
    await page.evaluate(() => window.ui.setState(window.stateForCodec('h265')));
    await page.waitForFunction(() => document.querySelector('#stream-mode-radio-media-h265').checked
        && document.querySelector('#stream-window-header').textContent.includes('Direct H.265'));
    await page.evaluate(() => window.ui.setState(window.stateForCodec('h264')));
    assert(await page.locator('#stream-mode-radio-media').isChecked());
    assert.deepEqual(selections, ['h265'], 'State updates must not write the shared codec back');
    // Labels and numeric values differ; the HTTP API accepts the numeric value.
    const response = page.waitForResponse('**/api/streamer/set_output_height?*');
    await page.locator('#stream-output-height-selector').selectOption('720', {force: true});
    await response;
    assert.deepEqual(heights, ['720']);
    await page.evaluate(() => window.ui.setState({...window.stateForCodec('h264'),
        features: {...window.stateForCodec('h264').features, output_height: 1080}}));
    assert.equal(await page.locator('#stream-output-height-selector').inputValue(), '1080');
    assert.deepEqual(heights, ['720'], 'State broadcasts must not rewrite the saved height');
    assert.deepEqual(errors, []);
    console.log('Video menu selects H.265 and follows another viewer without switching it back');
} finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
}
