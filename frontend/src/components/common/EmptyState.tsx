import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

export default function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1.5,
        py: 6,
        color: 'text.secondary',
        textAlign: 'center',
      }}
    >
      <Typography variant="body2">{message}</Typography>
      {action}
    </Box>
  );
}
