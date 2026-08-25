import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BellRing,
  CheckCircle2,
  CircleAlert,
  Edit3,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  Users,
  UserRound,
} from 'lucide-react';
import { toast } from 'sonner';

import type {
  Bot,
  NotificationJob,
  NotificationTarget,
  NotificationTargetInput,
} from '@/app/infra/entities/api';
import { httpClient } from '@/app/infra/http/HttpClient';
import { useCurrentWorkspace } from '@/app/infra/http';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
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

const EMPTY_FORM: NotificationTargetInput = {
  name: '',
  bot_uuid: '',
  target_type: 'person',
  target_id: '',
  enabled: true,
};

function createIdempotencyKey(): string {
  const randomPart =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `notification-ui-${randomPart}`;
}

function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'msg' in error) {
    return String((error as { msg: unknown }).msg);
  }
  return error instanceof Error ? error.message : String(error);
}

export default function NotificationsPage() {
  const { t } = useTranslation();
  const workspace = useCurrentWorkspace();
  const canManage = workspace?.permissions.includes('resource.manage') ?? false;
  const canSend = workspace?.permissions.includes('runtime.operate') ?? false;
  const [targets, setTargets] = useState<NotificationTarget[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTargetIds, setSelectedTargetIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [lastJob, setLastJob] = useState<NotificationJob | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(createIdempotencyKey);
  const [formOpen, setFormOpen] = useState(false);
  const [editingTarget, setEditingTarget] = useState<NotificationTarget | null>(
    null,
  );
  const [targetForm, setTargetForm] =
    useState<NotificationTargetInput>(EMPTY_FORM);
  const [savingTarget, setSavingTarget] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<NotificationTarget | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);

  const botNames = useMemo(
    () => new Map(bots.map((bot) => [bot.uuid, bot.name])),
    [bots],
  );
  const enabledTargets = useMemo(
    () => targets.filter((target) => target.enabled),
    [targets],
  );
  const allEnabledSelected =
    enabledTargets.length > 0 &&
    enabledTargets.every((target) => selectedTargetIds.includes(target.uuid));

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [targetPage, botPage] = await Promise.all([
        httpClient.getNotificationTargets(0, 100),
        httpClient.getBots(),
      ]);
      setTargets(targetPage.targets);
      setBots(botPage.bots);
      setSelectedTargetIds((current) =>
        current.filter((uuid) =>
          targetPage.targets.some(
            (target) => target.uuid === uuid && target.enabled,
          ),
        ),
      );
    } catch (error) {
      toast.error(
        t('notifications.loadError', { error: getErrorMessage(error) }),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const openCreate = () => {
    setEditingTarget(null);
    setTargetForm({ ...EMPTY_FORM, bot_uuid: bots[0]?.uuid ?? '' });
    setFormOpen(true);
  };

  const openEdit = (target: NotificationTarget) => {
    setEditingTarget(target);
    setTargetForm({
      name: target.name,
      bot_uuid: target.bot_uuid,
      target_type: target.target_type,
      target_id: target.target_id,
      enabled: target.enabled,
    });
    setFormOpen(true);
  };

  const saveTarget = async () => {
    if (
      !targetForm.name.trim() ||
      !targetForm.bot_uuid ||
      !targetForm.target_id.trim()
    ) {
      toast.error(t('notifications.requiredFields'));
      return;
    }
    setSavingTarget(true);
    try {
      if (editingTarget) {
        await httpClient.updateNotificationTarget(
          editingTarget.uuid,
          targetForm,
        );
        toast.success(t('notifications.updateSuccess'));
      } else {
        await httpClient.createNotificationTarget(targetForm);
        toast.success(t('notifications.createSuccess'));
      }
      setFormOpen(false);
      await loadData();
    } catch (error) {
      toast.error(
        t('notifications.saveError', { error: getErrorMessage(error) }),
      );
    } finally {
      setSavingTarget(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await httpClient.deleteNotificationTarget(deleteTarget.uuid);
      toast.success(t('notifications.deleteSuccess'));
      setDeleteTarget(null);
      await loadData();
    } catch (error) {
      toast.error(
        t('notifications.deleteError', { error: getErrorMessage(error) }),
      );
    } finally {
      setDeleting(false);
    }
  };

  const toggleTarget = (uuid: string, checked: boolean) => {
    setSelectedTargetIds((current) =>
      checked
        ? Array.from(new Set([...current, uuid]))
        : current.filter((item) => item !== uuid),
    );
  };

  const toggleAll = (checked: boolean) => {
    setSelectedTargetIds(
      checked ? enabledTargets.map((target) => target.uuid) : [],
    );
  };

  const testSend = async () => {
    if (selectedTargetIds.length === 0) {
      toast.error(t('notifications.selectAtLeastOne'));
      return;
    }
    if (!message.trim()) {
      toast.error(t('notifications.messageRequired'));
      return;
    }
    setSending(true);
    try {
      const response = await httpClient.sendNotification(
        selectedTargetIds,
        [{ type: 'Plain', text: message.trim() }],
        idempotencyKey,
      );
      setLastJob(response.job);
      if (response.job.status === 'succeeded') {
        toast.success(t('notifications.sendSuccess'));
      } else if (response.job.status === 'partial_failed') {
        toast.warning(t('notifications.partialFailed'));
      } else {
        toast.error(t('notifications.sendFailed'));
      }
      setIdempotencyKey(createIdempotencyKey());
    } catch (error) {
      // Keep the same key after a network failure: retrying the button cannot
      // duplicate an already accepted job.
      toast.error(
        t('notifications.sendError', { error: getErrorMessage(error) }),
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="h-full w-full overflow-y-auto pb-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <BellRing className="h-6 w-6 text-blue-500" />
              <h1 className="text-2xl font-semibold tracking-tight">
                {t('notifications.title')}
              </h1>
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              {t('notifications.description')}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void loadData()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('notifications.refresh')}
            </Button>
            {canManage && (
              <Button onClick={openCreate} disabled={bots.length === 0}>
                <Plus className="mr-2 h-4 w-4" />
                {t('notifications.createTarget')}
              </Button>
            )}
          </div>
        </div>

        <Card className="border-blue-500/20 bg-gradient-to-br from-blue-500/5 via-background to-background">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Send className="h-5 w-5 text-blue-500" />
              {t('notifications.testSend')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {selectedTargetIds.length === 0 ? (
                <span className="text-sm text-muted-foreground">
                  {t('notifications.chooseTargetsBelow')}
                </span>
              ) : (
                targets
                  .filter((target) => selectedTargetIds.includes(target.uuid))
                  .map((target) => (
                    <Badge key={target.uuid} variant="secondary">
                      {target.name}
                    </Badge>
                  ))
              )}
            </div>
            <Textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t('notifications.messagePlaceholder')}
              rows={4}
              maxLength={8000}
            />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">
                {t('notifications.idempotencyHint')}
              </p>
              <Button
                onClick={() => void testSend()}
                disabled={!canSend || sending || selectedTargetIds.length === 0}
              >
                {sending ? (
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                {sending
                  ? t('notifications.sending')
                  : t('notifications.sendNow')}
              </Button>
            </div>
          </CardContent>
        </Card>

        {lastJob && (
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                {lastJob.status === 'succeeded' ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                ) : (
                  <CircleAlert className="h-5 w-5 text-amber-500" />
                )}
                {t('notifications.lastResult')}
                <Badge variant="outline">
                  {t(`notifications.status.${lastJob.status}`)}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              {lastJob.outcomes.map((outcome, index) => (
                <div
                  key={`${outcome.target_uuid ?? outcome.target_id}-${index}`}
                  className="flex items-start justify-between gap-3 rounded-lg border p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {outcome.target_name}
                    </p>
                    {outcome.error && (
                      <p className="mt-1 break-words text-xs text-destructive">
                        {outcome.error}
                      </p>
                    )}
                  </div>
                  <Badge
                    variant={
                      outcome.status === 'sent' ? 'secondary' : 'outline'
                    }
                  >
                    {t(`notifications.status.${outcome.status}`)}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-lg">
                {t('notifications.managedTargets')}
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('notifications.targetCount', { count: targets.length })}
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-16 text-muted-foreground">
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                {t('common.loading')}
              </div>
            ) : targets.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-muted-foreground">
                <BellRing className="h-10 w-10 opacity-40" />
                <div>
                  <p className="font-medium text-foreground">
                    {t('notifications.emptyTitle')}
                  </p>
                  <p className="mt-1 text-sm">
                    {t('notifications.emptyDescription')}
                  </p>
                </div>
                {canManage && bots.length > 0 && (
                  <Button variant="outline" onClick={openCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    {t('notifications.createTarget')}
                  </Button>
                )}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox
                        checked={allEnabledSelected}
                        onCheckedChange={(checked) =>
                          toggleAll(checked === true)
                        }
                        aria-label={t('notifications.selectAll')}
                      />
                    </TableHead>
                    <TableHead>{t('notifications.targetName')}</TableHead>
                    <TableHead>{t('notifications.type')}</TableHead>
                    <TableHead>{t('notifications.bot')}</TableHead>
                    <TableHead>{t('notifications.targetId')}</TableHead>
                    <TableHead>{t('notifications.state')}</TableHead>
                    <TableHead className="text-right">
                      {t('notifications.actions')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {targets.map((target) => (
                    <TableRow key={target.uuid}>
                      <TableCell>
                        <Checkbox
                          disabled={!target.enabled}
                          checked={selectedTargetIds.includes(target.uuid)}
                          onCheckedChange={(checked) =>
                            toggleTarget(target.uuid, checked === true)
                          }
                          aria-label={t('notifications.selectTarget', {
                            name: target.name,
                          })}
                        />
                      </TableCell>
                      <TableCell className="font-medium">
                        {target.name}
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5">
                          {target.target_type === 'group' ? (
                            <Users className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <UserRound className="h-4 w-4 text-muted-foreground" />
                          )}
                          {t(`notifications.targetTypes.${target.target_type}`)}
                        </span>
                      </TableCell>
                      <TableCell>
                        {botNames.get(target.bot_uuid) ?? target.bot_uuid}
                      </TableCell>
                      <TableCell className="max-w-60 truncate font-mono text-xs">
                        {target.target_id}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={target.enabled ? 'secondary' : 'outline'}
                        >
                          {target.enabled
                            ? t('notifications.enabled')
                            : t('notifications.disabled')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {canManage && (
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openEdit(target)}
                              aria-label={t('notifications.editTarget')}
                            >
                              <Edit3 className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setDeleteTarget(target)}
                              aria-label={t('notifications.deleteTarget')}
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
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingTarget
                ? t('notifications.editTarget')
                : t('notifications.createTarget')}
            </DialogTitle>
            <DialogDescription>
              {t('notifications.formDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="notification-target-name">
                {t('notifications.targetName')}
              </Label>
              <Input
                id="notification-target-name"
                value={targetForm.name}
                onChange={(event) =>
                  setTargetForm((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                placeholder={t('notifications.namePlaceholder')}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t('notifications.bot')}</Label>
              <Select
                value={targetForm.bot_uuid}
                onValueChange={(value) =>
                  setTargetForm((current) => ({
                    ...current,
                    bot_uuid: value,
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder={t('notifications.selectBot')} />
                </SelectTrigger>
                <SelectContent>
                  {bots
                    .filter((bot): bot is Bot & { uuid: string } => !!bot.uuid)
                    .map((bot) => (
                      <SelectItem key={bot.uuid} value={bot.uuid}>
                        {bot.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>{t('notifications.type')}</Label>
              <Select
                value={targetForm.target_type}
                onValueChange={(value: 'person' | 'group') =>
                  setTargetForm((current) => ({
                    ...current,
                    target_type: value,
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="person">
                    {t('notifications.targetTypes.person')}
                  </SelectItem>
                  <SelectItem value="group">
                    {t('notifications.targetTypes.group')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="notification-target-id">
                {t('notifications.targetId')}
              </Label>
              <Input
                id="notification-target-id"
                value={targetForm.target_id}
                onChange={(event) =>
                  setTargetForm((current) => ({
                    ...current,
                    target_id: event.target.value,
                  }))
                }
                placeholder={t('notifications.targetIdPlaceholder')}
              />
              <p className="text-xs text-muted-foreground">
                {t('notifications.targetIdHint')}
              </p>
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <Label htmlFor="notification-target-enabled">
                  {t('notifications.enabled')}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t('notifications.enabledHint')}
                </p>
              </div>
              <Switch
                id="notification-target-enabled"
                checked={targetForm.enabled}
                onCheckedChange={(checked) =>
                  setTargetForm((current) => ({
                    ...current,
                    enabled: checked,
                  }))
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => void saveTarget()} disabled={savingTarget}>
              {savingTarget ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('notifications.deleteTarget')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('notifications.deleteConfirmation', {
                name: deleteTarget?.name,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmDelete()}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? t('notifications.deleting') : t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
