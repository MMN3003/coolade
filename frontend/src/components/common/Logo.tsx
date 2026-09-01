import { useTheme } from '@mui/material/styles';
import Box from '@mui/material/Box';

interface LogoProps {
  /** Pixel size of the square icon. Default 28. */
  size?: number;
  /** When true, render the icon followed by the «EcoCode» wordmark. */
  withWordmark?: boolean;
}

/**
 * EcoCode brand mark: a green leaf (eco) with a knocked-out `</>` glyph (code)
 * at its centre. Pure inline SVG — no external assets, crisp at small sizes.
 * The leaf uses the theme's green accent (identical in both modes) while the
 * `</>` cut-out uses the surface colour so it reads on light AND dark.
 */
export default function Logo({ size = 28, withWordmark = false }: LogoProps) {
  const theme = useTheme();
  const leaf = theme.palette.primary.main;
  const cut = theme.palette.background.paper;

  const icon = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="EcoCode"
      style={{ display: 'block', flexShrink: 0 }}
    >
      {/* Leaf blade */}
      <path
        d="M16 3C10 7 6 13 7 20c1 6 6 9 9 9s8-3 9-9c1-7-3-13-9-17Z"
        fill={leaf}
      />
      {/* Code glyph </>  cut into the leaf */}
      <g stroke={cut} strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M12.4 12.5 9 16l3.4 3.5" />
        <path d="M19.6 12.5 23 16l-3.4 3.5" />
        <path d="M17.4 11 15 21" />
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
        <Box component="span" sx={{ color: 'text.primary' }}>
          Eco
        </Box>
        <Box component="span" sx={{ color: 'primary.main' }}>
          Code
        </Box>
      </Box>
    </Box>
  );
}
