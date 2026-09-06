import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { useTranslation } from 'react-i18next';
import { authApi } from '@/api/endpoints';
import { getErrorMessage } from '@/utils/errors';

/** Self-service password change (local accounts). Requires the current
 * password; min 8 chars, confirmed twice. */
export default function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: () => authApi.changePassword({ current_password: current, new_password: next }),
    onSuccess: () => setDone(true),
  });

  function handleClose() {
    setCurrent('');
    setNext('');
    setConfirm('');
    setDone(false);
    mutation.reset();
    onClose();
  }

  const mismatch = confirm.length > 0 && next !== confirm;
  const tooShort = next.length > 0 && next.length < 8;
  const canSubmit =
    !mutation.isPending && current.length > 0 && next.length >= 8 && next === confirm;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>{t('auth.changePassword')}</DialogTitle>
      <DialogContent>
        {done ? (
          <Alert severity="success" sx={{ mt: 1 }}>
            {t('auth.passwordChanged')}
          </Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('auth.currentPassword')}
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
              fullWidth
              autoFocus
            />
            <TextField
              label={t('auth.newPassword')}
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              error={tooShort}
              helperText={t('auth.passwordMinLength')}
              fullWidth
            />
            <TextField
              label={t('auth.confirmPassword')}
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              error={mismatch}
              helperText={mismatch ? t('auth.passwordMismatch') : ' '}
              fullWidth
            />
            {mutation.isError && <Alert severity="error">{getErrorMessage(mutation.error)}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{done ? t('common.close') : t('common.cancel')}</Button>
        {!done && (
          <Button variant="contained" disabled={!canSubmit} onClick={() => mutation.mutate()}>
            {t('common.save')}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
