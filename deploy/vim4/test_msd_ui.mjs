import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = (await readFile(new URL('../../web/share/js/kvm/msd.js', import.meta.url), 'utf8'))
    .replace(/^import .*;$/gm, '').replace('export function Msd', 'function Msd');

test('storage updates remain independent of grouped images and partial drive events', () => {
    const elements = new Map(), progress = [];
    const element = id => {
        if (!elements.has(id)) elements.set(id, {options: [], value: '', checked: false});
        return elements.get(id);
    };
    const noop = () => {};
    const context = vm.createContext({
        ROOT_PREFIX: '', $: element,
        tools: {
            el: {setOnClick: noop, setEnabled: noop},
            hidden: {setVisible: noop}, feature: {setEnabled: noop},
            input: {getFile: () => null}, storage: {get: (_, fallback) => fallback},
            radio: {clickValue: noop, setOnClick: noop, getValue: () => 'name', setValue: noop, setEnabled: noop},
            selector: {
                addOption: (el, title, value) => el.options.push({title, value}),
                addComment: (el, comment) => el.options.push({comment}),
                addSeparator: el => el.options.push({separator: true}),
            },
            progress: {setSizeOf: (_, title, size, free) => progress.push({title, size, free}), setPercentOf: noop},
            makeTextId: value => value, formatSize: value => String(value), escape: value => value,
        },
    });
    vm.runInContext(source, context);
    const msd = new context.Msd();
    // WebSocket fields need not arrive together. Neither stage may read an
    // undeclared images variable or try Object.keys on an absent catalogue.
    msd.setState({enabled: true, online: true});
    msd.setState({drive: {connected: false, image: null, cdrom: true},
        storage: {parts: {'': {size: 1000, free: 800, writable: true}}}});
    assert.equal(progress.length, 1);
    assert.equal(progress[0].free, 800);
    const image = source => ({source, size: 100, mod_ts: 1, complete: true, writable: false});
    msd.setState({storage: {images: {'b.iso': image('onekvm'), 'a.iso': image('data'), 'c.iso': image('onekvm')}}});
    const selector = element('msd-image-selector');
    assert.deepEqual(selector.options.filter(option => option.value).map(option => option.value), ['a.iso', 'b.iso', 'c.iso']);
    assert.equal(selector.options.filter(option => option.comment === 'One-KVM 镜像').length, 1);
    assert.equal(selector.options.filter(option => option.comment === '共享数据盘').length, 1);
    element('msd-filter-input').value = 'b.';
    element('msd-filter-input').oninput();
    assert.deepEqual(selector.options.filter(option => option.value).map(option => option.value), ['b.iso']);
    msd.setState({drive: {connected: true, image: {...image('onekvm'), name: 'b.iso', in_storage: true, proto: 'storage'}}});
    assert.equal(selector.value, 'b.iso');
    assert.equal(progress.length, 1, 'Image updates must not rewrite storage progress');
});
