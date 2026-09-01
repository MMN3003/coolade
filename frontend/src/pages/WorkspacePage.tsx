import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import SaveIcon from '@mui/icons-material/SaveOutlined';
import { useTheme } from '@mui/material/styles';
import Editor from '@monaco-editor/react';
import { useTranslation } from 'react-i18next';
import { workspaceApi } from '@/api/endpoints';
import { languageForPath } from '@/lib/monaco';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';

/**
 * اصلاحیهٔ ۶ / amendment 6 — «ادیتور» (VS Code-style web editor, stage 1).
 * A Monaco editor over the user's server-side sandboxed workspace: browse the
 * files the assistant created/edited, open them, edit, and save back. Runs over
 * the SAME sandbox as chat (no shell) — command execution (git/Bash) is stage 2
 * behind a per-session isolated runner.
 */
export default function WorkspacePage() {
  const { t } = useTranslation();
  const theme = useTheme();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [value, setValue] = useState('');
  const [dirty, setDirty] = useState(false);

  const filesQuery = useQuery({ queryKey: ['workspace', 'files'], queryFn: workspaceApi.listFiles });

  const contentQuery = useQuery({
    queryKey: ['workspace', 'content', selected],
    queryFn: () => workspaceApi.readContent(selected!),
    enabled: !!selected,
  });

  useEffect(() => {
    if (contentQuery.data) {
      setValue(contentQuery.data.content);
      setDirty(false);
    }
  }, [contentQuery.data]);

  const relpath = contentQuery.data?.relpath ?? '';
  const language = useMemo(() => languageForPath(relpath), [relpath]);

  const saveMutation = useMutation({
    mutationFn: () => workspaceApi.save(relpath, value),
    onSuccess: () => {
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ['workspace', 'files'] });
    },
  });

  const files = filesQuery.data ?? [];

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 1.5 }}>
      <Typography variant="h5">{t('workspace.title')}</Typography>
      <Box sx={{ display: 'flex', gap: 1.5, flexGrow: 1, minHeight: 0 }}>
        {/* File tree */}
        <Paper variant="outlined" sx={{ width: 260, flexShrink: 0, overflowY: 'auto' }}>
          {filesQuery.isLoading && <LoadingState />}
          {filesQuery.isError && (
            <ErrorState message={getErrorMessage(filesQuery.error)} onRetry={() => filesQuery.refetch()} />
          )}
          {filesQuery.isSuccess && files.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2, textAlign: 'center' }}>
              {t('workspace.empty')}
            </Typography>
          )}
          <List dense disablePadding>
            {files.map((f) => (
              <ListItemButton
                key={f.file_id}
                selected={selected === f.file_id}
                onClick={() => setSelected(f.file_id)}
              >
                <ListItemText
                  primary={f.relpath}
                  primaryTypographyProps={{ variant: 'body2', noWrap: true, sx: { direction: 'ltr', textAlign: 'start' } }}
                />
              </ListItemButton>
            ))}
          </List>
        </Paper>

        {/* Editor */}
        <Paper variant="outlined" sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {!selected && (
            <Box sx={{ m: 'auto', p: 3, color: 'text.secondary' }}>
              <Typography variant="body2">{t('workspace.pickFile')}</Typography>
            </Box>
          )}
          {selected && (
            <>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 1, borderBottom: 1, borderColor: 'divider' }}>
                <Typography variant="body2" sx={{ direction: 'ltr', flexGrow: 1 }} noWrap>
                  {relpath}
                </Typography>
                {dirty && <Chip size="small" color="warning" variant="outlined" label={t('workspace.unsaved')} />}
                {contentQuery.data?.truncated && (
                  <Chip size="small" color="error" variant="outlined" label={t('workspace.truncated')} />
                )}
                <Button
                  size="small"
                  variant="contained"
                  startIcon={<SaveIcon />}
                  disabled={!dirty || saveMutation.isPending}
                  onClick={() => saveMutation.mutate()}
                >
                  {t('common.save')}
                </Button>
              </Box>
              {saveMutation.isError && (
                <Alert severity="error" sx={{ borderRadius: 0 }}>
                  {getErrorMessage(saveMutation.error)}
                </Alert>
              )}
              {contentQuery.isLoading ? (
                <LoadingState />
              ) : contentQuery.isError ? (
                <ErrorState message={getErrorMessage(contentQuery.error)} onRetry={() => contentQuery.refetch()} />
              ) : (
                <Box sx={{ flexGrow: 1, minHeight: 0 }}>
                  <Editor
                    height="100%"
                    language={language}
                    theme={theme.palette.mode === 'dark' ? 'vs-dark' : 'light'}
                    value={value}
                    onChange={(v: string | undefined) => {
                      setValue(v ?? '');
                      setDirty(true);
                    }}
                    options={{ fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false }}
                  />
                </Box>
              )}
            </>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
