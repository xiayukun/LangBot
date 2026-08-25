import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDirectory, '../..');
const contentPath = path.join(
  webRoot,
  'src/app/home/components/api-integration-dialog/AgentGuideContent.ts',
);

function loadContentBuilders() {
  const source = fs.readFileSync(contentPath, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  const loadedModule = { exports: {} };
  new Function('require', 'module', 'exports', compiled)(
    () => {
      throw new Error('AgentGuideContent must not have runtime imports');
    },
    loadedModule,
    loadedModule.exports,
  );
  return loadedModule.exports;
}

test('builds a Codex Streamable HTTP config without embedding a secret', () => {
  const { buildCodexMcpConfig } = loadContentBuilders();
  const config = buildCodexMcpConfig('https://notify.example.com/mcp');

  assert.match(config, /\[mcp_servers\.langbot_notify\]/);
  assert.match(config, /url = "https:\/\/notify\.example\.com\/mcp"/);
  assert.match(
    config,
    /env_http_headers = \{ "X-API-Key" = "LANGBOT_API_KEY" \}/,
  );
  assert.match(config, /default_tools_approval_mode = "writes"/);
  assert.doesNotMatch(config, /lbk_[A-Za-z0-9]/);
  assert.doesNotMatch(config, /<your-api-key>/);
});

test('builds a generic MCP client config with an explicit placeholder', () => {
  const { buildGenericMcpConfig } = loadContentBuilders();
  const parsed = JSON.parse(
    buildGenericMcpConfig('https://notify.example.com/mcp'),
  );

  assert.deepEqual(parsed, {
    mcpServers: {
      langbot_notify: {
        url: 'https://notify.example.com/mcp',
        headers: { 'X-API-Key': '<your-api-key>' },
      },
    },
  });
});

test('the API integration panel exposes a translated Agent Guide tab', () => {
  const panel = fs.readFileSync(
    path.join(
      webRoot,
      'src/app/home/components/api-integration-dialog/ApiIntegrationPanel.tsx',
    ),
    'utf8',
  );
  const agentGuidePanel = fs.readFileSync(
    path.join(
      webRoot,
      'src/app/home/components/api-integration-dialog/AgentGuidePanel.tsx',
    ),
    'utf8',
  );

  assert.match(panel, /TabsTrigger value="agent-guide"/);
  assert.match(panel, /<AgentGuidePanel/);
  assert.match(agentGuidePanel, /common\.agentGuidePrompt/);
  assert.match(agentGuidePanel, /buildCodexMcpConfig/);

  for (const locale of ['en-US.ts', 'zh-Hans.ts']) {
    const source = fs.readFileSync(
      path.join(webRoot, 'src/i18n/locales', locale),
      'utf8',
    );
    for (const key of [
      'agentGuideTab',
      'agentGuideHint',
      'agentGuidePromptTitle',
      'agentGuidePrompt',
      'agentGuideCodexConfigTitle',
      'agentGuideGenericConfigTitle',
    ]) {
      assert.match(source, new RegExp(`\\b${key}:`), `${locale} misses ${key}`);
    }
  }

  for (const locale of ['en-US.ts', 'zh-Hans.ts']) {
    const source = fs.readFileSync(
      path.join(webRoot, 'src/i18n/locales', locale),
      'utf8',
    );
    assert.match(source, /list_notification_targets/);
    assert.match(source, /send_notification/);
    assert.match(source, /get_notification_job/);
  }
});
