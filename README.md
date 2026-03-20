# turma-professor

Gerador semestral de site de consulta a partir do PDF de horários de turma.

## O que este projeto gera

- Busca 1: "Quem é o professor da Turma/Disciplina?" (por turma, listando disciplinas e professores).
- Busca 2: "Quais disciplinas/turmas desse professor?".
- Exibe e-mail do professor quando disponível na base de e-mails.
- Saídas: `index.html` e `data.json` (site estático + dados para auditoria).

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt`

## Como usar

### Com Make (recomendado)

```bash
make install
make generate
make serve
```

Fluxo único (instala + gera + sobe servidor):

```bash
make dev
```

Para subir sem regenerar:

```bash
make serve-only
```

Com variáveis customizadas:

```bash
make generate INPUT="input/SEU_ARQUIVO.PDF" OUTPUT="dist"
make serve HOST="0.0.0.0" PORT=8080
make dev INPUT="input/SEU_ARQUIVO.PDF" HOST="0.0.0.0" PORT=8080
make generate EMAIL_BASE="input/professores_emails.csv"
```

### Como indicar qual PDF processar no Make

Use a variável `INPUT` no comando:

```bash
make generate INPUT="input/MEU_PDF_DO_SEMESTRE.PDF"
```

Também funciona para `serve` e `dev`:

```bash
make serve INPUT="input/MEU_PDF_DO_SEMESTRE.PDF"
make dev INPUT="input/MEU_PDF_DO_SEMESTRE.PDF"
```

Se não informar `INPUT`, o padrão é:

- `input/HORÁRIO TURMAS 2026 1.PDF`

### Base incremental de e-mails de professores

Arquivo padrão:

- `input/professores_emails.csv`

Formato obrigatório:

```csv
professor,email
João Bosco de Souza,joao.souza@ifpe.edu.br
```

Como funciona:

- A cada geração, professores novos encontrados no PDF são adicionados automaticamente ao CSV com e-mail vazio.
- Você só precisa preencher os e-mails faltantes no CSV (a base é incrementada, sem perder os já preenchidos).
- O HTML passa a exibir o e-mail do professor quando existir na base.
- O topo do `index.html` inclui link para baixar o PDF de origem processado.

Para usar outro arquivo de base de e-mails no Make:

```bash
make generate EMAIL_BASE="input/minha_base_emails.csv"
make serve EMAIL_BASE="input/minha_base_emails.csv"
make dev EMAIL_BASE="input/minha_base_emails.csv"
```

### Comandos diretos Python

1. Instale dependências:

```bash
python -m pip install -r requirements.txt
```

2. Execute o gerador com o PDF de entrada:

```bash
python src/generate_site.py \
	--input "input/HORÁRIO TURMAS 2026 1.PDF" \
	--output "dist" \
	--email-base "input/professores_emails.csv"
```

## Rodar em servidor local

Para gerar os arquivos e iniciar um servidor local:

```bash
python src/run_local_server.py \
	--input "input/HORÁRIO TURMAS 2026 1.PDF" \
	--output "dist" \
	--host "127.0.0.1" \
	--port 8000 \
	--email-base "input/professores_emails.csv"
```

Depois, acesse:

- `http://127.0.0.1:8000`

Se quiser apenas subir o servidor sem regenerar os arquivos:

```bash
python src/run_local_server.py --output "dist" --skip-generate
```

3. Abra o site gerado:

- `dist/index.html`
- `dist/data.json`

## Estrutura de saída (GitHub Pages)

A geração publica os arquivos em 3 locais:

- Raiz do projeto: `index.html`, `data.json` e o PDF processado.
- Pasta `dist/`: `index.html`, `data.json` e o PDF processado.
- Cópia versionada em `dist/<nome do PDF sem extensão>/` (ex.: `dist/HORÁRIO TURMAS 2026 1/`) com o mesmo conteúdo gerado.

## Observações

- O parser foi preparado para pequenas variações do PDF entre semestres.
- O parser roda em modo estrito: se houver página com seção de disciplinas não parseada, o comando falha com erro explícito (sem fallback silencioso).