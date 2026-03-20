from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


SECTION_HEADER = "Disciplina Tipo Professor Prédio Sala TurmaDiário"
RELATION_SECTION_MARKER = "Relação de Disciplinas, Professores e Locais de Aula"
SECTION_HEADER_PATTERN = re.compile(r"^Disciplina\s*Tipo\s*Professor\s*Prédio\s*Sala\s*TurmaDiário", re.IGNORECASE)
TURMA_DIARIO_PATTERN = re.compile(r"(\d{5}\.[A-Z-]+\.\d[A-Z])\s*([A-Z]*\d{6})")
DEFAULT_EMAIL_BASE = Path("input/professores_emails.csv")


@dataclass(frozen=True)
class CourseRecord:
    discipline_code: str
    discipline_name: str
    professor: str
    turma: str
    diario: str


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normalize_key(value: str) -> str:
    cleaned = normalize_text(value).lower()
    without_accents = "".join(
        ch for ch in unicodedata.normalize("NFD", cleaned) if unicodedata.category(ch) != "Mn"
    )
    return without_accents


def strip_location_segment(value: str) -> str:
    tokens = normalize_text(value).split(" ")
    if not tokens:
        return ""

    room_token = tokens[-1]
    if re.fullmatch(r"[A-Z]{1,4}\d{1,3}", room_token, flags=re.IGNORECASE):
        idx = len(tokens) - 2
        while idx >= 0 and not normalize_key(tokens[idx]).startswith("pr"):
            idx -= 1
        if idx >= 0:
            tokens = tokens[:idx]
        else:
            tokens = tokens[:-1]

    return normalize_text(" ".join(tokens))


def parse_pdf(input_pdf: Path, strict: bool = True) -> tuple[list[CourseRecord], dict[str, Any]]:
  reader = PdfReader(str(input_pdf))
  parsed_records: list[CourseRecord] = []
  invalid_chunks = 0
  pages_with_relation = 0
  pages_without_matches: list[int] = []
  invalid_chunk_samples: list[str] = []

  for page_number, page in enumerate(reader.pages, start=1):
    page_text = page.extract_text() or ""
    if RELATION_SECTION_MARKER not in page_text:
      continue
    pages_with_relation += 1

    section = page_text.split(RELATION_SECTION_MARKER, 1)[1]
    if SECTION_HEADER in section:
      section = section.split(SECTION_HEADER, 1)[1]
    if "Página:" in section:
      section = section.split("Página:", 1)[0]

    merged = SECTION_HEADER_PATTERN.sub("", section.replace("\n", ""))

    start_pos = 0
    page_matches = 0
    for match in TURMA_DIARIO_PATTERN.finditer(merged):
      chunk = normalize_text(merged[start_pos:match.start()])
      start_pos = match.end()
      page_matches += 1

      if not chunk:
        continue
      if " - " not in chunk or " Normal " not in chunk:
        invalid_chunks += 1
        if len(invalid_chunk_samples) < 8:
          invalid_chunk_samples.append(
            f"página {page_number}: trecho inválido '{chunk[:120]}'"
          )
        continue

      discipline_code, rest = chunk.split(" - ", 1)
      discipline_name, professor_with_location = rest.split(" Normal ", 1)
      professor = strip_location_segment(professor_with_location)

      record = CourseRecord(
        discipline_code=normalize_text(discipline_code),
        discipline_name=normalize_text(discipline_name),
        professor=normalize_text(professor),
        turma=normalize_text(match.group(1)),
        diario=normalize_text(match.group(2)),
      )
      if not record.discipline_code or not record.discipline_name or not record.turma or not record.diario:
        invalid_chunks += 1
        if len(invalid_chunk_samples) < 8:
          invalid_chunk_samples.append(
            f"página {page_number}: registro incompleto '{chunk[:120]}'"
          )
        continue

      parsed_records.append(record)

    if page_matches == 0:
      pages_without_matches.append(page_number)

  unique_records = {
    (record.turma, record.diario): record
    for record in parsed_records
    if record.discipline_code and record.discipline_name and record.turma and record.diario
  }

  diagnostics = {
    "invalid_chunks": invalid_chunks,
    "pages_with_relation": pages_with_relation,
    "pages_without_matches": pages_without_matches,
    "invalid_chunk_samples": invalid_chunk_samples,
  }

  if strict:
    errors: list[str] = []
    if pages_with_relation == 0:
      errors.append("Nenhuma seção de relação de disciplinas foi encontrada no PDF.")
    if pages_without_matches:
      pages_str = ", ".join(str(page) for page in pages_without_matches)
      errors.append(f"Páginas com seção de disciplinas mas sem matches turma+diário: {pages_str}.")
    if invalid_chunks > 0:
      errors.append(f"Foram encontrados {invalid_chunks} trechos inválidos durante o parsing.")
      if invalid_chunk_samples:
        errors.extend(invalid_chunk_samples)
    if not unique_records:
      errors.append("Nenhum registro válido foi extraído do PDF.")

    if errors:
      joined = "\n- " + "\n- ".join(errors)
      raise SystemExit("Falha de parsing em modo estrito:" + joined)

  return list(unique_records.values()), diagnostics


def ensure_email_base(
  email_base_path: Path, professors: list[str]
) -> tuple[dict[str, str], int, int]:
  email_base_path.parent.mkdir(parents=True, exist_ok=True)
  if not email_base_path.exists() or email_base_path.stat().st_size == 0:
    email_base_path.write_text("professor,email\n", encoding="utf-8")

  with email_base_path.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle)
    fieldnames = reader.fieldnames or []
    if "professor" not in fieldnames or "email" not in fieldnames:
      raise SystemExit(
        f"Arquivo de e-mails inválido em {email_base_path}. "
        "Use cabeçalho: professor,email"
      )

    professor_emails: dict[str, str] = {}
    existing_keys: set[str] = set()
    for row in reader:
      professor_name = normalize_text(row.get("professor", ""))
      email = normalize_text(row.get("email", ""))
      if not professor_name:
        continue
      key = normalize_key(professor_name)
      if key in existing_keys:
        continue
      existing_keys.add(key)
      professor_emails[key] = email

    new_rows = []
    for professor in sorted(
        {normalize_text(name) for name in professors if normalize_text(name)},
        key=normalize_key,
    ):
        key = normalize_key(professor)
        if key in existing_keys:
            continue
        new_rows.append({"professor": professor, "email": ""})
        existing_keys.add(key)
        professor_emails[key] = ""

    if new_rows:
        with email_base_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["professor", "email"])
            writer.writerows(new_rows)

    professors_without_email = sum(1 for value in professor_emails.values() if not value)
    return professor_emails, len(new_rows), professors_without_email


def build_indexes(records: list[CourseRecord], professor_emails: dict[str, str]) -> dict[str, Any]:
  by_turma: dict[str, list[dict[str, str]]] = {}
  by_professor: dict[str, dict[str, Any]] = {}

  for record in records:
    has_professor = bool(record.professor)
    professor_key = normalize_key(record.professor) if has_professor else ""
    professor_email = professor_emails.get(professor_key, "") if has_professor else ""
    professor_display = record.professor if has_professor else "Não informado"

    by_turma.setdefault(record.turma, []).append(
      {
        "discipline_code": record.discipline_code,
        "discipline_name": record.discipline_name,
        "professor": professor_display,
        "professor_email": professor_email,
        "diario": record.diario,
      }
    )

    if has_professor:
      if professor_key not in by_professor:
        by_professor[professor_key] = {
          "professor": record.professor,
          "email": professor_email,
          "items": [],
        }

      by_professor[professor_key]["items"].append(
        {
          "turma": record.turma,
          "discipline_code": record.discipline_code,
          "discipline_name": record.discipline_name,
          "professor_email": professor_email,
          "diario": record.diario,
        }
      )

  for turma, items in by_turma.items():
    unique_items = {
      (
        item["discipline_code"],
        item["discipline_name"],
        item["professor"],
        item["professor_email"],
        item["diario"],
      ): item
      for item in items
    }
    by_turma[turma] = sorted(unique_items.values(), key=lambda x: (x["discipline_name"], x["professor"]))

  for professor_key, content in by_professor.items():
    unique_items = {
      (
        item["turma"],
        item["discipline_code"],
        item["discipline_name"],
        item["professor_email"],
        item["diario"],
      ): item
      for item in content["items"]
    }
    content["items"] = sorted(unique_items.values(), key=lambda x: (x["turma"], x["discipline_name"]))

  return {
    "records": sorted([asdict(r) for r in records], key=lambda x: (x["turma"], x["discipline_name"])),
    "by_turma": dict(sorted(by_turma.items(), key=lambda x: x[0])),
    "by_professor": dict(
      sorted(by_professor.items(), key=lambda x: normalize_key(x[1]["professor"]))
    ),
  }


def render_html(data: dict[str, Any], metadata: dict[str, Any]) -> str:
    data_json = json.dumps(data, ensure_ascii=False)
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Consulta Turmas e Professores</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin-bottom: 8px; }}
    .meta {{ margin: 0 0 24px 0; color: #555; font-size: 0.95rem; }}
    .block {{ border: 1px solid #ddd; padding: 16px; margin-bottom: 20px; border-radius: 8px; }}
    label {{ display: block; margin-bottom: 8px; font-weight: 600; }}
    input {{ padding: 8px; min-width: 320px; }}
    button {{ margin-left: 8px; padding: 8px 12px; cursor: pointer; }}
    .result {{ margin-top: 12px; }}
    .actions {{ margin-top: 10px; display: flex; gap: 8px; align-items: center; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .empty {{ color: #666; margin-top: 8px; }}
    .email {{ margin: 4px 0 10px 0; }}
      .download {{ margin: 0 0 12px 0; }}
  </style>
</head>
<body>
  <h1>Consulta de Turmas, Disciplinas e Professores</h1>
    <p class="download"><a id="pdfDownload" href="#" download>Baixar PDF de origem</a></p>
  <p class=\"meta\" id=\"meta\"></p>

  <section class=\"block\">
    <h2>Quem são os professores da Turma?</h2>
    <label for=\"turmaInput\">Turma</label>
    <input id=\"turmaInput\" list=\"turmasList\" placeholder=\"Ex.: 20261.ADPL.3V\" />
    <datalist id=\"turmasList\"></datalist>
    <button id=\"searchTurma\">Buscar</button>
    <div class=\"actions\">
        <button id=\"copyTurmaEmails\" type=\"button\">Copiar e-mails da turma</button>
      <span id=\"copyTurmaEmailsStatus\" class=\"empty\"></span>
    </div>
    <div id=\"resultTurma\" class=\"result\"></div>
  </section>

  <section class=\"block\">
    <h2>Quais disciplinas/turmas desse professor?</h2>
    <label for=\"profInput\">Professor</label>
    <input id=\"profInput\" list=\"profsList\" placeholder=\"Digite o nome do professor\" />
    <datalist id=\"profsList\"></datalist>
    <button id=\"searchProf\">Buscar</button>
    <div id=\"resultProf\" class=\"result\"></div>
  </section>

  <script>
    const DATA = {data_json};
    const META = {metadata_json};

    const turmaInput = document.getElementById('turmaInput');
    const profInput = document.getElementById('profInput');
    const resultTurma = document.getElementById('resultTurma');
    const resultProf = document.getElementById('resultProf');
    const copyTurmaEmailsButton = document.getElementById('copyTurmaEmails');
    const copyTurmaEmailsStatus = document.getElementById('copyTurmaEmailsStatus');

    document.getElementById('meta').textContent =
      `Gerado em ${{META.generated_at}} • Registros: ${{META.total_records}} • PDF: ${{META.input_file}}`;
    const pdfDownload = document.getElementById('pdfDownload');
    pdfDownload.href = encodeURI(META.pdf_download_file);
    pdfDownload.setAttribute('download', META.pdf_download_file);

    const turmas = Object.keys(DATA.by_turma).sort();
    const profEntries = Object.values(DATA.by_professor)
      .map(v => v.professor)
      .sort((a, b) => a.localeCompare(b, 'pt-BR'));

    const turmasList = document.getElementById('turmasList');
    turmas.forEach(turma => {{
      const option = document.createElement('option');
      option.value = turma;
      turmasList.appendChild(option);
    }});

    const profsList = document.getElementById('profsList');
    profEntries.forEach(name => {{
      const option = document.createElement('option');
      option.value = name;
      profsList.appendChild(option);
    }});

    function normalize(value) {{
      return value
        .normalize('NFD')
        .replace(/\\p{{Diacritic}}/gu, '')
        .toLowerCase()
        .replace(/\\s+/g, ' ')
        .trim();
    }}

    function renderEmpty(target, message) {{
      target.innerHTML = `<p class=\"empty\">${{message}}</p>`;
    }}

    function emailsFromTurma(turma) {{
      const items = DATA.by_turma[turma] || [];
      const emails = items
        .map(item => (item.professor_email || '').trim())
        .filter(email => email.length > 0);
      return Array.from(new Set(emails));
    }}

    async function copyText(text) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        return;
      }}

      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }}

    function renderTurmaResults(items) {{
      const rows = items.map(item => `
        <tr>
          <td>${{item.discipline_code}}</td>
          <td>${{item.discipline_name}}</td>
          <td>${{item.professor}}</td>
          <td>${{item.professor_email ? `<a href="mailto:${{item.professor_email}}">${{item.professor_email}}</a>` : 'Não informado'}}</td>
        </tr>
      `).join('');

      resultTurma.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Código</th>
              <th>Disciplina</th>
              <th>Professor</th>
              <th>E-mail</th>
            </tr>
          </thead>
          <tbody>${{rows}}</tbody>
        </table>
      `;
    }}

    function renderProfessorResults(content) {{
      const rows = content.items.map(item => `
        <tr>
          <td>${{item.turma}}</td>
          <td>${{item.discipline_code}}</td>
          <td>${{item.discipline_name}}</td>
        </tr>
      `).join('');

      const emailLine = content.email
        ? `<p class="email"><strong>E-mail:</strong> <a href="mailto:${{content.email}}">${{content.email}}</a></p>`
        : `<p class="email"><strong>E-mail:</strong> Não informado</p>`;

      resultProf.innerHTML = `
        <p><strong>Professor:</strong> ${{content.professor}}</p>
        ${{emailLine}}
        <table>
          <thead>
            <tr>
              <th>Turma</th>
              <th>Código</th>
              <th>Disciplina</th>
            </tr>
          </thead>
          <tbody>${{rows}}</tbody>
        </table>
      `;
    }}

    function findProfessorByInput(inputValue) {{
      const wanted = normalize(inputValue);
      if (!wanted) return null;

      if (DATA.by_professor[wanted]) {{
        return DATA.by_professor[wanted];
      }}

      const matches = Object.entries(DATA.by_professor)
        .filter(([key, value]) => key.includes(wanted) || normalize(value.professor).includes(wanted));

      if (matches.length === 1) {{
        return matches[0][1];
      }}

      return null;
    }}

    document.getElementById('searchTurma').addEventListener('click', () => {{
      const turma = turmaInput.value.trim();
      if (!turma) {{
        renderEmpty(resultTurma, 'Informe uma turma para buscar.');
        return;
      }}

      const items = DATA.by_turma[turma];
      if (!items || items.length === 0) {{
        renderEmpty(resultTurma, 'Nenhum resultado para a turma informada.');
        return;
      }}

      renderTurmaResults(items);
    }});

    document.getElementById('searchProf').addEventListener('click', () => {{
      const raw = profInput.value.trim();
      if (!raw) {{
        renderEmpty(resultProf, 'Informe um professor para buscar.');
        return;
      }}

      const content = findProfessorByInput(raw);
      if (!content) {{
        renderEmpty(resultProf, 'Nenhum resultado para o professor informado. Dica: selecione pelo autocomplete.');
        return;
      }}

      renderProfessorResults(content);
    }});

    copyTurmaEmailsButton.addEventListener('click', async () => {{
      const emailCells = resultTurma.querySelectorAll('tbody tr td:nth-child(4)');
      const emails = Array.from(emailCells)
        .map(cell => {{
          const link = cell.querySelector('a');
          return (link ? link.textContent : cell.textContent || '').trim();
        }})
        .filter(email => email.length > 0 && email.includes('@'));

      const uniqueEmails = Array.from(new Set(emails));

      if (uniqueEmails.length === 0) {{
        copyTurmaEmailsStatus.textContent = 'Nenhum e-mail disponível na tabela para copiar.';
        return;
      }}

      try {{
        await copyText(uniqueEmails.join(','));
        copyTurmaEmailsStatus.textContent = `${{uniqueEmails.length}} e-mail(s) copiado(s).`;
      }} catch (error) {{
        copyTurmaEmailsStatus.textContent = 'Não foi possível copiar os e-mails.';
      }}
    }});
  </script>
</body>
</html>
"""


def generate(
    input_pdf: Path,
    output_dir: Path,
    email_base_path: Path = DEFAULT_EMAIL_BASE,
) -> tuple[Path, Path, dict[str, Any]]:
    records, parse_diagnostics = parse_pdf(input_pdf, strict=True)
    professor_emails, emails_added, professors_without_email = ensure_email_base(
        email_base_path,
        [record.professor for record in records],
    )
    indexes = build_indexes(records, professor_emails)

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": input_pdf.name,
        "total_records": len(records),
        "invalid_chunks": parse_diagnostics["invalid_chunks"],
        "pages_with_relation": parse_diagnostics["pages_with_relation"],
        "pages_without_matches": parse_diagnostics["pages_without_matches"],
        "total_turmas": len(indexes["by_turma"]),
        "total_professors": len(indexes["by_professor"]),
        "email_base_file": str(email_base_path),
        "professors_added_to_email_base": emails_added,
        "professors_without_email": professors_without_email,
        "pdf_download_file": input_pdf.name,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    root_output_dir = Path.cwd()
    versioned_output_dir = output_dir / input_pdf.stem
    versioned_output_dir.mkdir(parents=True, exist_ok=True)

    data_path = output_dir / "data.json"
    html_path = output_dir / "index.html"
    pdf_copy_path = output_dir / input_pdf.name

    root_data_path = root_output_dir / "data.json"
    root_html_path = root_output_dir / "index.html"
    root_pdf_copy_path = root_output_dir / input_pdf.name

    versioned_data_path = versioned_output_dir / "data.json"
    versioned_html_path = versioned_output_dir / "index.html"
    versioned_pdf_copy_path = versioned_output_dir / input_pdf.name

    data_payload = {
        "metadata": metadata,
        "records": indexes["records"],
        "by_turma": indexes["by_turma"],
        "by_professor": indexes["by_professor"],
    }

    data_path.write_text(json.dumps(data_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(indexes, metadata), encoding="utf-8")
    shutil.copy2(input_pdf, pdf_copy_path)

    root_data_path.write_text(json.dumps(data_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    root_html_path.write_text(render_html(indexes, metadata), encoding="utf-8")
    shutil.copy2(input_pdf, root_pdf_copy_path)

    versioned_data_path.write_text(json.dumps(data_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    versioned_html_path.write_text(render_html(indexes, metadata), encoding="utf-8")
    shutil.copy2(input_pdf, versioned_pdf_copy_path)

    return html_path, data_path, metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera site estático (HTML + JSON) de consulta turma/professor a partir do PDF semestral."
    )
    parser.add_argument("--input", required=True, type=Path, help="Caminho para o PDF de entrada")
    parser.add_argument("--output", required=False, type=Path, default=Path("dist"), help="Pasta de saída")
    parser.add_argument(
      "--email-base",
      required=False,
      type=Path,
      default=DEFAULT_EMAIL_BASE,
      help="Arquivo CSV incremental de e-mails (colunas: professor,email).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        raise SystemExit(f"Arquivo de entrada não encontrado: {args.input}")

    html_path, data_path, metadata = generate(args.input, args.output, args.email_base)

    print("Geração concluída.")
    print(f"- HTML: {html_path}")
    print(f"- JSON: {data_path}")
    print(
        "- Estatísticas: "
        f"registros={metadata['total_records']}, "
        f"turmas={metadata['total_turmas']}, "
        f"professores={metadata['total_professors']}, "
        f"fragmentos_inválidos={metadata['invalid_chunks']}, "
        f"novos_professores_na_base_email={metadata['professors_added_to_email_base']}, "
        f"professores_sem_email={metadata['professors_without_email']}"
    )


if __name__ == "__main__":
    main()