import { useMemo } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { knowledgeApi } from '@/api/endpoints';
import KnowledgeEntriesEditor from '@/components/knowledge/KnowledgeEntriesEditor';

/**
 * «حافظه و قوانین من» — amendment-7 (docs/KNOWLEDGE.md). The ONE knowledge
 * surface a user owns: their own rules/knowledge (scope user), including what
 * the learning job extracted from their chats (tagged «یادگرفته‌شده»). Entries
 * an admin set about the user show read-only. Service/team knowledge and the
 * learning switches are admin-managed (product decision 2026-09-10).
 */
export default function KnowledgePage() {
  const { t } = useTranslation();
  const meApi = useMemo(() => knowledgeApi.me(), []);
  return (
    <Box sx={{ p: 3, maxWidth: 960, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        {t('knowledge.title')}
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('knowledge.intro')}
      </Alert>
      <KnowledgeEntriesEditor api={meApi} queryKey={['knowledge', 'me', 'entries']} />
    </Box>
  );
}
