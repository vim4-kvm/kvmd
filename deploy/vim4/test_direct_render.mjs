import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = (await readFile(new URL('../../web/share/js/kvm/stream_media.js', import.meta.url), 'utf8'))
    .replace(/^import .*;$/gm, '').replace('export function MediaStreamer', 'function MediaStreamer');

test('Direct presents the latest decoded frame and releases superseded frames', async () => {
    const callbacks = [];
    const drawn = [];
    let socket;
    let output;
    const canvas = {width: 640, height: 480, getContext: () => ({drawImage: frame => drawn.push(frame)})};
    const context = vm.createContext({
        tools: {feature: {setEnabled() {}}, makeWsUrl: () => '', info() {}},
        $: () => canvas,
        window: {VideoDecoder: true, requestAnimationFrame: callback => callbacks.push(callback)},
        WebSocket: class {
            constructor() { socket = this; }
            send() {}
            close() {}
        },
        VideoDecoder: class {
            constructor(init) { output = init.output; this.state = 'unconfigured'; }
            configure() { this.state = 'configured'; }
            decode() {}
            close() { this.state = 'closed'; }
        },
        EncodedVideoChunk: class {}, Uint8Array, performance,
    });
    vm.runInContext(source, context);
    const streamer = new context.MediaStreamer(() => {}, () => {}, () => {}, () => {}, () => {});
    streamer.ensureStream({source: {online: true}});
    await socket.onmessage({data: JSON.stringify({event_type: 'media', event: {video: {h264: {profile_level_id: '640033'}}}})});
    await socket.onmessage({data: new Uint8Array([1, 1, 0]).buffer});
    const frame = () => ({displayWidth: 640, displayHeight: 480, closed: 0, close() { this.closed++; }});
    const first = frame(), second = frame(), latest = frame();
    output(first); output(second); output(latest);
    assert.equal(callbacks.length, 1, 'A burst schedules only one paint');
    assert.equal(first.closed, 1);
    assert.equal(second.closed, 1);
    assert.equal(latest.closed, 0);
    callbacks.shift()();
    assert.deepEqual(drawn, [latest]);
    assert.equal(latest.closed, 1);
    const pending = frame();
    output(pending);
    streamer.stopStream();
    assert.equal(pending.closed, 1);
    callbacks.shift()();
    assert.deepEqual(drawn, [latest], 'Stopping must cancel the pending presentation');
});
