'use strict';

const assert = require('assert');
const fs = require('fs');
const {
  createPseudoCatalog,
  placeholders,
  pseudoLocalize,
} = require('./i18n-pseudo-catalog.js');

const source = JSON.parse(fs.readFileSync('web/src/i18n/en.json', 'utf8'));
const pseudo = createPseudoCatalog(source);

assert.deepEqual(Object.keys(pseudo), Object.keys(source), 'Pseudo catalog must preserve key parity');
for (const key of Object.keys(source)) {
  assert(pseudo[key].startsWith('⟦') && pseudo[key].endsWith('⟧'), `${key} needs pseudo markers`);
  assert.deepEqual(
    placeholders(pseudo[key]),
    placeholders(source[key]),
    `${key} placeholders must remain byte-for-byte stable`,
  );
  assert(
    [...pseudo[key]].length > [...source[key]].length,
    `${key} must expand to reveal narrow layouts`,
  );
}

assert.equal(
  pseudoLocalize('Hello {name}'),
  '⟦Ħëŀŀö {name}～～～⟧',
);
assert.throws(() => createPseudoCatalog([]), /catalog must be an object/);
assert.throws(
  () => createPseudoCatalog({ bad: 42 }),
  /catalog value must be a string/,
);

console.log(`PASS: pseudo-localization pressure catalog (${Object.keys(pseudo).length} keys)`);
