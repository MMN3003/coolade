import Box from '@mui/material/Box';
import FormControl from '@mui/material/FormControl';
import Select, { type SelectChangeEvent } from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import { useTranslation } from 'react-i18next';
import type { ThinkingLevel } from '@/api/types';

/** Fixed ladder + order, per TECH.md §5.7 (قطعی — not admin-configurable). */
export const THINKING_LEVELS: ThinkingLevel[] = ['off', 'standard', 'deep'];

const RANK: Record<ThinkingLevel, number> = { off: 0, standard: 1, deep: 2 };

export function thinkingLevelRank(level: ThinkingLevel): number {
  return RANK[level];
}

/**
 * Compact 3-level picker beside the model picker (اصلاحیهٔ ۲ / Issue D,
 * TECH.md §9). Options are capped by `maxLevel` (from `/api/auth/me`'s
 * `max_thinking_level`) — a level above the cap is never offered, matching
 * the backend's own `effective = min(requested, cap)` clamp (§5.7).
 */
export default function ThinkingLevelPicker({
  value,
  maxLevel,
  onChange,
  disabled,
  pill,
}: {
  value: ThinkingLevel;
  maxLevel: ThinkingLevel;
  onChange: (level: ThinkingLevel) => void;
  disabled?: boolean;
  /** Render as a rounded "pill" to sit beside the model pill. */
  pill?: boolean;
}) {
  const { t } = useTranslation();

  const labels: Record<ThinkingLevel, string> = {
    off: t('chat.thinkingOff'),
    standard: t('chat.thinkingStandard'),
    deep: t('chat.thinkingDeep'),
  };

  const allowed = THINKING_LEVELS.filter((l) => thinkingLevelRank(l) <= thinkingLevelRank(maxLevel));

  function handleChange(e: SelectChangeEvent) {
    onChange(e.target.value as ThinkingLevel);
  }

  const pillSx = pill
    ? {
        borderRadius: 999,
        bgcolor: 'action.hover',
        fontWeight: 600,
        '& .MuiOutlinedInput-notchedOutline': { borderColor: 'transparent' },
        '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
        '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
        '& .MuiSelect-select': { py: 0.75 },
      }
    : undefined;

  return (
    <FormControl size="small" sx={{ minWidth: 130 }}>
      <Select
        value={allowed.includes(value) ? value : allowed[0]}
        onChange={handleChange}
        disabled={disabled || allowed.length === 0}
        sx={pillSx}
        renderValue={(v) => (
          <Box>
            <PsychologyOutlinedIcon fontSize="inherit" sx={{ verticalAlign: 'middle', me: 0.5 }} />
            {labels[v as ThinkingLevel]}
          </Box>
        )}
      >
        {allowed.map((level) => (
          <MenuItem key={level} value={level}>
            {labels[level]}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
