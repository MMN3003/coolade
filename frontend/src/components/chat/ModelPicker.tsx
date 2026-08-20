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
}: {
  models: string[];
  value: string | null;
  onChange: (modelKey: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();

  function handleChange(e: SelectChangeEvent) {
    onChange(e.target.value);
  }

  return (
    <FormControl size="small" sx={{ minWidth: 200 }}>
      <Select
        value={value ?? ''}
        onChange={handleChange}
        displayEmpty
        disabled={disabled || models.length === 0}
        renderValue={(v) => (v ? v : t('chat.selectModel'))}
        sx={{ '& .MuiSelect-select': { direction: 'ltr' } }}
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
