import asyncio
import os
import tempfile
import json
import time

from app.embeddings import get_model
from app.services.embedding_store import count_chroma_documents, get_chroma_collection_name, get_chroma_persist_dir
from app.services.ingestion import ingest_pdf
from app.agents.retrieval import retrieve
from app.observability import logger


def make_pdf_bytes(text: str) -> bytes:
    header = b'%PDF-1.4\n'
    objs = [
        b'1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n',
        b'2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n',
        b'3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>endobj\n',
        None,
        b'5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n',
    ]
    stream = f'BT /F1 18 Tf 36 72 Td ({text}) Tj ET'.encode('latin-1')
    objs[3] = b'4 0 obj<< /Length ' + str(len(stream)).encode() + b' >>stream\n' + stream + b'\nendstream\nendobj\n'
    offsets = [0]
    current = len(header)
    body = b''
    for obj in objs:
        offsets.append(current)
        body += obj
        current += len(obj)
    xref_start = len(header) + len(body)
    xref = b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    trailer = b'trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref_start).encode() + b'\n%%EOF\n'
    return header + body + xref + trailer


async def main():
    fd, pdf_path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    with open(pdf_path, 'wb') as fh:
        fh.write(make_pdf_bytes('Alice Johnson'))
    try:
        print('---TRACE START---')
        before = count_chroma_documents()
        print('chroma_before=', before)
        ingest_result = await ingest_pdf(pdf_path, owner_id=6, document_id=1, tenant_id=1, workspace_id=1)
        after = count_chroma_documents()
        print('chroma_after=', after)
        # Small sleep to let background indexing settle if any
        await asyncio.sleep(0.5)
        retrieval = await retrieve('what is the name of the person in this PVC card', {'user_id': 6, 'retrieval_strategy': 'hybrid'})
        print('persist_dir=', get_chroma_persist_dir())
        print('collection=', get_chroma_collection_name())
        print('model_loaded=', get_model() is not None)
        print('before=', before, 'after=', after, 'ingest_status=', ingest_result.get('status'), 'chunks=', ingest_result.get('chunks_stored'), 'error=', ingest_result.get('error'))
        print('retrieval_chunks=', len(retrieval.get('chunks') or []), 'source=', retrieval.get('source'), 'warning=', retrieval.get('warning'))
        if retrieval.get('chunks'):
            top = retrieval['chunks'][0]
            print('top_source=', top.get('source'), 'top_text=', top.get('content', '')[:80])
        print('---TRACE END---')
    finally:
        try:
            os.remove(pdf_path)
        except Exception:
            pass


if __name__ == '__main__':
    asyncio.run(main())
