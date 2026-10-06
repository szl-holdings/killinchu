// Exercise the graph handlers embedded in the shipped console source.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'killinchu_elite_console.py'), 'utf8'
).replace(/\r\n/g, '\n');
const escapeHelper = source.match(/^function esc\(s\).*$/m)?.[0];
assert.ok(escapeHelper, 'console escape helper must be present');

function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `missing graph section: ${start}`);
  return source.slice(from, to);
}

const graphs = {
  mesh3d: section('let _fg=null;\nfunction mesh3d(', '// ===================== GENIUS'),
  dag3d: section('function dag3d(', '// cytoscape 2D graph'),
};

for (const [name, graphSource] of Object.entries(graphs)) {
  test(`${name} renders a graph failure as text`, () => {
    const injected = '<img src=x onerror=alert(1)>';
    const host = { innerHTML: '', clientWidth: 400, clientHeight: 300 };
    const graph = {
      backgroundColor() { return this; },
      width() { return this; },
      height() { return this; },
      graphData() { throw new Error(injected); },
    };
    const context = {
      host,
      window: { ForceGraph3D: true },
      ForceGraph3D: () => () => graph,
      setTimeout() { throw new Error('graphData should fail first'); },
    };
    const script = `${escapeHelper}\nfunction el(){ return host; }\n${graphSource}\n${name}('graph', [], []);`;
    vm.runInNewContext(script, context);
    assert.match(host.innerHTML, /3D init: &lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(host.innerHTML, /<img/);
  });
}
