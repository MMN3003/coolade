import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { useTranslation } from 'react-i18next';
import { teamsApi } from '@/api/endpoints';
import TeamMemoryManager from '@/components/teams/TeamMemoryManager';
import ErrorState from '@/components/common/ErrorState';

/**
 * `/teams/:id/memory` — «حافظهٔ مشترک تیم» for a team the current user is a
 * member of (TECH.md v1.4 §9, Issue I). The team name/label comes from the
 * `/api/teams/mine` list (cached under ['teams','mine'] by `TeamsPage`) since
 * the contract (§8) has no single-team detail endpoint for members — only
 * `GET /api/teams/{id}/members`. If the id isn't in that list (e.g. deep
 * link, or membership changed) the header falls back to a generic label;
 * the file list itself is the real membership check (backend 404s
 * non-members per §8, rendered via the uniform ApiError message below).
 */
export default function TeamMemoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { teamId: teamIdParam } = useParams();
  const teamId = Number(teamIdParam);

  const mineQuery = useQuery({ queryKey: ['teams', 'mine'], queryFn: teamsApi.mine });
  const team = useMemo(() => mineQuery.data?.find((tm) => tm.id === teamId), [mineQuery.data, teamId]);

  const api = useMemo(
    () => ({
      list: () => teamsApi.memory.list(teamId),
      upload: (file: File) => teamsApi.memory.upload(teamId, file),
      downloadUrl: (fileId: string) => teamsApi.memory.downloadUrl(teamId, fileId),
      remove: (fileId: string) => teamsApi.memory.remove(teamId, fileId),
    }),
    [teamId],
  );

  if (!Number.isFinite(teamId)) {
    return <ErrorState message={t('common.noData')} />;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <IconButton size="small" onClick={() => navigate('/teams')} aria-label={t('teams.memory.back')}>
          <ArrowForwardIcon fontSize="small" />
        </IconButton>
        <Typography variant="h5" fontWeight={700}>
          {t('teams.memory.title')}
          {team ? ` — ${team.name}` : ''}
        </Typography>
      </Box>

      <TeamMemoryManager api={api} queryKey={['teams', teamId, 'memory', 'files']} />
    </Box>
  );
}
