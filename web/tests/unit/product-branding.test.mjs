import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDirectory, '../..');

function read(relativePath) {
  return fs.readFileSync(path.join(webRoot, relativePath), 'utf8');
}

test('the application shell displays the Feishu Agent Hub product name', () => {
  const index = read('index.html');
  const documentTitle = read('src/hooks/useDocumentTitle.ts');
  const sidebar = read(
    'src/app/home/components/home-sidebar/HomeSidebar.tsx',
  );

  assert.match(index, /<title>Feishu Agent Hub<\/title>/);
  assert.match(documentTitle, /const APP_NAME = 'Feishu Agent Hub'/);
  assert.match(sidebar, /tooltip="Feishu Agent Hub"/);
  assert.match(sidebar, />\s*Feishu Agent Hub\s*</);
});
