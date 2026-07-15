#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'app.js'), 'utf8');
const checks = [
  ['pull single-flight', 'if (_syncPullPromise) return _syncPullPromise'],
  ['pull cooldown', 'Date.now() - _syncPullCompletedAt < minIntervalMs'],
  ['background pull pause', "document.visibilityState === 'hidden'"],
  ['single family polling timer', 'if (_familySyncTimer) clearInterval(_familySyncTimer)'],
  ['single foreground listener', 'if (!_familyVisibilityBound)'],
  ['push coalescing', '_syncPushTimers.has(key)'],
  ['identical push suppression', 'Date.now() - previous.at < 30000'],
];

for (const [label, token] of checks) {
  if (!source.includes(token)) throw new Error(`${label}: missing ${token}`);
  console.log(`PASS ${label}`);
}

console.log('Cloud sync request guard PASS');
