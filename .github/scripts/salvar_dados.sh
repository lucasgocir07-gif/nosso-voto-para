#!/usr/bin/env bash
# Grava no repositório o que o robô mudou em dados/ e relatorios/ (coletas, análises, fila de posts).
# Uso: bash .github/scripts/salvar_dados.sh "mensagem do registro"
set -euo pipefail

git add dados relatorios
if git diff --cached --quiet; then
  echo "Nada novo para guardar."
  exit 0
fi
git commit -m "$1"

# Outro robô pode ter gravado algo no meio do caminho: junta e tenta de novo
for tentativa in 1 2 3; do
  if git pull --rebase && git push; then
    exit 0
  fi
  echo "Tentativa $tentativa falhou; tentando de novo em 10 s"
  sleep 10
done
exit 1
