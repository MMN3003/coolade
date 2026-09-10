import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import InputAdornment from '@mui/material/InputAdornment';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import Avatar from '@mui/material/Avatar';
import Chip from '@mui/material/Chip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogActions from '@mui/material/DialogActions';
import SearchIcon from '@mui/icons-material/Search';
import AddCommentOutlinedIcon from '@mui/icons-material/AddCommentOutlined';
import EditIcon from '@mui/icons-material/EditOutlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import LogoutIcon from '@mui/icons-material/LogoutOutlined';
import KeyOutlinedIcon from '@mui/icons-material/KeyOutlined';
import ChatIcon from '@mui/icons-material/ChatBubbleOutline';
import CodeIcon from '@mui/icons-material/CodeOutlined';
import TerminalIcon from '@mui/icons-material/TerminalOutlined';
import BarChartIcon from '@mui/icons-material/BarChartOutlined';
import KeyIcon from '@mui/icons-material/VpnKeyOutlined';
import HelpIcon from '@mui/icons-material/HelpOutlineOutlined';
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import TuneIcon from '@mui/icons-material/TuneOutlined';
import AssessmentIcon from '@mui/icons-material/AssessmentOutlined';
import MemoryIcon from '@mui/icons-material/MemoryOutlined';
import CardMembershipIcon from '@mui/icons-material/CardMembershipOutlined';
import CloudSyncIcon from '@mui/icons-material/CloudSyncOutlined';
import HubIcon from '@mui/icons-material/HubOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import ChangePasswordDialog from '@/components/common/ChangePasswordDialog';
import HistoryIcon from '@mui/icons-material/HistoryOutlined';
import LightModeIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined';
import { useTranslation } from 'react-i18next';
import Logo from '@/components/common/Logo';
import { useAuthStore } from '@/store/authStore';
import { useUiStore } from '@/store/uiStore';
import { authApi, conversationsApi } from '@/api/endpoints';
import type { Conversation } from '@/api/types';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { getErrorMessage } from '@/utils/errors';

interface NavItem {
  label: string;
  icon: ReactNode;
  path: string;
}

interface Props {
  /** Called after any navigation — used by the mobile drawer to close itself. */
  onNavigate?: () => void;
  /** Collapse (desktop) or close (mobile) the sidebar. */
  onCollapse?: () => void;
}

type Bucket = 'week' | 'month' | 'older';

function bucketOf(iso: string): Bucket {
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000;
  if (days <= 7) return 'week';
  if (days <= 30) return 'month';
  return 'older';
}

export default function AppSidebar({ onNavigate, onCollapse }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const reset = useAuthStore((s) => s.reset);
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  const activeConversationId = useMemo(() => {
    const m = location.pathname.match(/^\/chat\/(\d+)/);
    return m ? Number(m[1]) : undefined;
  }, [location.pathname]);
  const showHistory = location.pathname === '/chat' || location.pathname.startsWith('/chat/');

  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [pwOpen, setPwOpen] = useState(false);

  const listQuery = useQuery({
    queryKey: ['conversations', debouncedSearch],
    queryFn: () => conversationsApi.list(debouncedSearch || undefined),
    enabled: showHistory,
    // Light polling while anything is generating so a turn started in another
    // tab/session refreshes the spinner here too (TECH.md §9).
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
      if (activeConversationId === id) navigate('/chat');
    },
  });

  const userItems: NavItem[] = [
    { label: t('nav.chat'), icon: <ChatIcon />, path: '/chat' },
    { label: t('nav.workspaces', 'ورک‌اسپیس‌های کد'), icon: <CodeIcon />, path: '/workspaces' },
    { label: t('nav.cli', 'اتصال ابزارها'), icon: <TerminalIcon />, path: '/cli' },
    { label: t('nav.help'), icon: <HelpIcon />, path: '/help' },
    { label: t('nav.usage'), icon: <BarChartIcon />, path: '/usage' },
    { label: t('nav.keys'), icon: <KeyIcon />, path: '/keys' },
    { label: t('nav.teams'), icon: <GroupsOutlinedIcon />, path: '/teams' },
    { label: t('nav.knowledge'), icon: <PsychologyOutlinedIcon />, path: '/knowledge' },
  ];

  const adminItems: NavItem[] = [
    { label: t('nav.adminUsers'), icon: <PeopleIcon />, path: '/admin/users' },
    { label: t('nav.adminTeams'), icon: <GroupsOutlinedIcon />, path: '/admin/teams' },
    { label: t('nav.adminPolicies'), icon: <TuneIcon />, path: '/admin/policies' },
    { label: t('nav.adminUsage'), icon: <AssessmentIcon />, path: '/admin/usage' },
    { label: t('nav.adminModels'), icon: <MemoryIcon />, path: '/admin/models' },
    { label: t('nav.plans'), icon: <CardMembershipIcon />, path: '/admin/plans' },
    { label: t('nav.services'), icon: <HubIcon />, path: '/admin/services' },
    { label: t('nav.adminKnowledge'), icon: <PsychologyOutlinedIcon />, path: '/admin/knowledge' },
    { label: t('nav.adminSettings'), icon: <CloudSyncIcon />, path: '/admin/settings' },
    { label: t('nav.adminAudit'), icon: <HistoryIcon />, path: '/admin/audit' },
  ];

  function go(path: string) {
    navigate(path);
    onNavigate?.();
  }

  function isSelected(path: string) {
    if (path === '/chat') return location.pathname === '/chat' || location.pathname.startsWith('/chat/');
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

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

  async function handleLogout() {
    setMenuAnchor(null);
    try {
      await authApi.logout();
    } finally {
      reset();
      navigate('/login', { replace: true });
    }
  }

  const grouped = useMemo(() => {
    const groups: Record<Bucket, Conversation[]> = { week: [], month: [], older: [] };
    for (const c of listQuery.data ?? []) groups[bucketOf(c.updated_at || c.created_at)].push(c);
    return groups;
  }, [listQuery.data]);

  const bucketLabel: Record<Bucket, string> = {
    week: t('chat.historyLastWeek'),
    month: t('chat.history30Days'),
    older: t('chat.historyOlder'),
  };

  function renderConversation(conv: Conversation) {
    const renaming = renamingId === conv.id;
    return (
      <ListItemButton
        key={conv.id}
        selected={conv.id === activeConversationId}
        onClick={() => !renaming && go(`/chat/${conv.id}`)}
        sx={{ alignItems: 'center', gap: 0.5, py: 0.5, minHeight: 38, '& .row-actions': { opacity: 0 }, '&:hover .row-actions': { opacity: 1 } }}
      >
        {renaming ? (
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
                <CircularProgress size={13} sx={{ flexShrink: 0 }} />
              </Tooltip>
            )}
            <ListItemText
              primary={conv.title}
              primaryTypographyProps={{ noWrap: true, variant: 'body2' }}
            />
            <Box className="row-actions" sx={{ display: 'flex', gap: 0.25, transition: 'opacity .15s' }}>
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
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: 'background.paper' }}>
      {/* Header: brand + collapse, new chat, search */}
      <Box sx={{ p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Logo withWordmark size={26} />
          {onCollapse && (
            <Tooltip title={t('chat.collapseSidebar')}>
              <IconButton size="small" onClick={onCollapse}>
                <MenuOpenIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
        <Button
          variant="contained"
          startIcon={<AddCommentOutlinedIcon />}
          onClick={() => go('/chat')}
          fullWidth
        >
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

      {/* Scrollable middle: primary nav + admin nav + conversation history */}
      <Box sx={{ flexGrow: 1, overflowY: 'auto', px: 1, pb: 1 }}>
        <List disablePadding sx={{ '& .MuiListItemIcon-root': { minWidth: 34 } }}>
          {userItems.map((item) => (
            <ListItemButton
              key={item.path}
              selected={isSelected(item.path)}
              onClick={() => go(item.path)}
              sx={{ py: 0.5, minHeight: 40 }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body2' }} />
            </ListItemButton>
          ))}
        </List>

        {user?.role === 'admin' && (
          <>
            <Divider sx={{ my: 1 }} />
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ px: 1.5, py: 0.5, display: 'block' }}
            >
              {t('nav.admin')}
            </Typography>
            <List disablePadding sx={{ '& .MuiListItemIcon-root': { minWidth: 34 } }}>
              {adminItems.map((item) => (
                <ListItemButton
                  key={item.path}
                  selected={isSelected(item.path)}
                  onClick={() => go(item.path)}
                  sx={{ py: 0.5, minHeight: 40 }}
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body2' }} />
                </ListItemButton>
              ))}
            </List>
          </>
        )}

        {showHistory && (
          <>
            <Divider sx={{ my: 1 }} />
            {listQuery.isLoading && (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
                <CircularProgress size={20} />
              </Box>
            )}
            {listQuery.isError && (
              <Typography variant="caption" color="error" sx={{ px: 1.5, display: 'block' }}>
                {getErrorMessage(listQuery.error)}
              </Typography>
            )}
            {listQuery.data && listQuery.data.length === 0 && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ px: 1.5, py: 1, textAlign: 'center' }}
              >
                {t('chat.noConversations')}
              </Typography>
            )}
            {(['week', 'month', 'older'] as Bucket[]).map((b) =>
              grouped[b].length ? (
                <Box key={b} sx={{ mb: 0.5 }}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ px: 1.5, py: 0.5, display: 'block', fontWeight: 600 }}
                  >
                    {bucketLabel[b]}
                  </Typography>
                  <List disablePadding>{grouped[b].map(renderConversation)}</List>
                </Box>
              ) : null,
            )}
          </>
        )}
      </Box>

      {/* Footer: account row + theme toggle */}
      <Divider />
      <Box sx={{ p: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <ListItemButton
          onClick={(e) => setMenuAnchor(e.currentTarget)}
          sx={{ gap: 1, py: 0.75, flexGrow: 1, minWidth: 0 }}
        >
          <Avatar sx={{ width: 30, height: 30, bgcolor: 'primary.main', fontSize: 14 }}>
            {(user?.display_name || user?.username || '؟').slice(0, 1)}
          </Avatar>
          <ListItemText
            primary={user?.display_name || user?.username}
            secondary={user?.role === 'admin' ? t('admin.users.roleAdmin') : t('admin.users.roleUser')}
            primaryTypographyProps={{ variant: 'body2', noWrap: true, fontWeight: 600 }}
            secondaryTypographyProps={{ variant: 'caption' }}
          />
        </ListItemButton>
        <Tooltip title={themeMode === 'dark' ? t('theme.toLight') : t('theme.toDark')}>
          <IconButton
            onClick={toggleTheme}
            size="small"
            aria-label={themeMode === 'dark' ? t('theme.toLight') : t('theme.toDark')}
            sx={{ flexShrink: 0 }}
          >
            {themeMode === 'dark' ? (
              <LightModeIcon fontSize="small" />
            ) : (
              <DarkModeIcon fontSize="small" />
            )}
          </IconButton>
        </Tooltip>
        <Menu
          anchorEl={menuAnchor}
          open={!!menuAnchor}
          onClose={() => setMenuAnchor(null)}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          transformOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          {!!user?.teams?.length && (
            <MenuItem disabled sx={{ opacity: '1 !important' }}>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxWidth: 220 }}>
                {user.teams.map((tm) => (
                  <Chip key={tm.id} size="small" variant="outlined" label={tm.name} />
                ))}
              </Box>
            </MenuItem>
          )}
          {!!user?.teams?.length && <Divider />}
          {user?.auth_source !== 'ldap' && (
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                setPwOpen(true);
              }}
            >
              <ListItemIcon>
                <KeyOutlinedIcon fontSize="small" />
              </ListItemIcon>
              {t('auth.changePassword')}
            </MenuItem>
          )}
          <MenuItem onClick={handleLogout}>
            <ListItemIcon>
              <LogoutIcon fontSize="small" />
            </ListItemIcon>
            {t('auth.logout')}
          </MenuItem>
        </Menu>
        <ChangePasswordDialog open={pwOpen} onClose={() => setPwOpen(false)} />
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
