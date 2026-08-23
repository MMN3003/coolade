import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { useTranslation } from 'react-i18next';
import { adminTeamsApi } from '@/api/endpoints';
import TeamMemoryManager from '@/components/teams/TeamMemoryManager';
import ErrorState from '@/components/common/ErrorState';

/**
 * `/admin/teams/:id/memory` — admin route to the same team-memory manager
 * component `/teams/:id/memory` uses, pointed at the `/api/admin/teams/{id}/
 * memory/files` endpoint family instead (no membership required — TECH.md
 * v1.4 §8/§9/§10: "ادمین از /admin/teams هم به همان کامپوننت (root تیم)
 * دسترسی دارد"). Team name comes from `GET /api/admin/teams/{id}`.
 */
export default function AdminTeamMemoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { teamId: teamIdParam } = useParams();
  const teamId = Number(teamIdParam);

  const teamQuery = useQuery({
    queryKey: ['admin', 'team', teamId, 'detail'],
    queryFn: () => adminTeamsApi.get(teamId),
    enabled: Number.isFinite(teamId),
  });

  const api = useMemo(
    () => ({
      list: () => adminTeamsApi.memory.list(teamId),
      upload: (file: File) => adminTeamsApi.memory.upload(teamId, file),
      downloadUrl: (fileId: string) => adminTeamsApi.memory.downloadUrl(teamId, fileId),
      remove: (fileId: string) => adminTeamsApi.memory.remove(teamId, fileId),
    }),
    [teamId],
  );

  if (!Number.isFinite(teamId)) {
    return <ErrorState message={t('common.noData')} />;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <IconButton size="small" onClick={() => navigate('/admin/teams')} aria-label={t('teams.memory.back')}>
          <ArrowForwardIcon fontSize="small" />
        </IconButton>
        <Typography variant="h5" fontWeight={700}>
          {t('teams.memory.title')}
          {teamQuery.data ? ` — ${teamQuery.data.name}` : ''}
        </Typography>
      </Box>

      {/* Team header name is best-effort (falls back to no suffix if the
          detail fetch fails/404s); the file manager below runs its own
          independent query and is the authoritative source of errors. */}
      <TeamMemoryManager api={api} queryKey={['admin', 'team', teamId, 'memory', 'files']} />
    </Box>
  );
}
