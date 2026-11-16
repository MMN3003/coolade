/**
 * Copy text to the clipboard, working on plain HTTP too.
 *
 * `navigator.clipboard` only exists in a secure context (HTTPS or localhost),
 * so on a LAN deployment served over http://<ip>:<port> it is `undefined` and
 * every copy button silently threw. Fall back to the legacy
 * `document.execCommand('copy')` on a hidden, off-screen textarea, which still
 * works from a user gesture on insecure origins.
 */
export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied / document not focused — try the legacy path.
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  // Keep it out of view and out of layout without `display:none` (which
  // would make it unselectable). Font size ≥16px stops iOS zooming in.
  textarea.style.position = 'fixed';
  textarea.style.top = '0';
  textarea.style.left = '0';
  textarea.style.width = '1px';
  textarea.style.height = '1px';
  textarea.style.opacity = '0';
  textarea.style.fontSize = '16px';
  textarea.style.pointerEvents = 'none';
  document.body.appendChild(textarea);

  const previousFocus = document.activeElement as HTMLElement | null;
  const selection = document.getSelection();
  const previousRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  textarea.focus({ preventScroll: true });
  textarea.select();
  textarea.setSelectionRange(0, text.length); // iOS Safari ignores select()

  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }

  document.body.removeChild(textarea);
  if (previousRange && selection) {
    selection.removeAllRanges();
    selection.addRange(previousRange);
  }
  previousFocus?.focus?.({ preventScroll: true });
  return ok;
}
