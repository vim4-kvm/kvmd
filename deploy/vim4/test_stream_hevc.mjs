import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../../web/share/js/kvm/stream_hevc.js', import.meta.url), 'utf8');
const {hevcCodecFromAnnexB} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function sps(level, start = [0, 0, 0, 1]) {
    const rbsp = [1, 1, 0x60, 0, 0, 0, 0xb0, 0, 0, 0, 0, 0, level];
    const escaped = [];
    let zeros = 0;
    for (const byte of rbsp) {
        if (zeros === 2 && byte <= 3) {
            escaped.push(3);
            zeros = 0;
        }
        escaped.push(byte);
        zeros = byte === 0 ? zeros + 1 : 0;
    }
    return [...start, 0x42, 1, ...escaped];
}

test('HEVC decoder level follows SPS across resolution changes and mixed start codes', () => {
    for (const level of [93, 120, 153]) {
        const accessUnit = new Uint8Array([0, 0, 1, 0x40, 1, 0x80, ...sps(level, [0, 0, 1]),
            0, 0, 0, 1, 0x44, 1, 0x80, 0, 0, 1, 0x26, 1, 0x80]);
        assert.equal(hevcCodecFromAnnexB(accessUnit), `hev1.1.6.L${level}.B0`);
    }
});

test('missing and truncated SPS cannot configure a decoder', () => {
    assert.equal(hevcCodecFromAnnexB(new Uint8Array([0, 0, 1, 0x26, 1, 0x80])), null);
    assert.throws(() => hevcCodecFromAnnexB(new Uint8Array([0, 0, 0, 1, 0x42, 1, 1])), /Truncated/);
});
