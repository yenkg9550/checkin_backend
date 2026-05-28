#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# commit.sh  ─  CheckIn Backend（FastAPI + SQLAlchemy）
# 用法：
#   bash commit.sh            # 自動產生 commit message
#   bash commit.sh "自訂訊息"  # 使用自訂 commit message
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. 若尚未初始化 git，自動 init ──────────────────────────
if ! git rev-parse --git-dir &>/dev/null; then
  echo "⚙️  初始化 git repository..."
  git init
  if [[ ! -f .gitignore ]]; then
    cat > .gitignore <<'EOF'
__pycache__/
*.pyc
*.pyo
.env
.env.*
!.env.example
*.db
*.sqlite3
.DS_Store
*.log
EOF
    echo "✅ 已建立 .gitignore"
  fi
fi

# ── 2. git add 全部變動 ──────────────────────────────────────
git add -A

# ── 3. 確認有東西可以 commit ─────────────────────────────────
if git diff --cached --quiet; then
  echo "✨ 沒有任何變動，無需 commit。"
  exit 0
fi

# ── 4. 分析變動的檔案，自動產生 commit message ───────────────
if [[ $# -ge 1 && -n "$1" ]]; then
  COMMIT_MSG="$1"
else
  CHANGED_FILES=$(git diff --cached --name-only)
  ADDED=$(git diff --cached --name-only --diff-filter=A | wc -l | tr -d ' ')
  MODIFIED=$(git diff --cached --name-only --diff-filter=M | wc -l | tr -d ' ')
  DELETED=$(git diff --cached --name-only --diff-filter=D | wc -l | tr -d ' ')

  SCOPES=()
  echo "$CHANGED_FILES" | grep -q "models\.py"              && SCOPES+=("models")
  echo "$CHANGED_FILES" | grep -q "schemas\.py"             && SCOPES+=("schemas")
  echo "$CHANGED_FILES" | grep -q "routers/auth\.py"        && SCOPES+=("auth")
  echo "$CHANGED_FILES" | grep -q "routers/admin\.py"       && SCOPES+=("admin")
  echo "$CHANGED_FILES" | grep -q "routers/attendance\.py"  && SCOPES+=("attendance")
  echo "$CHANGED_FILES" | grep -q "routers/webhook\.py"     && SCOPES+=("webhook")
  echo "$CHANGED_FILES" | grep -q "utils/"                  && SCOPES+=("utils")
  echo "$CHANGED_FILES" | grep -q "main\.py"                && SCOPES+=("main")
  echo "$CHANGED_FILES" | grep -q "database\.py"            && SCOPES+=("database")
  echo "$CHANGED_FILES" | grep -q "config\.py"              && SCOPES+=("config")
  echo "$CHANGED_FILES" | grep -q "requirements\.txt\|render\.yaml\|\.env\|commit\.sh\|\.gitignore" && SCOPES+=("infra")
  echo "$CHANGED_FILES" | grep -q "\.md$"                   && SCOPES+=("docs")

  IFS=$'\n' UNIQUE_SCOPES=($(printf "%s\n" "${SCOPES[@]:-other}" | sort -u))
  SCOPE_STR=$(IFS=", "; echo "${UNIQUE_SCOPES[*]}")

  STATS=""
  [[ "$ADDED"    -gt 0 ]] && STATS+="${ADDED} 新增"
  [[ "$MODIFIED" -gt 0 ]] && { [[ -n "$STATS" ]] && STATS+=", "; STATS+="${MODIFIED} 修改"; }
  [[ "$DELETED"  -gt 0 ]] && { [[ -n "$STATS" ]] && STATS+=", "; STATS+="${DELETED} 刪除"; }

  TOTAL=$(( ADDED + MODIFIED + DELETED ))
  if [[ "$TOTAL" -eq 1 ]]; then
    SINGLE_FILE=$(echo "$CHANGED_FILES" | head -1 | xargs basename)
    COMMIT_MSG="feat(${SCOPE_STR}): update ${SINGLE_FILE}"
  else
    COMMIT_MSG="feat(${SCOPE_STR}): ${STATS} 個檔案"
  fi
fi

# ── 5. 執行 commit ───────────────────────────────────────────
git commit -m "$COMMIT_MSG"

echo ""
echo "✅ Commit 完成！"
echo "   訊息：$COMMIT_MSG"
echo ""
git log --oneline -5
