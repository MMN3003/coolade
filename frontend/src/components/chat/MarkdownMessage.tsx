import { useRef, useState, type ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import ContentCopyIcon from '@mui/icons-material/ContentCopyOutlined';
import CheckIcon from '@mui/icons-material/Check';
import { useTranslation } from 'react-i18next';
import { copyText } from '@/utils/clipboard';

function CodeBlock(props: ComponentPropsWithoutRef<'pre'>) {
  const { t } = useTranslation();
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    const text = preRef.current?.textContent ?? '';
    void copyText(text).then((ok) => {
      if (!ok) return;
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <Box
      sx={{
        position: 'relative',
        '&:hover .copy-code-btn, & .copy-code-btn:focus-visible': { opacity: 1 },
        // Touch screens have no hover — keep the button visible there.
        '@media (hover: none)': { '& .copy-code-btn': { opacity: 1 } },
        direction: 'ltr',
        my: 1,
      }}
    >
      <Tooltip title={copied ? t('chat.copiedCode') : t('chat.copyCode')}>
        <IconButton
          className="copy-code-btn"
          size="small"
          onClick={handleCopy}
          sx={{
            position: 'absolute',
            top: 6,
            insetInlineEnd: 6,
            opacity: 0,
            transition: 'opacity .15s',
            bgcolor: 'rgba(255,255,255,0.08)',
            color: 'grey.300',
            '&:hover': { bgcolor: 'rgba(255,255,255,0.16)' },
          }}
        >
          {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
      <Box
        component="pre"
        ref={preRef}
        {...props}
        sx={{
          borderRadius: 2,
          p: 2,
          overflowX: 'auto',
          fontSize: '0.85rem',
          m: 0,
        }}
      />
    </Box>
  );
}

export default function MarkdownMessage({ content }: { content: string }) {
  return (
    <Box
      sx={{
        '& p': { m: 0, mb: 1, '&:last-child': { mb: 0 } },
        '& ul, & ol': { mt: 0, mb: 1, pInlineStart: 3 },
        '& code:not(pre code)': {
          bgcolor: 'action.hover',
          px: 0.6,
          py: 0.15,
          borderRadius: 1,
          fontSize: '0.85em',
          direction: 'ltr',
          unicodeBidi: 'embed',
          display: 'inline-block',
        },
        '& table': { borderCollapse: 'collapse', my: 1 },
        '& th, & td': { border: 1, borderColor: 'divider', px: 1, py: 0.5 },
        '& blockquote': {
          borderInlineStart: 3,
          borderColor: 'divider',
          m: 0,
          ps: 1.5,
          color: 'text.secondary',
        },
        '& a': { color: 'secondary.main' },
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{ pre: CodeBlock }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  );
}
