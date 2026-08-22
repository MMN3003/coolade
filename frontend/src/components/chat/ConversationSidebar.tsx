import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Tooltip from '@mui/material/Tooltip';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import { useTranslation } from 'react-i18next';
import { conversationsApi } from '@/api/endpoints';
import type { Conversation } from '@/api/types';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';
import { getErrorMessage } from '@/utils/errors';

export default function ConversationSidebar({ activeId }: { activeId?: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

  const listQuery = useQuery({
    queryKey: ['conversations', debouncedSearch],
    queryFn: () => conversationsApi.list(debouncedSearch || undefined),
    // اصلاحیهٔ ۲ / Issue A (TECH.md §9): the sidebar spinner is normally kept
    // fresh by invalidation after a stream's `done`/`idle`/`error`, but a
    // *different* tab/session generating in a conversation we're not viewing
    // wouldn't otherwise notify us — light polling while anything is
    // generating catches that case without polling when idle.
    refetchInterval: (query) => (query.state.data?.some((c) => c.generating) ? 10_000 : false),
  });

  const renameMutation = useMutation({
    mutationFn: (vars: { id: number; title: string }) =>
      conversationsApi.update(vars.id, { title: vars.title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      setRenamingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => conversationsApi.remove(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      setDeleteTarget(null);
      if (activeId === id) navigate('/chat');
    },
  });

  function startRename(conv: Conversation) {
    setRenamingId(conv.id);
    setRenameValue(conv.title);
  }

  function commitRename(id: number) {
    const title = renameValue.trim();
    if (!title) {
      setRenamingId(null);
      return;
    }
    renameMutation.mutate({ id, title });
  }

  return (
    <Box
      sx={{
        width: 300,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      <Box sx={{ p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/chat')} fullWidth>
          {t('chat.newConversation')}
        </Button>
        <TextField
          size="small"
          placeholder={t('chat.searchConversations')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
      </Box>
      <Divider />
      <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
        {listQuery.isLoading && <LoadingState />}
        {listQuery.isError && (
          <ErrorState
            message={getErrorMessage(listQuery.error)}
            onRetry={() => listQuery.refetch()}
          />
        )}
        {listQuery.data && listQuery.data.length === 0 && (
          <EmptyState message={t('chat.noConversations')} />
        )}
        {listQuery.data && (
          <List disablePadding>
            {listQuery.data.map((conv) => (
              <ListItemButton
                key={conv.id}
                selected={conv.id === activeId}
                onClick={() => renamingId !== conv.id && navigate(`/chat/${conv.id}`)}
                sx={{ alignItems: 'flex-start', gap: 0.5 }}
              >
                {renamingId === conv.id ? (
                  <Box
                    sx={{ display: 'flex', alignItems: 'center', gap: 0.5, width: '100%' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <TextField
                      size="small"
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commitRename(conv.id);
                        if (e.key === 'Escape') setRenamingId(null);
                      }}
                      fullWidth
                    />
                    <IconButton size="small" onClick={() => commitRename(conv.id)}>
                      <CheckIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" onClick={() => setRenamingId(null)}>
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  </Box>
                ) : (
                  <>
                    {conv.generating && (
                      <Tooltip title={t('chat.generating')}>
                        <CircularProgress size={14} sx={{ mt: 0.5, flexShrink: 0 }} />
                      </Tooltip>
                    )}
                    <ListItemText
                      primary={conv.title}
                      primaryTypographyProps={{ noWrap: true, variant: 'body2' }}
                    />
                    <Box sx={{ display: 'flex', gap: 0.25 }}>
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          startRename(conv);
                        }}
                      >
                        <EditIcon fontSize="inherit" />
                      </IconButton>
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(conv);
                        }}
                      >
                        <DeleteIcon fontSize="inherit" />
                      </IconButton>
                    </Box>
                  </>
                )}
              </ListItemButton>
            ))}
          </List>
        )}
      </Box>

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>{t('chat.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('chat.deleteConfirmBody')}</DialogContentText>
          {deleteMutation.isError && (
            <Typography color="error" variant="body2" sx={{ mt: 1 }}>
              {getErrorMessage(deleteMutation.error)}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={deleteMutation.isPending}
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
