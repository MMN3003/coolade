import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { workspacesV2Api, type WorkspaceV2 } from '@/api/endpoints';

function statusColor(s: string): 'success' | 'default' | 'warning' {
  if (s === 'running') return 'success';
  if (s === 'provisioning' || s === 'stopping') return 'warning';
  return 'default';
}

export default function WorkspacesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('repo');
  const [repoUrl, setRepoUrl] = useState('');
  const [baseBranch, setBaseBranch] = useState('main');
  const [err, setErr] = useState<string | null>(null);

  const { data: workspaces = [], isLoading } = useQuery({
    queryKey: ['workspaces-v2'],
    queryFn: workspacesV2Api.list,
    refetchInterval: 5000,
  });
  const { data: gitlab } = useQuery({ queryKey: ['gitlab-status'], queryFn: workspacesV2Api.gitlabStatus });

  const invalidate = () => qc.invalidateQueries({ queryKey: ['workspaces-v2'] });
  const createMut = useMutation({
    mutationFn: () =>
      workspacesV2Api.create({
        name,
        kind,
        repo_url: kind === 'repo' ? repoUrl : null,
        base_branch: kind === 'repo' ? baseBranch : null,
      }),
    onSuccess: () => {
      setOpen(false);
      setName('');
      setRepoUrl('');
      setErr(null);
      invalidate();
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'خطا در ساخت ورک‌اسپیس'),
  });
  const resumeMut = useMutation({ mutationFn: workspacesV2Api.resume, onSuccess: invalidate });
  const stopMut = useMutation({ mutationFn: workspacesV2Api.stop, onSuccess: invalidate });
  const removeMut = useMutation({ mutationFn: workspacesV2Api.remove, onSuccess: invalidate });

  const openIde = (w: WorkspaceV2) => window.open(`/ide/${w.id}/`, '_blank');

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h5">ورک‌اسپیس‌های کد</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>
          ورک‌اسپیس جدید
        </Button>
      </Stack>

      {!gitlab?.connected && (
        <Alert severity="info" sx={{ mb: 2 }}>
          برای ورک‌اسپیس ریپویی، ابتدا توکن گیت‌لب شخصی‌ات را در صفحهٔ «کلیدها/پروفایل» ثبت کن. ورک‌اسپیس شخصی
          (بدون ریپو) بدون توکن هم ساخته می‌شود.
        </Alert>
      )}

      <Paper variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>نام</TableCell>
              <TableCell>نوع</TableCell>
              <TableCell>وضعیت</TableCell>
              <TableCell>ریپو</TableCell>
              <TableCell align="right">عملیات</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {workspaces.map((w) => (
              <TableRow key={w.id}>
                <TableCell>{w.name}</TableCell>
                <TableCell>{w.kind === 'repo' ? 'ریپویی' : 'شخصی'}</TableCell>
                <TableCell>
                  <Chip size="small" color={statusColor(w.status)} label={w.status} />
                </TableCell>
                <TableCell sx={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {w.repo_url || '—'}
                </TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    {w.status === 'running' ? (
                      <>
                        <Button size="small" variant="contained" onClick={() => openIde(w)}>
                          باز کردن IDE
                        </Button>
                        <Button size="small" onClick={() => stopMut.mutate(w.id)}>
                          توقف
                        </Button>
                      </>
                    ) : (
                      <Button size="small" variant="outlined" onClick={() => resumeMut.mutate(w.id)}>
                        راه‌اندازی
                      </Button>
                    )}
                    <Button size="small" color="error" onClick={() => removeMut.mutate(w.id)}>
                      حذف
                    </Button>
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && workspaces.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ color: 'text.secondary', py: 4 }}>
                  هنوز ورک‌اسپیسی نساخته‌ای.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>ورک‌اسپیس جدید</DialogTitle>
        <DialogContent>
          {err && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {err}
            </Alert>
          )}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="نام" value={name} onChange={(e) => setName(e.target.value)} fullWidth />
            <TextField
              select
              label="نوع"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              fullWidth
            >
              <MenuItem value="repo">ریپویی (کد از گیت‌لب)</MenuItem>
              <MenuItem value="personal">شخصی (بدون ریپو)</MenuItem>
            </TextField>
            {kind === 'repo' && (
              <>
                <TextField
                  label="آدرس ریپو (https)"
                  placeholder="https://git.ecobin.ir/team/project.git"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  fullWidth
                />
                <TextField
                  label="برنچ مبنا"
                  value={baseBranch}
                  onChange={(e) => setBaseBranch(e.target.value)}
                  fullWidth
                />
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>انصراف</Button>
          <Button
            variant="contained"
            disabled={!name || (kind === 'repo' && !repoUrl) || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            {createMut.isPending ? 'در حال ساخت…' : 'ساخت'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
