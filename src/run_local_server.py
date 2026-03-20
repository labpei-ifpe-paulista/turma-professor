from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from generate_site import generate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inicia servidor local para consulta turma-professor."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("input/HORÁRIO TURMAS 2026 1.PDF"),
        help="PDF de entrada usado para gerar os arquivos antes de servir.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist"),
        help="Pasta de saída dos arquivos gerados e raiz do servidor.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host do servidor local.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Porta do servidor local.",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Não regenera HTML/JSON antes de iniciar o servidor.",
    )
    parser.add_argument(
        "--email-base",
        type=Path,
        default=Path("input/professores_emails.csv"),
        help="Arquivo CSV incremental de e-mails (colunas: professor,email).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.skip_generate:
        if not args.input.exists():
            raise SystemExit(f"Arquivo de entrada não encontrado: {args.input}")
        html_path, data_path, metadata = generate(args.input, args.output, args.email_base)
        print("Arquivos gerados com sucesso:")
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
    else:
        args.output.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(args.output))
    server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"Servidor local ativo em: http://{args.host}:{args.port}")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()