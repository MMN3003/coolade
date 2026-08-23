import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import FolderSharedOutlinedIcon from '@mui/icons-material/FolderSharedOutlined';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import { useTranslation } from 'react-i18next';
import { teamsApi } from '@/api/endpoints';
import { getErrorMessage } from '@/utils/errors';
import LoadingState from '@/components/common/LoadingState';
import ErrorState from '@/components/common/ErrorState';
import EmptyState from '@/components/common/EmptyState';

/**
 * «تیم‌های من» — read-only list of the current user's teams (TECH.md v1.4
 * §9, Issue H). Each row links to that team's shared-memory page
 * (`/teams/:id/memory`, Issue I). Membership itself is enforced server-side
 * (`GET /api/teams/mine` only ever returns the caller's own teams).
 */
export default function TeamsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const teamsQuery = useQuery({ queryKey: ['teams', 'mine'], queryFn: teamsApi.mine });

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('teams.title')}
      </Typography>

      <Paper>
        {teamsQuery.isLoading && <LoadingState />}
        {teamsQuery.isError && (
          <ErrorState message={getErrorMessage(teamsQuery.error)} onRetry={() => teamsQuery.refetch()} />
        )}
        {teamsQuery.isSuccess && teamsQuery.data.length === 0 && <EmptyState message={t('teams.empty')} />}
        {teamsQuery.data && teamsQuery.data.length > 0 && (
          <List disablePadding>
            {teamsQuery.data.map((team) => (
              <ListItemButton
                key={team.id}
                divider
                onClick={() => navigate(`/teams/${team.id}/memory`)}
              >
                <FolderSharedOutlinedIcon color="action" sx={{ mr: 1.5 }} />
                <ListItemText
                  primary={team.name}
                  secondary={t('teams.membersCount', { count: team.member_count })}
                />
                <Stack direction="row" spacing={1} alignItems="center">
                  <Chip
                    size="small"
                    variant="outlined"
                    label={team.role_in_team === 'lead' ? t('teams.roleLead') : t('teams.roleMember')}
                  />
                  <ChevronLeftIcon fontSize="small" color="action" />
                </Stack>
              </ListItemButton>
            ))}
          </List>
        )}
      </Paper>
    </Box>
  );
}
