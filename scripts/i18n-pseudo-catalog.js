'use strict';

const PLACEHOLDER_RE = /\{[A-Za-z][A-Za-z0-9_]*\}/g;
const LATIN_MAP = Object.freeze({
  A: 'Å', B: 'Ɓ', C: 'Ç', D: 'Ð', E: 'Ë', F: 'Ƒ', G: 'Ĝ', H: 'Ħ',
  I: 'Ï', J: 'Ĵ', K: 'Ķ', L: 'Ŀ', M: 'M', N: 'Ñ', O: 'Ö', P: 'Þ',
  Q: 'Q', R: 'Ŕ', S: 'Š', T: 'Ŧ', U: 'Ü', V: 'V', W: 'Ŵ', X: 'X',
  Y: 'Ÿ', Z: 'Ž',
  a: 'å', b: 'ƀ', c: 'ç', d: 'ð', e: 'ë', f: 'ƒ', g: 'ĝ', h: 'ħ',
  i: 'ï', j: 'ĵ', k: 'ķ', l: 'ŀ', m: 'm', n: 'ñ', o: 'ö', p: 'þ',
  q: 'q', r: 'ŕ', s: 'š', t: 'ŧ', u: 'ü', v: 'v', w: 'ŵ', x: 'x',
  y: 'ÿ', z: 'ž',
});

function placeholders(value) {
  return String(value).match(PLACEHOLDER_RE) || [];
}

function pseudoSegment(value) {
  return [...value].map((character) => LATIN_MAP[character] || character).join('');
}

function pseudoLocalize(value, expansionRatio = 0.35) {
  const source = String(value);
  const parts = [];
  let lastIndex = 0;
  for (const match of source.matchAll(PLACEHOLDER_RE)) {
    parts.push(pseudoSegment(source.slice(lastIndex, match.index)));
    parts.push(match[0]);
    lastIndex = match.index + match[0].length;
  }
  parts.push(pseudoSegment(source.slice(lastIndex)));
  const visibleLength = [...source.replace(PLACEHOLDER_RE, '')].length;
  const expansion = '～'.repeat(Math.max(1, Math.ceil(visibleLength * expansionRatio)));
  return `⟦${parts.join('')}${expansion}⟧`;
}

function createPseudoCatalog(catalog, expansionRatio) {
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) {
    throw new TypeError('i18n catalog must be an object');
  }
  return Object.fromEntries(
    Object.entries(catalog).map(([key, value]) => {
      if (typeof value !== 'string') {
        throw new TypeError(`i18n catalog value must be a string: ${key}`);
      }
      return [key, pseudoLocalize(value, expansionRatio)];
    }),
  );
}

module.exports = {
  createPseudoCatalog,
  placeholders,
  pseudoLocalize,
};
