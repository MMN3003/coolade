import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Switch from '@mui/material/Switch';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import AddIcon from '@mui/icons-material/Add';
import { useTranslation } from 'react-i18next';
import { adminModelsApi } from '@/api/endpoints';
import type { AdminModel, CreateModelRequest } from '@/api/types';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

// Contract note: ModelCreate has no is_enabled — new models are enabled by default.
const emptyForm: CreateModelRequest = {
  model_key: '',
  display_name: '',
  upstream_model: '',
  input_weight: 3,
  output_weight: 15,
  cache_read_weight: 0.3,
  sort_order: 0,
};

function UpstreamModelCell({ model }: { model: AdminModel }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(model.upstream_model);

  const mutation = useMutation({
    mutationFn: (v: string) => adminModelsApi.update(model.id, { upstream_model: v }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });

  return (
    <TextField
      size="small"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const v = value.trim();
        if (v && v !== model.upstream_model) mutation.mutate(v);
        else setValue(model.upstream_model);
      }}
      sx={{ width: 220 }}
      inputProps={{ style: { fontFamily: 'monospace', direction: 'ltr' } }}
    />
  );
}

function WeightCell({
  model,
  field,
}: {
  model: AdminModel;
  field: 'input_weight' | 'output_weight' | 'cache_read_weight';
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(String(model[field]));

  const mutation = useMutation({
    mutationFn: (v: number) => adminModelsApi.update(model.id, { [field]: v }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });

  return (
    <TextField
      size="small"
      type="number"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const num = Number(value);
        if (!Number.isNaN(num) && num !== model[field]) mutation.mutate(num);
      }}
      sx={{ width: 100 }}
      inputProps={{ step: 0.1 }}
    />
  );
}

export default function AdminModelsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const listQuery = useQuery({ queryKey: ['admin', 'models'], queryFn: adminModelsApi.list });

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateModelRequest>(emptyForm);

  const toggleEnabledMutation = useMutation({
    mutationFn: (m: AdminModel) => adminModelsApi.update(m.id, { is_enabled: !m.is_enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });

  const createMutation = useMutation({
    mutationFn: (body: CreateModelRequest) => adminModelsApi.create(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] });
      setCreateOpen(false);
      setForm(emptyForm);
    },
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>
          {t('admin.models.title')}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          {t('admin.models.addModel')}
        </Button>
      </Box>

      <Paper>
        {listQuery.isLoading && <LoadingState />}
        {listQuery.isError && (
          <ErrorState message={getErrorMessage(listQuery.error)} onRetry={() => listQuery.refetch()} />
        )}
        {listQuery.data && (
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t('admin.models.modelKey')}</TableCell>
                <TableCell>{t('admin.models.displayName')}</TableCell>
                <TableCell>{t('admin.models.upstreamModel')}</TableCell>
                <TableCell>{t('admin.models.inputWeight')}</TableCell>
                <TableCell>{t('admin.models.outputWeight')}</TableCell>
                <TableCell>{t('admin.models.cacheReadWeight')}</TableCell>
                <TableCell>{t('admin.models.enabled')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listQuery.data.map((m) => (
                <TableRow key={m.id} hover>
                  <TableCell sx={{ fontFamily: 'monospace', direction: 'ltr' }}>{m.model_key}</TableCell>
                  <TableCell>{m.display_name}</TableCell>
                  <TableCell>
                    <UpstreamModelCell model={m} />
                  </TableCell>
                  <TableCell>
                    <WeightCell model={m} field="input_weight" />
                  </TableCell>
                  <TableCell>
                    <WeightCell model={m} field="output_weight" />
                  </TableCell>
                  <TableCell>
                    <WeightCell model={m} field="cache_read_weight" />
                  </TableCell>
                  <TableCell>
                    <Switch checked={m.is_enabled} onChange={() => toggleEnabledMutation.mutate(m)} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('admin.models.addModel')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('admin.models.modelKey')}
              value={form.model_key}
              onChange={(e) => setForm({ ...form, model_key: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('admin.models.displayName')}
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              label={t('admin.models.upstreamModel')}
              value={form.upstream_model}
              onChange={(e) => setForm({ ...form, upstream_model: e.target.value })}
              fullWidth
              required
            />
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('admin.models.inputWeight')}
                type="number"
                value={form.input_weight}
                onChange={(e) => setForm({ ...form, input_weight: Number(e.target.value) })}
                fullWidth
              />
              <TextField
                label={t('admin.models.outputWeight')}
                type="number"
                value={form.output_weight}
                onChange={(e) => setForm({ ...form, output_weight: Number(e.target.value) })}
                fullWidth
              />
              <TextField
                label={t('admin.models.cacheReadWeight')}
                type="number"
                value={form.cache_read_weight}
                onChange={(e) => setForm({ ...form, cache_read_weight: Number(e.target.value) })}
                fullWidth
              />
            </Stack>
            {createMutation.isError && <Alert severity="error">{getErrorMessage(createMutation.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.model_key || !form.display_name || !form.upstream_model || createMutation.isPending}
            onClick={() => createMutation.mutate(form)}
          >
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
