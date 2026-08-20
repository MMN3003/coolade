import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';

export default function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        py: 6,
        color: 'text.secondary',
      }}
    >
      <CircularProgress size={32} />
      <Typography variant="body2">{label ?? t('common.loading')}</Typography>
    </Box>
  );
}
