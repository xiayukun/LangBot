import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const webRoot = path.resolve(import.meta.dirname, '../..');

function read(relativePath) {
  return fs.readFileSync(path.join(webRoot, relativePath), 'utf8');
}

test('bot form exposes strict and fallback routing modes', () => {
  const source = read('src/app/home/bots/components/bot-form/BotForm.tsx');

  assert.match(source, /routing_mode:\s*z\.enum/);
  assert.match(source, /routing_mode:\s*'routes_only'/);
  assert.match(source, /name="routing_mode"/);
  assert.match(source, /value="routes_only"/);
  assert.match(source, /value="fallback_default"/);
});

test('bot API type and both required locales describe routing mode', () => {
  const apiSource = read('src/app/infra/entities/api/index.ts');
  const english = read('src/i18n/locales/en-US.ts');
  const chinese = read('src/i18n/locales/zh-Hans.ts');

  assert.match(
    apiSource,
    /routing_mode\?:\s*'routes_only'\s*\|\s*'fallback_default'/,
  );
  for (const locale of [english, chinese]) {
    assert.match(locale, /routingMode:/);
    assert.match(locale, /routingModeRoutesOnly:/);
    assert.match(locale, /routingModeFallbackDefault:/);
    assert.match(locale, /routingModeRoutesOnlyDescription:/);
  }
});

test('each routing rule can choose mention-only or all group messages', () => {
  const editor = read(
    'src/app/home/bots/components/bot-form/RoutingRulesEditor.tsx',
  );
  const apiSource = read('src/app/infra/entities/api/index.ts');
  const english = read('src/i18n/locales/en-US.ts');
  const chinese = read('src/i18n/locales/zh-Hans.ts');

  assert.match(apiSource, /group_trigger\?:\s*'mention'\s*\|\s*'all'/);
  assert.match(editor, /group_trigger:\s*'mention'/);
  assert.match(editor, /value="mention"/);
  assert.match(editor, /value="all"/);
  for (const locale of [english, chinese]) {
    assert.match(locale, /groupTrigger:/);
    assert.match(locale, /groupTriggerMention:/);
    assert.match(locale, /groupTriggerAll:/);
  }
});
