# Spike §۳/§۳.۷ — "complete" workspace image: code-server + Claude Code CLI +
# the official Claude Code extension baked in, the built-in Copilot chat REMOVED,
# and defaults that make Claude Code the primary chat. Mirrors the D2.3 production
# image. Serves BOTH use cases: plain chat (just use the Claude Code panel) and
# development (open a repo folder and let the agent edit code).
FROM codercom/code-server:latest

# --- root: system deps + Claude Code CLI (for headless `claude -p`) + drop Copilot ---
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg git \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
# Remove the built-in GitHub Copilot chat so the only chat is Claude Code (§۳.۱۱ finding).
RUN rm -rf /usr/lib/code-server/lib/vscode/extensions/copilot \
           /usr/lib/code-server/lib/vscode/extensions/copilot-chat 2>/dev/null || true

# --- coder: Claude Code extension (linux-x64 explicit — arch-resolution finding §۳.۱۱) ---
USER coder
RUN curl -fsSL -o /tmp/cc.vsix \
      "https://open-vsx.org/api/Anthropic/claude-code/linux-x64/2.1.251/file/Anthropic.claude-code-2.1.251@linux-x64.vsix" \
 && code-server --install-extension /tmp/cc.vsix && rm /tmp/cc.vsix

# --- default settings: Claude Code is the primary chat; external (env) auth ---
RUN mkdir -p /home/coder/.local/share/code-server/User \
 && printf '%s\n' '{' \
      '  "security.workspace.trust.enabled": false,' \
      '  "workbench.startupEditor": "none",' \
      '  "telemetry.telemetryLevel": "off",' \
      '  "chat.commandCenter.enabled": false,' \
      '  "chat.disableAIFeatures": true,' \
      '  "workbench.secondarySideBar.defaultVisibility": "hidden",' \
      '  "claudeCode.preferredLocation": "sidebar",' \
      '  "claudeCode.disableLoginPrompt": true,' \
      '  "claudeCode.hideOnboarding": true,' \
      '  "claudeCode.initialPermissionMode": "acceptEdits"' \
      '}' > /home/coder/.local/share/code-server/User/settings.json

# --- a small sample project so "development" mode has real code to work on ---
RUN mkdir -p /home/coder/project \
 && printf '%s\n' '# نمونه — از چت Claude Code بخواه رویش کار کند' \
      'def greet(name):' \
      '    return "hello " + name' \
      '' \
      'if __name__ == "__main__":' \
      '    print(greet("world"))' > /home/coder/project/app.py \
 && printf '%s\n' '# پروژهٔ نمونه' '' \
      'تابع `greet` در `app.py` هست.' \
      'در پنل Claude Code (نوار کناری چپ) امتحان کن:' \
      '«به greet یک پیام خوش‌آمد فارسی اضافه کن و یک تست بنویس».' > /home/coder/project/README.md
