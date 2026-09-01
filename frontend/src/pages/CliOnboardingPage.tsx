import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import ContentCopyIcon from '@mui/icons-material/ContentCopyOutlined';
import { keysApi } from '@/api/endpoints';

// Relay base derived from wherever the app is served — works on localhost and behind
// the domain/CDN with no hardcoding.
function relayBase(): string {
  return `${window.location.origin}/relay`;
}

function CodeBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <Paper
      variant="outlined"
      sx={{
        position: 'relative',
        p: 2,
        pr: 6,
        bgcolor: 'action.hover',
        fontFamily: 'monospace',
        fontSize: 13,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        direction: 'ltr',
        textAlign: 'left',
      }}
    >
      {text}
      <Tooltip title={copied ? 'کپی شد' : 'کپی'}>
        <IconButton size="small" onClick={copy} sx={{ position: 'absolute', top: 6, insetInlineEnd: 6 }}>
          <ContentCopyIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Paper>
  );
}

export default function CliOnboardingPage() {
  const [name, setName] = useState('کلید من');
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  const createMut = useMutation({
    mutationFn: () => keysApi.create({ name }),
    onSuccess: (res) => setCreatedKey(res.key),
  });

  const base = relayBase();
  const k = createdKey ?? '<کلید-شما>';

  const cliSnippet = useMemo(
    () => `export ANTHROPIC_BASE_URL=${base}\nexport ANTHROPIC_AUTH_TOKEN=${k}\nclaude`,
    [base, k],
  );
  const vscodeSnippet = useMemo(
    () =>
      `{\n` +
      `  "claudeCode.disableLoginPrompt": true,\n` +
      `  "claudeCode.hideOnboarding": true,\n` +
      `  "claudeCode.environmentVariables": {\n` +
      `    "ANTHROPIC_BASE_URL": "${base}",\n` +
      `    "ANTHROPIC_AUTH_TOKEN": "${k}"\n  }\n}`,
    [base, k],
  );

  return (
    <Box sx={{ p: 3, maxWidth: 860, mx: 'auto' }}>
      <Typography variant="h5" sx={{ mb: 1 }}>
        اتصال ابزارها به گیت‌وی EcoCode
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        هر ابزارِ سازگار با Anthropic را روی سیستم خودت وصل کن؛ فقط مدل‌کال‌ها از گیت‌وی ما رد می‌شوند
        (سهمیه + لاگ مرکزی). کد و فایل‌هایت لوکال می‌مانند و نیازی به هیچ کانتینری نیست.
      </Typography>

      {/* shared: create a key once, used in all snippets below */}
      <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          کلید شخصی (برای همهٔ ابزارها یکی کافی است)
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <TextField
            size="small"
            label="نام کلید"
            value={name}
            onChange={(e) => setName(e.target.value)}
            sx={{ maxWidth: 260 }}
          />
          <Button variant="contained" onClick={() => createMut.mutate()} disabled={createMut.isPending}>
            {createMut.isPending ? 'در حال ساخت…' : 'ساخت کلید'}
          </Button>
        </Stack>
        {createdKey ? (
          <Alert severity="warning">
            این کلید فقط همین یک‌بار نشان داده می‌شود — همین حالا در قطعه‌های زیر جای‌گذاری شد؛ کپی‌اش کن.
          </Alert>
        ) : (
          <Alert severity="info">بعد از ساخت، کلید خودکار در همهٔ قطعه‌های زیر قرار می‌گیرد.</Alert>
        )}
      </Paper>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab label="Claude Code (ترمینال)" />
        <Tab label="Claude Code (افزونهٔ VS Code)" />
        <Tab label="Cline" />
        <Tab label="ابزارهای دیگر" />
      </Tabs>

      {/* --- Claude Code CLI --- */}
      {tab === 0 && (
        <Stack spacing={2}>
          <Typography variant="subtitle2">۱) نصب (یک‌بار):</Typography>
          <CodeBlock text="npm install -g @anthropic-ai/claude-code" />
          <Typography variant="subtitle2">۲) در پوشهٔ پروژه‌ات اجرا کن:</Typography>
          <CodeBlock text={cliSnippet} />
          <Typography variant="body2" color="text.secondary">
            برای دائمی‌شدن، دو خط export را در <code>~/.bashrc</code> یا <code>~/.zshrc</code> بگذار.
          </Typography>
        </Stack>
      )}

      {/* --- Claude Code VS Code extension --- */}
      {tab === 1 && (
        <Stack spacing={2}>
          <Alert severity="warning">
            مهم: افزونه، آدرس/کلید را از <b>محیطِ سیستم (process env)</b> می‌خواند، نه از تنظیمِ
            <code>environmentVariables</code>. پس اگر فقط setting را بگذاری، همچنان «login» می‌خواهد. باید
            env را در سطح سیستم بگذاری و VS Code آن را ارث ببرد.
          </Alert>
          <Typography variant="subtitle2">
            ۱) VS Code را <b>کامل ببند</b>، سپس از ترمینال با این env بازش کن (macOS/Linux):
          </Typography>
          <CodeBlock text={cliSnippet.replace('\nclaude', '\ncode')} />
          <Typography variant="subtitle2">ویندوز (PowerShell):</Typography>
          <CodeBlock
            text={`$env:ANTHROPIC_BASE_URL="${base}"; $env:ANTHROPIC_AUTH_TOKEN="${k}"; code`}
          />
          <Typography variant="subtitle2">۲) این را هم به settings.json اضافه کن:</Typography>
          <CodeBlock text={vscodeSnippet} />
          <Typography variant="body2" color="text.secondary">
            بعد پنل Claude Code را باز کن. چون extension host متغیرها را از محیط می‌بیند و
            <code>disableLoginPrompt</code> روشن است، دیگر login نمی‌خواهد.
          </Typography>
          <Alert severity="info">
            اگر VS Code از قبل باز باشد و فقط <code>code</code> بزنی، instance قدیمی با env قدیمی فوکوس
            می‌شود — حتماً اول کامل ببندش. ساده‌ترین و تضمینی‌ترین جایگزین: تب «ترمینال» (CLI در ترمینالِ
            داخل VS Code) که قطعاً کار می‌کند.
          </Alert>
        </Stack>
      )}

      {/* --- Cline --- */}
      {tab === 2 && (
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Cline را از مارکت‌پلیس VS Code نصب کن، بعد در تنظیمات آن:
          </Typography>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography component="div" variant="body2">
              <b>API Provider:</b> Anthropic
              <br />
              <b>Anthropic API Key:</b> کلید بالا را بگذار
              <br />
              <b>Use custom base URL:</b> تیک بزن، و آدرس زیر را وارد کن:
            </Typography>
          </Paper>
          <CodeBlock text={base} />
          <Alert severity="info">
            Cline کلید را با هدر <code>x-api-key</code> می‌فرستد و گیت‌وی ما آن را می‌پذیرد. مدل‌های استاندارد
            Anthropic (sonnet/haiku/opus) را انتخاب کن. مصرفش هم مثل بقیه در «مصرف من» ثبت می‌شود.
          </Alert>
        </Stack>
      )}

      {/* --- other tools --- */}
      {tab === 3 && (
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            هر ابزاری که <b>API آنتروپیک (Messages)</b> را با <b>Base URL دلخواه</b> پشتیبانی کند کار می‌کند
            (aider، Continue، اسکریپت‌های SDK، …). فقط این دو را ست کن:
          </Typography>
          <CodeBlock text={`Base URL:  ${base}\nAPI Key:   ${k}`} />
          <Typography variant="body2" color="text.secondary">
            ابزار باید کلید را در هدر <code>Authorization: Bearer</code> یا <code>x-api-key</code> بفرستد و
            به مسیر <code>/v1/messages</code> (زیر همان Base URL) درخواست بدهد — یعنی رفتار استاندارد SDK
            آنتروپیک. مسیرهای فقط-OpenAI پشتیبانی نمی‌شوند.
          </Typography>
        </Stack>
      )}

      <Alert severity="success" sx={{ mt: 3 }}>
        مصرف همهٔ این مسیرها با برچسب <b>api</b> در «مصرف من» دیده می‌شود و سهمیهٔ مرکزی رویشان اعمال است.
      </Alert>
    </Box>
  );
}
