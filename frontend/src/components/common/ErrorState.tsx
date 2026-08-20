import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { useTranslation } from 'react-i18next';

export default function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1.5,
        py: 6,
        color: 'error.main',
        textAlign: 'center',
      }}
    >
      <ErrorOutlineIcon fontSize="large" />
      <Typography variant="body1">{message ?? t('common.somethingWrong')}</Typography>
      {onRetry && (
        <Button onClick={onRetry} size="small" variant="outlined">
          {t('common.retry')}
        </Button>
      )}
    </Box>
  );
}
