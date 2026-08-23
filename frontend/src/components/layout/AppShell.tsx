import { useState, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Box from '@mui/material/Box';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Avatar from '@mui/material/Avatar';
import Chip from '@mui/material/Chip';
import ListSubheader from '@mui/material/ListSubheader';
import MenuIcon from '@mui/icons-material/Menu';
import ChatIcon from '@mui/icons-material/ChatBubbleOutline';
import BarChartIcon from '@mui/icons-material/BarChartOutlined';
import KeyIcon from '@mui/icons-material/VpnKeyOutlined';
import HelpIcon from '@mui/icons-material/HelpOutlineOutlined';
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import TuneIcon from '@mui/icons-material/TuneOutlined';
import AssessmentIcon from '@mui/icons-material/AssessmentOutlined';
import MemoryIcon from '@mui/icons-material/MemoryOutlined';
import CloudSyncIcon from '@mui/icons-material/CloudSyncOutlined';
import HistoryIcon from '@mui/icons-material/HistoryOutlined';
import LogoutIcon from '@mui/icons-material/LogoutOutlined';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/authStore';
import { authApi } from '@/api/endpoints';
import QuotaBanner from './QuotaBanner';

const DRAWER_WIDTH = 260;

interface NavItem {
  label: string;
  icon: ReactNode;
  path: string;
}

export default function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const reset = useAuthStore((s) => s.reset);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);

  const userItems: NavItem[] = [
    { label: t('nav.chat'), icon: <ChatIcon />, path: '/chat' },
    { label: t('nav.usage'), icon: <BarChartIcon />, path: '/usage' },
    { label: t('nav.keys'), icon: <KeyIcon />, path: '/keys' },
    { label: t('nav.teams'), icon: <GroupsOutlinedIcon />, path: '/teams' },
    { label: t('nav.help'), icon: <HelpIcon />, path: '/help' },
  ];

  const adminItems: NavItem[] = [
    { label: t('nav.adminUsers'), icon: <PeopleIcon />, path: '/admin/users' },
    { label: t('nav.adminTeams'), icon: <GroupsOutlinedIcon />, path: '/admin/teams' },
    { label: t('nav.adminPolicies'), icon: <TuneIcon />, path: '/admin/policies' },
    { label: t('nav.adminUsage'), icon: <AssessmentIcon />, path: '/admin/usage' },
    { label: t('nav.adminModels'), icon: <MemoryIcon />, path: '/admin/models' },
    { label: t('nav.adminSettings'), icon: <CloudSyncIcon />, path: '/admin/settings' },
    { label: t('nav.adminAudit'), icon: <HistoryIcon />, path: '/admin/audit' },
  ];

  async function handleLogout() {
    setMenuAnchor(null);
    try {
      await authApi.logout();
    } finally {
      reset();
      navigate('/login', { replace: true });
    }
  }

  function isSelected(path: string) {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  const drawerContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar>
        <Typography variant="h6" noWrap fontWeight={700} color="primary.main">
          {t('app.name')}
        </Typography>
      </Toolbar>
      <Divider />
      <List>
        {userItems.map((item) => (
          <ListItemButton
            key={item.path}
            selected={isSelected(item.path)}
            onClick={() => {
              navigate(item.path);
              setMobileOpen(false);
            }}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        ))}
      </List>
      {user?.role === 'admin' && (
        <>
          <Divider />
          <List subheader={<ListSubheader component="div">{t('nav.admin')}</ListSubheader>}>
            {adminItems.map((item) => (
              <ListItemButton
                key={item.path}
                selected={isSelected(item.path)}
                onClick={() => {
                  navigate(item.path);
                  setMobileOpen(false);
                }}
              >
                <ListItemIcon>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            ))}
          </List>
        </>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            edge="start"
            sx={{ display: { md: 'none' } }}
            onClick={() => setMobileOpen(true)}
          >
            <MenuIcon />
          </IconButton>
          <Box sx={{ flexGrow: 1 }} />
          <IconButton onClick={(e) => setMenuAnchor(e.currentTarget)} size="small">
            <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.main', fontSize: 15 }}>
              {(user?.display_name || user?.username || '؟').slice(0, 1)}
            </Avatar>
          </IconButton>
          <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
            <MenuItem disabled sx={{ opacity: '1 !important' }}>
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  {user?.display_name || user?.username}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {user?.role === 'admin' ? t('admin.users.roleAdmin') : t('admin.users.roleUser')}
                </Typography>
                {/* اصلاحیهٔ ۴ / Issue H (TECH.md §10): "نمایش تیم‌ها در نمای پروفایل/هدر از /me" */}
                {!!user?.teams?.length && (
                  <Box sx={{ mt: 0.75, display: 'flex', flexWrap: 'wrap', gap: 0.5, maxWidth: 220 }}>
                    {user.teams.map((tm) => (
                      <Chip key={tm.id} size="small" variant="outlined" label={tm.name} />
                    ))}
                  </Box>
                )}
              </Box>
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              {t('auth.logout')}
            </MenuItem>
          </Menu>
        </Toolbar>
        <QuotaBanner />
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH },
          }}
        >
          {drawerContent}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
          }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
        }}
      >
        <Toolbar />
        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
