import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDirectory, '../..');

test('notification center is routed and discoverable from the home sidebar', () => {
  const router = fs.readFileSync(path.join(webRoot, 'src/router.tsx'), 'utf8');
  const sidebar = fs.readFileSync(
    path.join(
      webRoot,
      'src/app/home/components/home-sidebar/sidbarConfigList.tsx',
    ),
    'utf8',
  );
  const layout = fs.readFileSync(
    path.join(webRoot, 'src/app/home/layout.tsx'),
    'utf8',
  );

  assert.match(router, /path: '\/home\/notifications'/);
  assert.match(router, /<NotificationsPage \/>/);
  assert.match(sidebar, /id: 'notifications'/);
  assert.match(sidebar, /route: '\/home\/notifications'/);
  assert.match(layout, /startsWith\('\/home\/notifications'\)/);
});

test('backend client exposes managed target CRUD and idempotent sending', () => {
  const client = fs.readFileSync(
    path.join(webRoot, 'src/app/infra/http/BackendClient.ts'),
    'utf8',
  );

  for (const method of [
    'getNotificationTargets',
    'createNotificationTarget',
    'updateNotificationTarget',
    'deleteNotificationTarget',
    'sendNotification',
    'getNotificationJob',
  ]) {
    assert.match(client, new RegExp(`\\b${method}\\(`));
  }
  assert.match(client, /'Idempotency-Key': idempotencyKey/);
});

test('notification page supports target management and multi-select test sends', () => {
  const page = fs.readFileSync(
    path.join(webRoot, 'src/app/home/notifications/page.tsx'),
    'utf8',
  );

  assert.match(page, /createNotificationTarget/);
  assert.match(page, /updateNotificationTarget/);
  assert.match(page, /deleteNotificationTarget/);
  assert.match(page, /sendNotification/);
  assert.match(page, /selectedTargetIds/);
  assert.match(page, /type: 'Plain'/);

  for (const locale of ['en-US.ts', 'zh-Hans.ts']) {
    const source = fs.readFileSync(
      path.join(webRoot, 'src/i18n/locales', locale),
      'utf8',
    );
    assert.match(source, /notifications: \{/);
    for (const key of [
      'title',
      'description',
      'createTarget',
      'testSend',
      'idempotencyHint',
      'partialFailed',
    ]) {
      assert.match(source, new RegExp(`\\b${key}:`), `${locale} misses ${key}`);
    }
  }
});
