function escapeTomlString(value: string): string {
  return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
}

export function buildCodexMcpConfig(mcpEndpoint: string): string {
  // Codex reads MCP servers and environment-backed HTTP headers from config.toml.
  // Source: https://developers.openai.com/codex/extend/mcp
  return `[mcp_servers.langbot_notify]
url = "${escapeTomlString(mcpEndpoint)}"
env_http_headers = { "X-API-Key" = "LANGBOT_API_KEY" }
required = false
default_tools_approval_mode = "writes"`;
}

export function buildGenericMcpConfig(mcpEndpoint: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        langbot_notify: {
          url: mcpEndpoint,
          headers: { 'X-API-Key': '<your-api-key>' },
        },
      },
    },
    null,
    2,
  );
}
