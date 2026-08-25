import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bot,
  Edit3,
  Eye,
  MessageSquare,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

import type {
  AgentConnector,
  AgentConnectorInput,
  AgentConversationSummary,
  ApiRespAgentConversationHistory,
} from '@/app/infra/entities/api';
import { useCurrentWorkspace } from '@/app/infra/http';
import { httpClient } from '@/app/infra/http/HttpClient';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

type ConnectorForm = Omit<AgentConnectorInput, 'skill_names'> & {
  skill_names_text: string;
};

const EMPTY_FORM: ConnectorForm = {
  name: '',
  kind: 'http',
  endpoint_url: 'http://127.0.0.1:8765/invoke',
  system_prompt: '',
  skill_names_text: '',
  enabled: true,
  timeout_seconds: 30,
};

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'msg' in error) {
    return String((error as { msg: unknown }).msg);
  }
  return error instanceof Error ? error.message : String(error);
}

function toInput(form: ConnectorForm): AgentConnectorInput {
  return {
    name: form.name.trim(),
    kind: form.kind,
    endpoint_url: form.endpoint_url.trim(),
    system_prompt: form.system_prompt,
    skill_names: form.skill_names_text
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean),
    enabled: form.enabled,
    timeout_seconds: Number(form.timeout_seconds),
  };
}

function messageText(messageChain: Array<Record<string, unknown>>): string {
  const text = messageChain
    .filter((item) => item.type === 'Plain' && typeof item.text === 'string')
    .map((item) => String(item.text))
    .join('');
  return text || JSON.stringify(messageChain);
}

export default function AgentConnectorsPage() {
  const { t } = useTranslation();
  const workspace = useCurrentWorkspace();
  const canManage = workspace?.permissions.includes('resource.manage') ?? false;
  const [connectors, setConnectors] = useState<AgentConnector[]>([]);
  const [conversations, setConversations] = useState<
    AgentConversationSummary[]
  >([]);
  const [history, setHistory] =
    useState<ApiRespAgentConversationHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<ConnectorForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<AgentConnector | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<AgentConnector | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const loadConnectors = useCallback(async () => {
    setLoading(true);
    try {
      const [connectorResponse, conversationResponse] = await Promise.all([
        httpClient.getAgentConnectors(),
        httpClient.getAgentConversations(100),
      ]);
      setConnectors(connectorResponse.connectors);
      setConversations(conversationResponse.conversations);
    } catch (error) {
      toast.error(
        t('agentConnectors.loadError', { error: getErrorMessage(error) }),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadConnectors();
  }, [loadConnectors]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setFormOpen(true);
  };

  const openEdit = (connector: AgentConnector) => {
    setEditing(connector);
    setForm({
      name: connector.name,
      kind: connector.kind,
      endpoint_url: connector.endpoint_url,
      system_prompt: connector.system_prompt,
      skill_names_text: connector.skill_names.join(', '),
      enabled: connector.enabled,
      timeout_seconds: connector.timeout_seconds,
    });
    setFormOpen(true);
  };

  const saveConnector = async () => {
    const input = toInput(form);
    if (!input.name || !input.endpoint_url) {
      toast.error(t('agentConnectors.requiredFields'));
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await httpClient.updateAgentConnector(editing.uuid, input);
        toast.success(t('agentConnectors.updateSuccess'));
      } else {
        await httpClient.createAgentConnector(input);
        toast.success(t('agentConnectors.createSuccess'));
      }
      setFormOpen(false);
      await loadConnectors();
    } catch (error) {
      toast.error(
        t('agentConnectors.saveError', { error: getErrorMessage(error) }),
      );
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await httpClient.deleteAgentConnector(deleting.uuid);
      toast.success(t('agentConnectors.deleteSuccess'));
      setDeleting(null);
      await loadConnectors();
    } catch (error) {
      toast.error(
        t('agentConnectors.deleteError', { error: getErrorMessage(error) }),
      );
    } finally {
      setDeleteBusy(false);
    }
  };

  const openHistory = async (conversationUuid: string) => {
    setHistoryLoading(true);
    try {
      setHistory(
        await httpClient.getAgentConversationHistory(conversationUuid, 200),
      );
    } catch (error) {
      toast.error(
        t('agentConnectors.historyLoadError', {
          error: getErrorMessage(error),
        }),
      );
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="h-6 w-6 text-blue-500" />
            <h1 className="text-2xl font-semibold">
              {t('agentConnectors.title')}
            </h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('agentConnectors.description')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void loadConnectors()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('agentConnectors.refresh')}
          </Button>
          {canManage && (
            <Button onClick={openCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('agentConnectors.create')}
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('agentConnectors.protocolTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>{t('agentConnectors.protocolDescription')}</p>
          <p>{t('agentConnectors.securityHint')}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('agentConnectors.conversationHistory')}</CardTitle>
        </CardHeader>
        <CardContent>
          {conversations.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <MessageSquare className="mx-auto mb-3 h-9 w-9 opacity-40" />
              {t('agentConnectors.noConversations')}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('agentConnectors.connector')}</TableHead>
                  <TableHead>{t('agentConnectors.session')}</TableHead>
                  <TableHead>{t('agentConnectors.messageCount')}</TableHead>
                  <TableHead>{t('agentConnectors.cursor')}</TableHead>
                  <TableHead>{t('agentConnectors.lastMessage')}</TableHead>
                  <TableHead className="text-right">
                    {t('agentConnectors.actions')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conversation) => (
                  <TableRow key={conversation.uuid}>
                    <TableCell>
                      {conversation.connector_name ??
                        conversation.connector_uuid}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {conversation.launcher_type}:{conversation.launcher_id}
                    </TableCell>
                    <TableCell>{conversation.message_count}</TableCell>
                    <TableCell>
                      {conversation.cursor_message_id ?? '—'}
                    </TableCell>
                    <TableCell>
                      {conversation.last_message_at
                        ? new Date(
                            conversation.last_message_at,
                          ).toLocaleString()
                        : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t('agentConnectors.viewHistory')}
                        disabled={historyLoading}
                        onClick={() => void openHistory(conversation.uuid)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('agentConnectors.managed')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {t('common.loading')}
            </p>
          ) : connectors.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              <Bot className="mx-auto mb-3 h-10 w-10 opacity-40" />
              <p>{t('agentConnectors.empty')}</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('agentConnectors.name')}</TableHead>
                  <TableHead>{t('agentConnectors.kind')}</TableHead>
                  <TableHead>{t('agentConnectors.endpoint')}</TableHead>
                  <TableHead>{t('agentConnectors.skills')}</TableHead>
                  <TableHead>{t('agentConnectors.state')}</TableHead>
                  <TableHead className="text-right">
                    {t('agentConnectors.actions')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connectors.map((connector) => (
                  <TableRow key={connector.uuid}>
                    <TableCell className="font-medium">
                      {connector.name}
                    </TableCell>
                    <TableCell>
                      {t(`agentConnectors.kinds.${connector.kind}`)}
                    </TableCell>
                    <TableCell className="max-w-[360px] truncate font-mono text-xs">
                      {connector.endpoint_url}
                    </TableCell>
                    <TableCell>{connector.skill_names.length}</TableCell>
                    <TableCell>
                      <Badge
                        variant={connector.enabled ? 'default' : 'secondary'}
                      >
                        {connector.enabled
                          ? t('agentConnectors.enabled')
                          : t('agentConnectors.disabled')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {canManage && (
                        <div className="inline-flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t('agentConnectors.edit')}
                            onClick={() => openEdit(connector)}
                          >
                            <Edit3 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={t('agentConnectors.delete')}
                            onClick={() => setDeleting(connector)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editing
                ? t('agentConnectors.edit')
                : t('agentConnectors.create')}
            </DialogTitle>
            <DialogDescription>
              {t('agentConnectors.formDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="connector-name">
                {t('agentConnectors.name')}
              </Label>
              <Input
                id="connector-name"
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
              />
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>{t('agentConnectors.kind')}</Label>
                <Select
                  value={form.kind}
                  onValueChange={(kind: AgentConnectorInput['kind']) =>
                    setForm((current) => ({ ...current, kind }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="http">
                      {t('agentConnectors.kinds.http')}
                    </SelectItem>
                    <SelectItem value="codex_bridge">
                      {t('agentConnectors.kinds.codex_bridge')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="connector-timeout">
                  {t('agentConnectors.timeout')}
                </Label>
                <Input
                  id="connector-timeout"
                  type="number"
                  min={1}
                  max={120}
                  value={form.timeout_seconds}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      timeout_seconds: Number(event.target.value),
                    }))
                  }
                />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="connector-endpoint">
                {t('agentConnectors.endpoint')}
              </Label>
              <Input
                id="connector-endpoint"
                value={form.endpoint_url}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    endpoint_url: event.target.value,
                  }))
                }
              />
              <p className="text-xs text-muted-foreground">
                {t('agentConnectors.endpointHint')}
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="connector-prompt">
                {t('agentConnectors.systemPrompt')}
              </Label>
              <Textarea
                id="connector-prompt"
                rows={6}
                value={form.system_prompt}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    system_prompt: event.target.value,
                  }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="connector-skills">
                {t('agentConnectors.skillNames')}
              </Label>
              <Input
                id="connector-skills"
                value={form.skill_names_text}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    skill_names_text: event.target.value,
                  }))
                }
                placeholder={t('agentConnectors.skillNamesPlaceholder')}
              />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <Label>{t('agentConnectors.enabled')}</Label>
                <p className="text-xs text-muted-foreground">
                  {t('agentConnectors.enabledHint')}
                </p>
              </div>
              <Switch
                checked={form.enabled}
                onCheckedChange={(enabled) =>
                  setForm((current) => ({ ...current, enabled }))
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => void saveConnector()} disabled={saving}>
              {saving ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('agentConnectors.delete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('agentConnectors.deleteConfirmation', {
                name: deleting?.name ?? '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmDelete()}
              disabled={deleteBusy}
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={history !== null}
        onOpenChange={(open) => !open && setHistory(null)}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('agentConnectors.conversationHistory')}
            </DialogTitle>
            <DialogDescription>
              {history
                ? `${history.conversation.launcher_type}:${history.conversation.launcher_id}`
                : ''}
            </DialogDescription>
          </DialogHeader>
          {history && (
            <div className="space-y-6">
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">
                  {t('agentConnectors.messages')}
                </h3>
                {history.messages.map((message) => (
                  <div
                    key={message.id}
                    className="rounded-md border p-3 text-sm"
                  >
                    <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                      <Badge
                        variant={
                          message.role === 'assistant' ? 'default' : 'secondary'
                        }
                      >
                        {message.role}
                      </Badge>
                      <span>#{message.id}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words">
                      {messageText(message.message_chain)}
                    </p>
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold">
                  {t('agentConnectors.invocationAudit')}
                </h3>
                {history.invocations.map((invocation) => (
                  <div
                    key={invocation.uuid}
                    className="rounded-md border p-3 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{invocation.status}</Badge>
                      <span className="font-mono text-xs">
                        {invocation.uuid}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        → #{invocation.through_message_id}
                      </span>
                    </div>
                    {invocation.error && (
                      <p className="mt-2 break-words text-sm text-destructive">
                        {invocation.error}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
