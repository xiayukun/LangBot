import { Check, Copy } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  buildCodexMcpConfig,
  buildGenericMcpConfig,
} from './AgentGuideContent';

interface CopyBlockProps {
  id: string;
  label: string;
  value: string;
  copyLabel: string;
  isCopied: boolean;
  onCopy: (value: string) => void;
  wrap?: boolean;
}

function CopyBlock({
  id,
  label,
  value,
  copyLabel,
  isCopied,
  onCopy,
  wrap = false,
}: CopyBlockProps) {
  return (
    <section className="space-y-2" aria-labelledby={id}>
      <div className="flex items-center justify-between gap-3">
        <h3 id={id} className="text-sm font-medium">
          {label}
        </h3>
        <Button
          variant="outline"
          size="sm"
          type="button"
          className="shrink-0 gap-2"
          onClick={() => onCopy(value)}
          aria-label={copyLabel}
        >
          {isCopied ? (
            <Check className="h-4 w-4 text-green-600" aria-hidden="true" />
          ) : (
            <Copy className="h-4 w-4" aria-hidden="true" />
          )}
          {copyLabel}
        </Button>
      </div>
      <pre
        className={`max-h-72 overflow-auto rounded border bg-muted px-3 py-2 text-xs ${
          wrap ? 'whitespace-pre-wrap break-words' : ''
        }`}
      >
        {value}
      </pre>
    </section>
  );
}

interface AgentGuidePanelProps {
  mcpEndpoint: string;
  copiedValue: string | null;
  onCopy: (value: string) => void;
}

export default function AgentGuidePanel({
  mcpEndpoint,
  copiedValue,
  onCopy,
}: AgentGuidePanelProps) {
  const { t } = useTranslation();
  const agentPrompt = t('common.agentGuidePrompt', { mcpEndpoint });
  const codexConfig = buildCodexMcpConfig(mcpEndpoint);
  const genericConfig = buildGenericMcpConfig(mcpEndpoint);

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        {t('common.agentGuideHint')}
      </p>

      <CopyBlock
        id="agent-guide-prompt"
        label={t('common.agentGuidePromptTitle')}
        value={agentPrompt}
        copyLabel={t('common.agentGuideCopyPrompt')}
        isCopied={copiedValue === agentPrompt}
        onCopy={onCopy}
        wrap
      />

      <div className="space-y-2">
        <CopyBlock
          id="agent-guide-codex-config"
          label={t('common.agentGuideCodexConfigTitle')}
          value={codexConfig}
          copyLabel={t('common.copy')}
          isCopied={copiedValue === codexConfig}
          onCopy={onCopy}
        />
        <p className="text-sm text-muted-foreground">
          {t('common.agentGuideCodexConfigHint')}
        </p>
      </div>

      <CopyBlock
        id="agent-guide-generic-config"
        label={t('common.agentGuideGenericConfigTitle')}
        value={genericConfig}
        copyLabel={t('common.copy')}
        isCopied={copiedValue === genericConfig}
        onCopy={onCopy}
      />
    </div>
  );
}
