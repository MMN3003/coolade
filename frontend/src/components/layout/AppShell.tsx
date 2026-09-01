import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import MenuIcon from '@mui/icons-material/Menu';
import ViewSidebarOutlinedIcon from '@mui/icons-material/ViewSidebarOutlined';
import { useTranslation } from 'react-i18next';
import AppSidebar from './AppSidebar';
import QuotaBanner from './QuotaBanner';

const SIDEBAR_WIDTH = 272;

/**
 * Unified ChatGPT-style shell: a single rich sidebar on the RTL-primary
 * (right) side that consolidates the new-chat / search / primary nav / admin
 * nav / conversation history / account row, plus the main content area with
 * the quota banner pinned above the routed <Outlet/>. The old top AppBar and
 * the chat page's separate nav column are gone.
 */
export default function AppShell() {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Desktop permanent sidebar (right side in RTL — first flex child). */}
      <Box
        sx={{
          display: { xs: 'none', md: collapsed ? 'none' : 'flex' },
          flexDirection: 'column',
          width: SIDEBAR_WIDTH,
          flexShrink: 0,
          height: '100%',
          borderInlineEnd: 1,
          borderColor: 'divider',
        }}
      >
        <AppSidebar onCollapse={() => setCollapsed(true)} />
      </Box>

      {/* Mobile temporary drawer. */}
      <Drawer
        anchor="right"
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { width: SIDEBAR_WIDTH, boxSizing: 'border-box' },
        }}
      >
        <AppSidebar onNavigate={() => setMobileOpen(false)} onCollapse={() => setMobileOpen(false)} />
      </Drawer>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Floating opener: expands the collapsed desktop sidebar. The sidebar
            lives on the RTL-primary (right) side, so the opener is pinned to the
            inline-start edge — which resolves to the RIGHT under dir="rtl". */}
        {collapsed && (
          <Tooltip title={t('chat.expandSidebar')}>
            <IconButton
              onClick={() => setCollapsed(false)}
              size="small"
              sx={{
                display: { xs: 'none', md: 'inline-flex' },
                position: 'absolute',
                top: 8,
                insetInlineStart: 8,
                zIndex: 1200,
                bgcolor: 'background.paper',
                border: 1,
                borderColor: 'divider',
              }}
            >
              <ViewSidebarOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        {/* Floating opener: mobile drawer (also anchored right → inline-start). */}
        <Tooltip title={t('chat.expandSidebar')}>
          <IconButton
            onClick={() => setMobileOpen(true)}
            size="small"
            sx={{
              display: { xs: 'inline-flex', md: 'none' },
              position: 'absolute',
              top: 8,
              insetInlineStart: 8,
              zIndex: 1200,
              bgcolor: 'background.paper',
              border: 1,
              borderColor: 'divider',
            }}
          >
            <MenuIcon fontSize="small" />
          </IconButton>
        </Tooltip>

        <QuotaBanner />
        <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
