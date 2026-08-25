import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const webRoot = path.resolve(import.meta.dirname, '../..');
const read = (relativePath) =>
  fs.readFileSync(path.join(webRoot, relativePath), 'utf8');

test('Agent connector management is routed and exposed by the backend client', () => {
  const router = read('src/router.tsx');
  const sidebar = read(
    'src/app/home/components/home-sidebar/sidbarConfigList.tsx',
  );
  const client = read('src/app/infra/http/BackendClient.ts');

  assert.match(router, /path: '\/home\/agent-connectors'/);
  assert.match(router, /<AgentConnectorsPage \/>/);
  assert.match(sidebar, /id: 'agent-connectors'/);
  for (const method of [
    'getAgentConnectors',
    'createAgentConnector',
    'updateAgentConnector',
    'deleteAgentConnector',
    'getAgentConversations',
    'getAgentConversationHistory',
  ]) {
    assert.match(client, new RegExp(`\\b${method}\\(`));
  }
});

test('bot routes can select exactly one Agent connector destination', () => {
  const editor = read(
    'src/app/home/bots/components/bot-form/RoutingRulesEditor.tsx',
  );
  const form = read('src/app/home/bots/components/bot-form/BotForm.tsx');
  const api = read('src/app/infra/entities/api/index.ts');

  assert.match(api, /agent_connector_uuid\?: string/);
  assert.match(editor, /value={`agent:\${connector\.uuid}`}/);
  assert.match(editor, /pipeline_uuid: undefined/);
  assert.match(
    form,
    /Boolean\(rule\.pipeline_uuid\).*Boolean\(rule\.agent_connector_uuid\)/s,
  );
});

test('connector page manages prompt, skills, endpoint, and never asks for a secret', () => {
  const page = read('src/app/home/agent-connectors/page.tsx');

  assert.match(page, /system_prompt/);
  assert.match(page, /skill_names_text/);
  assert.match(page, /endpoint_url/);
  assert.match(page, /timeout_seconds/);
  assert.match(page, /conversationHistory/);
  assert.match(page, /invocationAudit/);
  assert.doesNotMatch(page, /api[_ -]?key/i);
});
