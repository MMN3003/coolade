import { Box, Container, Paper, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

import MarkdownMessage from '@/components/chat/MarkdownMessage';
import { API_GUIDE_FA } from '@/content/apiGuide';
import { applyBranding } from '@/branding';

/**
 * In-panel user guide for the API/web-service usage. Content is bundled as a
 * markdown string (see src/content/apiGuide.ts, kept in sync with
 * docs/API-GUIDE.md) and rendered with the same Markdown renderer as chat.
 */
export default function HelpPage() {
  const { t } = useTranslation();

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Typography variant="h5" component="h1" gutterBottom fontWeight={700}>
        {t('help.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {t('help.subtitle')}
      </Typography>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Box sx={{ '& pre': { overflowX: 'auto' }, '& table': { display: 'block', overflowX: 'auto' } }}>
          <MarkdownMessage content={applyBranding(API_GUIDE_FA)} />
        </Box>
      </Paper>
    </Container>
  );
}
