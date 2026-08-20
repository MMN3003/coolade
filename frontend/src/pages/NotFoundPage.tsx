import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { useNavigate } from 'react-router-dom';

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        gap: 2,
        py: 8,
      }}
    >
      <Typography variant="h4">۴۰۴</Typography>
      <Typography color="text.secondary">این صفحه یافت نشد.</Typography>
      <Button variant="contained" onClick={() => navigate('/chat')}>
        بازگشت به چت
      </Button>
    </Box>
  );
}
