import FormControl from '@mui/material/FormControl';
import Select, { type SelectChangeEvent } from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import { useTranslation } from 'react-i18next';

/**
 * Model picker over the user's allowed models. Per the real contract,
 * /api/auth/me returns `allowed_models` as bare model KEYS (string[]),
 * so the key doubles as the label (e.g. "claude-sonnet").
 */
export default function ModelPicker({
  models,
  value,
  onChange,
  disabled,
  pill,
}: {
  models: string[];
  value: string | null;
  onChange: (modelKey: string) => void;
  disabled?: boolean;
  /** Render as a rounded, borderless-ish "pill" (GapGPT centered model chip). */
  pill?: boolean;
}) {
  const { t } = useTranslation();

  function handleChange(e: SelectChangeEvent) {
    onChange(e.target.value);
  }

  const pillSx = pill
    ? {
        borderRadius: 999,
        bgcolor: 'action.hover',
        fontWeight: 600,
        '& .MuiOutlinedInput-notchedOutline': { borderColor: 'transparent' },
        '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
        '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
        '& .MuiSelect-select': { direction: 'ltr', py: 0.75 },
      }
    : { '& .MuiSelect-select': { direction: 'ltr' } };

  return (
    <FormControl size="small" sx={{ minWidth: pill ? 160 : 200 }}>
      <Select
        value={value ?? ''}
        onChange={handleChange}
        displayEmpty
        disabled={disabled || models.length === 0}
        renderValue={(v) => (v ? v : t('chat.selectModel'))}
        sx={pillSx}
      >
        {models.map((key) => (
          <MenuItem key={key} value={key} sx={{ direction: 'ltr' }}>
            {key}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
