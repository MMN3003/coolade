import { useTheme } from '@mui/material/styles';
import Box from '@mui/material/Box';

import { branding } from '@/branding';

interface LogoProps {
  /** Pixel size of the square icon. Default 28. */
  size?: number;
  /** When true, render the icon followed by the product-name wordmark (APP_NAME). */
  withWordmark?: boolean;
}

/**
 * Coolade brand mark: a cool drop with a knocked-out `</>` glyph (code)
 * at its centre. Pure inline SVG — no external assets, crisp at small sizes.
 * The drop uses the theme's accent colour (identical in both modes) while the
 * `</>` cut-out uses the surface colour so it reads on light AND dark.
 */
export default function Logo({ size = 28, withWordmark = false }: LogoProps) {
  const theme = useTheme();
  const drop = theme.palette.primary.main;
  const cut = theme.palette.background.paper;

  const icon = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label={branding.name}
      style={{ display: 'block', flexShrink: 0 }}
    >
      {/* Drop */}
      <path d="M16 2.5C16 2.5 6.5 13 6.5 19.5a9.5 9.5 0 0 0 19 0C25.5 13 16 2.5 16 2.5Z" fill={drop} />
      {/* Code glyph </>  cut into the drop */}
      <g stroke={cut} strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M12.6 16.5 9.6 19.5l3 3" />
        <path d="M19.4 16.5l3 3-3 3" />
        <path d="M17.2 15.5 14.8 23.5" />
      </g>
    </svg>
  );

  if (!withWordmark) return icon;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      {icon}
      <Box
        component="span"
        sx={{
          fontWeight: 800,
          fontSize: size * 0.62,
          lineHeight: 1,
          letterSpacing: '.2px',
          whiteSpace: 'nowrap',
        }}
      >
        <Box component="span" sx={{ color: 'primary.main' }}>
          {branding.name}
        </Box>
      </Box>
    </Box>
  );
}
